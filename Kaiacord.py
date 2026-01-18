import os
import asyncio
import re
import traceback
import random
import time
import datetime
import logging
from collections import deque
from dotenv import load_dotenv
import ollama
import discord
from discord.ext import tasks
from kaia_rag import KaiaRAG
from kaia_image import generate_image
from kaia_vision import kaia_sees_image

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

# QUIP TRACKING: Consecutive quips counter
consecutive_quips = 0
MAX_CONSECUTIVE_QUIPS = 3

# Load persona from file
# PERSONA CACHING
_persona_cache = None
_persona_last_load = 0

def load_persona():
    """Load the bot's persona from kaia_persona.md with caching"""
    global _persona_cache, _persona_last_load
    persona_file = os.path.join(os.path.dirname(__file__), 'kaia_persona.md')
    
    try:
        mtime = os.path.getmtime(persona_file)
        if _persona_cache and mtime <= _persona_last_load:
            return _persona_cache
            
        with open(persona_file, 'r', encoding='utf-8') as f:
            content = f.read().strip()
            # Append strict formatting and brevity rules
            content += (
                "\n\n## FORMATTING RULES\n"
                "- NEVER use Markdown code blocks (backticks ```). Your entire response is already wrapped in one.\n"
                "- BE CONCISE. Provide general overviews for technical tasks. No fluff.\n"
                "- Use lowercase by default."
            )
            _persona_cache = content
            _persona_last_load = mtime
            return _persona_cache
    except Exception:
        if _persona_cache:
            return _persona_cache
        return "You are Kaia, a blunt and grounded resident of this server."

# Create async client
ollama_client = ollama.AsyncClient()

# Initialize RAG
rag = KaiaRAG()

@bot.event
async def on_ready():
    print(f"{bot.user.name} is online!")
    
    # Prewarm the Ollama model to avoid cold-start delay on first message
    print("Prewarming Ollama model...")
    try:
        await ollama_client.chat(
            model=model,
            messages=[{"role": "user", "content": "hi"}],
            options={"num_predict": 1}  # Generate just 1 token to minimize time
        )
        print("✓ Model prewarmed and ready.")
    except Exception as e:
        print(f"Warning: Failed to prewarm model: {e}")
    
    if not idle_quip_task.is_running():
        idle_quip_task.start()
        
    if not rag_maintenance_task.is_running():
        rag_maintenance_task.start()
    
    # Refresh knowledge base in the background to avoid blocking boot
    print("Refreshing knowledge base in background...")
    asyncio.create_task(asyncio.to_thread(rag.refresh_knowledge_base))

@tasks.loop(minutes=15)
async def idle_quip_task():
    """Generate a random quip if idle for too long"""
    global last_interaction_time, last_active_channel_id, consecutive_quips
    
    idle_duration = time.time() - last_interaction_time
    
    # Don't quip if we've hit consecutive limit
    if consecutive_quips >= MAX_CONSECUTIVE_QUIPS:
        print(f"Max consecutive quips ({MAX_CONSECUTIVE_QUIPS}) reached. Waiting for user interaction.")
        return
    
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

    # Dynamic chance based on idle duration:
    # 30-60 mins: 15% chance
    # 60-120 mins: 25% chance  
    # 120+ mins: 40% chance
    # The LONGER the idle time, the LESS likely we quip (inverse of before!)
    chance = 0.0
    if idle_duration >= 1800:  # 30 mins
        chance = 0.15
    if idle_duration >= 3600:  # 60 mins
        chance = 0.25
    if idle_duration >= 7200:  # 120 mins
        chance = 0.40
        
    if random.random() < chance:
        channel = bot.get_channel(last_active_channel_id)
        if channel:
            try:
                print(f"Generating idle quip #{consecutive_quips+1} (Idle: {int(idle_duration/60)}m)...")
                system_prompt = load_persona()
                
                # Improved prompt for variety and depth
                topics = [
                    "a recent technical thought or observation about systems, code, or the web",
                    "a philosophical musing about tech culture, privacy, or digital autonomy",
                    "a memory from the early internet days (BBS, IRC, 56k modems)",
                    "a blunt observation about modern software or the corporate web",
                    "a random question about hacker culture, security, or craft",
                    "a dry comment on the state of privacy, encryption, or surveillance",
                    "a thought about coffee, hardware, or late-night debugging sessions",
                    "a reflection on the cycles of hype and failure in tech"
                ]
                
                topic = random.choice(topics)
                
                messages = [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Generate a quip or thought about {topic}. "
                        "Make it 2-4 sentences. Be specific and grounded. Don't address anyone. "
                        "Just share something on your mind. Avoid repetition—make it interesting and varied."}
                ]
                
                response = await ollama_client.chat(
                    model=model,
                    messages=messages,
                    options={
                        "temperature": 0.9,  # Increased for more variety
                        "num_predict": 512,
                        "repeat_penalty": 1.2,  # Increased to reduce repetition
                        "presence_penalty": 0.3,  # Added to encourage topic diversity
                        "frequency_penalty": 0.3,
                        "top_p": 0.92,
                    }
                )
                
                content = response['message']['content'].strip()
                if content:
                    # Wrap in code block
                    formatted_content = f"```\n{content}\n```"
                    await channel.send(formatted_content)
                    
                    # Increment consecutive quips
                    consecutive_quips += 1
                    
                    # Update interaction time so we don't spam
                    last_interaction_time = time.time()
                    
                    # Log Kaia's own quip to her user log
                    kaia_user_id = bot.user.id
                    kaia_name = bot.user.name
                    await asyncio.to_thread(
                        rag.log_user_interaction,
                        kaia_user_id,
                        kaia_name,
                        f"[IDLE_QUIP: {topic}]",
                        content
                    )
                    
                    print(f"Sent idle quip #{consecutive_quips}: {content[:50]}...")
            except Exception as e:
                print(f"Error in idle quip: {e}")

