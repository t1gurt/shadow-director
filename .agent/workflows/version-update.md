---
description: バージョンアップとREADMEの更新手順
---

# バージョンアップとREADME更新

新機能を実装した後に実施するバージョンアップ手順です。

## 1. バージョンファイルの更新

ファイル: `src/version.py`

1. `__version__` を次のバージョンに更新（例: `1.6.0` → `1.7.0`）
2. `__update_date__` を今日の日付に更新
3. `LATEST_FEATURES` リストの先頭に新機能を追加
   - 新バージョンのコメント行を追加（例: `# v1.7.0 - 機能名`）
   - 機能の説明を文字列で追加

```python
# 例
__version__ = "1.7.0"
__update_date__ = "2026-01-10"

LATEST_FEATURES = [
    # v1.7.0 - 新機能
    "新機能の説明",
    # v1.6.0 - 前バージョン
    ...
]
```

## 2. READMEの更新

ファイル: `README.md`

1. **機能説明セクション**（該当する場合）に新機能を追記
2. **Current Deployment Status** セクションのバージョン番号を更新
3. **Latest Updates** セクションを追加・更新
   - 既存の Latest Updates は残す（v1.X.0 → v1.(X-1).0）
   - 新しい Latest Updates セクションを上に追加

```markdown
### Latest Updates (v1.7.0)
- 📝 **機能名**: 説明

### Latest Updates (v1.6.0)
- ...
```
