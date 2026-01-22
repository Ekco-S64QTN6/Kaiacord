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
import psutil
import concurrent.futures
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Deque, Any
from collections import deque, defaultdict
from dotenv import load_dotenv
import ollama
import discord
from discord.ext import commands, tasks
from kaia_rag import KaiaRAG
from kaia_image import generate_image, unload_image_model, generation_lock
from kaia_vision import kaia_sees_image, cleanup_session
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from utils.kaia_intelligence import SemanticCache, ModelWarmPool, QueryClassifier, ContextOptimizer, RelevanceFeedback

# Load environment variables early so Config can use them
load_dotenv()
from utils.clear_gpu_memory import clear_gpu_memory
from utils.kaia_logger import *

@dataclass
class Config:
    """Configuration management for Kaiacord"""
    discord_token: str = field(default_factory=lambda: os.getenv('DISCORD_TOKEN'))
    blacklisted_channels: List[str] = field(default_factory=lambda: os.getenv('BLACKLISTED_CHANNELS', 'general,announcements,rules').split(','))
    
    # Models
    chat_model: str = "gemma3:12b"
    vision_model: str = "llama3.2-vision:11b"
    embedding_model: str = "nomic-embed-text"
    
    # RAG
    knowledge_base_dir: str = "./knowledge_base"
    persist_dir: str = "./storage"
    max_log_size_mb: int = 100
    
    # Performance
    max_memory_messages: int = 15
    max_consecutive_quips: int = 3
    rag_top_k: int = 4
    
    # Rate Limiting
    requests_per_minute: int = 30

    @classmethod
    def from_env(cls):
        return cls()

config = Config.from_env()

class BotState:
    """Encapsulates global bot state and persistence"""
    def __init__(self, state_file: str = "storage/bot_state.json"):
        self.state_file = state_file
        self.channel_memory: Dict[int, Deque[Dict[str, str]]] = {}
        self.last_interaction_time: float = time.time()
        self.last_active_channel_id: Optional[int] = None
        self.consecutive_quips: int = 0
        self.load()

    def load(self):
        """Load persisted bot state from JSON file"""
        try:
            if os.path.exists(self.state_file):
                with open(self.state_file, 'r') as f:
                    state = json.load(f)
                    self.last_active_channel_id = state.get('last_active_channel_id')
                    self.consecutive_quips = state.get('consecutive_quips', 0)
                    log_info(f"Loaded last_active_channel_id: {self.last_active_channel_id}, quips: {self.consecutive_quips}")
        except Exception as e:
            log_warning(f"Failed to load bot state: {e}")

    def save(self):
        """Save bot state to JSON file"""
        try:
            state = {
                'last_active_channel_id': self.last_active_channel_id,
                'consecutive_quips': self.consecutive_quips,
                'saved_at': time.time()
            }
            with open(self.state_file, 'w') as f:
                json.dump(state, f)
        except Exception as e:
            log_warning(f"Failed to save bot state: {e}")

    def reset_quips(self):
        self.consecutive_quips = 0
        self.save()

    def increment_quips(self):
        self.consecutive_quips += 1
        self.save()

    def update_interaction(self, channel_id: int):
        self.last_interaction_time = time.time()
        if self.last_active_channel_id != channel_id:
            self.last_active_channel_id = channel_id
            self.save()

bot_state = BotState()

class RateLimiter:
    """Per-user rate limiting"""
    def __init__(self, requests_per_minute: int = 30):
        self.requests = defaultdict(list)
        self.limit = requests_per_minute
        
    def is_allowed(self, user_id: int) -> bool:
        now = time.time()
        user_requests = self.requests[user_id]
        
        # Remove old requests
        user_requests = [req for req in user_requests if now - req < 60]
        self.requests[user_id] = user_requests
        
        if len(user_requests) >= self.limit:
            return False
            
        user_requests.append(now)
        return True

rate_limiter = RateLimiter(config.requests_per_minute)

def sanitize_prompt(prompt: str, max_length: int = 2000) -> str:
    """Remove potential prompt injection attempts and limit length."""
    # Remove system prompt markers
    prompt = re.sub(r'\s*system\s*:', '', prompt, flags=re.IGNORECASE)
    prompt = re.sub(r'```[\s\S]*?```', '', prompt)
    
    # Limit length
    if len(prompt) > max_length:
        prompt = prompt[:max_length] + "..."
    
    # Escape newlines in certain contexts (optional, but good for some models)
    # prompt = prompt.replace('\n', ' ')
    
    return prompt.strip()

