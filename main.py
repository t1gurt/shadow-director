import os
import discord
from discord.ext import tasks
from dotenv import load_dotenv
from src.agents.orchestrator import Orchestrator
from src.version import __version__, __update_date__
from src.utils.progress_notifier import set_progress_callback, get_progress_notifier
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import logging
import asyncio

# Configure logging
logging.basicConfig(level=logging.INFO)

# Log version information at startup
logging.info("=" * 60)
logging.info(f"Shadow Director Bot - Version {__version__}")
logging.info(f"Last Updated: {__update_date__}")
logging.info("=" * 60)

# Load environment variables
load_dotenv()

TOKEN = os.getenv('DISCORD_BOT_TOKEN')

# --- Cloud Run Health Check Server ---
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")
    
    def log_message(self, format, *args):
        # Suppress logging for health checks to keep logs clean
        pass

def start_health_check_server():
    try:
        port = int(os.environ.get("PORT", 8080))
        server = HTTPServer(('0.0.0.0', port), HealthCheckHandler)
        logging.info(f"Health check server listening on port {port}")
        server.serve_forever()
    except Exception as e:
        logging.error(f"Health Check Server Failed: {e}")
# -------------------------------------

# Initialize Discord Client (Global)
intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)

# Orchestrator will be initialized lazily or in main
orchestrator = None

import datetime

# ... (imports) ...

# Global task variable to prevent duplicate tasks
scheduled_observation_task = None
scheduled_monthly_task = None

@tasks.loop(hours=168)
async def scheduled_observation():
    """
    Runs weekly (168 hours) to check for new funding opportunities.
    """
    # ... (existing code) ...

# Run everyday at 9:00 AM (assuming JST or system time)
@tasks.loop(time=datetime.time(hour=9, minute=0))
async def scheduled_monthly_summary():
    """
    Runs daily at 9:00 AM, but only executes logic on the 1st of the month.
    """
    global orchestrator
    if not orchestrator:
         logging.warning("Orchestrator not ready yet. Skipping monthly summary.")
         return

    now = datetime.datetime.now()
    # Check if it's the 1st day of the month
    if now.day != 1:
        return

    logging.info("It's the 1st of the month! Running monthly summary task...")
    try:
        # Run potentially long-running task in a separate thread to avoid blocking main loop
        notifications = await asyncio.to_thread(orchestrator.run_monthly_tasks)
        
        for user_id, message in notifications:
            try:
                user = await client.fetch_user(int(user_id))
                if user:
                    await user.send(message)
            except Exception as e:
                logging.error(f"Failed to send monthly summary to user {user_id}: {e}")
    except Exception as e:
        logging.error(f"Error in scheduled_monthly_summary: {e}")

@client.event
async def on_ready():
    global scheduled_observation_task, scheduled_monthly_task
    
    logging.info(f'We have logged in as {client.user}')
    logging.info(f'Bot Version: {__version__} (Updated: {__update_date__})')
    
    # Start Weekly Observation Task
    if scheduled_observation_task is None or scheduled_observation_task.done():
        logging.info("Starting scheduled_observation task...")
        if not scheduled_observation.is_running():
            scheduled_observation.start()
        scheduled_observation_task = asyncio.create_task(asyncio.sleep(0))
    
    # Start Monthly Summary Task
    if scheduled_monthly_task is None or scheduled_monthly_task.done():
        logging.info("Starting scheduled_monthly_summary task...")
        if not scheduled_monthly_summary.is_running():
            scheduled_monthly_summary.start()
        scheduled_monthly_task = asyncio.create_task(asyncio.sleep(0))

