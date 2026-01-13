# フォントスタイル保持機能 仕様書

## 概要

ドラフト記入時に、テンプレートのフォントスタイル（フォント名、サイズ、太字、斜体）を保持する機能。

## 変更ファイル

`src/tools/document_filler.py`

## 追加メソッド

### 1. `_get_existing_font_style(paragraph)`

段落から既存のフォントスタイルを取得。

```python
# 戻り値
{
    "font_name": "ＭＳ 明朝",
    "font_size": Pt(10.5),
    "bold": False,
    "italic": False
}
```

### 2. `_add_run_with_style(paragraph, text, style)`

指定されたスタイルでテキストを追加。

### 3. `_clear_and_add_with_style(paragraph, text)`

段落をクリアし、元のスタイルを保持してテキストを追加。

## 動作

1. テキスト追加前に既存のrunからフォントスタイルを取得
2. 段落をクリア
3. 取得したスタイルを適用して新しいrunを追加

## 対象箇所

- テーブルセルへの入力 (`_fill_word_table_cell`)
- 段落への入力 (`_fill_word_paragraph_with_pattern`)
  - next_line パターン
  - underline パターン
  - bracket パターン
  - inline パターン
