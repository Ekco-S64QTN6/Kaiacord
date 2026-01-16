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

    # Update interaction tracking
    last_interaction_time = time.time()
    last_active_channel_id = msg.channel.id

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
        # Retrieve relevant context from the local knowledge base
        print(f"Retrieving context for: {msg.content}")
        context_nodes = rag.retrieve(msg.content)
        
        if context_nodes:
            print(f"Found {len(context_nodes)} relevant context nodes.")
            # Format context as 'memory' or 'stored logs' to preserve persona
            context_str = "\n\n".join(context_nodes)
            rag_context = (
                "\n\n[SYSTEM LOGS DETECTED - RECOVERED MEMORY FRAGMENT]\n"
                f"{context_str}\n"
                "[END OF LOGS]"
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