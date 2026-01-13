# フォーマットファイル自動入力 - 機能仕様書

## 概要

ダウンロードした申請フォーマットファイル（Excel/Word）に、Geminiで生成したドラフト内容を自動入力し、記入済みファイルとして出力する機能。

---

## 新規作成ファイル

### 1. format_field_mapper.py

VLMを使用してExcel/Wordフォーマットのフィールドを検出し、ドラフト内容とマッピングする。

**クラス: `FormatFieldMapper`**

| メソッド | 説明 |
|:--------|:-----|
| `analyze_excel_fields(file_path)` | Excelファイルのフィールドを解析 |
| `analyze_word_fields(file_path)` | Wordファイルのフィールドを解析 |
| `map_draft_to_fields(fields, draft)` | ドラフト内容を各フィールドにマッピング |
| `analyze_format_file(file_path)` | ファイル形式を自動判定して解析 |

---

### 2. document_filler.py

openpyxl/python-docxを使用してファイルに入力する。

**クラス: `DocumentFiller`**

| メソッド | 説明 |
|:--------|:-----|
| `fill_excel(file_path, field_values)` | Excelに入力 |
| `fill_word(file_path, field_values)` | Wordに入力 |
| `fill_document(file_path, field_values)` | 形式を自動判定して入力 |

---

## 変更ファイル

### drafter.py

- `FormatFieldMapper`と`DocumentFiller`をインポート
- `create_draft`メソッドにStep 4（フォーマット入力）を追加
- 戻り値を5つに変更: `(message, content, filename, format_files, filled_files)`

### orchestrator.py

- `create_draft`呼び出しを5つの戻り値に対応
- `[FILLED_FILE_NEEDED:]`マーカーで入力済みファイルを送信

---

## 処理フロー

```
Step 1: フォーマット検索とダウンロード
Step 2: ファイル解析（Gemini 3.0 Pro）
Step 3: ドラフト生成
Step 4: フォーマット入力（新規）
  └─ フィールド検出（3段階フォールバック）
     ├─ Phase 1: テキストベース検出（キーワード・パターン）
     ├─ Phase 2: VLM解析（ドキュメント全体を解析）
     └─ Phase 3: フォールバック（全テーブルセルを候補として検出）
  └─ openpyxl/python-docxで入力
  └─ 入力済みファイルを返却
```

---

## 制限事項

| ケース | 対応 |
|:-------|:-----|
| 複雑なExcel（結合セル多数） | フィールド検出に失敗する可能性 |
| Wordのフローティングテキストボックス | 段落/テーブルのみ対応 |
| スキャンPDF（画像ベース） | 入力不可 |

**フォールバック**: 入力に失敗した場合は従来通りMarkdownドラフト + フォーマットファイルを返却。

---

## 依存パッケージ

```bash
pip install openpyxl python-docx
```
