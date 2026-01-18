# バグ分析: 資料送信時の内容未処理問題

## 問題の概要

ユーザーが資料ファイルを送信した際、Botは「資料、しっかりと受け取りました」と応答しているが、**資料の具体的な内容には一切触れていない**。

## ユーザーからの報告

```
ありがとうございます。資料、しっかりと受け取りました。詳細な事業計画や活動内容については、
後ほどじっくりと拝見し、整理させていただきますね。

ですが、書類には書ききれない、あなた自身の「熱」について、まずは深くお聞きしたいのです。

この団体を立ち上げよう、あるいはこの活動に命を吹き込もうと決心した時、
あなたの心を最も強く動かした出来事は何でしたか？
その時の情景や、突き動かされた感情について、ぜひ教えてください。

[設立者の魂理解度: 10% | 残り質問数: 13回]
```

→ 資料の具体的な内容には全く触れていない！

## 原因の推定

### 1. **ファイル処理エラーが発生した可能性**

[`main.py`](file:///c:/Users/keisu/workspace/shadow-director/main.py#L215-L231) の処理フロー：

```python
if message.attachments:
    # Call interviewer's async file processing method directly
    try:
        response = await orchestrator.interviewer.process_with_files_and_urls(
            user_input,
            str(message.channel.id),
            attachments=message.attachments
        )
    except Exception as e:
        logging.error(f"File processing error: {e}", exc_info=True)
        # Fallback to normal message processing
        response = await asyncio.to_thread(
            orchestrator.route_message,
            user_input + f"\n\n(添付ファイル: {len(message.attachments)}件 - 処理エラー)", 
            str(message.channel.id)
        )
```

→ **エラーが発生すると、ファイルの内容を読まずに通常のメッセージ処理にフォールバック**

### 2. **MIMEタイプエラーの影響**

先ほど修正した `file_processor.py` の `get_mime_type()` メソッドで、未対応のファイル形式（.docx, .xlsx など）を送信した場合、`ValueError` が発生します。

修正前の動作：
- `application/octet-stream` を送信 → Vertex AIが `400 INVALID_ARGUMENT` エラーを返す
- main.pyのexceptブロックでキャッチされる
- ファイル内容を読まずに通常の会話処理へフォールバック

### 3. **InterviewerAgentの動作**

[`interviewer.py`](file:///c:/Users/keisu/workspace/shadow-director/src/agents/interviewer.py#L508-L526) の通常処理：

```python
# Default to Interviewer
if attachments and len(attachments) > 0:
    # Add attachment info to the message
    attachment_info = f"\n\n📎 添付ファイル {len(attachments)}件:\n"
    for att in attachments:
        filename = getattr(att, 'filename', 'unknown')
        size = getattr(att, 'size', 0)
        attachment_info += f"  • {filename} ({size} bytes)\n"
    
    interviewer_response = self.interviewer.process_message(
        user_message + attachment_info, 
        user_id, 
        **kwargs
    )
```

→ **添付ファイルの存在は通知されるが、中身は処理されない**

## 検証すべきポイント

1. **送信されたファイルの種類は何か？**
   - サポートされているMIMEタイプ（PDF, TXT, MD, 画像など）か？
   - サポート外の形式（.docx, .xlsx, .pptxなど）か？

2. **エラーログに記録されているか？**
   - Cloud RunまたはローカルログでFileProcessor関連のエラーを確認

3. **エラーメッセージがユーザーに表示されたか？**
   - ユーザーには「処理エラー」のメッセージが見えなかった可能性

## 推奨される修正方法

### Option 1: エラーメッセージの改善

現在のエラーハンドリングでは、ユーザーに明確にエラーを通知していません。

```python
except Exception as e:
    logging.error(f"File processing error: {e}", exc_info=True)
    # ❌ ユーザーには「処理エラー」と添えられるだけで、詳細が伝わらない
    response = await asyncio.to_thread(
        orchestrator.route_message,
        user_input + f"\n\n(添付ファイル: {len(message.attachments)}件 - 処理エラー)", 
        str(message.channel.id)
    )
```

改善案：

```python
except ValueError as e:
    # MIMEタイプエラー（サポート外のファイル形式）
    error_msg = f"⚠️ ファイル形式エラー\n\n{str(e)}\n\n"
    error_msg += "通常の対話形式で情報を教えていただけますか？"
    await message.channel.send(error_msg)
    return
except Exception as e:
    logging.error(f"File processing error: {e}", exc_info=True)
    error_msg = f"⚠️ ファイルの読み込みに失敗しました。\n\nエラー: {str(e)}\n\n"
    error_msg += "通常の対話形式で情報を教えていただけますか？"
    await message.channel.send(error_msg)
    return
```

### Option 2: 未対応ファイル形式のサポート追加

.docx, .xlsx, .pptx などのOffice形式もVertex AIでサポートされている可能性があります。

要確認：
- [Vertex AI Gemini API - Supported MIME Types](https://cloud.google.com/vertex-ai/generative-ai/docs/model-reference/gemini)

### Option 3: ローカルでのファイル変換

未対応形式の場合、ローカルでテキスト抽出してから送信する方法も検討できます。

例：
- .docx → python-docx でテキスト抽出
- .xlsx → openpyxl でテキスト抽出
- .pptx → python-pptx でテキスト抽出

## 次のステップ

1. **ユーザーに確認**：どのようなファイル形式を送信したか？
2. **ログ確認**：エラーログでFileProcessor関連のエラーを確認
3. **修正実装**：エラーハンドリングの改善を実装

## 関連ファイル

- [`main.py:L215-231`](file:///c:/Users/keisu/workspace/shadow-director/main.py#L215-L231) - ファイル処理とエラーハンドリング
- [`src/tools/file_processor.py`](file:///c:/Users/keisu/workspace/shadow-director/src/tools/file_processor.py) - MIMEタイプ処理
- [`src/agents/interviewer.py`](file:///c:/Users/keisu/workspace/shadow-director/src/agents/interviewer.py) - ファイル処理メソッド
