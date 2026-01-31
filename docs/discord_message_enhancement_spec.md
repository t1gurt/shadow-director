# Discordメッセージ強化機能 仕様書

## 概要
Discordに表示されるメッセージを強化し、AIの「思考プロセス（Agent Thought）」と「リカバリー演出」を可視化する機能。

## 追加機能

### 1. 脳内開示（Agent Thought）
信頼性評価の前に、判断根拠を「独り言」形式で表示する。

**表示例:**
```
🧠 **Agent Thought: [令和8年度 WAM助成...] ドメイン解析完了**
_「政府ドメイン(.go.jp)のため信頼性は最高ランク」_

✅ **[令和8年度 WAM助成...] ➡ 信頼性評価: 95点 (Verified)**
```

### 2. 障害検知
ログイン壁、404、アクセス拒否などを検出した際に明示的に表示する。

**検出パターン:**
- `sign in`, `login`, `ログイン` → ログイン壁
- `404`, `not found`, `見つかりません` → ページ未発見
- `access denied`, `forbidden`, `403` → アクセス拒否
- `error`, `エラー` → エラーページ

**表示例:**
```
⚠️ **障害検知: ログイン壁**
_ページタイトル: "Sign in - Google Accounts"_
```

### 3. リカバリー演出
代替ルート探索時に、戦略変更と再検索を表示する。

**表示例:**
```
🧠 **Agent Thought: [Y's×SDGs...] 戦略変更**
_「指定されたURLにアクセスできないため、助成金名をキーに一般公開されている公式ページをGoogle検索で探します。」_

🔄 **[Y's×SDGs...] 再検索を実行中...**
_代替URLを探索_
```

## 変更ファイル

| ファイル | 変更内容 |
|---------|---------|
| `src/utils/progress_notifier.py` | THINKING/OBSTACLE/RECOVERY ステージ追加、`notify_thought()`, `notify_obstacle()`, `notify_recovery()` メソッド追加 |
| `src/logic/grant_finder.py` | 信頼性評価前にAgent Thought表示、リトライ時に障害検知・リカバリー演出表示、Playwright障害検知対応、**Gemini Thinking Output取得・表示** |
| `src/logic/grant_page_scraper.py` | `_detect_obstacle()` メソッド追加、ページタイトルから障害パターンを検出 |

## Gemini Thinking Output（生ログ）表示

`ThinkingConfig(include_thoughts=True)` を使用し、モデルの実際の思考プロセスを取得してDiscordに表示。

**表示例:**
```
🧠 **Agent Thought: AIの推論プロセス（生ログ）**
_「募集要項には『IT導入』の文字はないが、『業務効率化』という文脈があり、かつ過去の採択事例に類似のDX案件があるため、適合度Aと判定。ただし、締め切りまで3日しかないため、優先度を最高に設定。」_
```

**対象箇所:**
- `search_grants()` - 助成金検索時の推論
- `find_official_page()` - 公式ページ調査の推論
- リトライ検索時のリカバリー推論

**日本語化:**
プロンプトに `**重要: あなたの内部思考・推論プロセスはすべて日本語で行ってください。**` を追加し、Thinking Outputを日本語で出力。

## 処理フローへの影響
**なし** - メッセージ表示のみの変更であり、既存の処理ロジックは維持。
