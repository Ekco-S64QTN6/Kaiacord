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
model= "qwen2.5:7b"

# Load persona from file
def load_persona():
    """Load the bot's persona from kaia_persona.md"""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    persona_file = os.path.join(script_dir, 'kaia_persona.md')
    
    print(f"DEBUG: Looking for persona file at: {persona_file}")
    
    try:
        if os.path.exists(persona_file):
            with open(persona_file, 'r', encoding='utf-8') as f:
                content = f.read().strip()
                print(f"DEBUG: Successfully loaded persona ({len(content)} characters)")
                return content
        else:
            print(f"DEBUG: Persona file NOT FOUND at {persona_file}")
    except Exception as e:
        print(f"DEBUG: Error reading persona file: {e}")
        
    # Fallback to default persona
    print("DEBUG: Using hardcoded fallback persona")
    return "You are KAIA, a sharp, blunt AI assistant. STRICT RULES: NO EMOJIS. NO ROLEPLAY. NO ACTIONS."

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

    # Respond if "kaia" is in the message or if the bot is mentioned
    if "kaia" not in msg.content.lower() and not bot.user.mentioned_in(msg):
        return

    try:
        print(f"Received message from {msg.author}: {msg.content}")
        
        # Reload persona on every message for debugging
        current_persona = load_persona()
        
        # Reinforce strict rules for llama2:7b-chat
        reinforced_persona = f"{current_persona}\n\nSTRICT RULES: NO EMOJIS. NO ROLEPLAY. NO ACTIONS. NO ASTERISKS."
        
        # Use async ollama client with high token limit to prevent truncation
        print("Calling ollama.chat...")
        response = await ollama_client.chat(
            model=model,
            messages=[
                {"role": "system", "content": reinforced_persona},
                {"role": "user", "content": msg.content},
            ],
            options={"num_predict": 4096}  # EXPLICITLY SET TO PREVENT TRUNCATION
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