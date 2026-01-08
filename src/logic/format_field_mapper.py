"""
Format Field Mapper - VLMを使用してExcel/Wordフォーマットのフィールドを検出し、
ドラフト内容とマッピングする。

Cloud Run（Linux）対応。
"""

import logging
import json
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass


@dataclass
class FieldInfo:
    """フォーマット内のフィールド情報"""
    field_id: str           # 一意のID
    field_name: str         # フィールド名（ラベル）
    field_type: str         # "cell" | "table_cell" | "paragraph" | "text_box"
    location: Dict[str, Any]  # 位置情報（Excel: {"sheet": str, "row": int, "col": int}, Word: {"paragraph_idx": int} or {"table_idx": int, "row": int, "col": int}）
    max_length: Optional[int] = None  # 文字数制限
    description: Optional[str] = None  # 説明
    required: bool = False  # 必須項目


class FormatFieldMapper:
    """
    VLMでExcel/Wordフォーマットのフィールドを検出し、
    ドラフト内容とマッピングする。
    """
    
    def __init__(self, gemini_client=None, model_name: str = "gemini-3.0-pro"):
        """
        Args:
            gemini_client: Gemini APIクライアント
            model_name: 使用するモデル名
        """
        self.client = gemini_client
        self.model_name = model_name
        self.logger = logging.getLogger(__name__)
        
        if not self.client:
            try:
                from src.utils.gemini_client import get_gemini_client
                self.client = get_gemini_client()
            except Exception as e:
                self.logger.error(f"[FORMAT_MAPPER] Failed to initialize Gemini client: {e}")
    
    def analyze_excel_fields(self, file_path: str) -> List[FieldInfo]:
        """
        Excelファイルのフィールドを解析する。
        
        Args:
            file_path: Excelファイルのパス
            
        Returns:
            検出されたフィールドのリスト
        """
        fields = []
        
        try:
            import openpyxl
            
            wb = openpyxl.load_workbook(file_path, read_only=True)
            
            for sheet_name in wb.sheetnames:
                sheet = wb[sheet_name]
                sheet_fields = self._analyze_excel_sheet(sheet, sheet_name)
                fields.extend(sheet_fields)
            
            wb.close()
            
            self.logger.info(f"[FORMAT_MAPPER] Found {len(fields)} fields in Excel file")
            
            # VLMで追加解析（フィールドの意味を推論）
            if fields and self.client:
                fields = self._enhance_fields_with_vlm(fields, file_path, "excel")
            
        except ImportError:
            self.logger.warning("[FORMAT_MAPPER] openpyxl not installed")
        except Exception as e:
            self.logger.error(f"[FORMAT_MAPPER] Excel analysis failed: {e}")
        
        return fields
    
    def _analyze_excel_sheet(self, sheet, sheet_name: str) -> List[FieldInfo]:
        """
        Excelシートから入力フィールドを検出する。
        
        入力欄のパターン:
        - 空のセル（隣にラベルあり）
        - 下線（_____）で示された入力欄
        - 黄色/水色などの背景色のセル
        """
        fields = []
        
        try:
            # シートの使用範囲を取得
            max_row = min(sheet.max_row or 100, 100)
            max_col = min(sheet.max_column or 20, 20)
            
            for row in range(1, max_row + 1):
                for col in range(1, max_col + 1):
                    cell = sheet.cell(row=row, column=col)
                    
                    # ラベルセルを探す（テキストが入っている）
                    if cell.value and isinstance(cell.value, str):
                        cell_text = str(cell.value).strip()
                        
                        # 入力欄を示すキーワード
                        if any(keyword in cell_text for keyword in ['記入', '入力', '：', ':', '）', ')']):
                            # 右隣または下のセルが入力欄
                            right_cell = sheet.cell(row=row, column=col + 1)
                            below_cell = sheet.cell(row=row + 1, column=col) if row < max_row else None
                            
                            # 右隣が空なら入力欄候補
                            if right_cell and (right_cell.value is None or right_cell.value == ''):
                                field = FieldInfo(
                                    field_id=f"{sheet_name}_{row}_{col+1}",
                                    field_name=cell_text,
                                    field_type="cell",
                                    location={
                                        "sheet": sheet_name,
                                        "row": row,
                                        "col": col + 1
                                    }
                                )
                                fields.append(field)
                            # 下が空なら入力欄候補
                            elif below_cell and (below_cell.value is None or below_cell.value == ''):
                                field = FieldInfo(
                                    field_id=f"{sheet_name}_{row+1}_{col}",
                                    field_name=cell_text,
                                    field_type="cell",
                                    location={
                                        "sheet": sheet_name,
                                        "row": row + 1,
                                        "col": col
                                    }
                                )
                                fields.append(field)
                        
                        # 文字数制限を検出（例：「（400字以内）」）
                        import re
                        limit_match = re.search(r'(\d+)\s*[字文]', cell_text)
                        if limit_match:
                            # この近くのフィールドに制限を適用
                            for field in fields[-3:]:  # 直近3フィールド
                                if field.max_length is None:
                                    field.max_length = int(limit_match.group(1))
                                    break
        
        except Exception as e:
            self.logger.warning(f"[FORMAT_MAPPER] Error analyzing sheet {sheet_name}: {e}")
        
        return fields
    
    def analyze_word_fields(self, file_path: str) -> List[FieldInfo]:
        """
        Wordファイルのフィールドを解析する。
        
        Args:
            file_path: Wordファイルのパス
            
        Returns:
            検出されたフィールドのリスト
        """
        fields = []
        
        try:
            from docx import Document
            
            doc = Document(file_path)
            
            # テーブルからフィールドを検出
            for table_idx, table in enumerate(doc.tables):
                table_fields = self._analyze_word_table(table, table_idx)
                fields.extend(table_fields)
            
            # 段落からフィールドを検出（下線やプレースホルダー）
            paragraph_fields = self._analyze_word_paragraphs(doc.paragraphs)
            fields.extend(paragraph_fields)
            
            self.logger.info(f"[FORMAT_MAPPER] Found {len(fields)} fields in Word file")
            
            # VLMで追加解析
            if fields and self.client:
                fields = self._enhance_fields_with_vlm(fields, file_path, "word")
            
        except ImportError:
            self.logger.warning("[FORMAT_MAPPER] python-docx not installed")
        except Exception as e:
            self.logger.error(f"[FORMAT_MAPPER] Word analysis failed: {e}")
        
        return fields
    
    def _analyze_word_table(self, table, table_idx: int) -> List[FieldInfo]:
        """Wordテーブルからフィールドを検出"""
        fields = []
        
        try:
            for row_idx, row in enumerate(table.rows):
                cells = row.cells
                
                for col_idx, cell in enumerate(cells):
                    cell_text = cell.text.strip()
                    
                    # ラベルセルを探す
                    if cell_text and len(cell_text) < 100:
                        # 次のセルが空なら入力欄
                        if col_idx + 1 < len(cells):
                            next_cell = cells[col_idx + 1]
                            if not next_cell.text.strip():
                                field = FieldInfo(
                                    field_id=f"table{table_idx}_{row_idx}_{col_idx+1}",
                                    field_name=cell_text,
                                    field_type="table_cell",
                                    location={
                                        "table_idx": table_idx,
                                        "row": row_idx,
                                        "col": col_idx + 1
                                    }
                                )
                                fields.append(field)
        
        except Exception as e:
            self.logger.warning(f"[FORMAT_MAPPER] Error analyzing Word table: {e}")
        
        return fields
    
    def _analyze_word_paragraphs(self, paragraphs) -> List[FieldInfo]:
        """Word段落からフィールドを検出"""
        fields = []
        
        try:
            import re
            
            for para_idx, para in enumerate(paragraphs):
                text = para.text.strip()
                
                # 入力プレースホルダーを検出
                # パターン: 「○○：____」「○○（　　　）」
                placeholder_patterns = [
                    r'(.+?)[:：]\s*[_＿]{3,}',
                    r'(.+?)[(（]\s*[　\s]*[)）]',
                    r'(.+?)[:：]\s*$',  # コロンで終わる（次行が入力欄）
                ]
                
                for pattern in placeholder_patterns:
                    match = re.search(pattern, text)
                    if match:
                        field = FieldInfo(
                            field_id=f"para_{para_idx}",
                            field_name=match.group(1).strip(),
                            field_type="paragraph",
                            location={
                                "paragraph_idx": para_idx
                            }
                        )
                        fields.append(field)
                        break
        
        except Exception as e:
            self.logger.warning(f"[FORMAT_MAPPER] Error analyzing Word paragraphs: {e}")
        
        return fields
    
    def _enhance_fields_with_vlm(
        self, 
        fields: List[FieldInfo], 
        file_path: str, 
        file_type: str
    ) -> List[FieldInfo]:
        """VLMでフィールドの意味を推論して強化"""
        
        if not self.client:
            return fields
        
        try:
            # フィールド情報をテキスト化
            fields_text = "\n".join([
                f"- {f.field_name} (type: {f.field_type}, id: {f.field_id})"
                for f in fields
            ])
            
            prompt = f"""
以下は{file_type.upper()}申請フォーマットから検出されたフィールド一覧です。
各フィールドが実際に何を入力すべきかを推論し、JSONで返してください。

検出されたフィールド:
{fields_text}

出力形式（JSON配列）:
[
  {{
    "field_id": "フィールドID",
    "description": "このフィールドに入力すべき内容の説明",
    "required": true/false,
    "max_length": 数値またはnull
  }},
  ...
]

JSONのみを出力してください。
"""
            
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt
            )
            
            # JSONをパース
            response_text = response.text.strip()
            # コードブロックを除去
            if "```json" in response_text:
                response_text = response_text.split("```json")[1].split("```")[0]
            elif "```" in response_text:
                response_text = response_text.split("```")[1].split("```")[0]
            
            enhanced_data = json.loads(response_text)
            
            # フィールドを更新
            enhanced_map = {item["field_id"]: item for item in enhanced_data}
            for field in fields:
                if field.field_id in enhanced_map:
                    data = enhanced_map[field.field_id]
                    field.description = data.get("description")
                    field.required = data.get("required", False)
                    if data.get("max_length"):
                        field.max_length = data["max_length"]
            
            self.logger.info(f"[FORMAT_MAPPER] Enhanced {len(enhanced_data)} fields with VLM")
            
        except Exception as e:
            self.logger.warning(f"[FORMAT_MAPPER] VLM enhancement failed: {e}")
        
        return fields
    
    def map_draft_to_fields(
        self, 
        fields: List[FieldInfo], 
        draft: str,
        grant_name: str = ""
    ) -> Dict[str, str]:
        """
        Geminiでドラフト内容を各フィールドにマッピングする。
        
        Args:
            fields: フィールド情報のリスト
            draft: 生成されたドラフトテキスト
            grant_name: 助成金名
            
        Returns:
            {field_id: 入力値} のマッピング
        """
        if not fields or not draft or not self.client:
            return {}
        
        try:
            # フィールド情報をプロンプト用にフォーマット
            fields_prompt = "\n".join([
                f"- field_id: {f.field_id}\n  名前: {f.field_name}\n  説明: {f.description or '不明'}\n  文字数制限: {f.max_length or '制限なし'}"
                for f in fields
            ])
            
            prompt = f"""
以下のドラフト内容を、申請フォーマットの各フィールドに適切にマッピングしてください。

## 対象助成金
{grant_name}

## ドラフト内容
{draft[:10000]}

## マッピング先フィールド
{fields_prompt}

## 出力形式（JSON）
{{
  "field_id_1": "このフィールドに入力する内容",
  "field_id_2": "このフィールドに入力する内容",
  ...
}}

注意:
- 各フィールドの文字数制限を守ってください
- ドラフトに該当する内容がない場合は空文字列にしてください
- JSONのみを出力してください
"""
            
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt
            )
            
            # JSONをパース
            response_text = response.text.strip()
            if "```json" in response_text:
                response_text = response_text.split("```json")[1].split("```")[0]
            elif "```" in response_text:
                response_text = response_text.split("```")[1].split("```")[0]
            
            mapping = json.loads(response_text)
            
            self.logger.info(f"[FORMAT_MAPPER] Mapped {len(mapping)} fields from draft")
            
            return mapping
            
        except Exception as e:
            self.logger.error(f"[FORMAT_MAPPER] Draft mapping failed: {e}")
            return {}
    
    def analyze_format_file(self, file_path: str) -> Tuple[List[FieldInfo], str]:
        """
        ファイル形式を自動判定してフィールドを解析する。
        
        Args:
            file_path: ファイルパス
            
        Returns:
            (フィールドリスト, ファイルタイプ)
        """
        import os
        
        ext = os.path.splitext(file_path)[1].lower()
        
        if ext in ['.xlsx', '.xlsm', '.xls']:
            return self.analyze_excel_fields(file_path), "excel"
        elif ext in ['.docx', '.doc']:
            return self.analyze_word_fields(file_path), "word"
        else:
            self.logger.warning(f"[FORMAT_MAPPER] Unsupported file type: {ext}")
            return [], "unknown"
