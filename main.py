import os
import discord
from discord.ext import tasks
from dotenv import load_dotenv
from src.agents.orchestrator import Orchestrator
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import logging
import asyncio

# Configure logging
logging.basicConfig(level=logging.INFO)

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

# Global task variable to prevent duplicate scheduled_observation tasks
scheduled_observation_task = None

@tasks.loop(hours=168)
async def scheduled_observation():
    """
    Runs weekly (168 hours) to check for new funding opportunities.
    """
    global orchestrator
    if not orchestrator:
         logging.warning("Orchestrator not ready yet. Skipping observation.")
         return

    logging.info("Running scheduled observation task...")
    try:
        notifications = orchestrator.run_periodic_checks()
        
        for user_id, message in notifications:
            try:
                user = await client.fetch_user(int(user_id))
                if user:
                    await user.send(f"**[Autonomous Funding Watch]**\n新しい助成金情報が見つかりました。\n\n{message}")
            except Exception as e:
                logging.error(f"Failed to send notification to user {user_id}: {e}")
    except Exception as e:
        logging.error(f"Error in scheduled_observation: {e}")

@client.event
async def on_ready():
    global scheduled_observation_task
    
    logging.info(f'We have logged in as {client.user}')
    
    # Prevent duplicate task execution on reconnection
    # Only start if task is None or already done
    if scheduled_observation_task is None or scheduled_observation_task.done():
        logging.info("Starting scheduled_observation task...")
        if not scheduled_observation.is_running():
            scheduled_observation.start()
        scheduled_observation_task = asyncio.create_task(asyncio.sleep(0))  # Placeholder task
    else:
        logging.info("scheduled_observation task is already running, skipping duplicate start")

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
            # Check if message has attachments or URLs first (before typing indicator)
            has_attachments = len(message.attachments) > 0
            has_urls = 'http://' in user_input or 'https://' in user_input
            
            # Send progress message for file/URL processing
            progress_msg = None
            if has_attachments or has_urls:
                status_parts = []
                if has_attachments:
                    status_parts.append(f"📄 {len(message.attachments)}件のファイル")
                if has_urls:
                    import re
                    url_count = len(re.findall(r'https?://[^\s<>"{}|\\^`\[\]]+', user_input))
                    status_parts.append(f"🔗 {url_count}件のURL")
                
                progress_text = " と ".join(status_parts) + " を分析中..."
                progress_msg = await message.channel.send(f"⏳ {progress_text}")
                logging.info(f"Processing files/URLs for channel {message.channel.id}: {status_parts}")
            
            # Show typing indicator
            async with message.channel.typing():
                if orchestrator:
                    if has_attachments or has_urls:
                        # Use file/URL processing method
                        response = await orchestrator.interviewer.process_with_files_and_urls(
                            user_input, 
                            str(message.channel.id),
                            attachments=message.attachments if has_attachments else None
                        )
                    else:
                        # Normal text-only processing
                        response = orchestrator.route_message(user_input, str(message.channel.id))
                else:
                    response = "System initializing... Please wait."
            
            # Delete progress message after processing
            if progress_msg:
                try:
                    await progress_msg.delete()
                except:
                    pass  # Ignore if already deleted
            
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
