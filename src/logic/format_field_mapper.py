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
            
            self.logger.info(f"[FORMAT_MAPPER] Found {len(fields)} fields in Word file (text-based)")
            
            # テキストベースで検出できなかった場合、VLMでドキュメント全体を解析
            if not fields and self.client:
                self.logger.info("[FORMAT_MAPPER] No fields found with text-based analysis, trying VLM...")
                fields = self._analyze_word_with_vlm(doc, file_path)
            
            # VLMでも検出できなかった場合、全テーブルセルを強制的に入力候補として検出
            if not fields and doc.tables:
                self.logger.info("[FORMAT_MAPPER] VLM also failed, using fallback: all table cells")
                fields = self._fallback_word_all_cells(doc)
            
            # VLMで追加解析（フィールドの意味を推論）
            if fields and self.client:
                fields = self._enhance_fields_with_vlm(fields, file_path, "word")
            
        except ImportError:
            self.logger.warning("[FORMAT_MAPPER] python-docx not installed")
        except Exception as e:
            self.logger.error(f"[FORMAT_MAPPER] Word analysis failed: {e}")
        
        return fields
    
    def _fallback_word_all_cells(self, doc) -> List[FieldInfo]:
        """
        フォールバック: すべてのテーブルセルを入力候補として検出。
        ラベルセルの隣の空セルまたは長いセルを入力欄として扱う。
        """
        fields = []
        
        try:
            for table_idx, table in enumerate(doc.tables):
                for row_idx, row in enumerate(table.rows):
                    cells = row.cells
                    for col_idx, cell in enumerate(cells):
                        cell_text = cell.text.strip()
                        
                        # 空セル（入力欄候補）
                        if not cell_text:
                            # 左隣にラベルがあれば入力欄
                            if col_idx > 0:
                                label_cell = cells[col_idx - 1]
                                label_text = label_cell.text.strip()
                                if label_text and len(label_text) < 50:
                                    field = FieldInfo(
                                        field_id=f"table{table_idx}_{row_idx}_{col_idx}",
                                        field_name=label_text,
                                        field_type="table_cell",
                                        location={
                                            "table_idx": table_idx,
                                            "row": row_idx,
                                            "col": col_idx
                                        }
                                    )
                                    fields.append(field)
                        
                        # 長いセル（説明や記述欄の可能性）
                        elif len(cell_text) > 50 and col_idx > 0:
                            # 左隣がラベルなら入力欄
                            label_cell = cells[col_idx - 1]
                            label_text = label_cell.text.strip()
                            if label_text and len(label_text) < 50:
                                field = FieldInfo(
                                    field_id=f"table{table_idx}_{row_idx}_{col_idx}",
                                    field_name=label_text,
                                    field_type="table_cell",
                                    location={
                                        "table_idx": table_idx,
                                        "row": row_idx,
                                        "col": col_idx
                                    }
                                )
                                fields.append(field)
            
            self.logger.info(f"[FORMAT_MAPPER] Fallback detected {len(fields)} fields")
            
        except Exception as e:
            self.logger.warning(f"[FORMAT_MAPPER] Fallback analysis failed: {e}")
        
        return fields
    
    def _analyze_word_with_vlm(self, doc, file_path: str) -> List[FieldInfo]:
        """VLMを使ってWordドキュメント全体を解析しフィールドを抽出"""
        fields = []
        
        try:
            # ドキュメントの全テキストを抽出
            full_text = ""
            for para in doc.paragraphs:
                full_text += para.text + "\n"
            for table_idx, table in enumerate(doc.tables):
                full_text += f"\n[テーブル{table_idx + 1}]\n"
                for row in table.rows:
                    row_text = " | ".join([cell.text.strip() for cell in row.cells])
                    full_text += row_text + "\n"
            
            # VLMにフィールド検出を依頼
            prompt = f"""
以下はWord申請書フォーマットの内容です。
入力が必要なフィールド（記入欄、空欄、プレースホルダー）を検出してください。

## ドキュメント内容
{full_text[:8000]}

## 出力形式（JSON配列）
[
  {{
    "field_id": "table0_0_1",
    "field_name": "フィールド名/ラベル",
    "field_type": "table_cell または paragraph",
    "table_idx": テーブル番号（0から開始、テーブルの場合のみ）,
    "row": 行番号（テーブルの場合のみ）,
    "col": 列番号（テーブルの場合のみ）,
    "paragraph_idx": 段落番号（段落の場合のみ）,
    "description": "入力すべき内容の説明"
  }}
]

注意:
- 入力が必要な箇所のみを抽出してください
- 空欄、下線、「記入してください」などの指示がある箇所を検出
- ラベル（項目名）ではなく、入力欄の位置を特定してください
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
            
            vlm_fields = json.loads(response_text)
            
            for vf in vlm_fields:
                if vf.get("field_type") == "table_cell":
                    location = {
                        "table_idx": vf.get("table_idx", 0),
                        "row": vf.get("row", 0),
                        "col": vf.get("col", 0)
                    }
                else:
                    location = {
                        "paragraph_idx": vf.get("paragraph_idx", 0)
                    }
                
                field = FieldInfo(
                    field_id=vf.get("field_id", f"vlm_{len(fields)}"),
                    field_name=vf.get("field_name", ""),
                    field_type=vf.get("field_type", "table_cell"),
                    location=location,
                    description=vf.get("description")
                )
                fields.append(field)
            
            self.logger.info(f"[FORMAT_MAPPER] VLM detected {len(fields)} fields")
            
        except Exception as e:
            self.logger.error(f"[FORMAT_MAPPER] VLM Word analysis failed: {e}")
        
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
        """
        Word段落からフィールドを検出。
        
        対応パターン:
        - ラベル：____（下線プレースホルダー）
        - ラベル：（入力してください）
        - ラベル：　　（空白プレースホルダー）
        - ◻ ラベル：（チェックボックス形式）
        - 1. 質問文（200字以内）→ 次行入力
        - ラベル：（同一行に短い入力がある場合）
        """
        fields = []
        
        try:
            import re
            
            for para_idx, para in enumerate(paragraphs):
                text = para.text.strip()
                
                if not text or len(text) < 3:
                    continue
                
                # パターン1: チェックボックス形式 "◻ ラベル：入力"
                checkbox_match = re.match(r'^[◻☐□■◼◾▢☑✓✔]?\s*(.+?)[:：]\s*(.*)$', text)
                if checkbox_match:
                    label = checkbox_match.group(1).strip()
                    value_hint = checkbox_match.group(2).strip()
                    
                    # 括弧付きヒント or 空欄の場合は入力欄
                    if not value_hint or re.match(r'^[（(].+[)）]$', value_hint) or re.match(r'^[　\s]+$', value_hint) or re.match(r'^[_＿]+$', value_hint):
                        field = FieldInfo(
                            field_id=f"para_{para_idx}",
                            field_name=label,
                            field_type="paragraph",
                            location={
                                "paragraph_idx": para_idx,
                                "input_type": "inline"  # 同一行入力
                            },
                            description=value_hint if value_hint else None
                        )
                        fields.append(field)
                        continue
                
                # パターン2: 番号付き質問 "1. 質問文（文字数）" → 次の段落が入力欄
                question_match = re.match(r'^(\d+)[.．、]\s*(.+?)([（(]\d+字?以?内?[）)])?$', text)
                if question_match:
                    label = question_match.group(2).strip()
                    char_limit = question_match.group(3)
                    
                    # 次の段落を入力欄として検出
                    field = FieldInfo(
                        field_id=f"para_{para_idx + 1}",  # 次の段落
                        field_name=label,
                        field_type="paragraph",
                        location={
                            "paragraph_idx": para_idx + 1,
                            "input_type": "next_line"  # 次行入力
                        },
                        description=char_limit,
                        max_length=int(re.search(r'\d+', char_limit).group()) if char_limit and re.search(r'\d+', char_limit) else None
                    )
                    fields.append(field)
                    continue
                
                # パターン3: 下線プレースホルダー
                underline_match = re.search(r'(.+?)[:：]\s*[_＿]{3,}', text)
                if underline_match:
                    field = FieldInfo(
                        field_id=f"para_{para_idx}",
                        field_name=underline_match.group(1).strip(),
                        field_type="paragraph",
                        location={
                            "paragraph_idx": para_idx,
                            "input_type": "underline"
                        }
                    )
                    fields.append(field)
                    continue
                
                # パターン4: 空括弧プレースホルダー
                bracket_match = re.search(r'(.+?)[(（]\s*[　\s]*[)）]', text)
                if bracket_match:
                    field = FieldInfo(
                        field_id=f"para_{para_idx}",
                        field_name=bracket_match.group(1).strip(),
                        field_type="paragraph",
                        location={
                            "paragraph_idx": para_idx,
                            "input_type": "bracket"
                        }
                    )
                    fields.append(field)
                    continue
                
                # パターン5: コロン終端（次行入力）
                colon_end_match = re.match(r'^(.+?)[:：]\s*$', text)
                if colon_end_match:
                    field = FieldInfo(
                        field_id=f"para_{para_idx + 1}",  # 次の段落
                        field_name=colon_end_match.group(1).strip(),
                        field_type="paragraph",
                        location={
                            "paragraph_idx": para_idx + 1,
                            "input_type": "next_line"
                        }
                    )
                    fields.append(field)
                    continue
        
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
