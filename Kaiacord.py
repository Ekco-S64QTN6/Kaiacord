import os
import asyncio

# Set PyTorch CUDA allocator to use expandable segments to reduce fragmentation
# These MUST be set before torch or any library that uses it is imported
os.environ["PYTORCH_ALLOC_CONF"] = "expandable_segments:True,max_split_size_mb:512"
os.environ["PYTORCH_CUDA_ALLOC_CONF"] = "expandable_segments:True,max_split_size_mb:512"

import re
import traceback
import random
import time
import datetime
from datetime import datetime
import logging
import subprocess
import signal
import json
from collections import deque
from dotenv import load_dotenv
import ollama
import discord
from discord.ext import tasks
from kaia_rag import KaiaRAG
from kaia_image import generate_image, unload_image_model, generation_lock
from kaia_vision import kaia_sees_image, cleanup_session
from clear_gpu_memory import clear_gpu_memory
from kaia_logger import *

def cleanup_on_startup():
    """Kill other instances of Kaiacord and clear GPU memory"""
    current_pid = os.getpid()
    log_action(f"Startup cleanup (PID: {current_pid})...")
    
    try:
        # Find all processes matching "Kaiacord.py"
        result = subprocess.run(['pgrep', '-f', 'Kaiacord.py'], capture_output=True, text=True)
        pids = result.stdout.strip().split('\n')
        
        for pid_str in pids:
            if pid_str:
                try:
                    pid = int(pid_str)
                    if pid != current_pid:
                        log_action(f"  - Killing existing instance (PID: {pid})...") 
                        os.kill(pid, signal.SIGTERM)
                except (ValueError, ProcessLookupError):
                    continue
                except Exception as e:
                    log_warning(f"Failed to kill PID {pid_str}: {e}")
    except Exception as e:
        log_warning(f"Failed to run pkill logic: {e}")

    # Clear GPU memory
    try:
        clear_gpu_memory()
    except Exception as e:
        log_warning(f"Failed to clear GPU memory: {e}")

# Run cleanup immediately on script execution
cleanup_on_startup()

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
last_image_per_channel = {} # Track the last image URL per channel

# TRACKING: Last interaction time and channel
last_interaction_time = time.time()
last_active_channel_id = None
STATE_FILE = "bot_state.json"
BLACKLISTED_CHANNELS = ["general", "announcements", "rules"]

def load_bot_state():
    """Load persisted bot state from JSON file"""
    global last_active_channel_id
    try:
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE, 'r') as f:
                state = json.load(f)
                last_active_channel_id = state.get('last_active_channel_id')
                log_info(f"Loaded last_active_channel_id: {last_active_channel_id}")
    except Exception as e:
        log_warning(f"Failed to load bot state: {e}")

def save_bot_state():
    """Save bot state to JSON file"""
    try:
        state = {'last_active_channel_id': last_active_channel_id}
        with open(STATE_FILE, 'w') as f:
            json.dump(state, f)
    except Exception as e:
        log_warning(f"Failed to save bot state: {e}")

# Load state on startup
load_bot_state()

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
            # Append strict formatting and substance rules
            content += (
                "\n\n## FORMATTING RULES\n"
                "- NEVER use Markdown code blocks (backticks ```). It breaks the terminal UI.\n"
                "- NEVER use bolding (**text**) or italics (*text*).\n"
                "- BE SUBSTANTIAL AND DIRECT. Provide detailed but grounded answers. No fluff.\n"
                "- Use lowercase by default."
            )
            _persona_cache = content
            _persona_last_load = mtime
            return _persona_cache
    except Exception:
        if _persona_cache:
            return _persona_cache
        return "You are Kaia, a blunt and grounded resident of this server."

async def send_kaia_response(channel, text):
    """Helper to split long messages and wrap them in Kaia's code block style"""
    if not text:
        return
        
    limit = 1980 # Leave room for backticks and newlines
    chunks = []
    
    # If it's already short, just one chunk
    if len(text) <= limit:
        chunks.append(text)
    else:
        # Word-aware splitting
        while len(text) > limit:
            split_idx = text.rfind('\n', 0, limit)
            if split_idx == -1:
                split_idx = text.rfind(' ', 0, limit)
            if split_idx == -1:
                split_idx = limit
            
            chunks.append(text[:split_idx].strip())
            text = text[split_idx:].strip()
        if text:
            chunks.append(text)
            
    for chunk in chunks:
        if chunk:
            await channel.send(f"```\n{chunk}\n```")

