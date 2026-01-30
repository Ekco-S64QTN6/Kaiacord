import os
import sys
import asyncio
import uuid

# Set PyTorch CUDA allocator to use expandable segments to reduce fragmentation
# These MUST be set before torch or any library that uses it is imported
os.environ["PYTORCH_ALLOC_CONF"] = "expandable_segments:True,max_split_size_mb:512"
os.environ["PYTORCH_CUDA_ALLOC_CONF"] = "expandable_segments:True,max_split_size_mb:512"

# Initialize Unified Logging EARLY
from utils.unified_logging import replace_all_logging, logger
replace_all_logging()

# Initialize Stats Tracker
from utils.stats_tracker import stats_tracker
from utils.stats_poller import stats_poller
from utils.stats_helpers import (
    set_stats_poller, safe_start_stats_poller, safe_stop_stats_poller,
    is_stats_poller_available
)

# Initialize Dashboard (ANSI fallback)
from utils.btop_dashboard_legacy import BtopDashboard
# Curses dashboard (opt-in via KAIA_DASHBOARD=curses)
from utils.btop_dashboard_v2 import BtopDashboardV2
from utils.shutdown_fixed import shutdown_manager
from utils.news_debug import diagnose_news_pipeline, fix_news_ingestion
import curses
import threading

import re
import traceback
import random
import time
import datetime
from datetime import datetime
from pathlib import Path
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
from utils.kaia_rag import KaiaRAG, HallucinationDetector
from utils.kaia_image import generate_image, unload_image_model, generation_lock, is_image_gen_available
from utils.async_task_registry import task_registry
from utils.kaia_vision import kaia_sees_image, cleanup_session
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from utils.boilerplate_detector import BoilerplateDetector
from utils.kaia_intelligence import SemanticCache, ModelWarmPool, ContextOptimizer, RelevanceFeedback, PerformanceMonitor, PersonalizationEngine, PersistentStateManager, IntelligentCacheInvalidator, QueryClassifier
from utils.performance_optimizer import ResponseOptimizer, timed_response
from utils.knowledge_boundary import KnowledgeBoundary
# Load environment variables early so Config can use them
load_dotenv()

# EMERGENCY GPU FALLBACK
try:
    from utils.gpu_manager import OllamaGPUManager, GPUMonitor, LoggingPatcher
    gpu_available = True
except ImportError as e:
    print(f"⚠️  GPU Manager import failed: {e}")
    print("⚠️  Using CPU fallback mode")
    
    # Create dummy GPU classes
    class GPUMonitor:
        @staticmethod
        def get_gpu_info():
            return None
        
        @staticmethod 
        def is_gpu_available():
            return False
    
    class OllamaGPUManager:
        def __init__(self, model_name):
            self.model_name = model_name
            self.gpu_available = False
        
        async def ensure_gpu_loading(self, ollama_client):
            return False
        
        def get_gpu_options(self, for_chat=True):
            return {'num_thread': 8}  # CPU fallback
    
    gpu_available = False
from utils.clear_gpu_memory import clear_gpu_memory
from utils.kaia_logger import (
    log_success, log_info, log_warning, log_error, log_critical,
    log_action, log_model_action, log_message_received, log_response,
    log_context_retrieval, log_separator, set_monitor, log_debug
)
from utils.kaia_news import NewsRetrievalEnhancer, ResponseEnhancer, RAGEnhancer, NewsManager
# from utils.btop_dashboard import BtopDashboard, KaiaMonitor, BtopLoggingPatcher # Removed conflicting import

# GLOBAL KILL SWITCHES
# NOTE: News auto-trigger disabled intentionally.
# TODO: Re-enable only via explicit command (e.g. /news or kaia news).
NEWS_AUTO_TRIGGER_ENABLED = False

# Import managers from bot package
from bot.managers.config import Config, config
from bot.managers.state import BotState, bot_state
from bot.managers.rate_limiter import RateLimiter

# Rate limiter instance
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
    # REQUIREMENT: Prevent RAG from running during image gen
    if getattr(bot_state, 'is_generating_image', False):
        log_warning(f"RAG operation suppressed: image generation in progress")
        # Return empty list for retrieve, None for others
        fn_name = str(fn)
        if 'retrieve' in fn_name: return []
        return None
        
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

# Initialize Enhancers
news_enhancer = NewsRetrievalEnhancer()
news_manager = NewsManager()
response_enhancer = ResponseEnhancer()
rag_enhancer = RAGEnhancer()

def get_known_users() -> List[str]:
    """Scan knowledge base for actual user profiles to prevent hallucinations"""
    users = []
    
    # Check logs (primary source of truth)
    logs_dir = Path("./knowledge_base/user_logs")
    if logs_dir.exists():
        # user_logs contains directories like "Username_123456789/"
        for d in logs_dir.iterdir():
            if d.is_dir():
                # Extract name part (everything before the last underscore usually, but ID is long digits)
                # Format is usually Name_ID
                parts = d.name.split('_')
                if len(parts) > 1 and parts[-1].isdigit():
                    name = "_".join(parts[:-1]).replace("_", " ")
                else:
                    name = d.name.replace("_", " ")
                
                # Try to read profile summary
                profile_path = d / "user_profile.md"
                summary = "No profile available."
                if profile_path.exists():
                    try:
                        with open(profile_path, 'r', encoding='utf-8') as f:
                            content = f.read()
                            # Extract QUICK REFERENCE section
                            if "QUICK REFERENCE" in content:
                                start = content.find("QUICK REFERENCE")
                                end = content.find("\n\n", start + 20) # Find next double newline
                                if end == -1: end = len(content)
                                summary = content[start:end].replace("QUICK REFERENCE", "").strip()
                            else:
                                # Fallback to first few lines
                                summary = "\n".join(content.split('\n')[:5])
                    except Exception:
                        pass
                
                # Check if we already have this user (by name)
                # We need to store dicts or formatted strings now
                # Let's use a dict for deduplication then convert
                users.append({"name": name, "summary": summary})
                 
    # Deduplicate by name
    unique_users = {}
    for u in users:
        unique_users[u['name']] = u['summary']
        
    # Format as strings
    return [f"User: {name}\nSummary: {summary}" for name, summary in sorted(unique_users.items())]

# Initialize Bot
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
    persona_file = os.path.join(os.path.dirname(__file__), 'knowledge_base', 'kaia_persona.md')
    
    try:
        mtime = os.path.getmtime(persona_file)
        if _persona_cache and mtime <= _persona_last_load:
            return _persona_cache
            
        with open(persona_file, 'r', encoding='utf-8') as f:
            content = f.read().strip()
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
        log_warning("send_kaia_response called with empty text. Skipping.")
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

def extract_node_content(node) -> str:
    """Extract text content from RAG node regardless of format (DRY helper)."""
    if hasattr(node, 'text'):
        return node.text
    if hasattr(node, 'content'):
        return node.content
    if isinstance(node, dict):
        return node.get('text') or node.get('content') or str(node)
    return str(node)

# Create async client
ollama_client = ollama.AsyncClient()

from utils.unified_logging import log_ollama_interaction

# Initialize RAG
rag = KaiaRAG()

# ADD THIS TO YOUR IMPORTS
import re
from datetime import datetime, timedelta

