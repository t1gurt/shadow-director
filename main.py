import os
import discord
from discord.ext import tasks
from dotenv import load_dotenv
from src.agents.orchestrator import Orchestrator

# Load environment variables
load_dotenv()

TOKEN = os.getenv('DISCORD_BOT_TOKEN')

# Initialize Discord Client
intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)

# Initialize Orchestrator
orchestrator = Orchestrator()

@tasks.loop(hours=168)
async def scheduled_observation():
    """
    Runs weekly (168 hours) to check for new funding opportunities.
    """
    print("Running scheduled observation task...")
    notifications = orchestrator.run_periodic_checks()
    
    for user_id, message in notifications:
        try:
            user = await client.fetch_user(int(user_id))
            if user:
                await user.send(f"**[Autonomous Funding Watch]**\n新しい助成金情報が見つかりました。\n\n{message}")
        except Exception as e:
            print(f"Failed to send notification to user {user_id}: {e}")

@client.event
async def on_ready():
    print(f'We have logged in as {client.user}')
    if not scheduled_observation.is_running():
        scheduled_observation.start()

@client.event
async def on_message(message):
    if message.author == client.user:
        return

    # In a real bot, we might filter by channel or mention
    # if client.user in message.mentions: ...
    
    user_input = message.content
    try:
        response = orchestrator.route_message(user_input, str(message.author.id))
        await message.channel.send(response)
    except Exception as e:
        print(f"Error processing message: {e}")
        await message.channel.send("申し訳ありません、エラーが発生しました。")

def main():
    if not TOKEN:
        print("Error: DISCORD_BOT_TOKEN not found in environment variables.")
        print("Please create a .env file or set the variable.")
        return

    client.run(TOKEN)

if __name__ == "__main__":
    main()