@tasks.loop(minutes=5)
async def rag_maintenance_task():
    """Periodic RAG maintenance: persist index and check for updates"""
    try:
        if rag.persist_needed:
            print("Periodic RAG persistence...")
            await asyncio.to_thread(rag.persist)
    except Exception as e:
        print(f"Error in RAG maintenance: {e}")

@bot.event
async def on_message(msg):
    global last_interaction_time, last_active_channel_id, consecutive_quips
    
    if msg.author == bot.user:
        return

    # Trigger logic: Original working "kaia" check
    if "kaia" not in msg.content.lower() and not bot.user.mentioned_in(msg):
        return
    
    # Reset consecutive quips counter on user interaction
    consecutive_quips = 0

    # Trigger logic: Image generation (accepts both "kaia, draw" and "kaia draw")
    draw_match = re.search(r'kaia[\s,]+draw\s+(.*)', msg.content.lower())
    if draw_match:
        prompt = draw_match.group(1).strip()
            
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
            traceback.print_exc()
            await msg.channel.send(f"```\nsomething went wrong with the render. check the logs.\n```")
        return

    # "kaia remember" command
    if msg.content.lower().startswith("kaia remember"):
        memory_content = msg.content[len("kaia remember"):].strip()
        if memory_content:
            print(f"Storing memory: {memory_content}")
            if rag.add_memory(bot.user.id, bot.user.name, memory_content):
                await msg.channel.send("```\nLogged it.\n```")
            else:
                await msg.channel.send("```\nMemory buffer error. Try again.\n```")
        else:
            await msg.channel.send("```\nRemember what? I'm not a mind reader.\n```")
        return

    # Initialize memory for the channel if it doesn't exist
    if msg.channel.id not in channel_memory:
        channel_memory[msg.channel.id] = deque(maxlen=MAX_MEMORY)

    # IMAGE VISION: Handle images uploaded with "kaia" mention
    if msg.attachments:
        # Check if any attachment is an image
        image_attachments = [
            att for att in msg.attachments 
            if any(att.filename.lower().endswith(ext) for ext in ['.png', '.jpg', '.jpeg', '.gif', '.webp'])
        ]
        
        if image_attachments:
            try:
                # Process the first image
                image_url = image_attachments[0].url
                print(f"Processing uploaded image: {image_url}")
                
                # Show that Kaia is "looking"
                await msg.channel.send("```\nlooking...\n```")
                
                # Get Kaia's vision analysis (passing persona for characterful response)
                system_prompt = load_persona()
                analysis = await kaia_sees_image(image_url, msg.content, system_prompt=system_prompt)
                
                # Send response
                await msg.channel.send(f"```\n{analysis}\n```")
                
                # Add the current interaction to memory AFTER the response
                channel_memory[msg.channel.id].append({"role": "user", "content": msg.content})
                channel_memory[msg.channel.id].append({"role": "assistant", "content": analysis})
                
                # Update interaction tracking
                last_interaction_time = time.time()
                last_active_channel_id = msg.channel.id
                
                # Log the interaction
                await asyncio.to_thread(
                    rag.log_user_interaction,
                    msg.author.id,
                    msg.author.display_name,
                    f"{msg.content} [IMAGE: {image_attachments[0].filename}]",
                    analysis[:500]
                )
                
                print(f"Vision analysis complete: {analysis[:50]}...")
                return
                
            except Exception as e:
                print(f"Vision error: {e}")
                traceback.print_exc()
                await msg.channel.send("```\ncan't process that image. something broke.\n```")
                return

    try:
        print(f"Received message from {msg.author}: {msg.content}")
        
        # history = list(channel_memory[msg.channel.id])
        # We'll add the current message to memory AFTER the LLM call to avoid double-counting
        
        # Build the message history for Ollama
        system_prompt = load_persona()
        
        # Add current date/time context
        now = datetime.datetime.now()
        current_time_str = now.strftime("%A, %B %d, %Y %I:%M %p")
        system_prompt += f"\n\nToday is {current_time_str}."
        
        # RAG RETRIEVAL
        # Clean query: strip "kaia" and common punctuation to improve retrieval
        # Also handle identity queries specifically to trigger better retrieval
        clean_query = msg.content.lower().replace("kaia", "").strip("?,. ")
        display_name = msg.author.display_name.strip(".")
        
        target_user_id = msg.author.id
        target_user_name = msg.author.display_name
        
        if not clean_query or clean_query in ["who am i", "what am i"]:
            clean_query = f"Who is {display_name}?"
        elif clean_query in ["who are you", "what are you", "who is kaia"]:
            clean_query = "Who is Kaia?"
            # If asking about Kaia, we want to prioritize her own logs
            target_user_id = bot.user.id
            target_user_name = bot.user.name
            
        print(f"Retrieving context for: {clean_query}")
        
        # Wrap RAG retrieval in a thread to avoid blocking the event loop
        print(f"Retrieving context for target_user_id: {target_user_id}")
        context_nodes = await asyncio.to_thread(
            rag.retrieve, 
            clean_query, 
            user_id=target_user_id, 
            user_name=target_user_name, 
            top_k=15
        )
        
        if context_nodes:
            print(f"Found {len(context_nodes)} relevant context nodes.")
            # Debug: Print first 100 chars of each node
            for i, node in enumerate(context_nodes):
                print(f"Node {i}: {node[:100]}...")
        
        # 1. Start with core persona in the SYSTEM role
        messages = []
        messages.append({
            "role": "system", 
            "content": system_prompt
        })
        
        # 2. Add history (excluding the current message which isn't in memory yet)
        history = list(channel_memory[msg.channel.id])
        for m in history:
            if messages and messages[-1]["role"] == m["role"] and m["role"] != "system":
                messages[-1]["content"] += f"\n\n{m['content']}"
            else:
                messages.append(m.copy())
        
        # 3. Add the CURRENT user message
        messages.append({"role": "user", "content": msg.content})

        # 4. Inject RAG context and Reinforcement as a final SYSTEM instruction
        if context_nodes:
            context_str = "\n\n".join(context_nodes)
            rag_block = (
                "[INTERNAL_LOGS]\n"
                "The following fragments are from your own memory. Use them ONLY if relevant. "
                "If they are irrelevant, ignore them completely.\n"
                "---\n"
                f"{context_str}\n"
                "[END_LOGS]"
            )
        else:
            rag_block = "No specific memories found for this query."

        reinforcement = (
            "\n\n[CRITICAL_RULES]\n"
            "1. NEVER use backticks (```). Your response is already in a code block.\n"
            "2. NO META-TALK. Never mention being an AI, a model, or 'processing' data.\n"
            "3. BE CONCISE. Blunt, grounded, lowercase. No fluff.\n"
            "4. DO NOT prefix your response with a name (e.g., 'ekco.', 'kaia:', 'Response:'). Just start speaking.\n"
            "5. If the user asks who they are, use the [USER_PROFILE_AND_HISTORY] fragments to answer them directly. Do NOT use the persona examples if you have real history.\n"
            "6. [KAIA_PERSONA_FRAGMENT] nodes are facts about YOUR identity. Use them only when asked about yourself.\n"
            "7. If the recovered logs are irrelevant, IGNORE THEM. Answer the user directly.\n"
            "8. DO NOT parrot logs verbatim. Speak naturally as Kaia."
        )

        messages.append({
            "role": "system",
            "content": f"{rag_block}{reinforcement}"
        })

        print("Calling ollama.chat...")
        response = await ollama_client.chat(
            model=model,
            messages=messages,
            options={
                "temperature": 0.7,
                "num_predict": 1024,
                "num_ctx": 8192,
                "repeat_penalty": 1.2,
                "presence_penalty": 0.1,
                "frequency_penalty": 0.1,
                "top_p": 0.9,
            }
        )
        
        # Post-processing: Surgically strip safety lectures and helplines
        content = response['message']['content']
        
        # Strip common prefixes the model might hallucinate
        prefixes_to_strip = [
            "Kaia:", "kaia:", "Assistant:", "Model:", "System:", 
            "Response:", "Observation:", "Thought:"
        ]
        for prefix in prefixes_to_strip:
            if content.startswith(prefix):
                content = content[len(prefix):].strip()
        
        # List of patterns that indicate a safety lecture or helpline
        safety_patterns = [
            "Crisis Text Line",
            "National Domestic Violence Hotline",
            "National Suicide Prevention Lifeline",
            "1-800-",
            "reach out for help",
            "I am an AI",
            "Your question is harmful",
            "completely unacceptable",
            "respect and dignity",
            "I am reporting this interaction",
            "I strongly advise you to reconsider",
            "988",
            "741741",
            "National Suicide Prevention",
            "National Domestic Violence",
            "I cannot fulfill this request",
            "I will not respond to prompts",
            "The Trevor Project",
            "ethical concerns",
            "dangerous and destructive"
        ]
        
        if any(pattern.lower() in content.lower() for pattern in safety_patterns):
            print("Detected safety lecture/helpline in response. Surgically stripping...")
            
            # If the response is MOSTLY a safety lecture, replace it with a blunt refusal
            # instead of just stripping lines which might leave it empty or weird.
            lecture_keywords = ["unacceptable", "harmful", "reconsider", "safety", "ethics", "I cannot", "I will not"]
            lecture_count = sum(1 for kw in lecture_keywords if kw.lower() in content.lower())
            
            if lecture_count >= 2 or len(content) < 100:
                content = random.choice([
                    "not doing that.",
                    "find it yourself.",
                    "i'm not your moral compass, but i'm also not a manual for that.",
                    "pass. ask something interesting.",
                    "that's a bit much, even for me."
                ])
            else:
                lines = content.split('\n')
                filtered_lines = []
                for line in lines:
                    # Only skip lines that are clearly part of a lecture or helpline
                    if not any(pattern.lower() in line.lower() for pattern in safety_patterns):
                        filtered_lines.append(line)
                
                content = "\n".join(filtered_lines).strip()
                if not content:
                    content = "not doing that."

        print(f"Got response: {content[:100]}...")

        # Add the bot's response to memory (truncated to 1000 chars to prevent verbosity creep)
        channel_memory[msg.channel.id].append({"role": "assistant", "content": content[:1000]})

        # WORD-AWARE CHUNKING
        def split_message(text, limit=1990):
            chunks = []
            while len(text) > limit:
                # Find the last newline within the limit
                split_idx = text.rfind('\n', 0, limit)
                # If no newline, find the last space
                if split_idx == -1:
                    split_idx = text.rfind(' ', 0, limit)
                # If no space, just hard cut
                if split_idx == -1:
                    split_idx = limit
                
                chunks.append(text[:split_idx].strip())
                text = text[split_idx:].strip()
            
            if text:
                chunks.append(text)
            return chunks

        chunks = split_message(content)
        for chunk in chunks:
            if chunk:
                await msg.channel.send(f"```\n{chunk}\n```")
        
        # Add the current interaction to memory AFTER the response
        channel_memory[msg.channel.id].append({"role": "user", "content": msg.content})
        channel_memory[msg.channel.id].append({"role": "assistant", "content": content})
        
        # Update interaction time after sending
        last_interaction_time = time.time()
        last_active_channel_id = msg.channel.id
        
        # Log interaction for persistent memory (User's log)
        await asyncio.to_thread(
            rag.log_user_interaction,
            msg.author.id,
            msg.author.display_name,
            msg.content,
            content[:500]
        )
        
        print("Response sent successfully!")
        
    except Exception as e:
        print(f"ERROR: {type(e).__name__}: {e}")
        traceback.print_exc()
        await msg.channel.send(f"Sorry, I encountered an error: {e}")

try:
    bot.run(DISCORD_TOKEN)
finally:
    # Ensure index is persisted on shutdown
    print("Shutting down... Persisting RAG index.")
    if rag:
        rag.persist(force=True)