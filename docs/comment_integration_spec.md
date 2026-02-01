# 懸念点コメント埋め込み & 推敲結果反映 仕様書

## 概要

ドラフト作成後の懸念点（情報不足、不確実、文字数超過など）をWord/Excelファイルに直接埋め込み、ユーザーがレビューしやすい形式で提供する機能。また、推敲ループで改善されたドラフト内容をWord/Excel入力時の参照情報として活用する。

## 変更ファイル

| ファイル | 変更内容 |
|---------|---------|
| `src/agents/drafter.py` | `fill_fields_individually`に推敲済みドラフトを渡す |
| `src/logic/format_field_mapper.py` | `refined_draft`引数を追加、レポート簡略化 |
| `src/tools/document_filler.py` | Excel/Wordコメント埋め込み機能 |

---

## 機能詳細

### 1. 推敲結果のWord/Excel反映

推敲ループ（Critic Agent評価→改善）で改善されたドラフト内容が、Word/Excel入力時のプロンプトに参照情報として含まれるようになりました。

**メリット:**
- 推敲後の表現スタイルを踏襲した一貫性のある入力
- ドラフトと矛盾しない内容の生成

**実装:**
```python
# drafter.py
field_values = self.format_mapper.fill_fields_individually(
    fields=fields,
    profile=profile,
    grant_name=grant_name,
    grant_info=grant_info,
    refined_draft=draft_content  # 推敲後のドラフト
)
```

---

### 2. Excel懸念点コメント

懸念点がある項目には、Excelのセルコメント機能を使用して詳細を埋め込みます。

**コメント形式:**
```
【⚠️ 情報不足】
項目: 団体設立年月日
理由: プロファイルに設立日の情報が見つかりません。

※ 内容をご確認のうえ、必要に応じて修正してください。
(自動生成: Shadow Director AI)
```

**懸念点タイプ:**
| タイプ | アイコン | 説明 |
|--------|---------|------|
| `missing_info` | ⚠️ | 情報不足 |
| `uncertain` | ❓ | 要確認 |
| `length_exceeded` | 📏 | 文字数超過 |
| `truncated` | ✂️ | 回答省略 |

---

### 3. Wordネイティブコメント

WordのOOXML（Office Open XML）を直接操作して、正式なコメントを挿入します。

**実装方式:**
1. `commentRangeStart` / `commentRangeEnd` 要素でコメント範囲を指定
2. `commentReference` でコメントへの参照を追加
3. python-docxでSave後、ZIP操作で`comments.xml`を注入
4. `[Content_Types].xml`と`document.xml.rels`を更新

**メリット:**
- ✅ Wordの「コメント」パネルに一覧表示
- ✅ 返信・解決等の機能が使える
- ✅ 印刷時の表示/非表示を制御可能

**ドキュメント末尾の形式:**
```
────────────────────────────────────────
📋 Shadow Director AI - 懸念点一覧
以下の項目については、内容をご確認のうえ必要に応じて修正してください。

[※1] 【⚠️ 情報不足】団体設立年月日
    → プロファイルに設立日の情報が見つかりません。

[※2] 【📏 文字数超過】事業概要
    → 500字制限を23字超過（4.6%オーバー）

※ この懸念点一覧は提出前に削除してください。
```

---

### 4. テキストレポートの簡略化

Discordに表示されるテキストレポートは統計サマリーのみになり、詳細はWord/Excelのコメントを参照する形式に変更。

**変更前（詳細形式）:**
```markdown
## 📊 ドラフト品質レポート

**品質スコア**: 🟢 **85点** (優良)
**完成度**: 90% (45/50項目入力済み)

### ⚠️ 懸念点

#### 📏 文字数制限を超過した項目
- **事業概要**: 500字制限を23字超過（4.6%オーバー）

#### 📋 情報不足で埋められなかった項目
- **団体設立年月日**: プロファイルに設立日の情報が見つかりません。
...
```

**変更後（統計サマリー形式）:**
```markdown
## 📋 ドラフト品質サマリー

- **品質スコア**: 🟢 **85点** (優良)
- ✅ **正常入力**: 45項目
- ⚠️ **要確認**: 5項目（Word/Excelのコメントを参照）
  - 情報不足: 2項目 / 文字数超過: 2項目 / 省略あり: 1項目
- 🔧 **自動修正**: 3回の文字数超過を修正

> 💡 詳細は添付のWord/Excelファイル内のコメントをご確認ください。
```

---

## テスト確認事項

- [ ] Excelファイルの懸念点があるセルにコメントが追加されている
- [ ] Wordファイルの懸念点がある項目に `[※N]` マーカーが付いている
- [ ] Wordファイル末尾に懸念点一覧セクションがある
- [ ] Discordに表示されるレポートが統計サマリー形式になっている
- [ ] 推敲後のドラフト内容がWord/Excel入力に反映されている

---

## 2026-02-01 Bugfix: OOXML構造の修正

### 問題

Wordファイルを開くと「修正個所の表示」ダイアログが表示され、「文字のプロパティ」エラーが複数発生する。

### 原因

`comments.xml`に含まれるコメント要素のOOXML構造が不完全だった：
- `w:rPr`（ランプロパティ）要素が欠落
- `w:pPr`（段落プロパティ）要素が欠落
- 名前空間の一部が不足

### 修正内容

| メソッド | 修正内容 |
|---------|---------|
| `_add_comment_to_comments_part` | `w:rPr`と`w:pPr`を追加、`w:lang`属性を設定 |
| `_build_comments_xml` (新規) | 正しいOOXML形式を手動で構築 |
| `_inject_comments_to_docx` | `_build_comments_xml`を使用するよう変更 |

### 修正後のXML構造

```xml
<!-- document.xml内 (commentReferenceを含むrun) -->
<w:r>
  <w:rPr>
    <w:sz w:val="16"/>
    <w:szCs w:val="16"/>
  </w:rPr>
  <w:commentReference w:id="0"/>
</w:r>

<!-- comments.xml内 -->
<w:comment w:id="0" w:author="Shadow Director AI" w:date="..." w:initials="SD">
  <w:p>
    <w:pPr/>
    <w:r>
      <w:rPr><w:lang w:val="ja-JP"/></w:rPr>
      <w:t xml:space="preserve">【⚠️ 情報不足】...</w:t>
    </w:r>
  </w:p>
</w:comment>
```

### 検証結果

テストスクリプト `test_comment_fix.py` で生成した `testdata/test_comment_fixed_v2.docx` を確認:
- ✅ `w:rPr` が `commentReference` の前に正しく挿入されている
- ✅ `comments.xml` に正しい `w:pPr`, `w:rPr`, `w:lang` が含まれている
- ✅ `word/_rels/document.xml.rels` に `comments.xml` へのリレーションシップが追加されている
- ✅ `[Content_Types].xml` に `comments.xml` のオーバーライドが追加されている

---

## 2026-02-01 追加修正: XML更新メソッドの改善

### 問題

lxmlライブラリによるXML操作が、一部の環境で名前空間の処理に失敗し、リレーションシップとContent-Typeが正しく更新されていなかった。

### 修正内容

| メソッド | 修正内容 |
|---------|---------|
| `_add_comments_relationship` | lxmlからシンプルな文字列置換に変更 |
| `_add_comments_content_type` | lxmlからシンプルな文字列置換に変更 |

> [!NOTE]
> 以前のエラーファイルは修正前のコードで生成されたものです。
> 修正後は `testdata/test_comment_fixed_v2.docx` を開いてエラーがないことを確認してください。