class ImprovedSemanticCache:
    """Enhanced semantic cache with keyword pollution protection"""
    
    def __init__(self, threshold: float = 0.85):
        self.cache = {}
        self.exact_cache = {} # For compatibility with PersistentStateManager
        self.access_counts = {} # For compatibility with IntelligentCacheInvalidator
        self.threshold = threshold
        self.load_exceptions()
        self.load()
    
    def load_exceptions(self):
        """Load cache exceptions from file"""
        try:
            with open("config/cache_exceptions.json", "r") as f:
                self.exceptions = json.load(f)
        except:
            # Default exceptions
            self.exceptions = {
                "never_cache": [
                    "68k.news", "headlines from", "january", "february",
                    "news", "update", "breaking", "latest"
                ],
                "always_regenerate": ["news", "headline", "report", "update"],
                "keyword_blacklist": []
            }
    
    def should_cache_query(self, query: str, classification: str) -> bool:
        """Determine if a query should be cached at all"""
        query_lower = query.lower()
        
        # Never cache identity queries
        if classification in ["IDENTITY", "WHOAMI", "SELF"]:
            return False
        
        # Never cache queries with time/date references
        if any(phrase in query_lower for phrase in self.exceptions["never_cache"]):
            return False
        
        # Don't cache very short queries
        if len(query.strip()) < 10:
            return False
        
        # Don't cache queries with numbers (likely dates/versions)
        if re.search(r'\b\d{4}\b', query):  # Years like 2026
            return False
        
        # Don't cache queries with URLs
        if re.search(r'https?://', query_lower):
            return False
        
        return True
    
    def get_cache_key(self, query: str) -> str:
        """Create a normalized cache key"""
        # Remove extra whitespace
        normalized = ' '.join(query.strip().split())
        
        # Remove specific date patterns
        normalized = re.sub(r'\b(january|february|march|april|may|june|july|august|september|october|november|december)\s+\d{1,2},\s+\d{4}\b', 
                          '[DATE]', normalized, flags=re.IGNORECASE)
        
        # Remove years
        normalized = re.sub(r'\b\d{4}\b', '[YEAR]', normalized)
        
        # Remove numbers in headlines
        normalized = re.sub(r'\b\d+\b', '[NUMBER]', normalized)
        
        return normalized.lower()
    
    def get(self, query: str, classification: str) -> Optional[str]:
        """Get cached response if available and relevant"""
        if not self.should_cache_query(query, classification):
            if hasattr(performance_monitor, 'record_miss'):
                performance_monitor.record_miss()
            return None
        
        cache_key = self.get_cache_key(query)
        
        # Check for exact match first
        if cache_key in self.cache:
            entry = self.cache[cache_key]
            # Check if entry is expired (24 hours for news, 7 days for others)
            expiry_hours = 24 if any(word in query.lower() for word in ["news", "headline"]) else 168
            if datetime.now() - datetime.fromisoformat(entry["timestamp"]) < timedelta(hours=expiry_hours):
                if hasattr(performance_monitor, 'record_hit'):
                    performance_monitor.record_hit(exact=True)
                return entry["response"]
        
        # Check for semantic similarity (existing logic)
        for cached_query, entry in self.cache.items():
            similarity = self.calculate_similarity(cache_key, cached_query)
            
            # Higher threshold for news-related queries
            required_threshold = 0.95 if any(word in query.lower() for word in ["news", "headline"]) else self.threshold
            
            if similarity > required_threshold:
                # Additional check: don't return cached news for different dates
                if self.is_different_news(query, cached_query):
                    continue
                if hasattr(performance_monitor, 'record_hit'):
                    performance_monitor.record_hit()
                return entry["response"]
        
        if hasattr(performance_monitor, 'record_miss'):
            performance_monitor.record_miss()
        return None
    
    def is_different_news(self, query1: str, query2: str) -> bool:
        """Check if two news queries are about different dates/topics"""
        # Extract dates
        date_pattern = r'\b(january|february|march|april|may|june|july|august|september|october|november|december)\s+\d{1,2},\s+\d{4}\b'
        
        date1 = re.search(date_pattern, query1, re.IGNORECASE)
        date2 = re.search(date_pattern, query2, re.IGNORECASE)
        
        # If both have dates and they're different, they're different news
        if date1 and date2 and date1.group(0).lower() != date2.group(0).lower():
            return True
        
        # Check for different years
        year1 = re.search(r'\b\d{4}\b', query1)
        year2 = re.search(r'\b\d{4}\b', query2)
        if year1 and year2 and year1.group(0) != year2.group(0):
            return True
        
        return False
    
    def set(self, query: str, classification: str, response: str):
        """Cache a response"""
        if not self.should_cache_query(query, classification):
            return
        
        cache_key = self.get_cache_key(query)
        
        self.cache[cache_key] = {
            "response": response,
            "timestamp": datetime.now().isoformat(),
            "classification": classification,
            "original_query": query[:200]  # Store original for debugging
        }
        
        # Limit cache size
        if len(self.cache) > 1000:
            # Remove oldest entries
            sorted_entries = sorted(self.cache.items(), 
                                   key=lambda x: x[1]["timestamp"])
            for key, _ in sorted_entries[:100]:
                del self.cache[key]
    
    def calculate_similarity(self, query1: str, query2: str) -> float:
        """Calculate similarity between two queries"""
        # Simple Jaccard similarity for now
        # In production, you'd use embeddings
        words1 = set(query1.lower().split())
        words2 = set(query2.lower().split())
        
        if not words1 or not words2:
            return 0.0
        
        intersection = len(words1.intersection(words2))
        union = len(words1.union(words2))
        
        return intersection / union
    
    def save(self):
        """Save cache to disk"""
        with open("storage/semantic_cache.json", "w") as f:
            json.dump(self.cache, f, indent=2)
    
    def load(self):
        """Load cache from disk"""
        try:
            if os.path.exists("storage/semantic_cache.json"):
                with open("storage/semantic_cache.json", "r") as f:
                    self.cache = json.load(f)
        except:
            self.cache = {}

    def invalidate_exact(self, query):
        """For compatibility with IntelligentCacheInvalidator"""
        cache_key = self.get_cache_key(query)
        if cache_key in self.cache:
            del self.cache[cache_key]
            return True
        return False

    def invalidate_semantic_by_query(self, query):
        """For compatibility with IntelligentCacheInvalidator"""
        return self.invalidate_exact(query)

class EmergencyContaminationFilter:
    """Emergency filter to prevent ANY fictional content"""
    
    CONTAMINATION_PATTERNS = [
        r'\belena\b', r'\bjuanita\b', r'\bdeane\b', r'\bbonbons\b',
        r'\bthink tank\b', r'\bmiddle eastern affairs\b',
        r'\bi remember (a|the) conversation with\b',
        r'\bshe (said|worked|was)\b.*?\b(?:in|at|for)\b',
        r"\bback in (?:'90s|\d{4})\b",
        r'\bmark\b', r'\bxerox\b',
        r'\bi remember (a|the) guy\b',
        r'\belara vance\b', r'\baurora labs\b', r'\baurora project\b',
        r'\bkael drakkel\b', r'\bxylarite\b', r'\bstonecutters\b',
        r'\bcrimson hand\b'
    ]
    
    @classmethod
    def filter_response(cls, response: str) -> str:
        """Remove ANY contamination from response"""
        import re
        
        lines = response.split('\n')
        filtered_lines = []
        
        for line in lines:
            line_lower = line.lower()
            
            # Skip lines with contamination
            skip_line = False
            for pattern in cls.CONTAMINATION_PATTERNS:
                if re.search(pattern, line_lower):
                    skip_line = True
                    log_warning(f"[EMERGENCY FILTER] Removed contaminated line: {line[:80]}...")
                    break
            
            if not skip_line:
                filtered_lines.append(line)
        
        filtered_response = '\n'.join(filtered_lines)
        
        # CRITICAL: Never return empty - if filtering emptied response, return original
        if not filtered_response.strip():
            return response
        
        return filtered_response
    
    @classmethod
    def clean_response_for_discord(cls, response: str) -> str:
        """
        Remove any user profile data, metadata, or analysis text from responses.
        This prevents Kaia from accidentally including internal profiling data in her chat responses.
        """
        # Split response into lines
        lines = response.split('\n')
        cleaned_lines = []
        
        # Skip any lines that look like user profiles or system metadata
        skip_patterns = [
            'user profile:',
            '## user profile:',
            'updated personalization for',
            '[optimized: saved',
            'interaction indexed',
            'logs indexed:',
            'rag context:',
            'metadata:',
            'nodes retrieved:',
            'quick reference',
            'how to interact with them',
            'shared history & context',
            'their interests & expertise',
            'conversation style notes',
            'relationship status with kaia',
            'potential triggers & sensitivities',
            'growth opportunities'
        ]
        
        in_profile_block = False
        
        for line in lines:
            stripped = line.strip()
            if not stripped:
                if not in_profile_block:
                    cleaned_lines.append(line)
                continue
                
            line_lower = stripped.lower()
            
            # Check if line starts a profile block or is a metadata line
            # We only skip if the line STARTS with these patterns to avoid false positives in dialogue
            is_metadata = any(line_lower.startswith(pattern) for pattern in skip_patterns)
            is_header = stripped.startswith('#') or stripped.endswith(':')
            
            if is_metadata:
                if is_header:
                    in_profile_block = True
                continue
                
            # If in a profile block, check if we should exit
            if in_profile_block:
                # Dialogue usually starts with lowercase or common dialogue words
                # Or if it's a normal sentence that doesn't look like a bullet/metadata
                is_dialogue = stripped[0].islower() or any(line_lower.startswith(w) for w in ["yeah", "no", "well", "i ", "you ", "it's ", "that's "])
                is_bullet = stripped.startswith('- ') or stripped.startswith('* ') or (len(stripped) > 1 and stripped[0].isdigit() and stripped[1] == '.')
                
                if is_dialogue and not is_bullet:
                    in_profile_block = False
                else:
                    # Still in profile block, skip this line
                    continue
            
            # Additional check: skip lines that are just "User Profile" or similar if they slipped through
            if line_lower in [p.strip(':') for p in skip_patterns]:
                continue
            
            # Final check for specific contamination
            if 'Alan Turing' in line and ('mathematician' in line or 'computer scientist' in line):
                continue
            if 'This response was generated' in line or 'The following analysis' in line:
                continue
                
            cleaned_lines.append(line)
        
        # Rejoin lines
        cleaned_response = '\n'.join(cleaned_lines)
        
        # Additional cleanup: Remove any trailing metadata that might have slipped through
        end_markers = ['.', '?', '!', '...', '...']
        for marker in end_markers:
            if marker in cleaned_response:
                last_marker_pos = cleaned_response.rfind(marker)
                if last_marker_pos > len(cleaned_response) * 0.5:
                    next_char = cleaned_response[last_marker_pos + len(marker):].strip()
                    if next_char and not next_char[0].islower():
                        following_text = cleaned_response[last_marker_pos + len(marker):]
                        if any(x in following_text for x in ['User', 'Profile:', 'optimized:', 'Updated']):
                            cleaned_response = cleaned_response[:last_marker_pos + len(marker)]
        
        result = cleaned_response.strip()
        
        # CRITICAL: Never return empty - if cleaning emptied response, return original
        if not result:
            return response
        
        return result
    
    @classmethod
    def expand_news_query(cls, query: str) -> List[str]:
        """Expand news-related queries for better RAG retrieval"""
        expansions = []
        
        news_keywords = ["news", "update", "recent", "happening", "today", "latest", "headlines"]
        
        if any(keyword in query.lower() for keyword in news_keywords):
            # Add date-based expansions
            today = datetime.now().strftime("%Y-%m-%d")
            expansions.append(f"{query} {today}")
            expansions.append(f"news brief {today}")
            expansions.append(f"daily digest {today}")
            
            # Add section-based expansions
            expansions.append(f"tech outages {today}")
            expansions.append(f"security incidents {today}")
            expansions.append(f"AI developments {today}")
        
        return expansions

