# UPDATE_PROFILE インテント 仕様書

## 概要

インタビューを経由せずに、団体情報を直接登録できる機能。

## コマンド例

```
団体名はNPO法人○○、代表者は田中太郎です
電話番号は03-1234-5678
メールアドレスは info@example.org
設立年は2015年、年間予算は500万円
```

## 対応する情報

| カテゴリ | 入力例 |
|----------|--------|
| 団体名 (`org_name`) | 「団体名は○○」 |
| 代表者名 (`representative_name`) | 「代表者は△△」 |
| 電話番号 (`phone_number`) | 「電話番号は03-xxxx-xxxx」 |
| メールアドレス (`email_address`) | 「メールは○○@○○」 |
| ホームページ (`website_url`) | 「HPは https://...」 |
| 設立年 (`founding_year`) | 「設立年は2020年」 |
| 年間予算 (`annual_budget`) | 「年間予算は500万円」 |
| プロジェクト名 (`project_name`) | 「プロジェクト名は○○」 |

## 処理フロー

```
ユーザー入力
    ↓
ルーター（UPDATE_PROFILE判定）
    ↓
_handle_update_profile()
    ↓
insight_extractorで情報抽出
    ↓
ProfileManagerに保存
    ↓
更新結果を表示
```

## 変更ファイル

| ファイル | 変更内容 |
|----------|----------|
| `config/prompts.yaml` | `router`に`UPDATE_PROFILE`インテント追加 |
| `src/agents/orchestrator.py` | インテント判定とハンドラー追加 |

## 確認コマンド

登録後、「プロフィール」コマンドで保存済み情報を確認できます。
