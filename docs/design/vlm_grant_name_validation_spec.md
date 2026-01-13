# VLMによる申請書フォーマット判定の助成金名検証機能

## 概要

VLM（Vision Language Model）を使用して申請書フォーマットを判定する際に、対象の助成金名がファイル内容に含まれているかをチェックする機能を追加。これにより、別の助成金の申請書フォーマットが誤って対象助成金のフォーマットとして判定されることを防止する。

## 変更内容

### 1. `_classify_format_file` メソッドの拡張

- **ファイル**: `src/agents/orchestrator.py`
- **変更点**: `grant_name` パラメータを追加

```python
def _classify_format_file(self, filename: str, file_path: str = None, grant_name: str = None) -> str
```

### 2. `_classify_file_with_vlm` メソッドの拡張

- **ファイル**: `src/agents/orchestrator.py`
- **変更点**: 
  - `grant_name` パラメータを追加
  - VLMプロンプトに助成金名チェック指示を追加
  - `NOT_RELATED` 判定結果のハンドリング

### 3. 新規メソッド `_extract_grant_keywords`

助成金名から主要なキーワードを抽出するヘルパーメソッドを追加。

**抽出対象**:
- 財団名・法人名（例: 「公益財団法人○○財団」→「○○財団」）
- 助成プログラム名（例: 「○○助成金」）
- 基金名、協会名

## VLM判定ロジック

### 判定フロー

1. ファイル内容を抽出
2. 助成金名からキーワードを抽出
3. VLMに以下を問い合わせ:
   - ファイルの種類（申請書、募集要項など）
   - 助成金との関連性（キーワードがファイル内容に含まれるか）
4. 関連性がない場合は `NOT_RELATED` を返す
5. `NOT_RELATED` の場合は「📄 関連資料（別の助成金の可能性）」として分類

### VLMプロンプト

```
【重要】助成金の関連性チェック:
対象助成金名: {grant_name}
抽出キーワード: {keywords}

このファイルが上記の助成金に関連しているかを以下の基準で判定してください:
- ファイル内容に助成金名またはその主要キーワードが含まれているか
- 含まれていない場合は「NOT_RELATED」と判定してください
```

## 呼び出し箇所

### DRAFTインテント時

ユーザーメッセージから助成金名を抽出して渡す:
```python
# Extract grant name from user_message for file classification
extracted_grant_name = None
name_match = re.search(r'助成金名:\s*(.+?)(?:\n|$)', user_message)
if name_match:
    extracted_grant_name = name_match.group(1).strip()
...
file_type = self._classify_format_file(file_name, file_path, extracted_grant_name)
```

### Top Match自動ドラフト時

`opp['title']`（助成金タイトル）を渡す:
```python
file_type = self._classify_format_file(file_name, file_path, grant_title)
```

## 期待される効果

- **誤判定の防止**: 別の助成金の申請書が対象助成金のフォーマットとして誤って分類されることを防止
- **正確な分類**: 助成金に関連するファイルのみが「申請書フォーマット」として判定される
- **透明性**: 関連性がないファイルは「関連資料（別の助成金の可能性）」と明示

## 注意事項

- `grant_name` が `None` の場合は従来通りの判定（助成金名チェックなし）
- VLM判定はExcel/Word/PDFファイルのみに適用
- キーワードマッチング（ファイル名による判定）が先に評価される

## 非関連ファイルの通知対象外

### 動作概要

VLM判定で「別の助成金の可能性」と判定されたファイルは、ユーザーへの通知対象から**自動的に除外**される。

### 実装箇所

1. **DRAFTインテント処理** (`route_message`内)
2. **Top Match自動ドラフト処理** (`_process_top_match_drafts`内)

### フィルタリングロジック

```python
# ファイルをフィルタリング
related_files = []
unrelated_files = []

for file_path, file_name in format_files:
    file_type = self._classify_format_file(file_name, file_path, grant_name)
    if "別の助成金の可能性" in file_type:
        unrelated_files.append(...)  # 通知対象外
    else:
        related_files.append(...)    # 通知対象
```

### ユーザーへの通知

- **関連ファイルあり**: 通常通りファイル一覧を表示
- **関連ファイルなし（非関連のみ）**: 「ダウンロードしたファイルは対象助成金とは関連性が確認できませんでした」と表示
- **ファイルなし**: 「申請フォーマットファイルは見つかりませんでした」と表示

---

## 助成金のベースURL判定

### URL取得ロジック

ドラフト作成時の助成金URLは、以下の優先順位で決定される:

1. **`grant_info`から抽出**: `URL:\s*(https?://[^\s]+)` パターンでマッチ
2. **Observerからの情報**: Top Match処理時は `opp.get('official_url')` を使用
3. **見つからない場合**: Google Search Groundingで助成金名を検索

### 実装箇所

- **ファイル**: `src/agents/drafter.py`
- **メソッド**: `create_draft` (520-544行目)

```python
# Try to extract URL from grant_info
url_match = re.search(r'URL:\s*(https?://[^\s]+)', grant_info)
if url_match:
    grant_url = url_match.group(1).strip()
```

### URLの活用

- **URLあり**: Playwrightでページを直接スクレイピング
- **URLなし**: Google Search Groundingで検索して情報収集