# Initialize Intelligence Layer
performance_monitor = PerformanceMonitor()
semantic_cache = ImprovedSemanticCache(threshold=0.92)
model_warm_pool = ModelWarmPool(ollama_client)
query_classifier = QueryClassifier(ollama_client, model=config.chat_model, timeout=5.0)
# [CONSOLIDATED] NewsManager is initialized globally as news_manager
response_optimizer = ResponseOptimizer()
context_optimizer = ContextOptimizer(model_name=config.chat_model)
relevance_feedback = RelevanceFeedback(rag)
personalization_engine = PersonalizationEngine()
state_manager = PersistentStateManager()
cache_invalidator = IntelligentCacheInvalidator(semantic_cache)

class SelfHealingSystem:
    """Execute functions with fallback strategies."""
    @staticmethod
    async def call_with_fallback(func, *args, **kwargs):
        original_options = kwargs.get('options', {}).copy()  # Save GPU options
        
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            log_warning(f"Primary strategy failed: {e}. Trying simplified fallback...")
            
            # Fallback: Reduce context but PRESERVE GPU SETTINGS
            if 'messages' in kwargs:
                # Keep only system and last few messages
                kwargs['messages'] = [kwargs['messages'][0]] + kwargs['messages'][-2:]
            
            if 'options' in kwargs:
                # Merge: Keep original GPU options, only adjust response length
                kwargs['options'] = {**original_options, 'num_predict': 512}
            
            try:
                return await func(*args, **kwargs)
            except Exception as e2:
                log_error(f"Fallback failed: {e2}")
                raise e2

async def send_typing_feedback(channel, query):
    """Show typing indicator based on query complexity."""
    words = query.split()
    # Estimate complexity: long queries or technical keywords
    is_complex = len(words) > 10 or any(kw in query.lower() for kw in ['how', 'why', 'code', 'explain'])
    
    if is_complex:
        async with channel.typing():
            await asyncio.sleep(2) # Artificial delay for "thinking" feel
    else:
        async with channel.typing():
            await asyncio.sleep(0.5)

class KnowledgeBaseWatcher(FileSystemEventHandler):
    def __init__(self, rag, loop):
        self.rag = rag
        self.loop = loop
        self.queue = asyncio.Queue()
        self.processing_task = None
        
    def on_modified(self, event):
        if event.is_directory: return
        # Add to queue
        asyncio.run_coroutine_threadsafe(self.queue.put(event.src_path), self.loop)

    async def start_processing(self):
        """Dedicated task to process the file change queue."""
        log_success("Watchdog queue processor started.")
        while True:
            path = await self.queue.get()
            try:
                # Debounce: wait a bit for more changes
                await asyncio.sleep(2)
                # Clear any other pending changes for the same path
                while not self.queue.empty():
                    try:
                        self.queue.get_nowait()
                        self.queue.task_done()
                    except asyncio.QueueEmpty: break
                
                log_action(f"Processing queued change: {path}")
                # Invalidate cache for this file
                cache_invalidator.invalidate_for_file(path)
                await asyncio.to_thread(self.rag.refresh_knowledge_base)
                log_debug("Incremental RAG refresh complete.")
            except Exception as e:
                log_error(f"Watchdog processing failed: {e}")
            finally:
                self.queue.task_done()

def start_watcher(rag, loop):
    """Start the file system watcher for the knowledge base"""
    observer = Observer()
    event_handler = KnowledgeBaseWatcher(rag, loop)
    observer.schedule(event_handler, rag.knowledge_base_dir, recursive=True)
    observer.start()
    # Start the queue processor
    event_handler.processing_task = asyncio.create_task(event_handler.start_processing())
    log_success(f"Knowledge base watcher started on {rag.knowledge_base_dir}")
    return observer

async def prewarm_main_model():
    """Pre-warm the main chat model with GPU settings"""
    # Check if we're shutting down
    if shutdown_manager.shutting_down:
        return

    try:
        gpu_manager = OllamaGPUManager(config.chat_model)
        gpu_options = gpu_manager.get_gpu_options(for_chat=True)
        
        # Trigger GPU load without full chat test
        success = await gpu_manager.load_only(ollama_client)
        
        # ensure_gpu_loading already performs a chat call to verify the load.
        # We don't need a second one here which just adds latency.
        if success:
            print(f"✅ {config.chat_model} loaded and verified on GPU")
        else:
            print(f"⚠️  {config.chat_model} falling back to CPU")
            
    except Exception as e:
        if not shutdown_manager.shutting_down:
            print(f"⚠️  Pre-warm failed: {e}")

async def unload_chat_model():
    """Explicitly unload the chat model to free VRAM"""
    try:
        log_action(f"Unloading chat model {config.chat_model}...")
        await OllamaGPUManager.unload_model(ollama_client, config.chat_model)
        log_success("Chat model unloaded.")
    except Exception as e:
        log_warning(f"Failed to unload chat model: {e}")

@bot.command(name="news")
async def news_command(ctx, *, category: Optional[str] = None):
    """Manual news retrieval command
    
    Usage:
        !news - Get latest general/world news
        !news today - Get today's news summary
        !news technology - Get technology news
        !news hacker - Get hacker/security news
        !news [category] - Get news for specific category
    """
    log_action(f"Manual news request from {ctx.author} (Category: {category or 'general'})")
    
    try:
        # Default to general if no category specified
        if not category:
            category = "general"
        
        # Normalize category
        category = category.lower().strip()
        
        # Get news from manager
        news_content = news_manager.get_news(category)
        
        if news_content:
            # Send news in chunks if needed
            await send_kaia_response(ctx.channel, f"📰 **{category.title()} News**\n\n{news_content}")
            log_success(f"Sent {category} news to {ctx.author}")
        else:
            await ctx.send(f"```\nNo {category} news found. Try updating: `python tools/maintenance/update_kaia_news.py`\n```")
            log_warning(f"No {category} news available")
    
    except Exception as e:
        log_error(f"Error retrieving news: {e}")
        await ctx.send("```\nError retrieving news. Check logs for details.\n```")


async def sequenced_boot_tasks():
    """
    Run heavy boot tasks SEQUENTIALLY to prevent system overload.
    
    Order:
    1. RAG refresh/storage rebuild (CPU + Disk I/O intensive)
    2. News update (Network + CPU)
    3. GPU model loading (GPU + Memory intensive)
    
    This prevents the system freeze that occurs when all three run concurrently.
    """
    log_info("📦 Phase 1/3: Rebuilding knowledge index...")
    
    # 1. FIRST: RAG refresh/storage rebuild
    try:
        await run_rag(rag.refresh_knowledge_base)
        log_success("📦 Knowledge index ready.")
    except Exception as e:
        log_error(f"RAG refresh failed: {e}")
    
    # 2. SECOND: News update
    log_info("📰 Phase 2/3: Updating news...")
    try:
        await run_news_update()
        log_success("📰 News update complete.")
    except Exception as e:
        log_error(f"News update failed: {e}")
    
    # 3. LAST: GPU model loading
    log_info("🧠 Phase 3/3: Loading chat model into VRAM...")
    try:
        await prewarm_main_model()
        log_success("🧠 Chat model ready.")
    except Exception as e:
        log_error(f"Model prewarm failed: {e}")
    
    log_success("✅ Boot sequence complete.")
    bot_state.boot_complete = True


