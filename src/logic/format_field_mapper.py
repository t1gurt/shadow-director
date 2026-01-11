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
    input_length_type: str = "unknown"  # "short"（1行以内）| "long"（100字以上の長文）| "unknown"


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
        """VLMを使ってWordドキュメント全体を解析しフィールドを抽出（チャンク分割対応）"""
        all_fields = []
        
        try:
            # チャンクサイズの設定（1チャンクあたり最大30フィールドを目安）
            CHUNK_SIZE = 4000  # 文字数ベースでチャンク分割
            
            # ドキュメントの全テキストを構造を保って抽出
            chunks = []
            current_chunk = ""
            chunk_start_table = 0
            chunk_start_para = 0
            
            # 段落を収集
            para_texts = []
            for para_idx, para in enumerate(doc.paragraphs):
                text = para.text.strip()
                if text:
                    para_texts.append((para_idx, text))
            
            # テーブルを収集
            table_texts = []
            for table_idx, table in enumerate(doc.tables):
                table_text = f"\n[テーブル{table_idx}]\n"
                for row_idx, row in enumerate(table.rows):
                    row_text = " | ".join([f"[{col_idx}]{cell.text.strip()}" for col_idx, cell in enumerate(row.cells)])
                    table_text += f"  Row{row_idx}: {row_text}\n"
                table_texts.append((table_idx, table_text))
            
            # 段落をチャンクに分割
            para_chunk = ""
            para_chunk_indices = []
            for para_idx, text in para_texts:
                line = f"[段落{para_idx}] {text}\n"
                if len(para_chunk) + len(line) > CHUNK_SIZE:
                    if para_chunk:
                        chunks.append(("paragraph", para_chunk, para_chunk_indices.copy()))
                        para_chunk = ""
                        para_chunk_indices = []
                para_chunk += line
                para_chunk_indices.append(para_idx)
            if para_chunk:
                chunks.append(("paragraph", para_chunk, para_chunk_indices))
            
            # テーブルをチャンクに分割
            for table_idx, table_text in table_texts:
                if len(table_text) > CHUNK_SIZE:
                    # 大きなテーブルはさらに分割
                    lines = table_text.split('\n')
                    sub_chunk = ""
                    for line in lines:
                        if len(sub_chunk) + len(line) > CHUNK_SIZE:
                            if sub_chunk:
                                chunks.append(("table", sub_chunk, [table_idx]))
                                sub_chunk = ""
                        sub_chunk += line + "\n"
                    if sub_chunk:
                        chunks.append(("table", sub_chunk, [table_idx]))
                else:
                    chunks.append(("table", table_text, [table_idx]))
            
            self.logger.info(f"[FORMAT_MAPPER] Split document into {len(chunks)} chunks for VLM analysis")
            
            # 各チャンクに対してVLM解析を実行
            for chunk_idx, (chunk_type, chunk_text, indices) in enumerate(chunks):
                try:
                    chunk_fields = self._analyze_chunk_with_vlm(chunk_text, chunk_type, chunk_idx, len(chunks))
                    all_fields.extend(chunk_fields)
                    self.logger.info(f"[FORMAT_MAPPER] Chunk {chunk_idx + 1}/{len(chunks)}: found {len(chunk_fields)} fields")
                except Exception as e:
                    self.logger.warning(f"[FORMAT_MAPPER] Chunk {chunk_idx + 1} analysis failed: {e}")
            
            # 重複フィールドを除去（field_idベース）
            seen_ids = set()
            unique_fields = []
            for field in all_fields:
                if field.field_id not in seen_ids:
                    seen_ids.add(field.field_id)
                    unique_fields.append(field)
            
            self.logger.info(f"[FORMAT_MAPPER] VLM detected total {len(unique_fields)} unique fields (from {len(all_fields)} raw)")
            
            # 検出されたパターンをログに出力
            pattern_counts = {}
            for f in unique_fields:
                pattern = f.location.get("input_pattern", "unknown")
                pattern_counts[pattern] = pattern_counts.get(pattern, 0) + 1
            self.logger.info(f"[FORMAT_MAPPER] Pattern breakdown: {pattern_counts}")
            
            return unique_fields
            
        except Exception as e:
            self.logger.error(f"[FORMAT_MAPPER] VLM Word analysis failed: {e}")
        
        return all_fields
    
    def _analyze_chunk_with_vlm(self, chunk_text: str, chunk_type: str, chunk_idx: int, total_chunks: int) -> List[FieldInfo]:
        """単一チャンクをVLMで解析してフィールドを抽出"""
        fields = []
        
        if not self.client or not chunk_text.strip():
            return fields
        
        # VLMにフィールド検出を依頼（入力パターン検出を追加）
        prompt = f"""
以下はWord申請書フォーマットの一部（チャンク {chunk_idx + 1}/{total_chunks}）です。
入力が必要なフィールドを検出し、**入力パターン**を特定してください。

## ドキュメント内容
{chunk_text}

## 入力パターンの種類
1. **inline** - ラベルと同一行、コロン後に入力する（例：「団体名：」の後に入力）
2. **next_line** - ラベルの次の行に入力する（例：「1. 事業概要（200字以内）」の次行に入力）
3. **underline** - 下線プレースホルダー「____」を置換する
4. **bracket** - 括弧プレースホルダー「（　）」を置換する
5. **table_cell** - テーブルセル内に入力する（ラベルセルの隣の空セル）

## 出力形式（JSON配列）
[
  {{
    "field_id": "para_5 または table0_1_2",
    "field_name": "ラベル名（例：団体名、事業概要）",
    "field_type": "paragraph または table_cell",
    "input_pattern": "inline | next_line | underline | bracket | table_cell のいずれか",
    "table_idx": テーブル番号（0から、table_cellの場合のみ）,
    "row": 行番号（table_cellの場合のみ）,
    "col": 列番号（入力するセルの列、table_cellの場合のみ）,
    "paragraph_idx": 段落番号（paragraphの場合、入力する段落の番号）,
    "label_paragraph_idx": ラベルがある段落番号（next_lineの場合のみ）,
    "description": "入力すべき内容の説明",
    "max_length": 文字数制限があれば数値、なければnull
  }}
]

## 重要な注意
- **paragraph_idx**は実際に入力を行う段落の番号です
- next_lineパターンの場合、paragraph_idxはラベルの次の段落です
- inlineパターンの場合、paragraph_idxはラベルと同じ段落です
- 空欄、下線「____」、括弧「（　）」、「記入してください」などの指示がある箇所を検出
- フィールドがない場合は空配列[]を返してください
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
            input_pattern = vf.get("input_pattern", "inline")
            
            if vf.get("field_type") == "table_cell" or input_pattern == "table_cell":
                location = {
                    "table_idx": vf.get("table_idx", 0),
                    "row": vf.get("row", 0),
                    "col": vf.get("col", 0),
                    "input_pattern": "table_cell"
                }
                field_type = "table_cell"
            else:
                location = {
                    "paragraph_idx": vf.get("paragraph_idx", 0),
                    "input_pattern": input_pattern,
                    "label_paragraph_idx": vf.get("label_paragraph_idx")
                }
                field_type = "paragraph"
            
            field = FieldInfo(
                field_id=vf.get("field_id", f"vlm_chunk{chunk_idx}_{len(fields)}"),
                field_name=vf.get("field_name", ""),
                field_type=field_type,
                location=location,
                description=vf.get("description"),
                max_length=vf.get("max_length")
            )
            fields.append(field)
        
        return fields
    
    def _analyze_word_table(self, table, table_idx: int) -> List[FieldInfo]:
        """
        Wordテーブルからフィールドを検出（複数パターン対応）
        
        対応パターン:
        1. ラベル | 入力欄（空） のペア
        2. 1行に複数の ラベル | 入力欄 ペアがある場合
        3. ヘッダー行 + データ行パターン（例：｜項目｜金額｜説明｜）
        """
        fields = []
        
        try:
            rows = list(table.rows)
            if not rows:
                return fields
            
            # まず既存のラベル→入力パターンで検出を試みる
            label_input_fields = self._detect_label_input_pattern(table, table_idx, rows)
            
            # ヘッダー行パターンも検出
            header_row_fields = self._detect_header_row_pattern(table, table_idx, rows)
            
            # どちらか多く検出できた方を採用（両方併用すると重複の可能性）
            if len(header_row_fields) > len(label_input_fields):
                fields = header_row_fields
                self.logger.info(f"[FORMAT_MAPPER] Table {table_idx}: using header-row pattern, found {len(fields)} fields")
            else:
                fields = label_input_fields
                self.logger.info(f"[FORMAT_MAPPER] Table {table_idx}: using label-input pattern, found {len(fields)} fields")
        
        except Exception as e:
            self.logger.warning(f"[FORMAT_MAPPER] Error analyzing Word table: {e}")
        
        return fields
    
    def _detect_label_input_pattern(self, table, table_idx: int, rows) -> List[FieldInfo]:
        """ラベル→入力欄のペアパターンを検出"""
        fields = []
        
        for row_idx, row in enumerate(rows):
            cells = row.cells
            num_cells = len(cells)
            
            # 処理済みセルを追跡（1行内で複数フィールドを検出するため）
            processed_cols = set()
            
            col_idx = 0
            while col_idx < num_cells:
                # 既に処理済みのセルはスキップ
                if col_idx in processed_cols:
                    col_idx += 1
                    continue
                
                cell = cells[col_idx]
                cell_text = cell.text.strip()
                
                # ラベルセルを探す（テキストがあり、短めのもの）
                if cell_text and len(cell_text) < 100:
                    # 次のセルが空または入力欄候補なら入力欄
                    if col_idx + 1 < num_cells:
                        next_cell = cells[col_idx + 1]
                        next_text = next_cell.text.strip()
                        
                        # 空セル、下線、または空白のみの場合は入力欄
                        is_empty = not next_text
                        is_placeholder = next_text and (
                            all(c in '_＿　 ' for c in next_text) or
                            next_text in ['（　）', '(　)', '（）', '()']
                        )
                        
                        if is_empty or is_placeholder:
                            field = FieldInfo(
                                field_id=f"table{table_idx}_{row_idx}_{col_idx+1}",
                                field_name=cell_text,
                                field_type="table_cell",
                                location={
                                    "table_idx": table_idx,
                                    "row": row_idx,
                                    "col": col_idx + 1,
                                    "input_pattern": "table_cell"
                                }
                            )
                            fields.append(field)
                            
                            # ラベルセルと入力セルの両方を処理済みにマーク
                            processed_cols.add(col_idx)
                            processed_cols.add(col_idx + 1)
                            
                            # 次のセルへスキップ（入力欄の次から再開）
                            col_idx += 2
                            continue
                
                col_idx += 1
        
        return fields
    
    def _detect_header_row_pattern(self, table, table_idx: int, rows) -> List[FieldInfo]:
        """
        ヘッダー行 + データ行パターンを検出
        例: | 項目 | 金額 | 説明 | コメント |
            | xxx  | xxx  | xxx  | xxx      |
        """
        fields = []
        
        if len(rows) < 2:
            return fields
        
        # 1行目をヘッダー候補として検査
        first_row = rows[0]
        header_cells = first_row.cells
        
        # ヘッダー行の条件: 全てのセルにテキストがある、かつ短いテキスト
        header_texts = [cell.text.strip() for cell in header_cells]
        
        # ヘッダーらしさを判定
        if not all(text and len(text) < 50 for text in header_texts):
            return fields
        
        # 2行目以降のセルが入力欄候補かどうかを確認
        data_rows_count = 0
        for row_idx in range(1, len(rows)):
            row = rows[row_idx]
            cells = row.cells
            
            # データ行の条件: 少なくとも1つのセルが空または入力欄っぽい
            empty_or_placeholder_count = 0
            for cell in cells:
                text = cell.text.strip()
                is_empty = not text
                is_placeholder = text and (
                    all(c in '_＿　 ' for c in text) or
                    text in ['（　）', '(　)', '（）', '()']
                )
                if is_empty or is_placeholder:
                    empty_or_placeholder_count += 1
            
            # データ行と判定（半分以上が空または入力欄候補）
            if empty_or_placeholder_count >= len(cells) // 2:
                data_rows_count += 1
        
        # データ行が1つ以上あればヘッダー行パターンと判定
        if data_rows_count == 0:
            return fields
        
        # ヘッダー行パターンが確定 → 各データ行の各セルをフィールドとして登録
        for row_idx in range(1, len(rows)):
            row = rows[row_idx]
            cells = row.cells
            
            for col_idx, cell in enumerate(cells):
                # ヘッダーのラベルを取得
                if col_idx < len(header_texts):
                    header_label = header_texts[col_idx]
                else:
                    header_label = f"列{col_idx + 1}"
                
                # 既に値が入っているセルはスキップ（入力欄として認識しない）
                cell_text = cell.text.strip()
                is_empty = not cell_text
                is_placeholder = cell_text and (
                    all(c in '_＿　 ' for c in cell_text) or
                    cell_text in ['（　）', '(　)', '（）', '()']
                )
                
                if is_empty or is_placeholder:
                    # 行番号をラベルに含める（複数行がある場合の区別）
                    field_name = f"{header_label}（行{row_idx}）" if len(rows) > 2 else header_label
                    
                    field = FieldInfo(
                        field_id=f"table{table_idx}_{row_idx}_{col_idx}",
                        field_name=field_name,
                        field_type="table_cell",
                        location={
                            "table_idx": table_idx,
                            "row": row_idx,
                            "col": col_idx,
                            "input_pattern": "table_cell",
                            "header_label": header_label
                        }
                    )
                    fields.append(field)
        
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
        - 入れ子質問: 4. 親質問 → ①サブ項目（文字数制限）
        """
        fields = []
        
        try:
            import re
            
            # 親質問のコンテキストを追跡
            parent_question = None
            parent_question_idx = None
            
            for para_idx, para in enumerate(paragraphs):
                text = para.text.strip()
                
                if not text or len(text) < 3:
                    continue
                
                # 入れ子パターン: サブ項目を検出 ①②③, (1)(2)(3), ア.イ.ウ. 等
                sub_item_match = re.match(r'^[　\s]*([①②③④⑤⑥⑦⑧⑨⑩]|[(（][1-9１-９][)）]|[ア-オ][.．])(.+?)([（(]\d+字?以?内?[)）])?$', text)
                if sub_item_match and parent_question:
                    sub_marker = sub_item_match.group(1)
                    sub_label = sub_item_match.group(2).strip()
                    char_limit = sub_item_match.group(3)
                    
                    # 親質問名とサブ項目名を組み合わせる
                    combined_label = f"{parent_question} - {sub_marker}{sub_label}"
                    
                    field = FieldInfo(
                        field_id=f"para_{para_idx + 1}",  # 次の段落が入力欄
                        field_name=combined_label,
                        field_type="paragraph",
                        location={
                            "paragraph_idx": para_idx + 1,
                            "input_type": "next_line",
                            "parent_question": parent_question,
                            "parent_idx": parent_question_idx,
                            "sub_marker": sub_marker
                        },
                        description=char_limit,
                        max_length=int(re.search(r'\d+', char_limit).group()) if char_limit and re.search(r'\d+', char_limit) else None
                    )
                    fields.append(field)
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
                # この質問が「親質問」になる可能性がある
                question_match = re.match(r'^(\d+)[.．、]\s*(.+?)([（(]\d+字?以?内?[)）])?$', text)
                if question_match:
                    label = question_match.group(2).strip()
                    char_limit = question_match.group(3)
                    
                    # この質問を親質問として記憶（後続のサブ項目のため）
                    parent_question = f"{question_match.group(1)}. {label}"
                    parent_question_idx = para_idx
                    
                    # 文字数制限がある場合は直接の入力欄
                    if char_limit:
                        field = FieldInfo(
                            field_id=f"para_{para_idx + 1}",
                            field_name=label,
                            field_type="paragraph",
                            location={
                                "paragraph_idx": para_idx + 1,
                                "input_type": "next_line"
                            },
                            description=char_limit,
                            max_length=int(re.search(r'\d+', char_limit).group()) if re.search(r'\d+', char_limit) else None
                        )
                        fields.append(field)
                    # 文字数制限がない場合は、サブ項目が続く可能性があるので
                    # 親質問として記憶するだけで、フィールドは作成しない
                    continue
                
                # 番号なしの通常テキストが来たら親質問コンテキストをリセット
                # ただし、サブ項目（①②等）が来る可能性があるので少し猶予を持たせる
                if parent_question and para_idx > parent_question_idx + 5:
                    parent_question = None
                    parent_question_idx = None
                
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
        """VLMでフィールドの意味を推論して強化（チャンク分割対応）"""
        
        if not self.client or not fields:
            return fields
        
        try:
            # チャンクサイズの設定（1チャンクあたり最大50フィールド）
            CHUNK_SIZE = 50
            
            # フィールドをチャンクに分割
            field_chunks = [fields[i:i + CHUNK_SIZE] for i in range(0, len(fields), CHUNK_SIZE)]
            
            self.logger.info(f"[FORMAT_MAPPER] Enhancing {len(fields)} fields in {len(field_chunks)} chunks")
            
            all_enhanced_data = {}
            
            for chunk_idx, chunk in enumerate(field_chunks):
                try:
                    # フィールド情報をテキスト化
                    fields_text = "\n".join([
                        f"- {f.field_name} (type: {f.field_type}, id: {f.field_id})"
                        for f in chunk
                    ])
                    
                    prompt = f"""
以下は{file_type.upper()}申請フォーマットから検出されたフィールド一覧（チャンク {chunk_idx + 1}/{len(field_chunks)}）です。
各フィールドが実際に何を入力すべきかを推論し、JSONで返してください。

検出されたフィールド:
{fields_text}

出力形式（JSON配列）:
[
  {{
    "field_id": "フィールドID",
    "description": "このフィールドに入力すべき内容の説明",
    "required": true/false,
    "max_length": 数値またはnull,
    "input_length_type": "short" または "long"
  }},
  ...
]

■ input_length_type の判定基準:
- "short": 1行以内の短い入力（名前、日付、金額、電話番号、選択肢など）
  - テーブルセルで列幅が狭いもの
  - 数値、日付、コード、ID類
  - 「〇〇名」「〇〇年月日」「〇〇番号」などの項目名
- "long": 100文字以上の長文入力（説明文、概要、理由、計画など）
  - 「概要」「説明」「理由」「目的」「計画」「内容」を含む項目名
  - テーブルセルで広いスペースがあるもの
  - 自由記述欄

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
                    
                    # 結果をマージ
                    for item in enhanced_data:
                        all_enhanced_data[item["field_id"]] = item
                    
                    self.logger.info(f"[FORMAT_MAPPER] Chunk {chunk_idx + 1}/{len(field_chunks)}: enhanced {len(enhanced_data)} fields")
                    
                except Exception as chunk_error:
                    self.logger.warning(f"[FORMAT_MAPPER] Chunk {chunk_idx + 1} enhancement failed: {chunk_error}")
            
            # フィールドを更新
            for field in fields:
                if field.field_id in all_enhanced_data:
                    data = all_enhanced_data[field.field_id]
                    field.description = data.get("description")
                    field.required = data.get("required", False)
                    if data.get("max_length"):
                        field.max_length = data["max_length"]
                    # input_length_typeを反映（デフォルトはunknown）
                    input_length = data.get("input_length_type", "unknown")
                    if input_length in ["short", "long"]:
                        field.input_length_type = input_length
                    else:
                        # キーワードベースのフォールバック判定
                        field.input_length_type = self._infer_input_length_type(field.field_name)
            
            self.logger.info(f"[FORMAT_MAPPER] Enhanced total {len(all_enhanced_data)} fields with VLM")
            
        except Exception as e:
            self.logger.warning(f"[FORMAT_MAPPER] VLM enhancement failed: {e}")
        
        return fields
    
    def _infer_input_length_type(self, field_name: str) -> str:
        """
        フィールド名からinput_length_type（short/long）を推論する。
        VLM判定がない場合のフォールバック。
        """
        if not field_name:
            return "unknown"
        
        name_lower = field_name.lower()
        
        # 長文（long）を示すキーワード
        long_keywords = [
            '概要', '説明', '理由', '目的', '計画', '内容', '詳細',
            'プロジェクト', '事業', '活動', '取り組み', '実績', '成果',
            '課題', '問題', '背景', 'ビジョン', 'ミッション',
            'コメント', '備考', '補足', '自由記述',
            'description', 'summary', 'overview', 'detail', 'comment'
        ]
        
        # 短文（short）を示すキーワード
        short_keywords = [
            '名', '日', '年', '月', '番号', '電話', 'tel', 'fax',
            'url', 'メール', 'email', '住所', '金額', '円', '人数',
            '数', 'no', 'id', 'コード', '区分', '種別', '選択',
            'チェック', 'check'
        ]
        
        # 長文キーワードをチェック
        for kw in long_keywords:
            if kw in name_lower:
                return "long"
        
        # 短文キーワードをチェック
        for kw in short_keywords:
            if kw in name_lower:
                return "short"
        
        return "unknown"
    
    def map_draft_to_fields(
        self, 
        fields: List[FieldInfo], 
        draft: str,
        grant_name: str = "",
        include_field_info: bool = True
    ) -> Dict[str, Any]:
        """
        Geminiでドラフト内容を各フィールドにマッピングする。
        
        Args:
            fields: フィールド情報のリスト
            draft: 生成されたドラフトテキスト
            grant_name: 助成金名
            include_field_info: フィールド情報（入力パターン等）を含むかどうか
            
        Returns:
            Dict[str, Any] - 入力値と入力パターン情報を含むマッピング
            例: {
                "para_5": {
                    "value": "入力値",
                    "input_pattern": "inline",
                    "field_name": "団体名"
                }
            }
            include_field_info=Falseの場合は従来通り {field_id: 入力値}
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
            
            # 入力パターン情報を含める場合
            if include_field_info:
                # フィールドIDをキーにしたlocation/pattern情報を作成
                field_info_map = {f.field_id: f for f in fields}
                
                enhanced_mapping = {}
                for field_id, value in mapping.items():
                    field_info = field_info_map.get(field_id)
                    if field_info:
                        enhanced_mapping[field_id] = {
                            "value": value,
                            "input_pattern": field_info.location.get("input_pattern", "inline"),
                            "field_name": field_info.field_name,
                            "field_type": field_info.field_type,
                            "location": field_info.location
                        }
                    else:
                        enhanced_mapping[field_id] = {
                            "value": value,
                            "input_pattern": "inline",
                            "field_name": "",
                            "field_type": "unknown",
                            "location": {}
                        }
                
                return enhanced_mapping
            
            return mapping
            
        except Exception as e:
            self.logger.error(f"[FORMAT_MAPPER] Draft mapping failed: {e}")
            return {}
    
    def fill_fields_individually(
        self,
        fields: List[FieldInfo],
        profile: str,
        grant_name: str = "",
        grant_info: str = "",
        progress_callback=None
    ) -> Dict[str, Any]:
        """
        各フィールドに対して個別にGemini 3.0 Flashを呼び出し、
        プロファイル情報をもとに回答を生成する。
        
        Args:
            fields: フィールド情報のリスト
            profile: Soul Profile（NPOのプロファイル情報）
            grant_name: 助成金名
            grant_info: 助成金の詳細情報（募集要項など）
            progress_callback: 進捗通知用コールバック関数 (field_idx, total, field_name) -> None
            
        Returns:
            Dict[str, Any] - 入力値と入力パターン情報を含むマッピング
            例: {
                "para_5": {
                    "value": "入力値",
                    "input_pattern": "inline",
                    "field_name": "団体名"
                }
            }
        """
        if not fields or not profile or not self.client:
            self.logger.warning("[FORMAT_MAPPER] Missing required inputs for fill_fields_individually")
            return {}
        
        # gemini-3.0-flashモデルを使用（項目別処理用）
        flash_model = "gemini-3-flash-preview"
        
        result = {}
        total_fields = len(fields)
        
        for idx, field in enumerate(fields):
            try:
                # 進捗通知
                if progress_callback:
                    progress_callback(idx, total_fields, field.field_name)
                
                self.logger.info(f"[FORMAT_MAPPER] Processing field {idx + 1}/{total_fields}: {field.field_name}")
                
                # 入力長さタイプに応じた指示を構築
                length_instruction = ""
                if field.input_length_type == "short":
                    length_instruction = "\n\n**回答形式**: 1行以内の簡潔な回答（名前、日付、数値など）"
                    if field.max_length:
                        length_instruction += f"（{field.max_length}字以内）"
                elif field.input_length_type == "long":
                    if field.max_length:
                        # 長文で文字数制限あり：制限値の90%を目標に
                        target_length = int(field.max_length * 0.9)
                        length_instruction = f"""

**文字数制限**: {field.max_length}字以内
**目標文字数**: {target_length}字程度（制限の90%を目安に）
**重要**: 文字数制限を厳守してください。{field.max_length}字を超えないよう、適切に要約してください。"""
                    else:
                        length_instruction = "\n\n**回答形式**: 詳細な長文回答（100〜500字程度）"
                else:
                    # unknownの場合
                    if field.max_length:
                        length_instruction = f"\n\n**文字数制限**: {field.max_length}字以内で回答してください。"
                
                prompt = f"""あなたはNPOの助成金申請書作成を支援する専門家です。
以下のNPOプロファイル情報と助成金情報に基づいて、申請書の指定された項目に対する回答を作成してください。

# NPO Soul Profile（魂のプロファイル）
{profile[:6000]}

# 対象助成金
助成金名: {grant_name}
{grant_info[:3000] if grant_info else ""}

# 回答すべき項目
- **項目名**: {field.field_name}
- **説明**: {field.description or "（説明なし）"}
- **入力形式**: {field.input_length_type}
{length_instruction}

# 指示
1. NPOの情報を最大限活用して、この項目に対する適切な回答を作成してください
2. 助成金の目的や評価基準を意識した回答を心がけてください
3. 具体的で説得力のある内容にしてください
4. 回答本文のみを出力してください（項目名や説明は不要）
5. 文字数制限がある場合は必ず守ってください

# 懸念点の報告（重要）
- プロファイルに情報がなく回答できない場合: 回答の末尾に `[MISSING_INFO: 理由]` を付記
- 回答に自信がない・確認が必要な場合: 回答の末尾に `[UNCERTAIN: 理由]` を付記
- 問題なく回答できる場合: タグは不要

# 回答:"""

                response = self.client.models.generate_content(
                    model=flash_model,
                    contents=prompt
                )
                
                value = response.text.strip()
                
                # 懸念点タグを抽出
                concern_type = "none"
                concern_reason = ""
                
                import re
                # [MISSING_INFO: 理由] パターンを検出
                missing_match = re.search(r'\[MISSING_INFO:\s*([^\]]+)\]', value)
                if missing_match:
                    concern_type = "missing_info"
                    concern_reason = missing_match.group(1).strip()
                    value = re.sub(r'\s*\[MISSING_INFO:[^\]]+\]', '', value).strip()
                    self.logger.info(f"[FORMAT_MAPPER] Field {field.field_name} has missing info: {concern_reason}")
                
                # [UNCERTAIN: 理由] パターンを検出
                uncertain_match = re.search(r'\[UNCERTAIN:\s*([^\]]+)\]', value)
                if uncertain_match:
                    concern_type = "uncertain"
                    concern_reason = uncertain_match.group(1).strip()
                    value = re.sub(r'\s*\[UNCERTAIN:[^\]]+\]', '', value).strip()
                    self.logger.info(f"[FORMAT_MAPPER] Field {field.field_name} is uncertain: {concern_reason}")
                
                # 文字数制限がある場合はトリム（余裕を持たせる）
                if field.max_length and len(value) > field.max_length:
                    # 文字数オーバーの場合、末尾をトリムして適切に終わらせる
                    value = value[:field.max_length - 3] + "..."
                    self.logger.info(f"[FORMAT_MAPPER] Trimmed field {field.field_id} to {field.max_length} chars")
                
                # 結果を格納（懸念点情報を含む）
                result[field.field_id] = {
                    "value": value,
                    "input_pattern": field.location.get("input_pattern", "inline"),
                    "field_name": field.field_name,
                    "field_type": field.field_type,
                    "location": field.location,
                    "input_length_type": field.input_length_type,
                    "concern_type": concern_type,
                    "concern_reason": concern_reason
                }
                
                self.logger.info(f"[FORMAT_MAPPER] Successfully filled field: {field.field_name} ({len(value)} chars, concern: {concern_type})")
                
            except Exception as e:
                self.logger.error(f"[FORMAT_MAPPER] Error filling field {field.field_name}: {e}")
                # エラーの場合は空の値を設定
                result[field.field_id] = {
                    "value": "",
                    "input_pattern": field.location.get("input_pattern", "inline"),
                    "field_name": field.field_name,
                    "field_type": field.field_type,
                    "location": field.location,
                    "error": str(e)
                }
        
        self.logger.info(f"[FORMAT_MAPPER] Completed filling {len(result)} fields individually")
        return result
    
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
    
    def generate_concern_report(self, field_values: Dict[str, Any]) -> str:
        """
        入力結果から懸念点レポートを生成する。
        
        Args:
            field_values: fill_fields_individuallyの戻り値
            
        Returns:
            Markdown形式のレポート
        """
        missing_info_fields = []
        uncertain_fields = []
        
        for field_id, data in field_values.items():
            concern_type = data.get("concern_type", "none")
            concern_reason = data.get("concern_reason", "")
            field_name = data.get("field_name", field_id)
            
            if concern_type == "missing_info":
                missing_info_fields.append({
                    "field_name": field_name,
                    "reason": concern_reason
                })
            elif concern_type == "uncertain":
                uncertain_fields.append({
                    "field_name": field_name,
                    "reason": concern_reason
                })
        
        # レポートが不要な場合
        if not missing_info_fields and not uncertain_fields:
            return ""
        
        # Markdown形式のレポートを生成
        report = "## ⚠️ 懸念点レポート\n\n"
        
        if missing_info_fields:
            report += "### 📋 情報不足で埋められなかった項目\n"
            for item in missing_info_fields:
                report += f"- **{item['field_name']}**: {item['reason']}\n"
            report += "\n"
        
        if uncertain_fields:
            report += "### ❓ 確認が必要な項目\n"
            for item in uncertain_fields:
                report += f"- **{item['field_name']}**: {item['reason']}\n"
            report += "\n"
        
        report += "> 💡 上記の項目については、ドラフトを確認し必要に応じて修正してください。\n"
        
        return report
