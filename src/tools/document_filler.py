"""
Document Filler - Excel/Wordフォーマットにドラフト内容を入力する。

Cloud Run（Linux）対応。openpyxlとpython-docxを使用。
"""

import logging
import os
import shutil
from typing import Dict, List, Optional, Tuple
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
        field_values: Dict[str, str],
        user_id: str = None
    ) -> Tuple[Optional[str], str]:
        """
        python-docxでWordに入力する。
        
        Args:
            file_path: テンプレートWordファイルのパス
            field_values: {field_id: 入力値}
                field_id形式: 
                  - "tableN_行_列" (テーブルセル)
                  - "para_N" (段落)
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
            
            for field_id, value in field_values.items():
                if not value:
                    continue
                
                try:
                    if field_id.startswith("table"):
                        # テーブルセル: "tableN_行_列"
                        filled = self._fill_word_table_cell(doc, field_id, value)
                    elif field_id.startswith("para_"):
                        # 段落: "para_N"
                        filled = self._fill_word_paragraph(doc, field_id, value)
                    else:
                        self.logger.warning(f"[DOC_FILLER] Unknown field_id format: {field_id}")
                        filled = False
                    
                    if filled:
                        filled_count += 1
                        
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
    
    def _fill_word_table_cell(self, doc, field_id: str, value: str) -> bool:
        """Wordテーブルセルに入力"""
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
            
            # 既存テキストをクリアして新しいテキストを設定
            # 注意: セル内の書式は維持したい場合は段落の最初のランを使う
            if cell.paragraphs:
                para = cell.paragraphs[0]
                para.clear()
                para.add_run(value)
            else:
                cell.text = value
            
            return True
            
        except Exception as e:
            self.logger.warning(f"[DOC_FILLER] Table cell fill error: {e}")
            return False
    
    def _fill_word_paragraph(self, doc, field_id: str, value: str) -> bool:
        """Word段落に入力（プレースホルダーを置換）"""
        try:
            # "para_N" をパース
            para_idx = int(field_id.replace("para_", ""))
            
            if para_idx >= len(doc.paragraphs):
                self.logger.warning(f"[DOC_FILLER] Paragraph {para_idx} not found")
                return False
            
            para = doc.paragraphs[para_idx]
            original_text = para.text
            
            # プレースホルダーパターンを置換
            import re
            
            # パターン: 「____」「＿＿＿」を置換
            new_text = re.sub(r'[_＿]{3,}', value, original_text)
            
            # パターン: 空括弧「（　）」を置換
            new_text = re.sub(r'[(（]\s*[　\s]*[)）]', f'（{value}）', new_text)
            
            if new_text != original_text:
                # テキストを更新
                para.clear()
                para.add_run(new_text)
                return True
            
            # プレースホルダーがない場合は末尾に追加
            para.add_run(f"\n{value}")
            return True
            
        except Exception as e:
            self.logger.warning(f"[DOC_FILLER] Paragraph fill error: {e}")
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
