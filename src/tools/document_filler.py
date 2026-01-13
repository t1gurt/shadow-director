"""
Document Filler - Excel/Wordフォーマットにドラフト内容を入力する。

Cloud Run（Linux）対応。openpyxlとpython-docxを使用。
"""

import logging
import os
import shutil
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime


class DocumentFiller:
    """
    Excel/Wordフォーマットにドラフト内容を入力する。
    Cloud Run（Linux）対応。
    """
    
    def __init__(self, output_dir: str = None):
        """
        Args:
            output_dir: 出力ディレクトリ（デフォルト: /tmp/filled_documents）
        """
        self.output_dir = output_dir or "/tmp/filled_documents"
        self.logger = logging.getLogger(__name__)
        
        # 出力ディレクトリを作成
        os.makedirs(self.output_dir, exist_ok=True)
    
    def _get_existing_font_style(self, paragraph):
        """
        段落から既存のフォントスタイルを取得する。
        最初のrunのスタイルを使用。
        
        Returns:
            Dict with font_name, font_size, bold, italic
        """
        style = {
            "font_name": None,
            "font_size": None,
            "bold": None,
            "italic": None
        }
        
        try:
            if paragraph.runs:
                first_run = paragraph.runs[0]
                if first_run.font:
                    style["font_name"] = first_run.font.name
                    style["font_size"] = first_run.font.size
                    style["bold"] = first_run.font.bold
                    style["italic"] = first_run.font.italic
            
            # runがない場合やフォントが取れない場合、段落スタイルから取得を試みる
            if style["font_name"] is None and paragraph.style and paragraph.style.font:
                style["font_name"] = paragraph.style.font.name
                style["font_size"] = paragraph.style.font.size
                style["bold"] = paragraph.style.font.bold
                style["italic"] = paragraph.style.font.italic
        except Exception as e:
            self.logger.debug(f"[DOC_FILLER] Could not get font style: {e}")
        
        return style
    
    def _add_run_with_style(self, paragraph, text: str, style: Dict = None):
        """
        指定されたスタイルでrunを追加する。
        
        Args:
            paragraph: 対象の段落
            text: 追加するテキスト
            style: フォントスタイル辞書（_get_existing_font_styleの戻り値）
        """
        run = paragraph.add_run(text)
        
        if style:
            try:
                if style.get("font_name"):
                    run.font.name = style["font_name"]
                if style.get("font_size"):
                    run.font.size = style["font_size"]
                if style.get("bold") is not None:
                    run.font.bold = style["bold"]
                if style.get("italic") is not None:
                    run.font.italic = style["italic"]
            except Exception as e:
                self.logger.debug(f"[DOC_FILLER] Could not apply font style: {e}")
        
        return run
    
    def _clear_and_add_with_style(self, paragraph, text: str):
        """
        段落をクリアしてスタイルを保持したままテキストを追加する。
        """
        # 既存のスタイルを保存
        style = self._get_existing_font_style(paragraph)
        
        # 段落をクリア
        paragraph.clear()
        
        # スタイルを適用してテキストを追加
        return self._add_run_with_style(paragraph, text, style)
    
    def fill_document(
        self, 
        file_path: str, 
        field_values: Dict[str, str],
        user_id: str = None
    ) -> Tuple[Optional[str], str]:
        """
        ファイル形式を自動判定してドキュメントに入力する。
        
        Args:
            file_path: テンプレートファイルのパス
            field_values: {field_id: 入力値} のマッピング
            user_id: ユーザーID（出力ファイル名に使用）
            
        Returns:
            (出力ファイルパス, メッセージ)
            入力失敗時は (None, エラーメッセージ)
        """
        if not os.path.exists(file_path):
            return None, f"ファイルが見つかりません: {file_path}"
        
        ext = os.path.splitext(file_path)[1].lower()
        
        try:
            if ext in ['.xlsx', '.xlsm', '.xls']:
                return self.fill_excel(file_path, field_values, user_id)
            elif ext in ['.docx', '.doc']:
                return self.fill_word(file_path, field_values, user_id)
            else:
                return None, f"未対応のファイル形式: {ext}"
        except Exception as e:
            self.logger.error(f"[DOC_FILLER] Fill failed: {e}")
            return None, f"入力エラー: {e}"
    
    def fill_excel(
        self, 
        file_path: str, 
        field_values: Dict[str, str],
        user_id: str = None
    ) -> Tuple[Optional[str], str]:
        """
        openpyxlでExcelに入力する。
        
        Args:
            file_path: テンプレートExcelファイルのパス
            field_values: {field_id: 入力値}
                field_id形式: "シート名_行_列" (例: "Sheet1_5_3")
            user_id: ユーザーID
            
        Returns:
            (出力ファイルパス, メッセージ)
        """
        try:
            import openpyxl
        except ImportError:
            return None, "openpyxlがインストールされていません"
        
        try:
            # テンプレートをコピー
            output_path = self._create_output_path(file_path, user_id, "xlsx")
            shutil.copy2(file_path, output_path)
            
            # ファイルを開いて編集
            wb = openpyxl.load_workbook(output_path)
            filled_count = 0
            
            for field_id, value in field_values.items():
                if not value:
                    continue
                
                try:
                    # field_id: "シート名_行_列"
                    parts = field_id.rsplit('_', 2)
                    if len(parts) != 3:
                        self.logger.warning(f"[DOC_FILLER] Invalid field_id format: {field_id}")
                        continue
                    
                    sheet_name, row_str, col_str = parts
                    row = int(row_str)
                    col = int(col_str)
                    
                    if sheet_name not in wb.sheetnames:
                        self.logger.warning(f"[DOC_FILLER] Sheet not found: {sheet_name}")
                        continue
                    
                    sheet = wb[sheet_name]
                    sheet.cell(row=row, column=col, value=value)
                    filled_count += 1
                    
                except (ValueError, IndexError) as e:
                    self.logger.warning(f"[DOC_FILLER] Error filling field {field_id}: {e}")
            
            wb.save(output_path)
            wb.close()
            
            self.logger.info(f"[DOC_FILLER] Filled {filled_count} fields in Excel")
            
            if filled_count == 0:
                return None, "入力できるフィールドがありませんでした"
            
            return output_path, f"Excelに{filled_count}項目を入力しました"
            
        except Exception as e:
            self.logger.error(f"[DOC_FILLER] Excel fill error: {e}")
            return None, f"Excel入力エラー: {e}"
    
    def fill_word(
        self, 
        file_path: str, 
        field_values: Dict[str, Any],
        user_id: str = None
    ) -> Tuple[Optional[str], str]:
        """
        python-docxでWordに入力する。
        
        Args:
            file_path: テンプレートWordファイルのパス
            field_values: フィールド値のマッピング
                新形式: {field_id: {"value": str, "input_pattern": str, "location": dict}}
                旧形式: {field_id: str} （互換性維持）
            user_id: ユーザーID
            
        Returns:
            (出力ファイルパス, メッセージ)
        """
        try:
            from docx import Document
        except ImportError:
            return None, "python-docxがインストールされていません"
        
        try:
            # テンプレートをコピー
            output_path = self._create_output_path(file_path, user_id, "docx")
            shutil.copy2(file_path, output_path)
            
            # ファイルを開いて編集
            doc = Document(output_path)
            filled_count = 0
            
            for field_id, field_data in field_values.items():
                # 新形式と旧形式の両方に対応
                if isinstance(field_data, dict):
                    value = field_data.get("value", "")
                    input_pattern = field_data.get("input_pattern", "inline")
                    location = field_data.get("location", {})
                    input_length_type = field_data.get("input_length_type", "unknown")
                else:
                    # 旧形式（文字列のみ）
                    value = field_data
                    input_pattern = "inline"
                    location = {}
                    input_length_type = "unknown"
                
                if not value:
                    continue
                
                try:
                    if field_id.startswith("table"):
                        # テーブルセル: "tableN_行_列" - input_length_typeを考慮
                        filled = self._fill_word_table_cell(doc, field_id, value, input_length_type)
                    elif field_id.startswith("para_"):
                        # 段落: "para_N" - 入力パターン情報を使用
                        filled = self._fill_word_paragraph_with_pattern(doc, field_id, value, input_pattern, location)
                    else:
                        self.logger.warning(f"[DOC_FILLER] Unknown field_id format: {field_id}")
                        filled = False
                    
                    if filled:
                        filled_count += 1
                        self.logger.debug(f"[DOC_FILLER] Filled {field_id} with pattern '{input_pattern}'")
                        
                except Exception as e:
                    self.logger.warning(f"[DOC_FILLER] Error filling field {field_id}: {e}")
            
            doc.save(output_path)
            
            self.logger.info(f"[DOC_FILLER] Filled {filled_count} fields in Word")
            
            if filled_count == 0:
                return None, "入力できるフィールドがありませんでした"
            
            return output_path, f"Wordに{filled_count}項目を入力しました"
            
        except Exception as e:
            self.logger.error(f"[DOC_FILLER] Word fill error: {e}")
            return None, f"Word入力エラー: {e}"
    
    def _fill_word_table_cell(self, doc, field_id: str, value: str, input_length_type: str = "unknown") -> bool:
        """
        Wordテーブルセルに入力。
        
        Args:
            doc: Wordドキュメント
            field_id: フィールドID（"tableN_行_列"形式）
            value: 入力値
            input_length_type: "short"（短文）, "long"（長文）, "unknown"
        """
        try:
            # "tableN_行_列" をパース
            parts = field_id.split('_')
            if len(parts) != 3:
                return False
            
            table_part = parts[0]  # "tableN"
            row = int(parts[1])
            col = int(parts[2])
            table_idx = int(table_part.replace("table", ""))
            
            if table_idx >= len(doc.tables):
                self.logger.warning(f"[DOC_FILLER] Table {table_idx} not found")
                return False
            
            table = doc.tables[table_idx]
            
            if row >= len(table.rows):
                self.logger.warning(f"[DOC_FILLER] Row {row} not found in table {table_idx}")
                return False
            
            cells = table.rows[row].cells
            if col >= len(cells):
                self.logger.warning(f"[DOC_FILLER] Col {col} not found in table {table_idx}, row {row}")
                return False
            
            cell = cells[col]
            
            # 長文の場合、テーブルセル内に収まるように処理
            # 短い場合はそのまま、長い場合は文字数を制限して...を付ける
            if input_length_type == "short" and len(value) > 50:
                # 短文フィールドに長いテキストが来た場合、切り詰める
                value = value[:47] + "..."
                self.logger.debug(f"[DOC_FILLER] Trimmed long value for short field: {field_id}")
            
            # 既存テキストをクリアして新しいテキストを設定
            # フォントスタイルを保持する
            if cell.paragraphs:
                para = cell.paragraphs[0]
                self._clear_and_add_with_style(para, value)
            else:
                cell.text = value
            
            return True
            
        except Exception as e:
            self.logger.warning(f"[DOC_FILLER] Table cell fill error: {e}")
            return False
    
    def _fill_word_paragraph(self, doc, field_id: str, value: str) -> bool:
        """
        Word段落に入力（プレースホルダーを置換）。
        
        対応する入力タイプ:
        - inline: コロン後に入力を追加
        - next_line: 段落全体を入力値で置換
        - underline: 下線プレースホルダーを置換
        - bracket: 空括弧プレースホルダーを置換
        """
        try:
            # "para_N" をパース
            para_idx = int(field_id.replace("para_", ""))
            
            if para_idx >= len(doc.paragraphs):
                self.logger.warning(f"[DOC_FILLER] Paragraph {para_idx} not found")
                return False
            
            para = doc.paragraphs[para_idx]
            original_text = para.text
            
            import re
            
            # パターン1: 下線プレースホルダー「____」「＿＿＿」を置換
            new_text = re.sub(r'[_＿]{3,}', value, original_text)
            if new_text != original_text:
                para.clear()
                para.add_run(new_text)
                return True
            
            # パターン2: 空括弧プレースホルダー「（　）」を置換
            new_text = re.sub(r'[(（]\s*[　\s]*[)）]', f'（{value}）', original_text)
            if new_text != original_text:
                para.clear()
                para.add_run(new_text)
                return True
            
            # パターン3: 括弧付きヒント「（入力してください）」を置換
            new_text = re.sub(r'[(（][^)）]+[)）]', f'（{value}）', original_text)
            if new_text != original_text:
                para.clear()
                para.add_run(new_text)
                return True
            
            # パターン4: コロン終端の場合、コロン後に入力を追加
            colon_match = re.match(r'^(.+?[:：])\s*$', original_text)
            if colon_match:
                new_text = f"{colon_match.group(1)} {value}"
                para.clear()
                para.add_run(new_text)
                return True
            
            # パターン5: コロンがある場合、コロン後を置換
            colon_replace_match = re.match(r'^(.+?[:：])\s*(.*)$', original_text)
            if colon_replace_match:
                prefix = colon_replace_match.group(1)
                current_value = colon_replace_match.group(2).strip()
                
                # 現在の値が空、空白のみ、またはヒント（括弧付き）の場合に置換
                if not current_value or re.match(r'^[　\s]+$', current_value) or re.match(r'^[（(].+[)）]$', current_value):
                    new_text = f"{prefix} {value}"
                    para.clear()
                    para.add_run(new_text)
                    return True
            
            # パターン6: 次行入力の場合（段落が比較的空の場合）、テキスト全体を置換
            if len(original_text.strip()) < 10:
                para.clear()
                para.add_run(value)
                return True
            
            # 上記いずれにも該当しない場合、段落末尾に追加
            para.add_run(f"\n{value}")
            return True
            
        except Exception as e:
            self.logger.warning(f"[DOC_FILLER] Paragraph fill error: {e}")
            return False
    
    def _fill_word_paragraph_with_pattern(
        self, 
        doc, 
        field_id: str, 
        value: str, 
        input_pattern: str,
        location: Dict[str, Any]
    ) -> bool:
        """
        VLMで検出された入力パターンに基づいてWord段落に入力する。
        
        Args:
            doc: Wordドキュメント
            field_id: フィールドID（"para_N"形式）
            value: 入力値
            input_pattern: 入力パターン（"inline", "next_line", "underline", "bracket"）
            location: 位置情報（paragraph_idx, label_paragraph_idx等）
            
        Returns:
            入力成功かどうか
        """
        try:
            import re
            
            # パターンに応じた処理
            para_idx = location.get("paragraph_idx")
            if para_idx is None:
                # field_idからパース
                para_idx = int(field_id.replace("para_", ""))
            
            if para_idx >= len(doc.paragraphs):
                self.logger.warning(f"[DOC_FILLER] Paragraph {para_idx} not found")
                return False
            
            para = doc.paragraphs[para_idx]
            original_text = para.text
            
            # パターン別の入力処理
            # 事前にスタイルを取得
            style = self._get_existing_font_style(para)
            
            if input_pattern == "next_line":
                # 次行入力: 段落全体を入力値で置換（スタイル保持）
                # この段落がラベルの次の段落なので、内容を完全に置き換える
                para.clear()
                self._add_run_with_style(para, value, style)
                self.logger.debug(f"[DOC_FILLER] Applied next_line pattern to para {para_idx}")
                return True
            
            elif input_pattern == "underline":
                # 下線プレースホルダー「____」を置換（スタイル保持）
                new_text = re.sub(r'[_＿]{2,}', value, original_text)
                if new_text != original_text:
                    para.clear()
                    self._add_run_with_style(para, new_text, style)
                    self.logger.debug(f"[DOC_FILLER] Applied underline pattern to para {para_idx}")
                    return True
                # 下線がない場合はinlineとして処理
                input_pattern = "inline"
            
            elif input_pattern == "bracket":
                # 括弧プレースホルダー「（　）」「（入力してください）」を置換（スタイル保持）
                # まず空括弧を試す
                new_text = re.sub(r'[(（]\s*[　\s]*[)）]', f'（{value}）', original_text)
                if new_text != original_text:
                    para.clear()
                    self._add_run_with_style(para, new_text, style)
                    self.logger.debug(f"[DOC_FILLER] Applied bracket pattern (empty) to para {para_idx}")
                    return True
                # ヒント付き括弧を試す
                new_text = re.sub(r'[(（][^)）]+[)）]', f'（{value}）', original_text)
                if new_text != original_text:
                    para.clear()
                    self._add_run_with_style(para, new_text, style)
                    self.logger.debug(f"[DOC_FILLER] Applied bracket pattern (with hint) to para {para_idx}")
                    return True
                # 括弧がない場合はinlineとして処理
                input_pattern = "inline"
            
            # inlineパターン（デフォルト）
            if input_pattern == "inline":
                # コロン後に入力を追加/置換（スタイル保持）
                colon_match = re.match(r'^(.+?[:：])\s*(.*)$', original_text)
                if colon_match:
                    prefix = colon_match.group(1)
                    current_value = colon_match.group(2).strip()
                    
                    # 現在の値が空、空白のみ、下線、またはヒント（括弧付き）の場合に置換
                    if (not current_value or 
                        re.match(r'^[　\s]+$', current_value) or 
                        re.match(r'^[_＿]+$', current_value) or
                        re.match(r'^[（(].+[)）]$', current_value)):
                        new_text = f"{prefix} {value}"
                        para.clear()
                        self._add_run_with_style(para, new_text, style)
                        self.logger.debug(f"[DOC_FILLER] Applied inline pattern to para {para_idx}")
                        return True
                    else:
                        # 既存の値がある場合は置き換える
                        new_text = f"{prefix} {value}"
                        para.clear()
                        self._add_run_with_style(para, new_text, style)
                        self.logger.debug(f"[DOC_FILLER] Replaced existing value with inline pattern in para {para_idx}")
                        return True
                
                # コロンがない場合は段落末尾に追加（スタイル保持）
                self._add_run_with_style(para, f" {value}", style)
                self.logger.debug(f"[DOC_FILLER] Appended value to para {para_idx} (no colon found)")
                return True
            
            # 不明なパターンの場合はフォールバックとして既存メソッドを使用
            self.logger.warning(f"[DOC_FILLER] Unknown pattern '{input_pattern}', using fallback")
            return self._fill_word_paragraph(doc, field_id, value)
            
        except Exception as e:
            self.logger.warning(f"[DOC_FILLER] Pattern-based paragraph fill error: {e}")
            # フォールバックとして既存メソッドを試す
            try:
                return self._fill_word_paragraph(doc, field_id, value)
            except:
                return False
    
    def _create_output_path(self, original_path: str, user_id: str, ext: str) -> str:
        """出力ファイルパスを生成"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        original_name = os.path.splitext(os.path.basename(original_path))[0]
        
        user_dir = os.path.join(self.output_dir, user_id or "default")
        os.makedirs(user_dir, exist_ok=True)
        
        output_name = f"{original_name}_filled_{timestamp}.{ext}"
        return os.path.join(user_dir, output_name)
    
    def cleanup_old_files(self, max_age_hours: int = 24):
        """古い出力ファイルを削除"""
        try:
            import time
            
            current_time = time.time()
            max_age_seconds = max_age_hours * 3600
            
            for root, dirs, files in os.walk(self.output_dir):
                for filename in files:
                    file_path = os.path.join(root, filename)
                    file_age = current_time - os.path.getmtime(file_path)
                    
                    if file_age > max_age_seconds:
                        os.remove(file_path)
                        self.logger.info(f"[DOC_FILLER] Cleaned up old file: {filename}")
                        
        except Exception as e:
            self.logger.warning(f"[DOC_FILLER] Cleanup error: {e}")
