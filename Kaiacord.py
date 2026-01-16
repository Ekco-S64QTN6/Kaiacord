import os
import asyncio
from collections import deque
from dotenv import load_dotenv
import ollama
import discord
import random
import time
import datetime
from discord.ext import tasks
from kaia_rag import KaiaRAG
from kaia_image import generate_image

# setup environment variables
load_dotenv()
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')

# setup bot
intents = discord.Intents.default()
intents.message_content = True
bot = discord.Client(intents=intents)

# ollama config
model = "gemma3:12b"

# MEMORY: Store the last 15 messages per channel
MAX_MEMORY = 15
channel_memory = {}

# TRACKING: Last interaction time and channel
last_interaction_time = time.time()
last_active_channel_id = None

# Load persona from file
def load_persona():
    """Load the bot's persona from kaia_persona.md"""
    persona_file = os.path.join(os.path.dirname(__file__), 'kaia_persona.md')
    try:
        with open(persona_file, 'r', encoding='utf-8') as f:
            return f.read().strip()
    except Exception:
        return "You are Kaia, a blunt and grounded resident of this server."

# Create async client
ollama_client = ollama.AsyncClient()

# Initialize RAG
rag = KaiaRAG()

@bot.event
async def on_ready():
    print(f"{bot.user.name} is online!")
    if not idle_quip_task.is_running():
        idle_quip_task.start()

@tasks.loop(minutes=15)
async def idle_quip_task():
    """Generate a random quip if idle for too long"""
    global last_interaction_time, last_active_channel_id
    
    idle_duration = time.time() - last_interaction_time
    
    # Fallback: If we don't have a channel yet, find one we can speak in
    if not last_active_channel_id:
        for guild in bot.guilds:
            for channel in guild.text_channels:
                if channel.permissions_for(guild.me).send_messages:
                    last_active_channel_id = channel.id
                    break
            if last_active_channel_id: break

    if not last_active_channel_id:
        return

    # Logic: 
    # 30+ mins idle: 30% chance every 15 mins
    # 60+ mins idle: 80% chance to force it
    if idle_duration >= 1740: # 29 mins to be safe
        chance = 0.3
        if idle_duration >= 3540: # 59 mins
            chance = 0.8
            
        if random.random() < chance:
            channel = bot.get_channel(last_active_channel_id)
            if channel:
                try:
                    print(f"Generating idle quip (Idle: {int(idle_duration/60)}m)...")
                    system_prompt = load_persona()
                    messages = [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": "Generate a short, random quip or a blunt question to the room. Don't address anyone specifically. Just something on your mind."}
                    ]
                    
                    response = await ollama_client.chat(
                        model=model,
                        messages=messages,
                        options={
                            "temperature": 0.8,
                            "num_predict": 512,
                            "repeat_penalty": 1.1,
                            "presence_penalty": 0.0,
                            "frequency_penalty": 0.0,
                            "top_p": 0.9,
                        }
                    )
                    
                    content = response['message']['content'].strip()
                    if content:
                        # Wrap in code block
                        formatted_content = f"```\n{content}\n```"
                        await channel.send(formatted_content)
                        # Update interaction time so we don't spam
                        last_interaction_time = time.time()
                        print(f"Sent idle quip: {content[:50]}...")
                except Exception as e:
                    print(f"Error in idle quip: {e}")

