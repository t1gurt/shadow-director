# Wordの1セルテーブル検出機能 仕様書

## 機能概要

Word文書内の1セル(1行1列)のテーブルを入力フィールドとして検出する機能を実装しました。従来は2カラム以上のテーブル(「ラベル列 | 入力列」形式)のみ対応していましたが、添付画像のような単一セルのテーブルにも対応できるようになりました。

## 対応パターン

### パターン1: 段落ラベル + 1セルテーブル

段落にラベルがあり、その直後に1セルの空テーブルがある場合に検出します。

**例:**
```
<メールアドレス>          ← 段落(ラベル)
┌────────────────┐
│                │        ← 1セルテーブル(入力欄)
└────────────────┘
```

**検出条件:**
- テーブルが1行1列(1セル)
- セル内が空、またはプレースホルダー(`_____`, `（　）`など)
- 直前の段落にラベルテキストがある(100文字以内)

**location情報:**
```python
{
    "table_idx": 0,
    "row": 0,
    "col": 0,
    "input_pattern": "single_cell_with_paragraph_label"
}
```

### パターン2: 1セル内ラベル + 下線プレースホルダー

1セル内に「ラベル：_____」のような形式で下線プレースホルダーがある場合に検出します。

**例:**
```
┌──────────────────┐
│ 団体名：_____    │  ← 1セル内にラベルと下線
└──────────────────┘
```

**検出条件:**
- テーブルが1行1列(1セル)
- セル内に「ラベル：___」パターンがある(下線3文字以上)

**location情報:**
```python
{
    "table_idx": 0,
    "row": 0,
    "col": 0,
    "input_pattern": "single_cell_underline"
}
```

### パターン3: 1セル内ラベル + 括弧プレースホルダー

1セル内に「ラベル（　）」のような形式で括弧プレースホルダーがある場合に検出します。

**例:**
```
┌──────────────────┐
│ 申請日（　）     │  ← 1セル内にラベルと括弧
└──────────────────┘
```

**検出条件:**
- テーブルが1行1列(1セル)
- セル内に「ラベル（　）」パターンがある

**location情報:**
```python
{
    "table_idx": 0,
    "row": 0,
    "col": 0,
    "input_pattern": "single_cell_bracket"
}
```

## 実装詳細

### 新規追加メソッド

#### 1. `_detect_single_cell_pattern`

1セルテーブルを検出する専用メソッド。

**シグネチャ:**
```python
def _detect_single_cell_pattern(
    self, 
    table, 
    table_idx: int, 
    block_items=None
) -> List[FieldInfo]
```

**処理フロー:**
1. セル内テキストを取得
2. 下線パターン(`___`)を検索 → 検出したら返す
3. 括弧パターン(`（　）`)を検索 → 検出したら返す
4. 空セルまたはプレースホルダーのみの場合:
   - `_find_label_before_table`で直前の段落からラベルを取得
   - ラベルがあれば、そのラベルを使用
   - なければ、デフォルトラベル(`テーブルN`)を使用

#### 2. `_find_label_before_table`

テーブルの直前の段落からラベルを取得するヘルパーメソッド。

**シグネチャ:**
```python
def _find_label_before_table(
    self, 
    table_idx: int, 
    block_items=None
) -> Optional[str]
```

**処理フロー:**
1. `block_items`内で指定されたテーブルを探す
2. 直前の要素が段落かどうかを確認
3. 段落のテキストが100文字以内であれば、ラベルとして採用
4. 末尾のコロン(`:`, `：`)を除去して返す

### 既存メソッドの変更

#### `_analyze_word_table`

**変更内容:**
- メソッドシグネチャに`block_items`パラメータを追加
- テーブルが1行1列の場合、`_detect_single_cell_pattern`を呼び出す分岐を追加

**変更前:**
```python
def _analyze_word_table(self, table, table_idx: int) -> List[FieldInfo]:
```

**変更後:**
```python
def _analyze_word_table(self, table, table_idx: int, block_items=None) -> List[FieldInfo]:
    # ...
    if len(rows) == 1 and len(rows[0].cells) == 1:
        return self._detect_single_cell_pattern(table, table_idx, block_items)
```

#### `analyze_word_fields`

**変更内容:**
- `_analyze_word_table`呼び出し時に`block_items`を渡すように変更

**変更前:**
```python
table_fields = self._analyze_word_table(table, table_idx)
```

**変更後:**
```python
table_fields = self._analyze_word_table(table, table_idx, block_items)
```

## 使用例

```python
from src.logic.format_field_mapper import FormatFieldMapper

mapper = FormatFieldMapper()
fields = mapper.analyze_word_fields("application_form.docx")

# 検出されたフィールドを確認
for field in fields:
    if field.location.get("input_pattern", "").startswith("single_cell"):
        print(f"1セルテーブル検出: {field.field_name}")
        print(f"  パターン: {field.location['input_pattern']}")
        print(f"  位置: テーブル{field.location['table_idx']}")
```

## 制限事項

### 1. block_itemsの依存性

段落ラベルを使用する検出パターン(`single_cell_with_paragraph_label`)は、`block_items`(ドキュメント要素の順序リスト)に依存しています。`block_items`が正しく構築できない環境では、このパターンの検出精度が低下する可能性があります。

### 2. ラベルの長さ制限

直前の段落をラベルとして使用する場合、100文字以内の段落のみが対象となります。これは、長い説明文をラベルとして誤検出することを防ぐためです。

### 3. プレースホルダーの形式

以下のプレースホルダー形式に対応しています:
- 下線: `___` (3文字以上の`_`または`＿`)
- 括弧: `（　）`, `(　)`, `（）`, `()`

これ以外の形式のプレースホルダーは検出されない可能性があります。

### 4. 既存のテーブル検出への影響

1セルテーブルの検出は、既存の2カラム以上のテーブル検出ロジックには影響しません。1行1列のテーブルだけが新しいロジックに分岐されます。

## テスト

以下のテストケースを作成しました(`tests/test_single_cell_table.py`):

1. **下線パターンの検出**: `test_single_cell_with_underline_pattern`
2. **括弧パターンの検出**: `test_single_cell_with_bracket_pattern`
3. **段落ラベルパターンの検出**: `test_single_cell_empty_with_paragraph_label`
4. **ラベルなしパターンの検出**: `test_single_cell_empty_without_label`
5. **プレースホルダーのみの検出**: `test_single_cell_with_placeholder_only`
6. **ラベル抽出**: `test_find_label_before_table`
7. **統合テスト**: `test_analyze_word_table_detects_single_cell`

## 実装日時

- 実装日: 2026-01-21
- 実装者: Antigravity AI
- レビュー: ユーザー承認済み(LGTM)

## 関連ファイル

- [`src/logic/format_field_mapper.py`](file:///C:/Users/keisu/workspace/shadow-director/src/logic/format_field_mapper.py#L591-L782): メイン実装
- [`tests/test_single_cell_table.py`](file:///C:/Users/keisu/workspace/shadow-director/tests/test_single_cell_table.py): テストコード
- [`docs/specs/word_single_cell_table.md`](file:///C:/Users/keisu/workspace/shadow-director/docs/specs/word_single_cell_table.md): 本仕様書