@bot.event
async def on_ready():
    # Dashboard is started in main()
    
    # Set initial metrics
    stats_tracker.set_stat('ollama_status', "🟢 ONLINE")
    stats_tracker.set_stat('active_model', config.chat_model)
    logger.log(f"{bot.user.name} is online!", "SUCCESS")
    
    log_success(f"{bot.user.name} is online!")
    
    # Start the knowledge base watcher
    loop = asyncio.get_running_loop()
    start_watcher(rag, loop)
    
    # Start the memory audit task
    memory_audit_task.start()
    
    # Load cold state
    state_manager.load_state(semantic_cache, personalization_engine, performance_monitor)
    
    if not idle_quip_task.is_running():
        idle_quip_task.start()
        
    if not rag_maintenance_task.is_running():
        rag_maintenance_task.start()
    
    # Start periodic news refresh (this just schedules future runs, doesn't run immediately)
    if not news_refresh_task.is_running():
        news_refresh_task.start()
    
    # Start social media mention polling
    if not social_mention_task.is_running():
        social_mention_task.start()
    
    # SEQUENCED BOOT: Run heavy tasks in order to prevent system overload
    # This replaces the previous concurrent asyncio.create_task() calls
    asyncio.create_task(sequenced_boot_tasks())

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
                
                # Add news to idle quips occasionally (20% chance)
                news_nodes = []
                if NEWS_AUTO_TRIGGER_ENABLED and random.random() < 0.20:
                    news_nodes = await run_rag(rag.retrieve, f"news brief {datetime.now().strftime('%Y-%m-%d')}", top_k=2)
                
                # Pull recent quips to avoid repetition
                recent_quips = await run_rag(rag.retrieve, "[IDLE_QUIP]", top_k=5)
                
                context_str = ""
                if context_nodes:
                    context_str = "\n\n[LOG_CONTEXT]\n" + "\n---\n".join(context_nodes)
                
                if news_nodes:
                    context_str += "\n\n[NEWS_CONTEXT]\n" + "\n---\n".join(news_nodes)
                
                if recent_quips:
                    context_str += "\n\n[RECENT_QUIPS_TO_AVOID_REPEATING]\n" + "\n---\n".join(recent_quips)
                
                system_prompt = load_persona()
                
                messages = [
                    {"role": "system", "content": system_prompt + context_str},
                    {"role": "user", "content": "Generate a short, witty idle thought or observation. 1-2 sentences max. "
                        "If there's log context, comment on something interesting or amusing from it - NO mocking. "
                        "Tone: dry humor, observational, like a coworker sharing a random thought. "
                        "Examples: 'why does every third error message include the word unexpected?', "
                        "'noticed someone was debugging at 3am again. respect.', "
                        "'that mana curve you posted is bold. i respect the chaos.' "
                        "If no context, share a wry observation about tech, coffee, or the strange things people do. "
                        "NO questions directed AT users. Just a standalone musing. "
                        "CRITICAL: Do not repeat or rephrase anything in the [RECENT_QUIPS_TO_AVOID_REPEATING] section. "
                        "No fluff. No intro. Just the thought."}
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
                
                # Log interaction
                log_ollama_interaction(str(messages), response['message']['content'])
                
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
                    
                    # Cross-post to Bluesky if enabled
                    if config.bluesky_enabled and config.bluesky_cross_post_quips:
                        try:
                            from utils.kaia_bluesky import post_quip_to_bluesky, is_bluesky_configured
                            if is_bluesky_configured():
                                bluesky_success = await post_quip_to_bluesky(content)
                                if bluesky_success:
                                    log_success("Cross-posted quip to Bluesky")
                        except Exception as bsky_e:
                            log_warning(f"Bluesky cross-post failed: {bsky_e}")
                    
                    # Cross-post to X if enabled
                    if config.x_enabled and config.x_cross_post_quips:
                        try:
                            from utils.kaia_twitter import post_quip_to_x, is_x_configured
                            if is_x_configured():
                                x_success = await post_quip_to_x(content)
                                if x_success:
                                    log_success("Cross-posted quip to X")
                        except Exception as x_e:
                            log_warning(f"X cross-post failed: {x_e}")
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

@tasks.loop(hours=6)
async def news_refresh_task():
    """Periodic news refresh to keep the database current."""
    try:
        log_action("Running periodic news refresh...")
        # Run refresh_news.py as a subprocess to avoid blocking
        process = await asyncio.create_subprocess_exec(
            sys.executable, "tools/maintenance/refresh_news.py",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()
        if process.returncode == 0:
            log_success("Periodic news refresh completed.")
        else:
            log_error(f"Periodic news refresh failed: {stderr.decode()}")
    except Exception as e:
        log_error(f"News refresh task failed: {e}")

@tasks.loop(minutes=5)
async def social_mention_task():
    """Check and reply to social media mentions on Bluesky and X."""
    # Skip if boot not complete
    if not bot_state.boot_complete:
        return
    
    try:
        from utils.kaia_social_responder import check_and_reply_mentions
        await check_and_reply_mentions()
    except Exception as e:
        log_error(f"Social mention task failed: {e}")

async def run_news_update():
    """Run the daily news update script."""
    try:
        log_action("Running daily news update script...")
        # Check for Gemini API key
        if not os.getenv("GEMINI_API_KEY"):
            log_warning("GEMINI_API_KEY not set, skipping automated news update.")
            return

        # Run with live output streaming
        process = await asyncio.create_subprocess_exec(
            sys.executable, "tools/maintenance/update_kaia_news.py",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT  # Merge stderr to stdout
        )
        
        # Stream output line by line for live progress
        async for line in process.stdout:
            decoded = line.decode().strip()
            if decoded:
                print(f"  {decoded}")  # Show in dashboard
        
        await process.wait()
        
        if process.returncode == 0:
            log_success("Daily news update completed.")
            # Trigger RAG refresh after news update
            await run_rag(rag.refresh_knowledge_base)
        else:
            log_error("Daily news update failed. Check output above.")
    except Exception as e:
        log_error(f"Failed to run news update: {e}")

# Memory audit tracking variables (module-level)
_last_log_rss = 0.0
_last_log_cache_size = -1
_first_run = True

@tasks.loop(minutes=15)
async def memory_audit_task():
    """Periodic memory audit and cleanup."""
    global _last_log_rss, _last_log_cache_size, _first_run
    try:
        process = psutil.Process()
        rss_mb = process.memory_info().rss / 1024 / 1024
        # Conditional Memory Audit Logging
        current_rss = rss_mb
        current_cache_size = len(semantic_cache.cache)
        
        rss_delta = abs(current_rss - _last_log_rss)
        cache_changed = current_cache_size != _last_log_cache_size
        
        if _first_run or rss_delta >= 50.0 or cache_changed:
            log_info(f"Memory Audit: RSS {rss_mb:.1f} MB | Cache: {current_cache_size} entries")
            _last_log_rss = current_rss
            _last_log_cache_size = current_cache_size
            _first_run = False
        else:
            # Downgrade to debug if not significant
            log_debug(f"Memory Audit: RSS {rss_mb:.1f} MB | Cache: {current_cache_size} entries")
        
        # If RSS > 8GB, trigger emergency cleanup
        # Skip if image generation is active to avoid interrupting Flux load
        # Flux needs more headroom (10GB)
        threshold = 10240 if bot_state.is_generating_image else 8192
        
        if rss_mb > threshold and not bot_state.is_generating_image:
            log_critical(f"Memory usage critical ({rss_mb:.1f}MB > {threshold}MB)! Clearing caches and GPU memory.")
            semantic_cache.cache.clear()
            semantic_cache.exact_cache.clear()
            clear_gpu_memory()
        elif rss_mb > threshold and bot_state.is_generating_image:
             log_warning(f"Memory usage high ({rss_mb:.1f}MB), but skipping cleanup due to active image generation.")
            
        # Report performance stats (Disabled per user request to reduce clutter)
        # log_info(performance_monitor.get_report())
        
        # Cleanup rate limiter to prevent unbounded memory growth
        rate_limiter.cleanup()
        
        # Save state
        state_manager.save_state(semantic_cache, personalization_engine, performance_monitor)
    except Exception as e:
        log_error(f"Memory audit failed: {e}")

async def handle_proper_news_query(message, query, category=None):
    """PROPER news handler that reads from actual files"""
    try:
        async with message.channel.typing():
            
            # Use consolidated NewsManager from global import
            from utils.kaia_news import NewsManager
            news_reader = news_manager  # Use global instance
            query_lower = query.lower()
            
            if not category:
                import re
                # Use regex with word boundaries to avoid partial matches like "ai" in "daily"
                cat_patterns = {
                    'politics': [r'\bpolitic', r'\belection', r'\bgovernment'],
                    'technology': [r'\btech', r'\bai\b', r'\bsoftware', r'\bhardware'],
                    'security': [r'\bsecurity', r'\bcyber', r'\bhack', r'\bcve'],
                    'business': [r'\bbusiness', r'\beconom', r'\bmarket'],
                    'science': [r'\bscience', r'\bresearch'],
                    'culture': [r'\bculture', r'\bmovie', r'\btv', r'\bmusic', r'\bgame', r'\bart', r'\bsociety'],
                    'hacker': [r'\bhacker', r'\blapsus', r'\banonymous', r'\bapt', r'\bctf']
                }
                
                # Check for specific categories first
                for cat, patterns in cat_patterns.items():
                    if any(re.search(p, query_lower) for p in patterns):
                        category = cat
                        break
                
                # Default to general if no specific category found
                if not category:
                    category = 'general'
            
            # Get ACTUAL news from NewsManager
            news_items = news_reader.get_news(category, limit=7)
            
            if not news_items:
                # Still no news - inform user
                await message.reply(
                    f"No news found for '{category}'.\n"
                    f"Add news files to knowledge_base/news/daily/"
                )
                return
            
            # Format response in Kaia's voice
            response = _format_news_response(news_items, category, query)
            
            # Send response
            await send_kaia_response(message.channel, response)
            
            # Log interaction
            await run_rag(rag.log_user_interaction, message.author.id, message.author.display_name, query, response)
            
    except Exception as e:
        log_error(f"Proper news error: {e}")
        # Fallback to RAG if available
        # Note: handle_general_query was removed in refactor, using general RAG flow
        await message.reply("I'm having trouble fetching the news right now. Let me check my general knowledge.")
        return

def _format_news_response(news_items, category, query):
    """Format actual news items without commentary and with available options"""
    # Build response
    lines = []
    
    for i, item in enumerate(news_items, 1):
        text = item.get('text', 'No content')
        # Truncate long items
        if len(text) > 200:
            text = text[:197] + "..."
        
        date_str = ""
        if item.get('date'):
            # Format date nicely
            try:
                dt = datetime.strptime(item['date'], "%Y-%m-%d")
                date_str = f" [{dt.strftime('%b %d')}]"
            except:
                date_str = f" [{item['date']}]"
        
        lines.append(f"{i}. {text}{date_str}")
    
    # Add available categories footer
    lines.append("\noptions: [general] [politics] [technology] [business] [security] [science] [culture] [hacker]")
    
    return "\n".join(lines)

def _is_entity_query(query: str) -> bool:
    """Check if query is asking about specific entities"""
    query_lower = query.lower()
    entity_indicators = [
        'who is', 'who are', 'who was', 'who were',
        'what is', 'what are',
        'tell me about',
        'explain',
        'describe'
    ]
    
    return any(indicator in query_lower for indicator in entity_indicators)

@bot.event
@timed_response(threshold=8.0)
async def on_message(msg: discord.Message):
    if msg.author == bot.user:
        return

    # TOTAL BLACKLIST: Ignore all messages in blacklisted channels
    if msg.channel.name.lower() in config.blacklisted_channels:
        return

    # BOOT GUARD: Don't process messages until boot sequence completes
    if not bot_state.boot_complete:
        log_info(f"Message from {msg.author.display_name} ignored - still booting")
        try:
            await msg.channel.send("```\nstill waking up. give me a minute.\n```")
        except:
            pass  # Silently fail if we can't send
        return

    # QUICK FIX: Handle !news command BEFORE kaia filter (so !news works alone)
    if msg.content.strip().startswith("!news"):
        try:
            # Parse category from command
            parts = msg.content.strip().split(maxsplit=1)
            category = parts[1].lower().strip() if len(parts) > 1 else "general"
            
            # SPECIAL CASE: !news today - returns today's news summary
            if category == "today":
                log_action(f"Today's news summary request from {msg.author}")
                from pathlib import Path
                
                # Get today's date and look for most recent news summary
                today = datetime.now()
                news_dir = Path("knowledge_base/news/daily")
                
                # Look for today's summary first, then fall back to most recent
                todays_summary = news_dir / f"news_summary_{today.strftime('%Y%m%d')}.md"
                
                if todays_summary.exists():
                    summary_content = todays_summary.read_text()
                    # Remove empty lines for compact formatting
                    lines = [line for line in summary_content.split('\n') if line.strip()]
                    compact_summary = '\n'.join(lines)
                    formatted = f"📰 **Today's News Summary ({today.strftime('%B %d, %Y')})**\n\n{compact_summary}"
                    # Add category options footer
                    formatted += "\n\n---\n**Other categories:** `!news general` `!news technology` `!news security` `!news hacker` `!news politics` `!news business` `!news science` `!news culture`"
                    await msg.channel.send(formatted.strip())
                    log_success(f"Sent today's news summary to {msg.author}")
                else:
                    # Find most recent summary file
                    summary_files = sorted(news_dir.glob("news_summary_*.md"), reverse=True)
                    if summary_files:
                        most_recent = summary_files[0]
                        # Extract date from filename
                        date_str = most_recent.stem.replace("news_summary_", "")
                        try:
                            file_date = datetime.strptime(date_str, "%Y%m%d")
                            date_display = file_date.strftime("%B %d, %Y")
                        except:
                            date_display = date_str
                        
                        summary_content = most_recent.read_text()
                        # Remove empty lines for compact formatting
                        lines = [line for line in summary_content.split('\n') if line.strip()]
                        compact_summary = '\n'.join(lines)
                        formatted = f"📰 **Latest News Summary ({date_display})**\n\n{compact_summary}"
                        # Add category options footer
                        formatted += "\n\n---\n**Other categories:** `!news general` `!news technology` `!news security` `!news hacker` `!news politics` `!news business` `!news science` `!news culture`"
                        await msg.channel.send(formatted.strip())
                        log_success(f"Sent latest news summary ({date_display}) to {msg.author}")
                    else:
                        await msg.channel.send("```\nNo news summaries found. Run: python tools/maintenance/update_kaia_news.py\n```")
                        log_warning("No news summary files found")
                return  # Exit early
            
            log_action(f"News request from {msg.author} (Category: {category})")
            
            # Get news from manager (returns list of dicts)
            news_items = news_manager.get_news(category)
            
            if news_items and len(news_items) > 0:
                # Format news items nicely
                formatted_news = f"📰 **{category.title()} News**\n\n"
                
                for i, item in enumerate(news_items[:10], 1):  # Limit to 10 items
                    if isinstance(item, dict):
                        text = item.get('text', str(item))
                        formatted_news += f"{i}. {text}\n\n"
                    else:
                        formatted_news += f"{i}. {item}\n\n"
                
                # Add category options footer
                available_categories = ["today", "technology", "security", "hacking", "politics", "business", "science", "culture", "general"]
                formatted_news += "---\n"
                formatted_news += "**Other categories:** " + " ".join([f"`!news {cat}`" for cat in available_categories if cat != category])
                
                # Send WITHOUT code block
                await msg.channel.send(formatted_news.strip())
                log_success(f"Sent {category} news to {msg.author}")
            else:
                await msg.channel.send(f"```\nNo {category} news found. Try updating: `python tools/maintenance/update_kaia_news.py`\n```")
                log_warning(f"No {category} news available")
            
            return  # Exit early, don't process as normal message
        except Exception as e:
            log_error(f"Error retrieving news: {e}")
            await msg.channel.send("```\nError retrieving news. Check logs for details.\n```")
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

    # Check if query is about unknown entities BEFORE RAG
    # boundary = KnowledgeBoundary()
    # 
    # query_entities = boundary.extract_entities(sanitized_content)
    # if query_entities and _is_entity_query(sanitized_content):
    #     # Check if we know these entities
    #     entity_check = boundary.check_known_entities(sanitized_content, "")
    #     
    #     if entity_check["unknown_in_context"] and len(entity_check["unknown_in_context"]) > 0:
    #         # We don't know these entities, respond immediately
    #         response = boundary.generate_boundary_response(
    #             entity_check["unknown_in_context"], 
    #             sanitized_content
    #         )
    #         await msg.reply(response)
    #         return


    # Trigger logic: Image generation
    # Refined phrase-based detection to catch natural language requests while preventing false positives
    request_phrases = [r"will you", r"can you", r"could you", r"please", r"kaia", r"i want you to", r"i'd like you to"]

    draw_intents = [r"draw", r"paint", r"generate", r"create", r"sketch", r"render"]
    shape_words = [r"portrait", r"landscape", r"picture", r"art", r"square", r"circle", r"triangle"]
    
    trigger_patterns = [
        # "kaia draw", "please draw", "will you draw a square"
        rf"(?:{'|'.join(request_phrases)})[\s,]+(?:a|an|the|some|me\s+a|to)?\s*(?:{'|'.join(draw_intents + shape_words)})",
        # "draw a cat kaia", "paint a sunset please" (Intent must be at the very start)
        rf"^(?:{'|'.join(draw_intents)})[\s,]+.*(?:kaia|please)"
    ]
    
    intent_match = None
    for pattern in trigger_patterns:
        match = re.search(pattern, sanitized_content.lower())
        if match:
            intent_match = match
            break

    
    if intent_match:
        # Extract everything after the draw word/intent
        all_keywords = draw_intents + shape_words
        draw_word_match = re.search(rf"\b({'|'.join(all_keywords)})\b", sanitized_content.lower())
        
        if draw_word_match:
            start_pos = draw_word_match.end()
            prompt = sanitized_content[start_pos:].strip()
            
            # Clean up leading noise (articles, filler words)
            prompt = re.sub(r'^(?:an|a|the|some|me\s+a|picture\s+of|image\s+of|art\s+of|portrait\s+of|sketch\s+of|landscape\s+of|square\s+of|circle\s+of|triangle\s+of|of|[\s,])+', '', prompt, flags=re.IGNORECASE).strip()
            
            # Clean up trailing noise (kaia, please)
            prompt = re.sub(r'\b(kaia|please|for me)\b[.!?]*$', '', prompt, flags=re.IGNORECASE).strip()
            
            # Final punctuation cleanup
            prompt = re.sub(r'[?.!,;:]+$', '', prompt).strip()
                
            # Final safety check: If the prompt is too long, it's likely a false positive
            if prompt and len(prompt.split()) <= 20:
                # Circuit breaker check - is image gen available?
                if not is_image_gen_available():
                    await msg.channel.send("```\nimage generation is offline. ask me normally instead.\n```")
                    return
                
                # Persona confirmation - send BEFORE acquiring semaphore
                await msg.channel.send("```\nflickering the screen. give me a second.\n```")
                    
                # Use semaphore to ensure only one image generation at a time
                async with image_semaphore:
                    try:
                        log_action(f"Generating image for prompt: {prompt}")
                        bot_state.is_generating_image = True
                        
                        # Generate a unique filename
                        temp_filename = f"gen_{uuid.uuid4().hex}.png"
                        temp_path = os.path.join("data", temp_filename)
                        os.makedirs("data", exist_ok=True)
                        
                        # Unload chat model to free VRAM for image generation
                        # CRITICAL: With 12GB VRAM, gemma3:12b (8GB) won't fit with Flux
                        await unload_chat_model()
                        # INCREASED WAIT: Give Ollama more time to fully release VRAM
                        await asyncio.sleep(3.0)
                        
                        # REQUIREMENT: Prevent stats from running during image gen
                        # Use safe helper to avoid NameError
                        safe_stop_stats_poller()
                        
                        success, result = await generate_image(prompt, temp_path)
                        
                        # Restart stats poller
                        safe_start_stats_poller()
                        
                        if success:
                            await msg.channel.send(file=discord.File(result))
                            image_path = result # for cleanup
                        else:
                            await msg.channel.send(f"```\nrender failed: {result}\n```")
                            image_path = None
                        
                        # Cleanup
                        try:
                            if image_path and os.path.exists(image_path):
                                os.remove(image_path)
                                log_success(f"Cleaned up temp file")
                        except Exception as cleanup_err:
                            log_warning(f"Failed to cleanup temp file: {cleanup_err}")

                    except Exception as e:
                        log_error(f"Image generation failed: {e}")
                        traceback.print_exc()
                        await msg.channel.send(f"```\nsomething went wrong with the render. check the logs.\n```")
                    finally:
                        bot_state.is_generating_image = False
                        try:
                            await unload_image_model()
                        except Exception as unload_err:
                            log_warning(f"Failed to unload image model: {unload_err}")
                            
                        await asyncio.sleep(1.5)
                        if not shutdown_manager.shutting_down:
                            await prewarm_main_model()
        return

    # "kaia remember" command
    if sanitized_content.lower().startswith("kaia remember"):
        memory_content = sanitized_content[len("kaia remember"):].strip()
        if memory_content:
            log_action(f"Storing memory: {memory_content}")
            success = await run_rag(rag.add_memory, msg.author.id, msg.author.display_name, memory_content)
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
    
    # Check for user list queries - MUST be BEFORE other processing
    q_lower = sanitized_content.lower().strip()
    
    # Stricter user list detection: Must be a relatively short query and match specific patterns
    # This prevents long philosophical rants from triggering a user dump
    is_user_list_query = False
    if len(q_lower) < 100: # Simple commands are usually short
        user_list_patterns = [
            r"kaia\s+(list|show|display)\s+(all\s+)?(users?|profiles?|known users?)",
            r"kaia\s+who\s+do\s+you\s+know",
            r"kaia\s+who\s+is\s+(on\s+this\s+server|here)",
            r"kaia\s+list\s+profiles"
        ]
        is_user_list_query = any(re.search(p, q_lower) for p in user_list_patterns)

    if is_user_list_query:
        log_info("Detected explicit user list query - fetching known users")
        known_users_formatted = get_known_users()
        log_info(f"Found {len(known_users_formatted)} known users")
        
        # Direct response construction
        if known_users_formatted:
            response_text = "Here are the users I'm aware of:\n\n" + "\n\n".join(known_users_formatted)
        else:
            response_text = "I'm aware of you, but I can't seem to access the full user database right now."
        
        # Send directly
        await send_kaia_response(msg.channel, response_text)
        
        # Log interaction
        await run_rag(rag.log_user_interaction, msg.author.id, msg.author.display_name, sanitized_content, response_text)
        return
    
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
                async with generation_lock:
                    log_action("VRAM Lock acquired for vision task.")
                    
                    # 1. Unload chat model to free VRAM for vision
                    # CRITICAL: With 12GB VRAM, gemma3:12b (8GB) + llama3.2-vision (7GB) won't fit
                    await unload_chat_model()
                    await asyncio.sleep(1.0)  # Wait for VRAM to be released
                    
                    # 2. Process vision task
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
                # 3. Re-warm chat model
                await asyncio.sleep(1.5)
                if not shutdown_manager.shutting_down:
                    log_action("Re-warming chat model after vision task...")
                    await prewarm_main_model()
            return

    try:
        # [DISABLED] EMERGENCY HALLUCINATION CHECK
        # if HallucinationDetector.contains_hallucination(sanitized_content):
        #     log_warning(f"Hallucination detected in query from {msg.author.name}. Blocking.")
        #     await msg.channel.send("```\nnot following. try that again.\n```")
        #     return

        log_message_received(msg.author.name, str(msg.author.id), sanitized_content)
        # Log message (monitor is deprecated)
        # monitor.log_message(msg.author.name, sanitized_content, str(msg.author.id))
        

        # DIRECT NEWS QUERY BYPASS (fast path)
        query_lower = sanitized_content.lower()
        news_keywords = ['news', 'headlines', 'current events', 'latest', 'update', 'happening']
        
        # Check if it's clearly a news query
        is_direct_news = any(keyword in query_lower for keyword in news_keywords)
        if NEWS_AUTO_TRIGGER_ENABLED and is_direct_news and ('kaia' in query_lower or bot.user.mentioned_in(msg)):
            log_info("Detected direct news query - bypassing classification")
            # Skip classification, go directly to news handling
            # Use optimized response with caching
            await response_optimizer.get_optimized_response(
                sanitized_content,
                handle_proper_news_query,
                msg,
                sanitized_content
            )
            return

        # 1. TWO-LEVEL CACHE CHECK
        performance_monitor.start_timer('total')
        
        # Pre-classify for cache bypass (FAST PATH - Regex only)
        fast_category = query_classifier.fast_classify(msg.content)
        category = fast_category # Initial guess
        

        # 1.5 PERSONA-DRIVEN STATUS CONTEXT (Fast path)
        status_context = ""
        if fast_category == "COMMAND" and any(word in query_lower for word in ["status", "stats", "uptime", "info", "feeling", "how are you"]):
            log_info(f"Detected status/feeling query: {msg.content} - providing system stats as additional context")
            stats = stats_tracker.get_stats()
            status_context = (
                f"\n\n[CURRENT_SYSTEM_STATUS]\n"
                f"Uptime: {stats['uptime_hours']:.1f} hours\n"
                f"Messages processed: {stats['messages']}\n"
                f"Avg response time: {stats['avg_response_time']:.2f}s\n"
                f"Ollama Status: {stats.get('ollama_status', 'Unknown')}\n"
                f"Active Model: {stats.get('active_model', 'Unknown')}\n"
            )
            # We'll inject this into the system prompt later. We DO NOT bypass RAG.
            category = "COMMAND"

        if semantic_cache.should_cache_query(msg.content, category):
            performance_monitor.start_timer('cache_lookup')
            cached_response = semantic_cache.get(msg.content, category)
            performance_monitor.stop_timer('cache_lookup', 'cache_lookup_time')
            if cached_response:
                # Transparency indicator (Log only, don't show to user)
                log_info("Cache hit - serving cached response")
                await send_kaia_response(msg.channel, cached_response)
                performance_monitor.stop_timer('total', 'response_time')
                # Still log interaction for future RAG
                await run_rag(rag.log_user_interaction, msg.author.id, msg.author.display_name, msg.content, cached_response)
                return
        else:
            log_info(f"Cache bypassed for {category} query")

        # 2. HYBRID CLASSIFICATION & PARALLEL PIPELINE
        # Start full classification in parallel with RAG and Persona
        classification_task = asyncio.create_task(query_classifier.classify(msg.content))
        
        log_info(f"Fast-path classification: {fast_category.upper()}")

        # Start typing indicator
        asyncio.create_task(send_typing_feedback(msg.channel, msg.content))

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
        performance_monitor.start_timer('retrieval')
        persona_task = asyncio.create_task(load_persona_async())
        
        # Check if this is a news query (Use fast_category if available)
        is_news_query = NEWS_AUTO_TRIGGER_ENABLED and ((fast_category == 'news') or any(word in clean_query.lower() for word in ['news', 'latest', 'update', 'happening', 'today']))
        
        if is_news_query:
            log_info("Detected news query - activating enhanced retrieval")
            # 1. Enhance Query
            enhanced_query = news_enhancer.enhance_news_query(clean_query, msg.author.id)
            
            # 2. Prepare RAG Query
            rag_params = rag_enhancer.prepare_news_query(enhanced_query)
            
            # 3. Retrieve
            rag_task = asyncio.create_task(run_rag(
                rag.retrieve, 
                rag_params['query'], 
                top_k=rag_params['params']['similarity_top_k']
            ))
            news_tasks = [] # No separate expansion needed as it's handled in prepare_news_query
        else:
            rag_task = asyncio.create_task(run_rag(
                rag.retrieve, 
                clean_query, 
                user_id=target_user_id, 
                user_name=target_user_name, 
                top_k=config.rag_top_k,
                strict_identity=(fast_category in ["identity", "self", "whoami", "entity"]),
                include_news=NEWS_AUTO_TRIGGER_ENABLED
            ))
            
            # News Query Expansion (Legacy fallback)
            news_tasks = []
            if NEWS_AUTO_TRIGGER_ENABLED:
                news_expansions = EmergencyContaminationFilter.expand_news_query(clean_query)
                for expansion in news_expansions:
                    news_tasks.append(asyncio.create_task(run_rag(
                        rag.retrieve,
                        expansion,
                        top_k=2
                    )))
        
        # Personalization traits
        traits_task = asyncio.create_task(personalization_engine.get_user_traits(msg.author.id))
        
        # Wait for all to complete
        log_action("Waiting for parallel RAG and Persona tasks...")
        start_parallel = time.time()
        results = await asyncio.gather(persona_task, rag_task, traits_task, *news_tasks)
        end_parallel = time.time()
        log_info(f"Parallel tasks completed in {end_parallel - start_parallel:.2f}s")
        
        system_prompt = results[0]
        raw_nodes = results[1]
        user_traits = results[2]
        
        context_nodes = []
        if is_news_query:
            # 4. Process and diversify results
            deduplicated = rag_enhancer.deduplicate_results(raw_nodes)
            
            # Convert to news items format
            news_items = []
            for node in deduplicated:
                # SAFE FIX: Handle both strings and node objects
                if hasattr(node, 'text'):
                    content = node.text
                elif hasattr(node, 'content'):
                    content = node.content
                elif isinstance(node, dict) and 'text' in node:
                    content = node['text']
                elif isinstance(node, dict) and 'content' in node:
                    content = node['content']
                else:
                    content = str(node)

                # Also get metadata safely
                if hasattr(node, 'metadata'):
                    metadata = node.metadata
                elif isinstance(node, dict) and 'metadata' in node:
                    metadata = node['metadata']
                else:
                    metadata = {}
                
                news_items.append({
                    'content': content[:500],  # Limit content
                    'metadata': metadata,
                    'id': f"{hash(content) % 10000:04d}"
                })
            
            # Diversify and track
            diversified_items = news_enhancer.diversify_news_results(news_items, str(msg.author.id))
            news_ids = [item.get('id') for item in diversified_items]
            news_enhancer.track_mentioned_news(news_ids, str(msg.author.id))
            
            # Reconstruct context nodes
            context_nodes = [f"News: {item['content']}" for item in diversified_items]
        else:
            # Standard context processing
            context_nodes = []
            for node in raw_nodes:
                # SAFE FIX: Handle both strings and node objects
                if hasattr(node, 'text'):
                    content = node.text
                elif hasattr(node, 'content'):
                    content = node.content
                elif isinstance(node, dict) and 'text' in node:
                    content = node['text']
                elif isinstance(node, dict) and 'content' in node:
                    content = node['content']
                else:
                    content = str(node)
                
                context_nodes.append(content)

            # Add legacy news expansion results if any
            if len(results) > 3:
                for res in results[3:]:
                    for node in res:
                        if hasattr(node, 'text'):
                            context_nodes.append(node.text)
                        elif hasattr(node, 'content'):
                            context_nodes.append(node.content)
                        elif isinstance(node, dict) and 'text' in node:
                            context_nodes.append(node['text'])
                        elif isinstance(node, dict) and 'content' in node:
                            context_nodes.append(node['content'])
                        else:
                            context_nodes.append(str(node))   

        
        performance_monitor.stop_timer('retrieval', 'retrieval_time')
        
        # Adapt prompt based on traits
        system_prompt = personalization_engine.adapt_prompt(system_prompt, user_traits)
        
        now = datetime.now()
        current_time_str = now.strftime("%A, %B %d, %Y %I:%M %p")
        system_prompt += f"\n\nToday is {current_time_str}."
        
        if status_context:
            system_prompt += status_context
        
        # 3. CONTEXT OPTIMIZATION
        # Wait for full classification to finish (if not already done)
        try:
            # Wait for full classification to finish
            # With GPU acceleration and pre-warming, this should be < 0.5s
            log_action("Waiting for classification task...")
            start_class = time.time()
            category = await asyncio.wait_for(classification_task, timeout=5.0)
            end_class = time.time()
            log_info(f"Full classification result: {category.upper()} (took {end_class - start_class:.2f}s)")
        except asyncio.TimeoutError:
            log_warning(f"Full classification timed out after 5s, using fast-path: {fast_category.upper()}")
            category = fast_category
        except Exception as e:
            log_error(f"Classification task failed: {e}, using fast-path: {fast_category.upper()}")
            category = fast_category

        optimized_context = context_optimizer.optimize_context(
            category, 
            system_prompt, 
            context_nodes, 
            list(bot_state.channel_memory.get(msg.channel.id, []))
        )
        
        system_prompt = optimized_context['persona']
        context_str = optimized_context['rag']
        history_str = optimized_context['history']
        
        if context_str:
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
        
        messages = []
        messages.append({
            "role": "system", 
            "content": f"{system_prompt}\n\n{rag_block}\n\n[RECENT_HISTORY]\n{history_str}"
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
            "3. RESPONSE LENGTH: Aim for 3-8 sentences for complex or philosophical topics. For simple questions, 1-2 sentences is fine. Vary your length—sometimes a few words is right, sometimes a full paragraph is needed. Don't be a 3-word robot. Just stay grounded.\n"
            "4. NO name prefixes. Just start speaking.\n"
            "5. IDENTITY: Use 'User Profile' for deep summaries only when explicitly asked. No hallucinations. Never claim ignorance if records exist.\n"
            "6. BANNED WORDS: 'signal', 'noise', 'system', 'function', 'analyze', 'relevant', 'information', 'aspect', 'curious', 'parameters', 'observe', 'identify', 'patterns', 'processing', 'request', 'operating within', 'as an AI', 'my purpose is'.\n"
            "7. PRIVATE THOUGHTS: Never include internal labels like 'USER PROFILE', 'QUICK REFERENCE', or any bracketed tags in your response. Your inner thoughts and data labels must remain private. DO NOT dump raw profile data.\n"
            "8. STRICT NO FICTIONAL ANECDOTES: Never make up personal stories, fictional people (e.g., 'Leo the bartender', 'Mark at Xerox'), or specific years/places (e.g., 'back in '98', 'server migration in '21') to structure your answer. If it's not in the logs, it didn't happen. No 'I remember...' tropes.\n"
            "9. NO LEADING QUESTIONS: Never end responses with 'what are you building, really?' or similar formulaic questions."
        )

        messages.append({
            "role": "system",
            "content": reinforcement
        })

        log_action("Calling ollama.chat with self-healing...")
        
        # [DISABLED] Check if context contains hallucinations
        # context_hallucination = False
        # for m in messages:
        #     if HallucinationDetector.contains_hallucination(m['content']):
        #         context_hallucination = True
        #         break
        # 
        # if context_hallucination:
        #     log_warning("Hallucination detected in RAG context! Cleaning before sending to LLM.")
        #     for m in messages:
        #         if m['role'] == 'system' and '### LOGS' in m['content']:
        #             m['content'] = HallucinationDetector.clean_response(m['content'])

        # Get GPU options
        gpu_manager = OllamaGPUManager(config.chat_model)
        gpu_options = gpu_manager.get_gpu_options(for_chat=True)

        log_action("Calling ollama.chat with self-healing...")
        start_chat = time.time()
        response = await SelfHealingSystem.call_with_fallback(
            ollama_client.chat,
            model=config.chat_model,
            messages=messages,
            options=gpu_options
        )
        end_chat = time.time()
        
        # Log interaction
        log_ollama_interaction(str(messages[-2:]), response['message']['content'])
        
        log_info(f"LLM chat call completed in {end_chat - start_chat:.2f}s")
        response_time = end_chat - start_chat
        
        performance_monitor.stop_timer('total', 'response_time')
        content = response['message']['content']
        
        # LOG RAW RESPONSE FOR DEBUGGING
        log_info(f"Raw LLM response: {content[:200]}...")
        
        # [DISABLED] CLEAN HALLUCINATIONS FROM RESPONSE
        # if HallucinationDetector.contains_hallucination(content):
        #     log_critical(f"Hallucination detected in response for {msg.author.name}!")
        #     content = HallucinationDetector.clean_response(content)
        #     if not content:
        #         log_warning("Response stripped entirely by HallucinationDetector.")
        #         content = "..." # Fallback
        # 
        # # EMERGENCY CONTAMINATION FILTER
        # content = EmergencyContaminationFilter.filter_response(content)

        # ENHANCE RESPONSE
        if is_news_query:
            # If the model didn't use the enhanced format, force it or wrap it
            # But actually, we want to use the enhancer to format the raw news items if the model failed
            # For now, let's trust the model but maybe apply the tone enhancer
            pass
        elif category in ["IDENTITY", "SELF", "WHOAMI"]:
            log_info(f"Enhancing identity response for query: {clean_query}")
            content = response_enhancer.enhance_identity_response(content, 'casual' if 'who' in clean_query.lower() else 'direct')

        # 4. CACHE, FEEDBACK & PERSONALIZATION
        # Clean response before caching to prevent feedback loops
        # [DISABLED] clean_content = EmergencyContaminationFilter.clean_response_for_discord(content)
        clean_content = content
        
        semantic_cache.set(msg.content, category, clean_content)
        semantic_cache.save()
        await relevance_feedback.log_interaction(msg.content, clean_content, msg.author.id)
        await personalization_engine.learn_from_interaction(msg.author.id, msg.content, clean_content)
        
        # Track context for invalidation
        cache_invalidator.track(msg.content, context_nodes)
        
        # Transparency indicator for optimization (moved to logs, not Discord)
        if optimized_context.get('tokens_saved', 0) > 500:
            log_info(f"Context optimization saved {int(optimized_context['tokens_saved'])} tokens")
            
        prefixes_to_strip = [
            "Kaia:", "kaia:", "Assistant:", "Model:", "System:", 
            "Response:", "Observation:", "Thought:"
        ]
        for prefix in prefixes_to_strip:
            if content.startswith(prefix):
                content = content[len(prefix):].strip()
        
        content = content.replace("`", "")
        
        # REMOVE BOILERPLATE QUESTION ENDINGS
        # [DISABLED] content = BoilerplateDetector.clean_response(content)
        pass
        
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
                    log_warning("Response stripped entirely by safety filter.")
                    content = "not doing that."
        
        # DISCORD-SPECIFIC CLEANING (Profile stripping, etc.)
        # [DISABLED] content = EmergencyContaminationFilter.clean_response_for_discord(content)
        pass
        
        # FINAL FALLBACK: Ensure we never send an empty string
        if not content or not content.strip():
            log_warning("Final response content is empty after all filters. Using fallback.")
            content = "..."
            
        log_response("Got response:", content, response_time=response_time)
        await send_kaia_response(msg.channel, content)
        
        bot_state.channel_memory[msg.channel.id].append({"role": "user", "content": sanitized_content})
        bot_state.channel_memory[msg.channel.id].append({"role": "assistant", "content": content})
        
        bot_state.update_interaction(msg.channel.id)
        
        # Update stats
        stats_tracker.increment_messages(msg.author.id)
        stats_tracker.record_response_time(response_time)
        
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

# ==================== INITIALIZATION FUNCTIONS ====================

def perform_startup_tasks():
    """
    Perform startup tasks that need to run before either mode.
    Returns stats_poller for cleanup.
    
    IMPORTANT: This function must NOT block. All potentially slow
    operations run in background threads with timeouts.
    """
    # Run cleanup immediately on script execution
    cleanup_on_startup()
    
    # 1. News update DISABLED at startup (Rollback)
    print("📰 News update disabled at startup (Rollback)")
    
    # 2. Check news system (fast, non-blocking)
    print("📰 News system initialization skipped at boot (Rollback)")
    
    # 3. Initialize stats poller
    stats_poller.start()
    log_success("Stats poller started.")
    
    # Register stats_poller with helper module for safe access
    set_stats_poller(stats_poller)
    log_success("Stats poller registered with helper module.")
    
    # 4. Register with shutdown manager
    shutdown_manager.register_stats_poller(stats_poller)
    shutdown_manager.setup()
    
    # 5. Done
    print("✅ Startup tasks complete")
    
    return stats_poller

async def run_bot_async(stats_poller, stop_event=None):
    """
    Run the Discord bot with asyncio.
    If stop_event is provided, will exit when it's set.
    """
    # Pre-warm classification model (register for tracking)
    prewarm_task = asyncio.create_task(query_classifier.pre_warm())
    task_registry.register("prewarm_classifier", prewarm_task)
    
    # Wait a bit for initialization
    await asyncio.sleep(2)
    
    try:
        async with bot:
            # If we have a stop event, create a background task to check it
            if stop_event:
                async def check_stop():
                    while not stop_event.is_set():
                        await asyncio.sleep(0.5)
                    # Signal bot to close
                    await bot.close()
                stop_task = asyncio.create_task(check_stop())
                task_registry.register("stop_checker", stop_task)
            
            await bot.start(config.discord_token)
    except KeyboardInterrupt:
        print("\n⚠️  Keyboard interrupt received")
    except asyncio.CancelledError:
        print("\n⚠️  Bot task cancelled")
    except Exception as e:
        print(f"\n❌ Error: {e}")
    finally:
        await perform_async_cleanup(stats_poller)

async def perform_async_cleanup(stats_poller):
    """Perform async cleanup tasks"""
    print("\n" + "="*80)
    print("🔄 Shutting down...")
    print("="*80 + "\n")
    
    # Disable dashboard mode in logger
    logger.set_dashboard_mode(False)
    
    # Reset terminal
    sys.stdout.write('\033[0m\033[?25h\033[?1049l\033[H\033[2J')
    sys.stdout.flush()
    
    # Clean shutdown
    if stats_poller:
        stats_poller.stop()
    
    shutdown_manager.cleanup()
    
    # Async cleanup
    if rag:
        log_action("Persisting RAG index...")
        await run_rag(rag.persist, force=True)
        log_success("Index persisted.")
        
    # Cleanup vision session
    log_action("Cleaning up vision session...")
    try:
        await cleanup_session()
        log_success("Vision session closed.")
    except Exception as e:
        log_warning(f"Failed to cleanup vision session: {e}")
        
    # Close Ollama clients
    log_action("Closing Ollama clients...")
    try:
        log_action("Unloading main model...")
        await ollama_client.generate(model=config.chat_model, keep_alive=0)
        
        if hasattr(ollama_client, '_client'):
            await ollama_client._client.aclose()
        
        from utils.kaia_vision import ollama_client as vision_ollama_client
        if hasattr(vision_ollama_client, '_client'):
            await vision_ollama_client._client.aclose()
        log_success("Ollama clients closed and models unloaded.")
    except Exception as e:
        log_warning(f"Failed to close Ollama clients: {e}")
        
    log_success("Shutdown complete.")

# ==================== CURSES MODE (Main Thread) ====================

def run_curses_mode():
    """
    Run in curses dashboard mode.
    curses runs in MAIN THREAD (required for signal handling).
    Discord bot runs in BACKGROUND THREAD with its own asyncio loop.
    
    IMPORTANT: Signal handlers are set up FIRST before any blocking
    operations, so Ctrl+C always triggers clean shutdown.
    """
    if not config.discord_token:
        log_critical("DISCORD_TOKEN not found in environment variables!")
        sys.exit(1)
    
    print("🚀 Starting in curses dashboard mode...")
    print("   Dashboard runs in main thread, bot in background thread")
    print("   Press Q in dashboard to quit\n")
    
    # Set up shutdown handler FIRST (before any blocking operations)
    # This ensures Ctrl+C is always handled cleanly
    shutdown_manager.setup()
    
    # Initialize variables for cleanup
    stop_event = threading.Event()
    bot_thread = None
    dashboard = None
    stats_poller = None
    
    def run_bot_in_thread():
        """Run the async bot in a background thread"""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(run_bot_async(stats_poller, stop_event))
        finally:
            loop.close()
    
    try:
        # Perform startup tasks (now non-blocking)
        stats_poller = perform_startup_tasks()
        
        # Start Discord bot in background thread
        bot_thread = threading.Thread(target=run_bot_in_thread, daemon=True, name="DiscordBot")
        bot_thread.start()
        print("✅ Discord bot started in background thread")
        
        # Enable dashboard mode in logger (suppresses stdout)
        logger.set_dashboard_mode(True)
        
        # Create and run dashboard in MAIN THREAD
        dashboard = BtopDashboardV2(
            stats_poller=stats_poller,
            logger=logger,
            stats_tracker=stats_tracker
        )
        
        # This runs curses.wrapper in main thread - required for signal handling
        dashboard.run()
        
    except KeyboardInterrupt:
        print("\n⚠️  Keyboard interrupt received")
    except Exception as e:
        print(f"\n❌ Dashboard error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # Signal bot to stop
        stop_event.set()
        
        # Give bot thread time to notice stop event
        time.sleep(0.5)
        
        # Stop dashboard if it exists
        if dashboard:
            try:
                dashboard.stop()
            except:
                pass
        
        # Disable dashboard mode
        logger.set_dashboard_mode(False)
        
        # Reset terminal
        sys.stdout.write('\033[0m\033[?25h\033[?1049l\033[H\033[2J')
        sys.stdout.flush()
        
        # Wait for bot thread with longer timeout
        if bot_thread and bot_thread.is_alive():
            print("Waiting for bot to shut down...")
            bot_thread.join(timeout=10)
            if bot_thread.is_alive():
                print("⚠️  Bot thread still alive after timeout - forcing cleanup")
        
        # Force GPU cleanup
        try:
            from utils.clear_gpu_memory import force_clear_gpu
            if force_clear_gpu():
                print("  ✅ GPU memory released")
            else:
                print("  ⚠️  GPU cleanup incomplete")
        except Exception as e:
            print(f"  ❌ GPU cleanup error: {e}")
        
        # Stop stats poller
        if stats_poller:
            stats_poller.stop()
        
        # Run async cleanup in new event loop
        print("  🔄 Running async cleanup...")
        cleanup_loop = asyncio.new_event_loop()
        try:
            cleanup_loop.run_until_complete(shutdown_manager.async_shutdown())
        except Exception as e:
            print(f"  ❌ Async cleanup error: {e}")
        finally:
            cleanup_loop.close()
        
        print("Curses mode shutdown complete.")

# ==================== SIMPLE MODE (Original Behavior) ====================

async def run_simple_mode():
    """
    Run in simple/ANSI mode (original behavior).
    asyncio runs in main thread.
    """
    if not config.discord_token:
        log_critical("DISCORD_TOKEN not found in environment variables!")
        sys.exit(1)
    
    print("🚀 Using simple logger (set KAIA_DASHBOARD=curses for TUI)")
    
    # Perform startup tasks
    stats_poller = perform_startup_tasks()
    
    # Create simple dashboard placeholder
    class SimpleLogger:
        def __init__(self):
            self.metrics = type('obj', (object,), {
                'ollama_status': '🟢 ONLINE',
                'active_model': 'gemma3:12b',
                'uptime': '0s',
                'cpu_percent': 0.0,
                'gpu_percent': 0.0,
                'gpu_memory': '0/0 MB',
                'ram_usage': '0/0 MB',
                'active_users': 0,
                'total_messages': 0,
                'response_time': 0.0,
                'rag_documents': 0,
                'rag_size': '0 MB',
                'cache_hit_rate': 0.0,
                'request_queue': 0
            })()
        
        def add_log(self, msg): print(f"[LOG] {msg}")
        def update_metrics(self, metrics): pass
        def add_alert(self, msg, level): print(f"[{level.upper()}] {msg}")
        def run(self): pass
        def stop(self): pass

    dashboard = SimpleLogger()
    
    # Run bot directly in this asyncio context
    await run_bot_async(stats_poller)

# ==================== ENTRY POINT ====================

def main():
    """
    Main entry point - selects mode based on KAIA_DASHBOARD environment variable.
    
    KAIA_DASHBOARD=curses: Run curses dashboard in main thread, bot in background
    Otherwise: Run in simple mode with asyncio in main thread (original behavior)
    """
    dashboard_mode = os.environ.get('KAIA_DASHBOARD', 'curses').lower()  # Default: curses
    
    if dashboard_mode == 'curses':
        # Curses mode: curses in main thread, bot in background
        run_curses_mode()
    else:
        # Simple mode: asyncio in main thread (original behavior)
        try:
            asyncio.run(run_simple_mode())
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()