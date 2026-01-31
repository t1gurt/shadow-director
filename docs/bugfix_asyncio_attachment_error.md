# バグ修正: PowerPointファイル添付時のasyncioエラー

## 問題

PowerPointファイル（または他の添付ファイル）を最初に送信すると、以下のエラーが発生していました：

```
ERROR:root:Error processing message: There is no current event loop in thread 'asyncio_1'.
```

## 原因

1. **main.py (line 216)**: `orchestrator.route_message()` が `await asyncio.to_thread()` で別スレッドから呼び出されていた
2. **orchestrator.py (line 512)**: 添付ファイルがある場合、`asyncio.get_event_loop()` を呼び出そうとしていた
3. **エラー発生**: ワーカースレッド内から `asyncio.get_event_loop()` を呼び出すと、そのスレッドには実行中のイベントループが存在しないためエラーが発生

### 詳細な流れ

```
Discord メッセージ受信 (main.py)
    ↓
asyncio.to_thread() で別スレッドに委譲
    ↓
orchestrator.route_message() (同期メソッド) - ワーカースレッドで実行
    ↓
添付ファイルあり → asyncio.get_event_loop() を呼び出し
    ↓
❌ エラー: "There is no current event loop in thread 'asyncio_1'"
```

## 解決策

### 修正内容

#### 1. orchestrator.py の修正

`asyncio.get_event_loop()` の呼び出しを削除し、添付ファイル情報を単純にメッセージに追加する方式に変更しました。

**修正前** (lines 509-525):
```python
if attachments and len(attachments) > 0:
    import asyncio
    loop = asyncio.get_event_loop()  # ← これがエラーの原因
    if loop.is_running():
        interviewer_response = self.interviewer.process_message(...)
```

**修正後**:
```python
if attachments and len(attachments) > 0:
    # 添付ファイル情報をメッセージに追加
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

#### 2. main.py の修正

添付ファイルがある場合、非同期処理可能なコンテキストで直接 `interviewer.process_with_files_and_urls()` を呼び出すように変更しました。

**修正前** (lines 213-221):
```python
if orchestrator:
    response = await asyncio.to_thread(
        orchestrator.route_message,
        user_input, 
        str(message.channel.id),
        attachments=message.attachments if message.attachments else None
    )
```

**修正後**:
```python
if orchestrator:
    # 添付ファイルがある場合は非同期メソッドを直接呼び出し
    if message.attachments:
        try:
            response = await orchestrator.interviewer.process_with_files_and_urls(
                user_input,
                str(message.channel.id),
                attachments=message.attachments
            )
        except Exception as e:
            logging.error(f"File processing error: {e}", exc_info=True)
            # フォールバック：通常のメッセージ処理
            response = await asyncio.to_thread(
                orchestrator.route_message,
                user_input + f"\n\n(添付ファイル: {len(message.attachments)}件 - 処理エラー)", 
                str(message.channel.id)
            )
    else:
        # 添付ファイルなし - 通常の同期ルーティング
        response = await asyncio.to_thread(
            orchestrator.route_message,
            user_input, 
            str(message.channel.id)
        )
```

### 修正後の処理フロー

```
Discord メッセージ受信 (main.py)
    ↓
添付ファイルあり？
    ↓ YES
    interviewer.process_with_files_and_urls() (非同期メソッド)
    → 非同期コンテキストで file_processor.process_discord_attachments() を実行
    → Gemini APIでファイル分析
    → インタビュー質問を生成
    ↓ NO
    asyncio.to_thread() → orchestrator.route_message()
    → 通常のルーティング処理
```

## テスト方法

1. Discordチャンネルで Shadow Director をメンション
2. PowerPointファイル、PDFファイル、または画像を添付して送信
3. エラーが発生せず、ファイル内容が分析されて応答が返ることを確認

## 関連ファイル

- `main.py` (lines 210-241): Discord メッセージハンドリング
- `src/agents/orchestrator.py` (lines 507-527): メッセージルーティング
- `src/agents/interviewer.py` (lines 108-247): ファイル処理とインタビュー
- `src/tools/file_processor.py`: 添付ファイル処理ユーティリティ

## 技術的な教訓

### asyncio.get_event_loop() の落とし穴

- `asyncio.get_event_loop()` は、現在のスレッドにイベントループが存在しない場合にエラーを発生させます
- `asyncio.to_thread()` で実行されるワーカースレッドには、デフォルトでイベントループが存在しません
- 非同期処理が必要な場合は、`asyncio.to_thread()` を使わず、直接 `await` で呼び出すべきです

### 設計原則

1. **非同期メソッドは非同期コンテキストから呼び出す**: `process_with_files_and_urls()` のような非同期メソッドは、非同期関数内で直接 `await` すべき
2. **同期メソッドはスレッドプールで実行**: `route_message()` のような同期メソッドは `asyncio.to_thread()` で実行可能
3. **混在させない**: 同期メソッド内から `asyncio.get_event_loop()` を呼び出さない

## 影響範囲

- ✅ PowerPoint、PDF、画像などの添付ファイル処理が正常動作
- ✅ エラーログが出力されなくなる
- ✅ ユーザーエクスペリエンスの向上
- ⚠️ 添付ファイルがある場合のルーティングロジックが変更（orchestrator経由ではなく、直接interviewer呼び出し）

## セキュリティ確認

- ✅ ハードコーディングは避けています
- ✅ 環境変数からの設定読み込みを継続使用
- ✅ エラーハンドリングを強化（try-except追加）