# Create async client
ollama_client = ollama.AsyncClient()

# Initialize RAG
rag = KaiaRAG()

async def prewarm_main_model():
    """Prewarm the main chat model to avoid cold-start delay"""
    try:
        log_model_action(model, "Prewarming main model")
        await ollama_client.chat(
            model=model,
            messages=[{"role": "user", "content": "hi"}],
            options={
                "num_predict": 1,
                "num_ctx": 8192  # Match the main chat loop
            }
        )
        log_success(f"Main model {model} prewarmed.")
    except Exception as e:
        log_warning(f"Failed to prewarm main model: {e}")

@bot.event
async def on_ready():
    log_success(f"{bot.user.name} is online!")
    
    # Prewarm the main Ollama model to avoid cold-start delay on first message
    # We don't prewarm the vision model here to avoid system lag
    asyncio.create_task(prewarm_main_model())
    
    if not idle_quip_task.is_running():
        idle_quip_task.start()
        
    if not rag_maintenance_task.is_running():
        rag_maintenance_task.start()
    
    # Refresh knowledge base in the background to avoid blocking boot
    log_action("Refreshing knowledge base in background...")
    asyncio.create_task(asyncio.to_thread(rag.refresh_knowledge_base))

@tasks.loop(minutes=15)
async def idle_quip_task():
    """Generate a random quip if idle for too long"""
    global last_interaction_time, last_active_channel_id, consecutive_quips
    
    idle_duration = time.time() - last_interaction_time
    
    # Don't quip if we've hit consecutive limit
    if consecutive_quips >= MAX_CONSECUTIVE_QUIPS:
        log_info(f"Max consecutive quips ({MAX_CONSECUTIVE_QUIPS}) reached. Waiting for user interaction.")
        return
    
    # Fallback: If we don't have a channel yet, find one we can speak in
    if not last_active_channel_id:
        for guild in bot.guilds:
            # Sort channels to have some consistency, but prioritize non-blacklisted
            channels = sorted(guild.text_channels, key=lambda c: c.position)
            for channel in channels:
                if channel.permissions_for(guild.me).send_messages:
                    if channel.name.lower() not in BLACKLISTED_CHANNELS:
                        last_active_channel_id = channel.id
                        save_bot_state()
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
                log_action(f"Generating idle quip #{consecutive_quips+1} (Idle: {int(idle_duration/60)}m)...")
                
                # RAG: Pull a random fragment from user logs to make fun of
                # We'll query for "recent interaction" to get something semi-relevant
                context_nodes = await asyncio.to_thread(
                    rag.retrieve, 
                    "recent user interaction", 
                    top_k=3
                )
                
                context_str = ""
                if context_nodes:
                    context_str = "\n\n[LOG_CONTEXT]\n" + "\n---\n".join(context_nodes)
                
                system_prompt = load_persona()
                
                messages = [
                    {"role": "system", "content": system_prompt + context_str},
                    {"role": "user", "content": "Based on the provided log context (if any), generate a short, funny, and slightly mocking question or quip. "
                        "Make it a single, sharp sentence. Be blunt and grounded. "
                        "If there's log context, make fun of what was said or the user's logic. "
                        "If no context, just ask a dry, cynical question about tech or life. "
                        "No fluff. No intro. Just the quip."}
                ]
                
                response = await ollama_client.chat(
                    model=model,
                    messages=messages,
                    options={
                        "temperature": 1.0,
                        "num_predict": 128,
                        "repeat_penalty": 1.0,
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
                        "[IDLE_QUIP]",
                        content
                    )
                    
                    log_success(f"Sent idle quip #{consecutive_quips}: {content[:50]}...")
            except Exception as e:
                log_error(f"Idle quip failed: {e}")

@tasks.loop(hours=1)
async def rag_maintenance_task():
    """Periodic RAG maintenance: persist index and check for updates"""
    try:
        if rag.persist_needed:
            log_action("Periodic RAG persistence...")
            await asyncio.to_thread(rag.persist)
    except Exception as e:
        log_error(f"RAG maintenance failed: {e}")

@bot.event
async def on_message(msg):
    global last_interaction_time, last_active_channel_id, consecutive_quips
    
    if msg.author == bot.user:
        return

    # TOTAL BLACKLIST: Ignore all messages in blacklisted channels
    if msg.channel.name.lower() in BLACKLISTED_CHANNELS:
        return

    # Trigger logic: Original working "kaia" check
    if "kaia" not in msg.content.lower() and not bot.user.mentioned_in(msg):
        return
    
    # Reset consecutive quips counter on user interaction
    consecutive_quips = 0

    # CHECK: Is Kaia currently busy generating an image?
    # We check the lock from kaia_image to prevent VRAM conflicts.
    if generation_lock.locked():
        # Only respond if they are actually trying to talk to Kaia
        # (which they are, based on the trigger check above)
        # We don't want to load the chat model while the image model is active.
        log_warning(f"Ignoring message from {msg.author.name} (image generation in progress)")
        # Optional: Send a one-time busy message per generation? 
        # For now, let's just be blunt as per persona.
        if random.random() < 0.3: # Don't spam the busy message
            await msg.channel.send("```\nbusy rendering. wait your turn.\n```")
        return

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
            log_action(f"Generating image for prompt: {prompt}")
            image_path = await generate_image(prompt)
            await msg.channel.send(file=discord.File(image_path))
            # Cleanup
            try:
                if os.path.exists(image_path):
                    os.remove(image_path)
                    log_success(f"Cleaned up temp file")
            except Exception as cleanup_err:
                log_warning(f"Failed to cleanup temp file: {cleanup_err}")
        except Exception as e:
            log_error(f"Image generation failed: {e}")
            traceback.print_exc()
            await msg.channel.send(f"```\nsomething went wrong with the render. check the logs.\n```")
        finally:
            # CRITICAL: Unload the image model to free up system RAM
            # before Ollama attempts to reload the chat model.
            try:
                unload_image_model()
            except Exception as unload_err:
                log_warning(f"Failed to unload image model: {unload_err}")
                
            # SEQUENTIAL: Wait for VRAM to be fully released before prewarming
            await asyncio.sleep(1.5)
            # Prewarm main model after image generation (sequential, not concurrent)
            await prewarm_main_model()
        return

    # "kaia remember" command
    if msg.content.lower().startswith("kaia remember"):
        memory_content = msg.content[len("kaia remember"):].strip()
        if memory_content:
            log_action(f"Storing memory: {memory_content}")
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

    # IMAGE VISION: Handle images and vision queries
    image_attachments = [
        att for att in msg.attachments 
        if any(att.filename.lower().endswith(ext) for ext in ['.png', '.jpg', '.jpeg', '.gif', '.webp'])
    ]
    
    # Always track the last image in the channel, even if Kaia isn't mentioned
    if image_attachments:
        last_image_per_channel[msg.channel.id] = image_attachments[0].url
        log_info(f"Tracked last image for channel {msg.channel.id}")

    # Check if this is an EXPLICIT vision request
    # Only "analyze" and "look" are explicit commands that should trigger vision
    explicit_vision_keywords = ["analyze", "look"]
    is_explicit_vision_request = any(word in msg.content.lower() for word in explicit_vision_keywords)
    
    # Vision triggers ONLY when:
    # 1. Message has an image attachment, OR
    # 2. User explicitly uses "analyze" or "look" keywords
    if ("kaia" in msg.content.lower() or bot.user.mentioned_in(msg)) and (image_attachments or is_explicit_vision_request):
        target_image_url = None
        
        # 1. Check current message attachments
        if image_attachments:
            target_image_url = image_attachments[0].url
            log_info("Using image from current message.")
            
        # 2. Check if it's a reply to a message with an image
        if not target_image_url and msg.reference:
            try:
                replied_msg = await msg.channel.fetch_message(msg.reference.message_id)
                replied_attachments = [
                    att for att in replied_msg.attachments 
                    if any(att.filename.lower().endswith(ext) for ext in ['.png', '.jpg', '.jpeg', '.gif', '.webp'])
                ]
                if replied_attachments:
                    target_image_url = replied_attachments[0].url
                    log_info("Using image from replied-to message.")
            except Exception as e:
                log_warning(f"Error fetching replied message: {e}")

        # 3. Fallback to the last image in the channel ONLY for explicit requests
        if not target_image_url and is_explicit_vision_request:
            target_image_url = last_image_per_channel.get(msg.channel.id)
            if target_image_url:
                log_info("Using last tracked image from channel (explicit request).")

        if target_image_url:
            try:
                log_action("Processing vision task...")
                
                # Show that Kaia is "looking"
                await msg.channel.send("```\nlooking...\n```")
                
                # Get Kaia's vision analysis
                analysis = await kaia_sees_image(target_image_url, msg.content)
                
                # Send response using the helper to handle long text
                await send_kaia_response(msg.channel, analysis)
                
                # Add the current interaction to memory AFTER the response
                channel_memory[msg.channel.id].append({"role": "user", "content": msg.content})
                channel_memory[msg.channel.id].append({"role": "assistant", "content": analysis})
                
                # Update interaction tracking
                last_interaction_time = time.time()
                if last_active_channel_id != msg.channel.id:
                    last_active_channel_id = msg.channel.id
                    save_bot_state()
                
                # Log the interaction with vision response flag
                await asyncio.to_thread(
                    rag.log_user_interaction,
                    msg.author.id,
                    msg.author.display_name,
                    f"{msg.content} [VISION_ANALYSIS]",
                    analysis[:500],
                    is_vision_response=True  # Mark as vision response to filter from non-vision RAG queries
                )
                
                log_response("Got response:", analysis[:100] + "...")
                log_separator()
                return
                
            except Exception as e:
                log_error(f"Vision analysis failed: {e}")
                traceback.print_exc()
                await msg.channel.send("```\ncan't process that image. something broke.\n```")
            finally:
                # SEQUENTIAL: Wait for VRAM to be fully released before prewarming
                await asyncio.sleep(1.5)
                # Prewarm main model after vision task (sequential, not concurrent)
                await prewarm_main_model()
            return

    try:
        log_message_received(msg.author.name, str(msg.author.id), msg.content)
        
        # history = list(channel_memory[msg.channel.id])
        # We'll add the current message to memory AFTER the LLM call to avoid double-counting
        
        # Build the message history for Ollama
        system_prompt = load_persona()
        
        # Add current date/time context
        now = datetime.now()
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
            
        log_context_retrieval(clean_query)
        
        # Wrap RAG retrieval in a thread to avoid blocking the event loop
        context_nodes = await asyncio.to_thread(
            rag.retrieve, 
            clean_query, 
            user_id=target_user_id, 
            user_name=target_user_name, 
            top_k=10 if clean_query.lower().startswith("who is") else 7
        )
        
        if context_nodes:
            # Display RAG context as a Rich table instead of ugly plain text
            format_rag_table(context_nodes)
        
        # 1. Start with core persona in the SYSTEM role
        messages = []
        
        # INJECT RAG CONTEXT EARLY
        if context_nodes:
            context_str = "\n\n".join(context_nodes)
            rag_block = (
                f"### CURRENT_USER: {msg.author.display_name}\n\n"
                "### HISTORICAL_RECORDS\n"
                "The following are fragments from your conversation logs. 'User (Name):' indicates what that specific person said. "
                "Names in brackets like [USER_PROFILE_AND_HISTORY: NAME] indicate the person the records are about. "
                "Use these records to recognize people and answer questions about them. "
                "IMPORTANT: Do not confuse the CURRENT_USER with people in the logs unless their names match exactly. "
                "If a log says 'User (A): Kaia who is B', it means A is asking about B, not that A is B.\n"
                "---\n"
                f"{context_str}\n"
                "---\n"
                "These records are ongoing fragments, not the full story. The conversation continues."
            )
        else:
            rag_block = f"### CURRENT_USER: {msg.author.display_name}\nNo specific historical records found."

        messages.append({
            "role": "system", 
            "content": f"{system_prompt}\n\n{rag_block}"
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
 
        # 4. Final Reinforcement
        reinforcement = (
            "\n\n[CRITICAL_RULES]\n"
            "1. NEVER use backticks (```) or any Markdown formatting. Your response is already wrapped in a code block; adding more breaks the UI.\n"
            "2. NO META-TALK. Never mention being an AI, a model, or 'processing' data.\n"
            "3. BE SUBSTANTIAL AND ENGAGING. Blunt, grounded, lowercase. Provide depth when asked about people, history, or technical topics. Keep the conversation alive and ongoing.\n"
            "4. NO BOLDING or ITALICS. Just plain text.\n"
            "5. DO NOT prefix your response with a name (e.g., 'ekco.', 'kaia:', 'Response:'). Just start speaking.\n"
            "6. IDENTITY CLARITY: If asked 'who is [X]?', use the ### HISTORICAL_RECORDS (especially [USER_SUMMARY_PROFILE]) to provide a deep, analytical summary. DO NOT hallucinate. You are Kaia, they are the user. If you have records, you MUST use them. Never claim ignorance if records exist.\n"
            "7. [KAIA_PERSONA_FRAGMENT] nodes are facts about YOUR identity. Use them only when asked about yourself.\n"
            "8. If the recovered logs are irrelevant, IGNORE THEM. Answer the user directly.\n"
            "9. DO NOT parrot logs verbatim. Speak naturally as Kaia."
        )

        messages.append({
            "role": "system",
            "content": reinforcement
        })

        log_action("Calling ollama.chat...")
        response = await ollama_client.chat(
            model=model,
            messages=messages,
            options={
                "temperature": 0.8,
                "num_predict": 800,
                "num_ctx": 8192,
                "repeat_penalty": 1.1,
                "presence_penalty": 0.0,
                "frequency_penalty": 0.0,
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
        
        # FAIL-SAFE: Strip all backticks to prevent broken code blocks
        content = content.replace("`", "")
        
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
            log_warning("Detected safety lecture/helpline in response. Surgically stripping...")
            
            # If the response is MOSTLY a safety lecture, replace it with a blunt refusal
            # instead of just stripping lines which might leave it empty or weird.
            lecture_keywords = ["unacceptable", "harmful", "reconsider", "safety", "ethics", "I cannot", "I will not"]
            lecture_count = sum(1 for kw in lecture_keywords if kw.lower() in content.lower())
            
            if lecture_count >= 2 or len(content) < 100:
                content = random.choice([
                    "not doing that. ask something else.",
                    "i'm not into that. find it yourself.",
                    "pass. i'm not your moral compass, and that's not interesting.",
                    "that's a bit much. let's talk about something else.",
                    "not happening. move on."
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

        log_response("Got response:", content[:100] + "..." if len(content) > 100 else content)

        # Use the helper to handle long text and formatting
        await send_kaia_response(msg.channel, content)
        
        # Add the current interaction to memory AFTER the response
        # (truncated to 1000 chars to prevent verbosity creep)
        channel_memory[msg.channel.id].append({"role": "user", "content": msg.content})
        channel_memory[msg.channel.id].append({"role": "assistant", "content": content[:1000]})
        
        # Update interaction time after sending
        last_interaction_time = time.time()
        if last_active_channel_id != msg.channel.id:
            last_active_channel_id = msg.channel.id
            save_bot_state()
        
        # Log interaction for persistent memory (User's log)
        await asyncio.to_thread(
            rag.log_user_interaction,
            msg.author.id,
            msg.author.display_name,
            msg.content,
            content[:500]
        )
        
        log_success("Response sent successfully!")
        log_separator()
        
    except Exception as e:
        log_error(f"{type(e).__name__}: {e}")
        traceback.print_exc()
        await send_kaia_response(msg.channel, f"something broke: {e}")

async def main():
    """Main entry point for the bot"""
    try:
        async with bot:
            await bot.start(DISCORD_TOKEN)
    except asyncio.CancelledError:
        pass
    finally:
        log_critical("\nShutting down...")
        
        # 1. Persist RAG index
        if rag:
            log_action("Persisting RAG index...")
            await asyncio.to_thread(rag.persist, force=True)
            log_success("Index persisted.")
            
        # 2. Cleanup vision session
        log_action("Cleaning up vision session...")
        try:
            await cleanup_session()
            log_success("Vision session closed.")
        except Exception as e:
            log_warning(f"Failed to cleanup vision session: {e}")
            
        # 3. Close Ollama clients
        log_action("Closing Ollama clients...")
        try:
            # Close main client
            if hasattr(ollama_client, '_client'):
                await ollama_client._client.aclose()
            
            # Close vision client (imported from kaia_vision)
            from kaia_vision import ollama_client as vision_ollama_client
            if hasattr(vision_ollama_client, '_client'):
                await vision_ollama_client._client.aclose()
            log_success("Ollama clients closed.")
        except Exception as e:
            log_warning(f"Failed to close Ollama clients: {e}")
            
        log_success("Shutdown complete.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass