import os
import asyncio
from dotenv import load_dotenv
import ollama
import discord


#setup environment variables
load_dotenv()
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')

#setup bot
intents = discord.Intents.default()
intents.message_content = True
bot = discord.Client(intents=intents)


#ollama config
model= "llama2:7b-chat"

# Load persona from file
def load_persona():
    """Load the bot's persona from kaia_persona.md"""
    persona_file = os.path.join(os.path.dirname(__file__), 'kaia_persona.md')
    try:
        with open(persona_file, 'r', encoding='utf-8') as f:
            return f.read().strip()
    except FileNotFoundError:
        # Fallback to default persona if file not found
        return "You are Kaia, a Linux-native AI assistant. Your persona is characterized by strategic thinking, precise execution, and intellectual clarity. Always prioritize clarity, conciseness, and technical utility."

system_prompt = load_persona()

# Create async client
ollama_client = ollama.AsyncClient()

# When bot is ready to start operating
@bot.event
async def on_ready():
    print(f"{bot.user.name} is online!")


# When a message gets sent to the Discord chat
@bot.event
async def on_message(msg):
    if msg.author == bot.user:
        return

    try:
        print(f"Received message from {msg.author}: {msg.content}")
        
        # Use async ollama client
        print("Calling ollama.chat...")
        response = await ollama_client.chat(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": msg.content},
            ],
        )
        print(f"Got response: {response['message']['content'][:100]}...")

        # Split response into chunks of 2000 characters (Discord's limit)
        content = response['message']['content']
        chunk_size = 2000
        num_chunks = (len(content) + chunk_size - 1) // chunk_size  # Ceiling division
        
        for part_num in range(num_chunks):
            start = part_num * chunk_size
            end = start + chunk_size
            await msg.channel.send(content[start:end])
        
        print("Response sent successfully!")
        
    except Exception as e:
        print(f"ERROR: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        await msg.channel.send(f"Sorry, I encountered an error: {e}")
# ----------------------------


bot.run(DISCORD_TOKEN)