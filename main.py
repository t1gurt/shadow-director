import os
import discord
from discord.ext import tasks
from dotenv import load_dotenv
from src.agents.orchestrator import Orchestrator
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import logging

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
    logging.info(f'We have logged in as {client.user}')
    if not scheduled_observation.is_running():
        scheduled_observation.start()

@client.event
async def on_message(message):
    global orchestrator
    if message.author == client.user:
        return

    user_input = message.content
    try:
        # Show typing indicator
        async with message.channel.typing():
            if orchestrator:
                # Use channel.id instead of author.id to isolate sessions per channel
                response = orchestrator.route_message(user_input, str(message.channel.id))
            else:
                response = "System initializing... Please wait."
        
        # File attachment logic
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

        await message.channel.send(response)
    except Exception as e:
        logging.error(f"Error processing message: {e}")
        await message.channel.send("申し訳ありません、エラーが発生しました。")

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
