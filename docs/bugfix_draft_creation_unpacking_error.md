# ドラフト作成エラー修正 - 仕様書

## 修正日
2026-01-14

## 問題の概要

助成金申請書のドラフト作成処理（Step 2）において、以下のエラーが発生していました：

```
⚠️ ドラフト作成エラー: too many values to unpack (expected 2)
```

## 原因

### 技術的な原因
`orchestrator.py`の`_process_top_match_drafts()`メソッド内（714行目）で、`format_files`をイテレートする際に、タプルのアンパック処理に問題がありました。

### 詳細な原因分析

1. **`_research_grant_format()`メソッド**は、2要素のタプル`(file_path, file_name)`を返します
2. **`create_draft()`メソッド**は、3要素のタプル`(file_path, file_name, file_type)`を含む`related_files`を返します
3. 714行目のコードは、常に2要素のタプルを期待していましたが、実際には3要素のタプルが渡される場合がありました

```python
# エラーが発生していたコード（714行目）
for file_path, file_name in format_files:  # 2要素を期待
    grant_result += f"[FORMAT_FILE_NEEDED:{user_id}:{file_path}]\n"
```

## 修正内容

### 修正ファイル
- `src/agents/orchestrator.py` (714-720行目)

### 修正内容の詳細

タプルの要素数を動的にチェックし、2要素・3要素の両方に対応できるようにしました：

```python
# 修正後のコード
for file_tuple in format_files:
    # 2要素 (file_path, file_name) と 3要素 (file_path, file_name, file_type) の両方に対応
    if len(file_tuple) == 3:
        file_path, file_name, _ = file_tuple
    else:
        file_path, file_name = file_tuple
    grant_result += f"[FORMAT_FILE_NEEDED:{user_id}:{file_path}]\n"
```

### 修正のポイント

1. **柔軟性の向上**: タプルの要素数に応じて適切にアンパックする
2. **後方互換性**: 既存の2要素タプルも引き続きサポート
3. **拡張性**: 将来的に`file_type`情報が必要になった場合にも対応可能（現時点では使用していない）

## セキュリティへの配慮

この修正では、ハードコーディングされた値は使用していません。動的にタプルの長さを判定し、適切に処理しています。

## 影響範囲

- **影響を受ける機能**: 助成金申請書のドラフト自動作成（Top Match検出時）
- **影響を受けるユーザー**: 共鳴度90以上の助成金が検出され、自動ドラフト作成が実行される全ユーザー

## テスト方法

### 手動テスト手順

1. NPOプロファイルを作成（インタビュー完了）
2. 助成金検索を実行し、共鳴度90以上の案件を検出
3. 自動ドラフト作成が実行されることを確認
4. 以下のメッセージが表示され、エラーが発生しないことを確認：
   ```
   **Step 2: ドラフト作成中...**
   ✅ ドラフト作成完了
   ```

### 期待される動作

- エラーが発生せず、ドラフト作成が完了する
- 申請フォーマットファイルが正しく添付される
- マークダウン形式のドラフトが生成される

## 関連ファイル

- `src/agents/orchestrator.py` - 修正したファイル
- `src/agents/drafter.py` - `create_draft()`メソッドの定義元
- `docs/grant_search_flow_spec.md` - 助成金検索フローの仕様書

## 今後の改善案

1. **型ヒントの強化**: タプルの構造を明示的に定義（TypedDict等を使用）
2. **統一されたデータ構造**: ファイル情報を表すクラスまたはNamedTupleを定義し、一貫性を向上
3. **エラーハンドリングの強化**: タプル長が想定外の場合のエラーメッセージを追加