@client.event
async def on_guild_channel_create(channel):
    """
    Send a welcome message when a new text channel is created.
    """
    # Only respond to text channels
    if not isinstance(channel, discord.TextChannel):
        return
    
    welcome_message = """👋 **NPO-SoulSync AgentのShadow Directorです！**

はじめまして。私はNPOの資金調達を支援するAIエージェントです。

**まず最初に、以下の資料を共有していただけますか？**
📄 団体の定款
🌐 ホームページのURL
📋 活動概要がわかる資料

これらの情報をもとに、貴団体に最適な助成金や資金調達の機会を見つけるお手伝いをします。

**使い方:**
`@Shadow Director メッセージ` の形式でメンションしてください。
例: `@Shadow Director こんにちは`

よろしくお願いします！"""
    
    try:
        await channel.send(welcome_message)
    except Exception as e:
        logging.error(f"Error sending welcome message: {e}")

@client.event
async def on_message(message):
    global orchestrator
    
    # Ignore messages from the bot itself
    if message.author == client.user:
        return
    
    # Only respond when the bot is mentioned
    if client.user not in message.mentions:
        return
    
    # Deduplication: Check if we're already processing this message
    # Use a simple in-memory cache with message ID
    if not hasattr(on_message, 'processing'):
        on_message.processing = set()
    
    if message.id in on_message.processing:
        logging.info(f"[DEDUP] Message {message.id} is already being processed, skipping")
        return
    
    # Mark as processing
    on_message.processing.add(message.id)
    
    try:
        # Remove the mention from the message content
        user_input = message.content.replace(f'<@{client.user.id}>', '').replace(f'<@!{client.user.id}>', '').strip()
        
        # Ignore empty messages after removing mention
        if not user_input and not message.attachments:
            return
        
        try:
            # Set up progress notification callback for this channel
            # Capture the current event loop (main thread loop)
            loop = asyncio.get_running_loop()
            
            async def send_progress(msg: str):
                try:
                    await message.channel.send(msg)
                except Exception as e:
                    logging.error(f"[PROGRESS] Failed to send progress: {e}")
            
            # Create a wrapper that can be called from sync code (running in other threads)
            def progress_callback(msg: str):
                # Schedule the async send in the main event loop
                try:
                    # Use the captured loop to schedule the task safely from another thread
                    loop.call_soon_threadsafe(
                        lambda: loop.create_task(send_progress(msg))
                    )
                except Exception as e:
                    logging.error(f"[PROGRESS] Callback error: {e}")
            
            # Set the global progress callback
            set_progress_callback(progress_callback)
            
            # Show typing indicator
            async with message.channel.typing():
                if orchestrator:
                    # Handle file attachments in async context
                    if message.attachments:
                        # Call interviewer's async file processing method directly
                        # This avoids the asyncio event loop error from threading
                        try:
                            response = await orchestrator.interviewer.process_with_files_and_urls(
                                user_input,
                                str(message.channel.id),
                                attachments=message.attachments
                            )
                        except ValueError as e:
                            # MIMEタイプエラー - サポート外のファイル形式
                            logging.error(f"Unsupported file format: {e}", exc_info=True)
                            
                            # Extract filenames from error message or attachments
                            unsupported_files = [att.filename for att in message.attachments]
                            
                            error_response = f"⚠️ **サポートされていないファイル形式が含まれています**\n\n"
                            error_response += f"**送信されたファイル**: {', '.join([f'`{f}`' for f in unsupported_files])}\n\n"
                            error_response += f"**エラー詳細**:\n{str(e)}\n\n"
                            error_response += "---\n\n"
                            error_response += "**📋 サポートされているファイル形式**:\n\n"
                            error_response += "**ドキュメント**: PDF, TXT, MD, HTML, CSS, JS, Python, JSON, XML, CSV\n"
                            error_response += "**画像**: JPEG, PNG, WebP, GIF, HEIC, HEIF\n"
                            error_response += "**音声**: WAV, MP3, AIFF, AAC, OGG, FLAC\n"
                            error_response += "**動画**: MP4, MPEG, MOV, AVI, FLV, WebM, WMV, 3GPP\n\n"
                            error_response += "---\n\n"
                            error_response += "**💡 解決方法**:\n\n"
                            error_response += "1. **PowerPoint (.pptx) の場合** → PDFに変換してから送信\n"
                            error_response += "2. **Word (.docx) の場合** → PDFに変換してから送信\n"
                            error_response += "3. **Excel (.xlsx) の場合** → PDFまたはCSVに変換してから送信\n"
                            error_response += "4. **資料の内容を直接テキストで教えていただく** こともできます\n\n"
                            error_response += "お手数ですが、上記の形式に変換してから再度お試しください。"
                            
                            await message.channel.send(error_response)
                            return
                        except Exception as e:
                            # その他のエラー
                            logging.error(f"File processing error: {e}", exc_info=True)
                            
                            error_response = f"⚠️ **ファイルの処理中にエラーが発生しました**\n\n"
                            error_response += f"**エラー内容**: {str(e)}\n\n"
                            error_response += "---\n\n"
                            error_response += "**💡 以下の方法をお試しください**:\n\n"
                            error_response += "1. ファイルサイズが大きすぎる場合は、小さくしてから再送信\n"
                            error_response += "2. ファイルが破損していないか確認\n"
                            error_response += "3. サポートされている形式（PDF、画像など）に変換\n"
                            error_response += "4. 資料の内容を直接テキストで教えていただく\n\n"
                            error_response += "もし問題が解決しない場合は、通常の対話形式で情報を教えていただけますか？"
                            
                            await message.channel.send(error_response)
                            return
                    else:
                        # No attachments - use normal synchronous routing
                        response = await asyncio.to_thread(
                            orchestrator.route_message,
                            user_input, 
                            str(message.channel.id)
                        )
                else:
                    response = "System initializing... Please wait."
            
            # Check for image marker (for slide images)
            if "[IMAGE_NEEDED:" in response:
                import re
                import io
                
                # Extract ALL image markers
                image_matches = re.findall(r'\[IMAGE_NEEDED:([^:]+):([^\]]+)\]', response)
                
                if image_matches:
                    logging.info(f"[IMAGE] Found {len(image_matches)} image markers")
                    
                    # Remove all image markers from response
                    for match in re.finditer(r'\[IMAGE_NEEDED:([^:]+):([^\]]+)\]', response):
                        response = response.replace(match.group(0), '').strip()
                    
                    # Process each image
                    for user_id, filename in image_matches:
                        try:
                            logging.info(f"[IMAGE] Processing: User={user_id}, File={filename}")
                            
                            # Get image from SlideGenerator
                            image_bytes = orchestrator.slide_generator.get_slide(user_id, filename)
                            
                            if image_bytes:
                                logging.info(f"[IMAGE] Image size: {len(image_bytes)} bytes")
                                
                                # Create file from image bytes
                                file_bytes = io.BytesIO(image_bytes)
                                discord_file = discord.File(file_bytes, filename=filename)
                                await message.channel.send(file=discord_file)
                                logging.info(f"[IMAGE] Image sent: {filename}")
                            else:
                                logging.error(f"[IMAGE] Image not found: {filename}")
                        except Exception as e:
                            logging.error(f"[IMAGE] Error processing {filename}: {e}", exc_info=True)
            
            # Check for format file marker (for application format files)
            if "[FORMAT_FILE_NEEDED:" in response:
                import re
                import io
                import os
                
                # Extract ALL format file markers
                format_file_matches = re.findall(r'\[FORMAT_FILE_NEEDED:([^:]+):([^\]]+)\]', response)
                
                if format_file_matches:
                    logging.info(f"[FORMAT_FILE] Found {len(format_file_matches)} format file markers")
                    
                    # Remove all markers from response
                    for match in re.finditer(r'\[FORMAT_FILE_NEEDED:([^:]+):([^\]]+)\]', response):
                        response = response.replace(match.group(0), '').strip()
                    
                    # Process each format file
                    for user_id, file_path in format_file_matches:
                        try:
                            logging.info(f"[FORMAT_FILE] Processing: User={user_id}, Path={file_path}")
                            
                            # Check if file exists and send
                            if os.path.exists(file_path):
                                file_size = os.path.getsize(file_path)
                                logging.info(f"[FORMAT_FILE] File size: {file_size} bytes")
                                
                                # Check Discord limit (25MB)
                                if file_size > 25 * 1024 * 1024:
                                    await message.channel.send(f"⚠️ フォーマットファイルが大きすぎます ({file_size / 1024 / 1024:.1f}MB)")
                                    # Delete oversized file
                                    try:
                                        os.remove(file_path)
                                        logging.info(f"[FORMAT_FILE] Deleted oversized file: {file_path}")
                                    except Exception as del_err:
                                        logging.error(f"[FORMAT_FILE] Failed to delete oversized file: {del_err}")
                                else:
                                    filename = os.path.basename(file_path)
                                    discord_file = discord.File(file_path, filename=filename)
                                    await message.channel.send(file=discord_file)
                                    logging.info(f"[FORMAT_FILE] File sent: {filename}")
                                    
                                    # Delete file after successful send
                                    try:
                                        os.remove(file_path)
                                        logging.info(f"[FORMAT_FILE] Deleted file after send: {file_path}")
                                    except Exception as del_err:
                                        logging.error(f"[FORMAT_FILE] Failed to delete file after send: {del_err}")
                                    
                            else:
                                logging.error(f"[FORMAT_FILE] File not found: {file_path}")
                                await message.channel.send(f"⚠️ フォーマットファイルが見つかりませんでした")
                        except Exception as e:
                            logging.error(f"[FORMAT_FILE] Error processing {file_path}: {e}", exc_info=True)
                            await message.channel.send(f"⚠️ フォーマットファイル送信エラー: {e}")
                            # Try to clean up file even on error
                            try:
                                if os.path.exists(file_path):
                                    os.remove(file_path)
                                    logging.info(f"[FORMAT_FILE] Cleaned up file after error: {file_path}")
                            except Exception as del_err:
                                logging.error(f"[FORMAT_FILE] Failed to clean up file after error: {del_err}")
            
            # Check for filled file marker (for auto-filled application format files)
            if "[FILLED_FILE_NEEDED:" in response:
                import re
                import io
                import os
                
                # Extract ALL filled file markers
                filled_file_matches = re.findall(r'\[FILLED_FILE_NEEDED:([^:]+):([^\]]+)\]', response)
                
                if filled_file_matches:
                    logging.info(f"[FILLED_FILE] Found {len(filled_file_matches)} filled file markers")
                    
                    # Remove all markers from response
                    for match in re.finditer(r'\[FILLED_FILE_NEEDED:([^:]+):([^\]]+)\]', response):
                        response = response.replace(match.group(0), '').strip()
                    
                    # Process each filled file
                    for user_id, file_path in filled_file_matches:
                        try:
                            logging.info(f"[FILLED_FILE] Processing: User={user_id}, Path={file_path}")
                            
                            # Check if file exists and send
                            if os.path.exists(file_path):
                                file_size = os.path.getsize(file_path)
                                logging.info(f"[FILLED_FILE] File size: {file_size} bytes")
                                
                                # Check Discord limit (25MB)
                                if file_size > 25 * 1024 * 1024:
                                    await message.channel.send(f"⚠️ 記入済みファイルが大きすぎます ({file_size / 1024 / 1024:.1f}MB)")
                                    try:
                                        os.remove(file_path)
                                        logging.info(f"[FILLED_FILE] Deleted oversized file: {file_path}")
                                    except Exception as del_err:
                                        logging.error(f"[FILLED_FILE] Failed to delete oversized file: {del_err}")
                                else:
                                    filename = os.path.basename(file_path)
                                    discord_file = discord.File(file_path, filename=filename)
                                    await message.channel.send(f"📋 **記入済み**: `{filename}`", file=discord_file)
                                    logging.info(f"[FILLED_FILE] File sent: {filename}")
                                    
                                    # Delete file after successful send
                                    try:
                                        os.remove(file_path)
                                        logging.info(f"[FILLED_FILE] Deleted file after send: {file_path}")
                                    except Exception as del_err:
                                        logging.error(f"[FILLED_FILE] Failed to delete file after send: {del_err}")
                                    
                            else:
                                logging.error(f"[FILLED_FILE] File not found: {file_path}")
                                await message.channel.send(f"⚠️ 記入済みファイルが見つかりませんでした")
                        except Exception as e:
                            logging.error(f"[FILLED_FILE] Error processing {file_path}: {e}", exc_info=True)
                            await message.channel.send(f"⚠️ 記入済みファイル送信エラー: {e}")
            
            # Check for attachment marker (for draft viewing)
            if "[ATTACHMENT_NEEDED:" in response:
                import re
                import io
                
                # Extract ALL marker info (for multiple drafts)
                matches = re.findall(r'\[ATTACHMENT_NEEDED:([^:]+):([^\]]+)\]', response)
                
                if matches:
                    logging.info(f"[ATTACHMENT] Found {len(matches)} attachment markers")
                    
                    # Remove all markers from response
                    for match in re.finditer(r'\[ATTACHMENT_NEEDED:([^:]+):([^\]]+)\]', response):
                        response = response.replace(match.group(0), '').strip()
                    
                    # Ensure response is within Discord's 2000 char limit
                    MAX_LENGTH = 2000
                    if len(response) > MAX_LENGTH:
                        response = response[:MAX_LENGTH - 50] + "\n\n...(省略)..."
                    
                    # Send response text first
                    await message.channel.send(response)
                    
                    # Process each attachment
                    for user_id, filename_hint in matches:
                        try:
                            logging.info(f"[ATTACHMENT] Processing: User={user_id}, Hint={filename_hint}")
                            
                            draft_content = None
                            filename = filename_hint
                            
                            if filename_hint == "latest":
                                _, draft_content = orchestrator.drafter.get_latest_draft(user_id)
                                # Get actual filename
                                drafts = orchestrator.drafter.docs_tool.list_drafts(user_id)
                                if drafts:
                                    filename = sorted(drafts)[-1]
                                else:
                                    filename = "draft.md"
                                logging.info(f"[ATTACHMENT] Latest draft: {filename}")
                            else:
                                draft_content = orchestrator.drafter.docs_tool.get_draft(user_id, filename)
                                logging.info(f"[ATTACHMENT] Specific draft: {filename}")
                            
                            if draft_content:
                                logging.info(f"[ATTACHMENT] Content length: {len(draft_content)} chars")
                                
                                # Create file from string content
                                file_bytes = io.BytesIO(draft_content.encode('utf-8'))
                                discord_file = discord.File(file_bytes, filename=filename)
                                await message.channel.send(file=discord_file)
                                logging.info(f"[ATTACHMENT] File sent: {filename}")
                            else:
                                logging.error(f"[ATTACHMENT] No content found for {filename}")
                                await message.channel.send(f"⚠️ `{filename}` の内容が取得できませんでした。")
                        except Exception as e:
                            logging.error(f"[ATTACHMENT] Error processing {filename_hint}: {e}", exc_info=True)
                            await message.channel.send(f"⚠️ ファイル添付エラー ({filename_hint}): {e}")
                    
                    return
            
            # File attachment logic for drafts (legacy)
            if "Draft created successfully at:" in response:
                 lines = response.split('\n')
                 file_path = ""
                 for line in lines:
                     if "Draft created successfully at:" in line:
                         file_path = line.replace("Draft created successfully at:", "").strip()
                         break
                 
                 if file_path and os.path.exists(file_path):
                     file_to_send = discord.File(file_path)
                     await message.channel.send(response, file=file_to_send)
                     return

            # Check for DRAFT_PENDING marker (for sequential draft processing)
            draft_pending_data = None
            if "[DRAFT_PENDING:" in response:
                import re
                import json
                import base64
                
                # Extract marker info (Base64 encoded JSON)
                match = re.search(r'\[DRAFT_PENDING:([^:]+):([A-Za-z0-9+/=]+)\]', response)
                if match:
                    pending_user_id = match.group(1)
                    matches_b64 = match.group(2)
                    logging.info(f"[DRAFT_PENDING] Found marker for user {pending_user_id}")
                    
                    # Remove marker from response
                    response = response.replace(match.group(0), '').strip()
                    
                    # Decode Base64 and parse JSON
                    try:
                        matches_json = base64.b64decode(matches_b64).decode('utf-8')
                        draft_pending_data = {
                            'user_id': pending_user_id,
                            'strong_matches': json.loads(matches_json)
                        }
                        logging.info(f"[DRAFT_PENDING] Parsed {len(draft_pending_data['strong_matches'])} matches")
                    except (json.JSONDecodeError, base64.binascii.Error, UnicodeDecodeError) as e:
                        logging.error(f"[DRAFT_PENDING] Failed to parse matches data: {e}")
            
            # Handle long messages (Discord 2000 char limit)
            MAX_LENGTH = 2000
            if len(response) > MAX_LENGTH:
                # Split into chunks
                chunks = []
                while response:
                    if len(response) <= MAX_LENGTH:
                        chunks.append(response)
                        break
                    # Find a good break point (newline or space)
                    split_pos = response.rfind('\n', 0, MAX_LENGTH)
                    if split_pos == -1:
                        split_pos = response.rfind(' ', 0, MAX_LENGTH)
                    if split_pos == -1:
                        split_pos = MAX_LENGTH
                    
                    chunks.append(response[:split_pos])
                    response = response[split_pos:].lstrip()
                
                # Send chunks
                for i, chunk in enumerate(chunks):
                    if i == 0:
                        await message.channel.send(chunk)
                    else:
                        await message.channel.send(f"(...続き {i+1}/{len(chunks)})\n{chunk}")
            else:
                await message.channel.send(response)
            
            # Process pending drafts AFTER report and slides are sent
            if draft_pending_data and orchestrator:
                logging.info(f"[DRAFT_PENDING] Starting async draft processing")
                
                # Define progress callback that handles file markers
                async def progress_callback(msg):
                    """Async callback to send messages and process file markers during draft processing."""
                    import re
                    import io
                    
                    if not msg:
                        return
                    
                    # Process FORMAT_FILE_NEEDED markers
                    if "[FORMAT_FILE_NEEDED:" in msg:
                        format_matches = re.findall(r'\[FORMAT_FILE_NEEDED:([^:]+):([^\]]+)\]', msg)
                        for uid, file_path in format_matches:
                            msg = msg.replace(f"[FORMAT_FILE_NEEDED:{uid}:{file_path}]", '').strip()
                            try:
                                if os.path.exists(file_path):
                                    file_size = os.path.getsize(file_path)
                                    if file_size <= 25 * 1024 * 1024:
                                        filename = os.path.basename(file_path)
                                        discord_file = discord.File(file_path, filename=filename)
                                        await message.channel.send(file=discord_file)
                                        logging.info(f"[PROGRESS_CB] Sent format file: {filename}")
                                        try:
                                            os.remove(file_path)
                                        except:
                                            pass
                            except Exception as e:
                                logging.error(f"[PROGRESS_CB] Format file error: {e}")
                    
                    # Process ATTACHMENT_NEEDED markers
                    if "[ATTACHMENT_NEEDED:" in msg:
                        attachment_matches = re.findall(r'\[ATTACHMENT_NEEDED:([^:]+):([^\]]+)\]', msg)
                        for uid, filename_hint in attachment_matches:
                            msg = msg.replace(f"[ATTACHMENT_NEEDED:{uid}:{filename_hint}]", '').strip()
                            try:
                                draft_content = None
                                if filename_hint == "latest":
                                    _, draft_content = orchestrator.drafter.get_latest_draft(uid)
                                    drafts = orchestrator.drafter.docs_tool.list_drafts(uid)
                                    filename = sorted(drafts)[-1] if drafts else "draft.md"
                                else:
                                    draft_content = orchestrator.drafter.docs_tool.get_draft(uid, filename_hint)
                                    filename = filename_hint
                                
                                if draft_content:
                                    file_bytes = io.BytesIO(draft_content.encode('utf-8'))
                                    discord_file = discord.File(file_bytes, filename=filename)
                                    await message.channel.send(file=discord_file)
                                    logging.info(f"[PROGRESS_CB] Sent draft file: {filename}")
                            except Exception as e:
                                logging.error(f"[PROGRESS_CB] Attachment error: {e}")
                    
                    # Send remaining text (handle Discord 2000 char limit)
                    if msg.strip():
                        MAX_LEN = 2000
                        if len(msg) > MAX_LEN:
                            chunks = []
                            while msg:
                                if len(msg) <= MAX_LEN:
                                    chunks.append(msg)
                                    break
                                split_pos = msg.rfind('\n', 0, MAX_LEN)
                                if split_pos == -1:
                                    split_pos = msg.rfind(' ', 0, MAX_LEN)
                                if split_pos == -1:
                                    split_pos = MAX_LEN
                                chunks.append(msg[:split_pos])
                                msg = msg[split_pos:].lstrip()
                            for chunk in chunks:
                                await message.channel.send(chunk)
                        else:
                            await message.channel.send(msg)
                
                try:
                    # Run draft processing in a separate thread
                    # Pass None as callback to accumulate all results in return value
                    # This ensures file markers are properly processed after the function returns
                    draft_result = await asyncio.to_thread(
                        orchestrator._process_top_match_drafts,
                        draft_pending_data['user_id'],
                        draft_pending_data['strong_matches'],
                        None  # Don't use async callback from sync thread - process results after return
                    )
                    
                    # Process any markers in draft result (images, attachments, etc.)
                    if draft_result:
                        # Handle FORMAT_FILE_NEEDED markers
                        if "[FORMAT_FILE_NEEDED:" in draft_result:
                            import re
                            import io
                            
                            format_file_matches = re.findall(r'\[FORMAT_FILE_NEEDED:([^:]+):([^\]]+)\]', draft_result)
                            for user_id_f, file_path in format_file_matches:
                                draft_result = draft_result.replace(f"[FORMAT_FILE_NEEDED:{user_id_f}:{file_path}]", '').strip()
                                try:
                                    if os.path.exists(file_path):
                                        file_size = os.path.getsize(file_path)
                                        if file_size <= 25 * 1024 * 1024:
                                            filename = os.path.basename(file_path)
                                            discord_file = discord.File(file_path, filename=filename)
                                            await message.channel.send(file=discord_file)
                                            try:
                                                os.remove(file_path)
                                            except:
                                                pass
                                except Exception as e:
                                    logging.error(f"[DRAFT_PENDING] Format file error: {e}")
                        
                        # Handle FILLED_FILE_NEEDED markers
                        if "[FILLED_FILE_NEEDED:" in draft_result:
                            import re
                            
                            filled_file_matches = re.findall(r'\[FILLED_FILE_NEEDED:([^:]+):([^\]]+)\]', draft_result)
                            for user_id_filled, file_path in filled_file_matches:
                                draft_result = draft_result.replace(f"[FILLED_FILE_NEEDED:{user_id_filled}:{file_path}]", '').strip()
                                try:
                                    if os.path.exists(file_path):
                                        file_size = os.path.getsize(file_path)
                                        if file_size <= 25 * 1024 * 1024:
                                            filename = os.path.basename(file_path)
                                            discord_file = discord.File(file_path, filename=filename)
                                            await message.channel.send(f"📋 **記入済み**: `{filename}`", file=discord_file)
                                            try:
                                                os.remove(file_path)
                                            except:
                                                pass
                                except Exception as e:
                                    logging.error(f"[DRAFT_PENDING] Filled file error: {e}")
                        
                        # Handle ATTACHMENT_NEEDED markers
                        if "[ATTACHMENT_NEEDED:" in draft_result:
                            import re
                            import io
                            
                            attachment_matches = re.findall(r'\[ATTACHMENT_NEEDED:([^:]+):([^\]]+)\]', draft_result)
                            for user_id_a, filename_hint in attachment_matches:
                                draft_result = draft_result.replace(f"[ATTACHMENT_NEEDED:{user_id_a}:{filename_hint}]", '').strip()
                                try:
                                    draft_content = None
                                    if filename_hint == "latest":
                                        _, draft_content = orchestrator.drafter.get_latest_draft(user_id_a)
                                        drafts = orchestrator.drafter.docs_tool.list_drafts(user_id_a)
                                        filename = sorted(drafts)[-1] if drafts else "draft.md"
                                    else:
                                        draft_content = orchestrator.drafter.docs_tool.get_draft(user_id_a, filename_hint)
                                        filename = filename_hint
                                    
                                    if draft_content:
                                        file_bytes = io.BytesIO(draft_content.encode('utf-8'))
                                        discord_file = discord.File(file_bytes, filename=filename)
                                        await message.channel.send(file=discord_file)
                                except Exception as e:
                                    logging.error(f"[DRAFT_PENDING] Attachment error: {e}")
                        
                        # Send remaining text if any
                        if draft_result.strip():
                            MAX_LENGTH = 2000
                            if len(draft_result) > MAX_LENGTH:
                                chunks = []
                                temp = draft_result
                                while temp:
                                    if len(temp) <= MAX_LENGTH:
                                        chunks.append(temp)
                                        break
                                    split_pos = temp.rfind('\n', 0, MAX_LENGTH)
                                    if split_pos == -1:
                                        split_pos = temp.rfind(' ', 0, MAX_LENGTH)
                                    if split_pos == -1:
                                        split_pos = MAX_LENGTH
                                    chunks.append(temp[:split_pos])
                                    temp = temp[split_pos:].lstrip()
                                for chunk in chunks:
                                    await message.channel.send(chunk)
                            else:
                                await message.channel.send(draft_result)
                                
                except Exception as e:
                    logging.error(f"[DRAFT_PENDING] Draft processing failed: {e}", exc_info=True)
                    await message.channel.send(f"⚠️ ドラフト処理中にエラーが発生しました: {e}")
                
        except Exception as e:
            logging.error(f"Error processing message: {e}")
            await message.channel.send("申し訳ありません、エラーが発生しました。")
    finally:
        # Clean up processing set
        if message.id in on_message.processing:
            on_message.processing.remove(message.id)
            logging.info(f"[DEDUP] Cleaned up message {message.id} from processing set")

def main():
    global orchestrator
    
    # 1. Start Health Check Server FIRST (Separate Thread)
    # This ensures Cloud Run sees the port open regardless of other failures
    thread = threading.Thread(target=start_health_check_server, daemon=True)
    thread.start()
    logging.info("Main thread: Started health check thread.")

    if not TOKEN:
        logging.error("Error: DISCORD_BOT_TOKEN not found in environment variables.")
        # But we keep running to satisfy Health Check
    else:
        # 2. Initialize Orchestrator (Safe Init)
        try:
            logging.info("Initializing Orchestrator...")
            orchestrator = Orchestrator()
            logging.info("Orchestrator initialized successfully.")
        except Exception as e:
            logging.critical(f"Failed to initialize Orchestrator: {e}")
            # Do NOT exit. Container keeps running.
        
        # 3. Run Discord Client (Blocking)
        try:
            logging.info("Starting Discord Client...")
            client.run(TOKEN)
        except Exception as e:
            logging.critical(f"Discord Client crash: {e}")
            # If client crashes, we exit main, daemon thread dies, container dies.
            # This is correct behavior for a bot crash.

if __name__ == "__main__":
    main()
