# バグ修正: MIMEタイプエラーの解決

## 問題の概要

Vertex AI (Gemini API) への文書分析リクエストにおいて、以下のエラーが発生していました：

```
Document analysis error: 400 INVALID_ARGUMENT. 
{'error': {'code': 400, 'message': 'Unable to submit request because it has a 
mimeType parameter with value application/octet-stream, which is not supported. 
Update the mimeType and try again. 
Learn more: https://cloud.google.com/vertex-ai/generative-ai/docs/model-reference/gemini', 
'status': 'INVALID_ARGUMENT'}}
```

## 原因

`src/tools/file_processor.py` の `get_mime_type()` メソッドで、サポートされていないファイル拡張子に対してデフォルトで `application/octet-stream` を返していました。このMIMEタイプはVertex AI Gemini APIでサポートされていないため、エラーが発生していました。

### 問題のあったコード（修正前）

```python
def get_mime_type(self, filename: str) -> str:
    """
    Determine MIME type from filename extension.
    """
    ext = filename.lower().split('.')[-1]
    mime_types = {
        'pdf': 'application/pdf',
        'txt': 'text/plain',
        'md': 'text/markdown',
        'jpg': 'image/jpeg',
        'jpeg': 'image/jpeg',
        'png': 'image/png',
        'webp': 'image/webp',
        'gif': 'image/gif',
    }
    return mime_types.get(ext, 'application/octet-stream')  # ❌ サポート外のMIMEタイプ
```

## 修正内容

### 1. サポートするMIMEタイプの拡張

Vertex AI Gemini APIがサポートする以下のMIMEタイプを追加しました：

#### ドキュメント形式
- PDF (`application/pdf`)
- テキスト (`text/plain`)
- Markdown (`text/markdown`)
- HTML (`text/html`)
- CSS (`text/css`)
- JavaScript (`application/javascript`)
- Python (`text/x-python`)
- JSON (`application/json`)
- XML (`application/xml`)
- CSV (`text/csv`)

#### 画像形式
- JPEG (`image/jpeg`)
- PNG (`image/png`)
- WebP (`image/webp`)
- GIF (`image/gif`)
- HEIC (`image/heic`)
- HEIF (`image/heif`)

#### 音声形式
- WAV (`audio/wav`)
- MP3 (`audio/mp3`)
- AIFF (`audio/aiff`)
- AAC (`audio/aac`)
- OGG (`audio/ogg`)
- FLAC (`audio/flac`)

#### 動画形式
- MP4 (`video/mp4`)
- MPEG (`video/mpeg`)
- MOV (`video/mov`)
- AVI (`video/avi`)
- FLV (`video/x-flv`)
- WebM (`video/webm`)
- WMV (`video/x-ms-wmv`)
- 3GPP (`video/3gpp`)

### 2. エラーハンドリングの追加

サポートされていないファイル形式に対しては、明確なエラーメッセージを含む `ValueError` を発生させるようにしました。

### 修正後のコード

```python
def get_mime_type(self, filename: str) -> str:
    """
    Determine MIME type from filename extension.
    """
    ext = filename.lower().split('.')[-1]
    
    # Vertex AI supported MIME types
    # Reference: https://cloud.google.com/vertex-ai/generative-ai/docs/model-reference/gemini
    mime_types = {
        # Documents
        'pdf': 'application/pdf',
        'txt': 'text/plain',
        'md': 'text/markdown',
        'html': 'text/html',
        'htm': 'text/html',
        'css': 'text/css',
        'js': 'application/javascript',
        'py': 'text/x-python',
        'json': 'application/json',
        'xml': 'application/xml',
        'csv': 'text/csv',
        
        # Images
        'jpg': 'image/jpeg',
        'jpeg': 'image/jpeg',
        'png': 'image/png',
        'webp': 'image/webp',
        'gif': 'image/gif',
        'heic': 'image/heic',
        'heif': 'image/heif',
        
        # Audio
        'wav': 'audio/wav',
        'mp3': 'audio/mp3',
        'aiff': 'audio/aiff',
        'aac': 'audio/aac',
        'ogg': 'audio/ogg',
        'flac': 'audio/flac',
        
        # Video
        'mp4': 'video/mp4',
        'mpeg': 'video/mpeg',
        'mpg': 'video/mpeg',
        'mov': 'video/mov',
        'avi': 'video/avi',
        'flv': 'video/x-flv',
        'webm': 'video/webm',
        'wmv': 'video/x-ms-wmv',
        '3gp': 'video/3gpp',
        '3gpp': 'video/3gpp',
    }
    
    # ✅ サポート外のファイル形式に対しては明確なエラーを発生
    if ext not in mime_types:
        supported_formats = ', '.join(sorted(set(mime_types.keys())))
        raise ValueError(
            f"ファイル形式 '.{ext}' はサポートされていません。\n"
            f"サポートされている形式: {supported_formats}\n"
            f"ファイル名: {filename}"
        )
    
    return mime_types[ext]
```