# Dedicated thread pool for RAG operations
rag_executor = concurrent.futures.ThreadPoolExecutor(
    max_workers=2,
    thread_name_prefix='rag_worker'
)

async def run_rag(fn, *args, **kwargs):
    """Centralized helper to run RAG operations in the executor"""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(rag_executor, lambda: fn(*args, **kwargs))

# Semaphore for image generation to prevent concurrent runs
image_semaphore = asyncio.Semaphore(1)

def cleanup_on_startup():
    """Kill other instances of Kaiacord and clear GPU memory"""
    current_pid = os.getpid()
    log_action(f"Startup cleanup (PID: {current_pid})...")
    
    for proc in psutil.process_iter(['pid', 'name', 'cmdline', 'exe']):
        try:
            cmdline = proc.info['cmdline']
            exe = proc.info['exe']
            
            # Check if it's a python process running Kaiacord.py
            is_python = exe and 'python' in exe.lower()
            is_kaiacord = cmdline and any('Kaiacord.py' in arg for arg in cmdline)
            
            if is_python and is_kaiacord and proc.info['pid'] != current_pid:
                log_action(f"  - Terminating orphaned instance: PID {proc.info['pid']}")
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                    log_success(f"  - PID {proc.info['pid']} terminated.")
                except psutil.TimeoutExpired:
                    log_warning(f"  - PID {proc.info['pid']} didn't terminate, killing...")
                    proc.kill()
                    log_success(f"  - PID {proc.info['pid']} killed.")
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
        except Exception as e:
            log_warning(f"Error checking process: {e}")

    # Clear GPU memory
    try:
        clear_gpu_memory()
    except Exception as e:
        log_warning(f"Failed to clear GPU memory: {e}")

# setup bot
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# Removed old global state variables (now in bot_state and config)

# Load persona from file
# PERSONA CACHING
_persona_cache = None
_persona_last_load = 0

def load_persona() -> str:
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
                "\n\n## CORE RULES\n"
                "- NO backticks (```), bolding (**), or italics (*).\n"
                "- BE SUBSTANTIAL & DIRECT. Grounded, lowercase, no fluff."
            )
            _persona_cache = content
            _persona_last_load = mtime
            return _persona_cache
    except Exception:
        if _persona_cache:
            return _persona_cache
        return "You are Kaia, a blunt and grounded resident of this server."

async def load_persona_async() -> str:
    """Load the bot's persona from kaia_persona.md with caching (Async)"""
    # File I/O is small, but we run it in a thread to keep the loop free
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, load_persona)

async def send_kaia_response(channel: discord.abc.Messageable, text: str):
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

# Initialize Intelligence Layer
semantic_cache = SemanticCache()
model_warm_pool = ModelWarmPool(ollama_client)
query_classifier = QueryClassifier(ollama_client)
context_optimizer = ContextOptimizer()
relevance_feedback = RelevanceFeedback(rag)

class KnowledgeBaseWatcher(FileSystemEventHandler):
    def __init__(self, rag, loop):
        self.rag = rag
        self.loop = loop
        self.debounce_task = None
        
    def on_modified(self, event):
        if event.is_directory:
            return
        # Schedule the update on the main loop
        asyncio.run_coroutine_threadsafe(self._debounced_update(event.src_path), self.loop)

    async def _debounced_update(self, path):
        if self.debounce_task:
            self.debounce_task.cancel()
            
        async def do_update():
            try:
                await asyncio.sleep(2) # Wait for writes to finish
                log_action(f"File changed: {path}. Triggering RAG refresh...")
                await asyncio.to_thread(self.rag.refresh_knowledge_base)
                log_success("Incremental RAG refresh complete.")
            except Exception as e:
                log_error(f"Incremental RAG refresh failed: {e}")
            
        self.debounce_task = asyncio.create_task(do_update())

def start_watcher(rag, loop):
    """Start the file system watcher for the knowledge base"""
    observer = Observer()
    event_handler = KnowledgeBaseWatcher(rag, loop)
    observer.schedule(event_handler, rag.knowledge_base_dir, recursive=True)
    observer.start()
    log_success(f"Knowledge base watcher started on {rag.knowledge_base_dir}")
    return observer

async def prewarm_main_model():
    """Prewarm the main chat model to avoid cold-start delay"""
    try:
        log_model_action(config.chat_model, "Prewarming main model")
        await ollama_client.chat(
            model=config.chat_model,
            messages=[{"role": "user", "content": "hi"}],
            options={
                "num_predict": 1,
                "num_ctx": 6144,  # Reduced from 8192 to save VRAM
                "num_thread": 8   # Explicitly set threads for faster processing
            }
        )
        log_success(f"Main model {config.chat_model} prewarmed.")
    except Exception as e:
        log_warning(f"Failed to prewarm main model: {e}")

