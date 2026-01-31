# インタビュー時のURL情報取得機能

## 機能概要

インタビューエージェントがユーザーからURLを受け取った際、そのURLの内容を自動的に取得・分析し、団体情報の抽出に活用する機能です。

## 実装内容

### アーキテクチャ

```
ユーザー入力（URL含む）
    ↓
InterviewerAgent.process_with_files_and_urls()
    ↓
URLAnalyzer.analyze_urls()
    ↓
SiteExplorer (Playwright)
    ↓
ウェブページアクセス・情報抽出
    ↓
Gemini による団体情報分析
```

### 主要コンポーネント

#### 1. URLAnalyzer (`src/tools/url_analyzer.py`)

**役割**: URLの内容を取得・分析するツールクラス

**主要メソッド**:
- `analyze_url(url: str)`: 単一URLを分析
- `analyze_urls(urls: List[str])`: 複数URLを一括分析

**抽出情報**:
- ページタイトル
- メタディスクリプション
- 本文の要約（最大500文字）
- アクセス成否
- エラーメッセージ（失敗時のみ）

**技術仕様**:
- `SiteExplorer`（Playwrightベース）を使用してページにアクセス
- デフォルトタイムアウト: 15秒
- ヘッドレスモードで動作
- エラー時は適切なエラーメッセージを返却

#### 2. InterviewerAgent の拡張 (`src/agents/interviewer.py`)

**変更点**:
1. `URLAnalyzer`のインポートとインスタンス化
2. `process_with_files_and_urls()`メソッドでURL内容を取得
3. 取得したURL情報を分析プロンプトに含める

## 使用方法

### Discord Bot経由

1. インタビュー中にURLを含むメッセージを送信
2. エージェントが自動的にURLにアクセスし内容を取得
3. 取得した情報をもとに団体情報を分析・質問を生成

**例**:
```
ユーザー: 当団体のウェブサイトです https://example-npo.org
エージェント: 📚 **資料を分析しました**

[ウェブサイト名]
URL: https://example-npo.org
説明: NPO法人の活動紹介サイト
内容: 私たちは地域の子どもたちに無料の学習支援を提供しています...

---

ウェブサイトによると、学習支援が主な活動とのことですね。
この活動を始めたきっかけは何でしたか？
```

### プログラム内での使用

```python
from src.tools.url_analyzer import URLAnalyzer

# URLAnalyzerのインスタンス作成
analyzer = URLAnalyzer()

# 単一URL分析
result = await analyzer.analyze_url("https://example.com")
if result['success']:
    print(result['title'])
    print(result['content_summary'])

# 複数URL分析
results = await analyzer.analyze_urls([
    "https://example.com",
    "https://example.org"
])
```

## エラーハンドリング

### 想定されるエラーケース

1. **URLにアクセスできない**
   - ネットワークエラー
   - タイムアウト
   - DNSエラー

2. **ページが存在しない（404等）**
   - SiteExplorerが検出して適切にエラーを返却

3. **Playwrightの起動失敗**
   - ブラウザの起動エラー
   - リソース不足

### エラー時の動作

- URLアクセスに失敗した場合、エラーメッセージをユーザーに通知
- 他の資料（添付ファイル等）がある場合は、それらの処理を継続
- URLのみでエラーが発生した場合は、通常のインタビューにフォールバック

## セキュリティ考慮事項

- タイムアウト設定により無限待機を防止
- 環境変数等のハードコーディングなし
- ユーザー入力のURLを直接使用（サニタイズは`SiteExplorer`レイヤーで実施）

## テスト

### 単体テスト

`tests/test_url_analyzer.py`で以下のケースをカバー:
- 正常系: 有効なURLの分析
- 異常系: 無効なURLの処理
- 複数URL処理
- コンテンツ要約の長さ制限

### 統合テスト

`mock_runner.py`を使用してエンドツーエンドテスト:
```bash
python mock_runner.py
# URLを含むメッセージを送信してテスト
```

### 手動テスト

`tests/manual_test_url_analyzer.py`で簡単な動作確認:
```bash
python tests/manual_test_url_analyzer.py
```

## 技術的詳細

### 依存関係

- `SiteExplorer` (既存): Playwrightベースのブラウザ自動化
- `playwright`: ウェブブラウザ制御ライブラリ
- `asyncio`: 非同期処理

### パフォーマンス

- 1URLあたり約3-10秒（ページの複雑さによる）
- 複数URLは順次処理（並列化は今後の拡張候補）

## 今後の拡張案

1. **並列URL処理**: 複数URLを同時に処理して高速化
2. **キャッシュ機能**: 同じURLに対する再アクセスを避ける
3. **スクリーンショット保存**: ページの視覚的情報も保存
4. **より詳細な情報抽出**: 連絡先、住所等の構造化データ抽出