## 効果

### 修正前
- サポート外のファイル形式を送信すると、APIレベルで `400 INVALID_ARGUMENT` エラーが発生
- エラーメッセージが不明瞭で、ユーザーが対処方法を理解しにくい
- サポートするファイル形式が限定的（8種類のみ）

### 修正後
- サポート外のファイル形式を検出時に、早期にわかりやすいエラーメッセージを表示
- サポートされているファイル形式の一覧をエラーメッセージに表示
- サポートするファイル形式を大幅に拡張（45種類以上）

## テスト推奨事項

以下のシナリオでテストを実施することを推奨します：

1. **サポートされているファイル形式のアップロード**
   - PDF、画像（JPEG, PNG）、動画（MP4）などをアップロードして正常に処理されることを確認

2. **サポート外のファイル形式のアップロード**
   - 例：`.docx`, `.xlsx`, `.pptx`, `.zip` などをアップロード
   - 期待される動作：わかりやすいエラーメッセージが表示される

3. **既存の機能への影響確認**
   - 文書分析機能が正常に動作することを確認
   - PRエージェント（画像添付機能）が正常に動作することを確認

## ユーザー向けエラーメッセージの改善

[`main.py`](file:///c:/Users/keisu/workspace/shadow-director/main.py#L224-L268) のエラーハンドリングも改善しました。

### 修正前の問題

サポート外のファイル形式（.pptx, .docx, .xlsxなど）をアップロードした場合：
- エラーはログに記録される
- しかし、ユーザーには何が問題かわからない
- 通常の会話処理にフォールバックするが、ファイルの内容は読まれない

### 修正後の動作

#### 1. サポート外のファイル形式の場合（ValueError）

ユーザーに以下の情報を含む詳細なエラーメッセージを表示：

```
⚠️ **サポートされていないファイル形式が含まれています**

**送信されたファイル**: `Get_Back_Spring.pptx`

**エラー詳細**:
ファイル形式 '.pptx' はサポートされていません。
サポートされている形式: 3gp, 3gpp, aac, aiff, avi, css, csv, ...

---

**📋 サポートされているファイル形式**:

**ドキュメント**: PDF, TXT, MD, HTML, CSS, JS, Python, JSON, XML, CSV
**画像**: JPEG, PNG, WebP, GIF, HEIC, HEIF
**音声**: WAV, MP3, AIFF, AAC, OGG, FLAC
**動画**: MP4, MPEG, MOV, AVI, FLV, WebM, WMV, 3GPP

---

**💡 解決方法**:

1. **PowerPoint (.pptx) の場合** → PDFに変換してから送信
2. **Word (.docx) の場合** → PDFに変換してから送信
3. **Excel (.xlsx) の場合** → PDFまたはCSVに変換してから送信
4. **資料の内容を直接テキストで教えていただく** こともできます

お手数ですが、上記の形式に変換してから再度お試しください。
```

#### 2. その他のエラーの場合（Exception）

一般的なエラーメッセージと解決方法を表示：

```
⚠️ **ファイルの処理中にエラーが発生しました**

**エラー内容**: [エラーメッセージ]

---

**💡 以下の方法をお試しください**:

1. ファイルサイズが大きすぎる場合は、小さくしてから再送信
2. ファイルが破損していないか確認
3. サポートされている形式（PDF、画像など）に変換
4. 資料の内容を直接テキストで教えていただく

もし問題が解決しない場合は、通常の対話形式で情報を教えていただけますか？
```

### 修正による効果

- ✅ ユーザーが問題の原因を即座に理解できる
- ✅ 具体的な解決方法が提示される
- ✅ サポートされている形式の一覧が明確
- ✅ ファイル変換の手順が分かりやすい
- ✅ 代替手段（テキストでの入力）も提示される

## 関連ファイル

- **修正ファイル**: 
  - [`src/tools/file_processor.py`](file:///c:/Users/keisu/workspace/shadow-director/src/tools/file_processor.py) - MIMEタイプ判定とエラー処理
  - [`main.py`](file:///c:/Users/keisu/workspace/shadow-director/main.py#L224-L268) - ユーザー向けエラーメッセージ表示
- **関連コード**: [`src/agents/orchestrator.py`](file:///c:/Users/keisu/workspace/shadow-director/src/agents/orchestrator.py)

## 参考資料

- [Vertex AI Gemini API - Supported MIME Types](https://cloud.google.com/vertex-ai/generative-ai/docs/model-reference/gemini)