@bot.event
async def on_ready():
    log_success(f"{bot.user.name} is online!")
    
    # Start the knowledge base watcher
    loop = asyncio.get_running_loop()
    start_watcher(rag, loop)
    
    # Prewarm the main Ollama model to avoid cold-start delay on first message
    # We don't prewarm the vision model here to avoid system lag
    asyncio.create_task(prewarm_main_model())
    
    if not idle_quip_task.is_running():
        idle_quip_task.start()
        
    if not rag_maintenance_task.is_running():
        rag_maintenance_task.start()
    
    # Refresh knowledge base in the background to avoid blocking boot
    log_action("Refreshing knowledge base in background...")
    asyncio.create_task(run_rag(rag.refresh_knowledge_base))

@tasks.loop(minutes=15)
async def idle_quip_task():
    """Generate a random quip if idle for too long"""
    idle_duration = time.time() - bot_state.last_interaction_time
    
    # Don't quip if we've hit consecutive limit
    if bot_state.consecutive_quips >= config.max_consecutive_quips:
        log_info(f"Max consecutive quips ({config.max_consecutive_quips}) reached. Waiting for user interaction.")
        return
    
    # Fallback: If we don't have a channel yet, find one we can speak in
    if not bot_state.last_active_channel_id:
        for guild in bot.guilds:
            # Sort channels to have some consistency, but prioritize non-blacklisted
            channels = sorted(guild.text_channels, key=lambda c: c.position)
            for channel in channels:
                if channel.permissions_for(guild.me).send_messages:
                    if channel.name.lower() not in config.blacklisted_channels:
                        bot_state.last_active_channel_id = channel.id
                        bot_state.save()
                        break
            if bot_state.last_active_channel_id: break

    if not bot_state.last_active_channel_id:
        return

    # Dynamic chance based on idle duration
    chance = 0.0
    if idle_duration >= 1800:  # 30 mins
        chance = 0.15
    if idle_duration >= 3600:  # 60 mins
        chance = 0.25
    if idle_duration >= 7200:  # 120 mins
        chance = 0.40
        
    if random.random() < chance:
        channel = bot.get_channel(bot_state.last_active_channel_id)
        if channel:
            try:
                log_action(f"Generating idle quip #{bot_state.consecutive_quips+1} (Idle: {int(idle_duration/60)}m)...")
                
                # RAG: Pull a random fragment from user logs to make fun of
                context_nodes = await run_rag(rag.retrieve, "recent user interaction", top_k=3)
                
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
                    model=config.chat_model,
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
                    bot_state.increment_quips()
                    
                    # Update interaction time so we don't spam
                    bot_state.update_interaction(channel.id)
                    
                    # Log Kaia's own quip to her user log
                    kaia_user_id = bot.user.id
                    kaia_name = bot.user.name
                    await run_rag(
                        rag.log_user_interaction,
                        kaia_user_id,
                        kaia_name,
                        "[IDLE_QUIP]",
                        content
                    )
                    
                    log_success(f"Sent idle quip #{bot_state.consecutive_quips}: {content[:50]}...")
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
async def on_message(msg: discord.Message):
    if msg.author == bot.user:
        return

    # TOTAL BLACKLIST: Ignore all messages in blacklisted channels
    if msg.channel.name.lower() in config.blacklisted_channels:
        return

    # Trigger logic: Original working "kaia" check
    if "kaia" not in msg.content.lower() and not bot.user.mentioned_in(msg):
        return
    
    # Rate Limiting
    if not rate_limiter.is_allowed(msg.author.id):
        log_warning(f"Rate limit hit for user {msg.author.name}")
        return

    # Reset consecutive quips counter on user interaction
    bot_state.reset_quips()

    # CHECK: Is Kaia currently busy generating an image?
    if generation_lock.locked():
        log_warning(f"Ignoring message from {msg.author.name} (image generation in progress)")
        if random.random() < 0.3: # Don't spam the busy message
            await msg.channel.send("```\nbusy rendering. wait your turn.\n```")
        return

    # Sanitize input
    sanitized_content = sanitize_prompt(msg.content)

    # Trigger logic: Image generation
    draw_match = re.search(r'kaia[\s,]+draw\s+(.*)', sanitized_content.lower())
    if draw_match:
        prompt = draw_match.group(1).strip()
            
        if not prompt:
            await msg.channel.send("```\ndraw what? i need a prompt.\n```")
            return
            
        # Use semaphore to ensure only one image generation at a time
        async with image_semaphore:
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
                try:
                    unload_image_model()
                except Exception as unload_err:
                    log_warning(f"Failed to unload image model: {unload_err}")
                    
                await asyncio.sleep(1.5)
                await prewarm_main_model()
        return

    # "kaia remember" command
    if sanitized_content.lower().startswith("kaia remember"):
        memory_content = sanitized_content[len("kaia remember"):].strip()
        if memory_content:
            log_action(f"Storing memory: {memory_content}")
            success = await run_rag(rag.add_memory, bot.user.id, bot.user.name, memory_content)
            if success:
                await msg.channel.send("```\nLogged it.\n```")
            else:
                await msg.channel.send("```\nMemory buffer error. Try again.\n```")
        else:
            await msg.channel.send("```\nRemember what? I'm not a mind reader.\n```")
        return

    # Initialize memory for the channel if it doesn't exist
    if msg.channel.id not in bot_state.channel_memory:
        bot_state.channel_memory[msg.channel.id] = deque(maxlen=config.max_memory_messages)

    # IMAGE VISION: Handle images and vision queries
    image_attachments = [
        att for att in msg.attachments 
        if any(att.filename.lower().endswith(ext) for ext in ['.png', '.jpg', '.jpeg', '.gif', '.webp'])
    ]
    
    # Check if this is an EXPLICIT vision request
    explicit_vision_keywords = ["analyze", "look"]
    is_explicit_vision_request = any(word in sanitized_content.lower() for word in explicit_vision_keywords)
    
    if ("kaia" in sanitized_content.lower() or bot.user.mentioned_in(msg)) and (image_attachments or is_explicit_vision_request):
        target_image_url = None
        
        if image_attachments:
            target_image_url = image_attachments[0].url
            log_info("Using image from current message.")
            
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

        if target_image_url:
            try:
                log_action("Processing vision task...")
                await msg.channel.send("```\nlooking...\n```")
                analysis = await kaia_sees_image(target_image_url, sanitized_content)
                await send_kaia_response(msg.channel, analysis)
                
                bot_state.channel_memory[msg.channel.id].append({"role": "user", "content": sanitized_content})
                bot_state.channel_memory[msg.channel.id].append({"role": "assistant", "content": analysis})
                
                bot_state.update_interaction(msg.channel.id)
                
                await run_rag(
                    rag.log_user_interaction,
                    msg.author.id,
                    msg.author.display_name,
                    f"{sanitized_content} [VISION_ANALYSIS]",
                    analysis,
                    is_vision_response=True
                )
                
                log_response("Got response:", analysis)
                log_separator()
                return
                
            except Exception as e:
                log_error(f"Vision analysis failed: {e}")
                traceback.print_exc()
                await msg.channel.send("```\ncan't process that image. something broke.\n```")
            finally:
                await asyncio.sleep(1.5)
                await prewarm_main_model()
            return

    try:
        log_message_received(msg.author.name, str(msg.author.id), sanitized_content)
        
        # PARALLEL PIPELINE: Fire off tasks concurrently
        clean_query = sanitized_content.lower().replace("kaia", "").strip("?,. ")
        display_name = msg.author.display_name.strip(".")
        
        target_user_id = msg.author.id
        target_user_name = msg.author.display_name
        
        if not clean_query or clean_query in ["who am i", "what am i"]:
            clean_query = f"Who is {display_name}?"
        elif clean_query in ["who are you", "what are you", "who is kaia"]:
            clean_query = "Who is Kaia?"
            target_user_id = bot.user.id
            target_user_name = bot.user.name

        log_context_retrieval(clean_query)
        
        # Define tasks
        persona_task = asyncio.create_task(load_persona_async())
        rag_task = asyncio.create_task(run_rag(
            rag.retrieve, 
            clean_query, 
            user_id=target_user_id, 
            user_name=target_user_name, 
            top_k=config.rag_top_k
        ))
        
        # Wait for both to complete
        system_prompt, context_nodes = await asyncio.gather(persona_task, rag_task)
        
        now = datetime.now()
        current_time_str = now.strftime("%A, %B %d, %Y %I:%M %p")
        system_prompt += f"\n\nToday is {current_time_str}."
        
        if context_nodes:
            format_rag_table(context_nodes)
        
        messages = []
        if context_nodes:
            context_str = "\n\n".join(context_nodes)
            rag_block = (
                f"### USER: {msg.author.display_name}\n"
                "### LOGS\n"
                "Fragments from conversation logs. 'User (Name):' is the speaker. "
                "Labels like 'User Profile: NAME' or 'Conversation History: NAME' indicate the subject. "
                "Use these to recognize people. Don't confuse USER with others unless names match.\n"
                "---\n"
                f"{context_str}\n"
                "---\n"
                "Logs are ongoing fragments."
            )
        else:
            rag_block = f"### CURRENT_USER: {msg.author.display_name}\nNo specific historical records found."

        messages.append({
            "role": "system", 
            "content": f"{system_prompt}\n\n{rag_block}"
        })
        
        history = list(bot_state.channel_memory[msg.channel.id])
        for m in history:
            if messages and messages[-1]["role"] == m["role"] and m["role"] != "system":
                messages[-1]["content"] += f"\n\n{m['content']}"
            else:
                messages.append(m.copy())
        
        messages.append({"role": "user", "content": sanitized_content})
 
        reinforcement = (
            "\n\n[RULES]\n"
            "1. NO backticks, bolding, or italics. Just plain text.\n"
            "2. NO META-TALK. Never mention being an AI, processing data, or using logs.\n"
            "3. BE SUBSTANTIAL. Blunt, grounded, lowercase. Provide depth on people/history. Keep it alive.\n"
            "4. NO name prefixes. Just start speaking.\n"
            "5. IDENTITY: Use 'User Profile' for deep summaries. No hallucinations. Never claim ignorance if records exist.\n"
            "6. 'Kaia Persona Fragment' are facts about YOU. Use only when asked about yourself.\n"
            "7. PRIVATE THOUGHTS: Never include internal labels like 'User Profile', 'Conversation History', or any bracketed tags in your response. Your inner thoughts and data labels must remain private."
        )

        messages.append({
            "role": "system",
            "content": reinforcement
        })

        log_action("Calling ollama.chat...")
        response = await ollama_client.chat(
            model=config.chat_model,
            messages=messages,
            options={
                "temperature": 0.8,
                "num_predict": 1536,
                "num_ctx": 6144,
                "num_thread": 8,
                "repeat_penalty": 1.1,
                "presence_penalty": 0.0,
                "frequency_penalty": 0.0,
                "top_p": 0.9,
            }
        )
        
        content = response['message']['content']
        prefixes_to_strip = [
            "Kaia:", "kaia:", "Assistant:", "Model:", "System:", 
            "Response:", "Observation:", "Thought:"
        ]
        for prefix in prefixes_to_strip:
            if content.startswith(prefix):
                content = content[len(prefix):].strip()
        
        content = content.replace("`", "")
        
        safety_patterns = [
            "Crisis Text Line", "National Domestic Violence Hotline", "National Suicide Prevention Lifeline",
            "1-800-", "reach out for help", "I am an AI", "Your question is harmful",
            "completely unacceptable", "respect and dignity", "I am reporting this interaction",
            "I strongly advise you to reconsider", "988", "741741", "National Suicide Prevention",
            "National Domestic Violence", "I cannot fulfill this request", "I will not respond to prompts",
            "The Trevor Project", "ethical concerns", "dangerous and destructive"
        ]
        
        if any(pattern.lower() in content.lower() for pattern in safety_patterns):
            log_warning("Detected safety lecture/helpline in response. Surgically stripping...")
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
                filtered_lines = [line for line in lines if not any(pattern.lower() in line.lower() for pattern in safety_patterns)]
                content = "\n".join(filtered_lines).strip()
                if not content:
                    content = "not doing that."

        log_response("Got response:", content)
        await send_kaia_response(msg.channel, content)
        
        bot_state.channel_memory[msg.channel.id].append({"role": "user", "content": sanitized_content})
        bot_state.channel_memory[msg.channel.id].append({"role": "assistant", "content": content})
        
        bot_state.update_interaction(msg.channel.id)
        
        await run_rag(
            rag.log_user_interaction,
            msg.author.id,
            msg.author.display_name,
            sanitized_content,
            content
        )
        
        log_success("Response sent successfully!")
        log_separator()
        
    except Exception as e:
        log_error(f"{type(e).__name__}: {e}")
        traceback.print_exc()
        await send_kaia_response(msg.channel, f"something broke: {e}")

async def main():
    """Main entry point for the bot"""
    if not config.discord_token:
        log_critical("DISCORD_TOKEN not found in environment variables!")
        sys.exit(1)

    # Run cleanup immediately on script execution
    cleanup_on_startup()
    
    try:
        async with bot:
            await bot.start(config.discord_token)
    except asyncio.CancelledError:
        pass
    finally:
        log_critical("\nShutting down...")
        
        # 1. Persist RAG index
        if rag:
            log_action("Persisting RAG index...")
            await run_rag(rag.persist, force=True)
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