@bot.event
async def on_message(msg):
    global last_interaction_time, last_active_channel_id
    
    if msg.author == bot.user:
        return

    # Trigger logic: Original working "kaia" check
    if "kaia" not in msg.content.lower() and not bot.user.mentioned_in(msg):
        return

    # Trigger logic: Image generation
    if "kaia, draw" in msg.content.lower():
        # Extract prompt after 'draw'
        try:
            prompt = msg.content.lower().split("draw", 1)[1].strip()
        except IndexError:
            prompt = ""
            
        if not prompt:
            await msg.channel.send("```\ndraw what? i need a prompt.\n```")
            return
            
        # Persona confirmation
        await msg.channel.send("```\nflickering the screen. give me a second.\n```")
        
        try:
            print(f"Generating image for prompt: {prompt}")
            image_path = await generate_image(prompt)
            await msg.channel.send(file=discord.File(image_path))
            # Cleanup
            if os.path.exists(image_path):
                os.remove(image_path)
                print(f"Cleaned up {image_path}")
        except Exception as e:
            print(f"Image generation error: {e}")
            import traceback
            traceback.print_exc()
            await msg.channel.send(f"```\nsomething went wrong with the render. check the logs.\n```")
        return

    # "kaia remember" command
    if msg.content.lower().startswith("kaia remember"):
        memory_content = msg.content[len("kaia remember"):].strip()
        if memory_content:
            print(f"Storing memory: {memory_content}")
            if rag.add_memory(memory_content):
                await msg.channel.send("```\nLogged it.\n```")
            else:
                await msg.channel.send("```\nMemory buffer error. Try again.\n```")
        else:
            await msg.channel.send("```\nRemember what? I'm not a mind reader.\n```")
        return

    try:
        print(f"Received message from {msg.author}: {msg.content}")
        
        # Initialize memory for the channel if it doesn't exist
        if msg.channel.id not in channel_memory:
            channel_memory[msg.channel.id] = deque(maxlen=MAX_MEMORY)
        
        # Add the current user message to memory
        channel_memory[msg.channel.id].append({"role": "user", "content": msg.content})
        
        # Build the message history for Ollama
        system_prompt = load_persona()
        
        # Add current date/time context
        now = datetime.datetime.now()
        current_time_str = now.strftime("%A, %B %d, %Y %I:%M %p")
        system_prompt += f"\n\nToday is {current_time_str}."
        
        messages = [{"role": "system", "content": system_prompt}]
        
        # Include all messages from memory
        for m in channel_memory[msg.channel.id]:
            messages.append(m)
        
        # RAG RETRIEVAL
        # Clean query: strip "kaia" and common punctuation to improve retrieval
        clean_query = msg.content.lower().replace("kaia", "").strip("?,. ")
        print(f"Retrieving context for: {clean_query}")
        context_nodes = rag.retrieve(clean_query)
        
        if context_nodes:
            print(f"Found {len(context_nodes)} relevant context nodes.")
            # Use a framing that sounds like her own logs/notes
            context_str = "\n\n".join(context_nodes)
            rag_context = (
                "\n\n[RECOVERED_LOG_ENTRY]\n"
                "you found these fragments in your local storage. they're part of your history and facts you know. "
                "don't act like a bot or an assistant. just use this information as if you've always known it. "
                "if the user asks about something here, you have the answer.\n"
                "---\n"
                f"{context_str}\n"
                "[END_OF_LOGS]"
            )
            # Inject into system prompt
            messages[0]["content"] += rag_context
        else:
            print("No relevant context found.")
        
        print("Calling ollama.chat...")
        response = await ollama_client.chat(
            model=model,
            messages=messages,
            options={
                "temperature": 0.8,      # Increased to allow for more natural phrasing
                "num_predict": 512,      # Increased so she doesn't feel forced to cut off
                "repeat_penalty": 1.1,   # Lowered to reduce the "robotic" feel
                "presence_penalty": 0.0, # Removed to stop the forced avoidance of words
                "frequency_penalty": 0.0, # Removed to stop the model from tripping over itself
                "top_p": 0.9,
            }
        )
        
        content = response['message']['content']
        print(f"Got response: {content[:100]}...")

        # Add the bot's response to memory (truncated to 300 chars to prevent verbosity creep)
        channel_memory[msg.channel.id].append({"role": "assistant", "content": content[:300]})

        # Split response into chunks of 1990 characters (to leave room for backticks)
        chunk_size = 1990
        num_chunks = (len(content) + chunk_size - 1) // chunk_size
        
        for part_num in range(num_chunks):
            start = part_num * chunk_size
            end = start + chunk_size
            chunk = content[start:end]
            # Wrap in code block
            await msg.channel.send(f"```\n{chunk}\n```")
        
        # Update interaction time after sending
        last_interaction_time = time.time()
        print("Response sent successfully!")
        
    except Exception as e:
        print(f"ERROR: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        await msg.channel.send(f"Sorry, I encountered an error: {e}")

bot.run(DISCORD_TOKEN)