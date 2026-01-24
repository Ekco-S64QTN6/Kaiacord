import os
import sys
import asyncio

# Set PyTorch CUDA allocator to use expandable segments to reduce fragmentation
# These MUST be set before torch or any library that uses it is imported
os.environ["PYTORCH_ALLOC_CONF"] = "expandable_segments:True,max_split_size_mb:512"
os.environ["PYTORCH_CUDA_ALLOC_CONF"] = "expandable_segments:True,max_split_size_mb:512"

# Initialize Unified Logging EARLY
from utils.unified_logging import replace_all_logging, logger
replace_all_logging()

# Initialize Stats Tracker
from utils.stats_tracker import stats_tracker

# Initialize Dashboard
from utils.btop_dashboard import BtopDashboard
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
from utils.kaia_image import generate_image, unload_image_model, generation_lock
from utils.kaia_vision import kaia_sees_image, cleanup_session
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from utils.boilerplate_detector import BoilerplateDetector
from utils.kaia_intelligence import SemanticCache, ModelWarmPool, ContextOptimizer, RelevanceFeedback, PerformanceMonitor, PersonalizationEngine, PersistentStateManager, IntelligentCacheInvalidator
from utils.kaia_intelligence_fixed import FixedQueryClassifier
from utils.fast_news import FastNewsRetriever
from utils.enhanced_news_integration import EnhancedNewsHandler
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
    log_context_retrieval, log_separator, set_monitor
)
from utils.kaia_news import NewsRetrievalEnhancer, ResponseEnhancer, RAGEnhancer
# from utils.btop_dashboard import BtopDashboard, KaiaMonitor, BtopLoggingPatcher # Removed conflicting import

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

    def should_use_cache(self, query_text: str, query_classification: str) -> bool:
        """Determine if semantic cache should be used for this query"""
        # NEVER use cache for identity questions
        if query_classification in ["IDENTITY", "SELF", "WHOAMI"]:
            return False
        
        # Never use cache for "who are you" or "who am i"
        identity_keywords = ["who are you", "who am i", "what are you", "define yourself"]
        if any(keyword in query_text.lower() for keyword in identity_keywords):
            return False
        
        return True

    @classmethod
    def from_env(cls):
        return cls()

config = Config.from_env()

# Dashboard will be initialized in main()
# monitor = KaiaMonitor(dashboard) # Deprecated
# set_monitor(monitor) # Deprecated

# No need for BtopLoggingPatcher anymore, ConsolidatedLogger handles it

class BotState:
    """Encapsulates global bot state and persistence"""
    def __init__(self, state_file: str = "storage/bot_state.json"):
        self.state_file = state_file
        self.channel_memory: Dict[int, Deque[Dict[str, str]]] = {}
        self.last_interaction_time: float = time.time()
        self.last_active_channel_id: Optional[int] = None
        self.consecutive_quips: int = 0
        self.is_generating_image: bool = False
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

# Initialize Enhancers
news_enhancer = NewsRetrievalEnhancer()
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
    persona_file = os.path.join(os.path.dirname(__file__), 'config', 'kaia_persona.md')
    
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
        return
        
    # Clean response for Discord
    text = EmergencyContaminationFilter.clean_response_for_discord(text)
    
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
        r"\bback in (?:'90s|\d{4})\b"
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
        
        # If we removed too much, provide clean fallback
        if len(filtered_response.strip()) < 20:
            filtered_response = ""
        
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
                
            # Check if line starts a profile block (case-insensitive)
            line_lower = line.lower()
            should_skip = any(pattern in line_lower for pattern in skip_patterns)
            
            if should_skip:
                in_profile_block = True
                continue
                
            # If in a profile block, check if we should exit
            # Exit if the line looks like dialogue (starts with lowercase or common dialogue words)
            # or if it doesn't look like a bullet point/metadata
            if in_profile_block:
                # Dialogue usually starts with lowercase in Kaia's persona
                is_dialogue = stripped[0].islower() or any(stripped.lower().startswith(w) for w in ["yeah", "no", "well", "i ", "you "])
                is_bullet = stripped.startswith('- ') or stripped.startswith('* ')
                
                if is_dialogue and not is_bullet:
                    in_profile_block = False
                else:
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
        
        return cleaned_response.strip()
    
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
model_warm_pool = ModelWarmPool(ollama_client)
query_classifier = FixedQueryClassifier(ollama_client, model=config.chat_model, timeout=3.0)
fast_news_retriever = FastNewsRetriever()
news_handler = EnhancedNewsHandler()
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
                log_success("Incremental RAG refresh complete.")
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
    try:
        gpu_manager = OllamaGPUManager(config.chat_model)
        gpu_options = gpu_manager.get_gpu_options(for_chat=True)
        
        # Force GPU load
        success = await gpu_manager.ensure_gpu_loading(ollama_client)
        
        if success:
            print(f"✅ {config.chat_model} loaded on GPU")
        else:
            print(f"⚠️  {config.chat_model} falling back to CPU")
            gpu_options = {'num_thread': 8}  # CPU fallback
        
        # Warm up with GPU settings
        response = await ollama_client.chat(
            model=config.chat_model,
            messages=[{"role": "user", "content": "Hello"}],
            options=gpu_options
        )
        print(f"✅ Model pre-warmed with options: {list(gpu_options.keys())}")
        
    except Exception as e:
        print(f"⚠️  Pre-warm failed: {e}")

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
                
                # Add news to idle quips
                news_nodes = await run_rag(rag.retrieve, f"news brief {datetime.now().strftime('%Y-%m-%d')}", top_k=2)
                
                context_str = ""
                if context_nodes:
                    context_str = "\n\n[LOG_CONTEXT]\n" + "\n---\n".join(context_nodes)
                
                if news_nodes:
                    context_str += "\n\n[NEWS_CONTEXT]\n" + "\n---\n".join(news_nodes)
                
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

@tasks.loop(minutes=15)
async def memory_audit_task():
    """Periodic memory audit and cleanup."""
    try:
        process = psutil.Process()
        rss_mb = process.memory_info().rss / 1024 / 1024
        log_info(f"Memory Audit: RSS {rss_mb:.1f} MB | Cache: {len(semantic_cache.cache)} entries")
        
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
            
        # Report performance stats
        log_info(performance_monitor.get_report())
        
        # Save state
        state_manager.save_state(semantic_cache, personalization_engine, performance_monitor)
    except Exception as e:
        log_error(f"Memory audit failed: {e}")

async def handle_proper_news_query(message, query, category=None):
    """PROPER news handler that reads from actual files"""
    try:
        async with message.channel.typing():
            
            # Initialize proper news reader
            from utils.proper_news_reader import ProperNewsReader
            news_reader = ProperNewsReader()
            
            # Extract category from query
            query_lower = query.lower()
            
            if not category:
                if 'politic' in query_lower:
                    category = 'politics'
                elif 'tech' in query_lower or 'ai' in query_lower or 'software' in query_lower:
                    category = 'technology'
                elif 'security' in query_lower or 'cyber' in query_lower or 'hack' in query_lower or 'cve' in query_lower:
                    category = 'security'
                elif 'business' in query_lower or 'econom' in query_lower or 'market' in query_lower:
                    category = 'business'
                elif 'science' in query_lower or 'research' in query_lower:
                    category = 'science'
                elif 'news' in query_lower or 'latest' in query_lower or 'update' in query_lower:
                    category = 'general'
                else:
                    category = 'general'
            
            # Get ACTUAL news from files
            news_items = news_reader.get_news_by_category(category, limit=7)
            
            if not news_items:
                # If no news found, scan for any news
                news_reader.scan_news_files()
                news_items = news_reader.get_news_by_category(category, limit=7)
            
            if not news_items:
                # Still no news - show what directories exist
                dirs = news_reader.news_dirs
                dir_list = ", ".join(str(d) for d in dirs)
                await message.reply(
                    f"No news found for '{category}'.\n"
                    f"I looked in: {dir_list}\n"
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
        await handle_general_query(message, query)

def _format_news_response(news_items, category, query):
    """Format actual news items in Kaia's voice"""
    import random
    
    # Kaia's opening lines
    openings = {
        'technology': [
            "Tech news from the logs:",
            "On the tech front:",
            "Digital developments:"
        ],
        'politics': [
            "Political movements:",
            "Government and policy:",
            "Political landscape:"
        ],
        'security': [
            "Security updates:",
            "Vulnerabilities and breaches:",
            "Cybersecurity situation:"
        ],
        'business': [
            "Business and markets:",
            "Economic developments:",
            "Corporate updates:"
        ],
        'science': [
            "Scientific developments:",
            "Research updates:",
            "Science news:"
        ],
        'general': [
            "Here's what I found:",
            "Latest from the feeds:",
            "Current events:"
        ]
    }
    
    opening = random.choice(openings.get(category, openings['general']))
    
    # Build response
    lines = [f"{opening}\n"]
    
    for i, item in enumerate(news_items, 1):
        text = item.get('text', 'No content')
        # Truncate long items
        if len(text) > 200:
            text = text[:197] + "..."
        
        date_str = ""
        if item.get('date'):
            # Format date nicely
            try:
                from datetime import datetime
                dt = datetime.strptime(item['date'], "%Y-%m-%d")
                date_str = f" [{dt.strftime('%b %d')}]"
            except:
                date_str = f" [{item['date']}]"
        
        lines.append(f"{i}. {text}{date_str}")
    
    # Add Kaia's commentary
    commentaries = {
        'technology': "\nThe future's here. It's just unevenly distributed.",
        'politics': "\nSame shit, different day.",
        'security': "\nPatch. Everything.",
        'business': "\nMoney never sleeps.",
        'science': "\nProgress, one breakthrough at a time.",
        'general': "\nIt's always something."
    }
    
    closing = commentaries.get(category, "\nThat's the latest.")
    lines.append(closing)
    
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
    boundary = KnowledgeBoundary()
    
    query_entities = boundary.extract_entities(sanitized_content)
    if query_entities and _is_entity_query(sanitized_content):
        # Check if we know these entities
        entity_check = boundary.check_known_entities(sanitized_content, "")
        
        if entity_check["unknown_in_context"] and len(entity_check["unknown_in_context"]) > 0:
            # We don't know these entities, respond immediately
            response = boundary.generate_boundary_response(
                entity_check["unknown_in_context"], 
                sanitized_content
            )
            await msg.reply(response)
            return

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
                bot_state.is_generating_image = True
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
                bot_state.is_generating_image = False
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
    q_lower = sanitized_content.lower()
    is_user_list_query = (
        ("user" in q_lower and any(w in q_lower for w in ["list", "know", "aware", "who", "what"])) or
        "who do you know" in q_lower or
        "profiles" in q_lower or
        "list all users" in q_lower
    )

    if is_user_list_query:
        log_info("Detected user list query - fetching known users")
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
        # EMERGENCY HALLUCINATION CHECK
        if HallucinationDetector.contains_hallucination(sanitized_content):
            log_warning(f"Hallucination detected in query from {msg.author.name}. Blocking.")
            await msg.channel.send("```\nnot following. try that again.\n```")
            return

        log_message_received(msg.author.name, str(msg.author.id), sanitized_content)
        # Log message (monitor is deprecated)
        # monitor.log_message(msg.author.name, sanitized_content, str(msg.author.id))
        
        # 0. SPECIAL HANDLERS (Bypass Cache)
        # Check if this is a user listing query
        # Broader detection: contains "user" AND (list/know/aware/who/what)
        # OR specific phrases like "who do you know"
        q_lower = sanitized_content.lower()
        is_user_list_query = (
            ("user" in q_lower and any(w in q_lower for w in ["list", "know", "aware", "who", "what"])) or
            "who do you know" in q_lower or
            "profiles" in q_lower or
            "list all users" in q_lower
        )
        
        if is_user_list_query:
            log_info("Detected user list query - fetching known users")
            known_users_formatted = get_known_users()
            log_info(f"Found {len(known_users_formatted)} known users")
            
            # Direct response construction to bypass potential LLM hallucinations/cache issues
            if known_users_formatted:
                response_text = "Here are the users I'm aware of:\n\n" + "\n\n".join(known_users_formatted)
            else:
                response_text = "I'm aware of you, Ekco. But I can't seem to access the full user database right now."
            
            # Send directly
            await send_kaia_response(msg.channel, response_text)
            
            # Log interaction
            await run_rag(rag.log_user_interaction, msg.author.id, msg.author.display_name, sanitized_content, response_text)
            # Log interaction
            await run_rag(rag.log_user_interaction, msg.author.id, msg.author.display_name, sanitized_content, response_text)
            return

        # DIRECT NEWS QUERY BYPASS (fast path)
        query_lower = sanitized_content.lower()
        news_keywords = ['news', 'headlines', 'current events', 'latest', 'update', 'happening']
        
        # Check if it's clearly a news query
        is_direct_news = any(keyword in query_lower for keyword in news_keywords)
        if is_direct_news and ('kaia' in query_lower or bot.user.mentioned_in(msg)):
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
        
        # Pre-classify for cache bypass
        category = await query_classifier.classify(msg.content)
        
        if semantic_cache.should_cache_query(msg.content, category):
            cached_response = semantic_cache.get(msg.content, category)
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
        # (Category already determined for cache check)
        log_info(f"Query classified as: {category.upper()}")

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
        
        # Check if this is a news query
        is_news_query = any(word in clean_query.lower() for word in ['news', 'latest', 'update', 'happening', 'today'])
        
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
                strict_identity=(category in ["IDENTITY", "SELF", "WHOAMI"])
            ))
            
            # News Query Expansion (Legacy fallback)
            news_expansions = EmergencyContaminationFilter.expand_news_query(clean_query)
            news_tasks = []
            for expansion in news_expansions:
                news_tasks.append(asyncio.create_task(run_rag(
                    rag.retrieve,
                    expansion,
                    top_k=2
                )))
        
        # Personalization traits
        traits_task = asyncio.create_task(personalization_engine.get_user_traits(msg.author.id))
        
        # Wait for all to complete
        # Wait for all to complete
        results = await asyncio.gather(persona_task, rag_task, traits_task, *news_tasks)
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
        
        # 3. CONTEXT OPTIMIZATION
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
            "3. BE SUBSTANTIAL. Blunt, grounded, lowercase. Provide depth on people/history. Keep it alive.\n"
            "4. NO name prefixes. Just start speaking.\n"
            "5. IDENTITY: Use 'User Profile' for deep summaries. No hallucinations. Never claim ignorance if records exist.\n"
            "6. BANNED WORDS: 'signal', 'noise', 'system', 'function', 'analyze', 'relevant', 'information', 'aspect', 'curious', 'parameters', 'observe', 'identify', 'patterns', 'processing', 'request', 'operating within', 'as an AI', 'my purpose is'.\n"
            "7. PRIVATE THOUGHTS: Never include internal labels like 'USER PROFILE', 'QUICK REFERENCE', or any bracketed tags in your response. Your inner thoughts and data labels must remain private. DO NOT dump raw profile data."
        )

        messages.append({
            "role": "system",
            "content": reinforcement
        })

        log_action("Calling ollama.chat with self-healing...")
        
        # Check if context contains hallucinations
        context_hallucination = False
        for m in messages:
            if HallucinationDetector.contains_hallucination(m['content']):
                context_hallucination = True
                break
        
        if context_hallucination:
            log_warning("Hallucination detected in RAG context! Cleaning before sending to LLM.")
            for m in messages:
                if m['role'] == 'system' and '### LOGS' in m['content']:
                    m['content'] = HallucinationDetector.clean_response(m['content'])

        # Get GPU options
        gpu_manager = OllamaGPUManager(config.chat_model)
        gpu_options = gpu_manager.get_gpu_options(for_chat=True)

        start_time = time.time()
        response = await SelfHealingSystem.call_with_fallback(
            ollama_client.chat,
            model=config.chat_model,
            messages=messages,
            options=gpu_options
        )
        end_time = time.time()
        response_time = end_time - start_time
        
        performance_monitor.stop_timer('total', 'response_time')
        content = response['message']['content']
        
        # CLEAN HALLUCINATIONS FROM RESPONSE
        if HallucinationDetector.contains_hallucination(content):
            log_critical(f"Hallucination detected in response for {msg.author.name}!")
            content = HallucinationDetector.clean_response(content)

        # EMERGENCY CONTAMINATION FILTER
        content = EmergencyContaminationFilter.filter_response(content)

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
        clean_content = EmergencyContaminationFilter.clean_response_for_discord(content)
        
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
        content = BoilerplateDetector.clean_response(content)
        
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

        log_response("Got response:", content, response_time=response_time)
        await send_kaia_response(msg.channel, content)
        
        bot_state.channel_memory[msg.channel.id].append({"role": "user", "content": sanitized_content})
        bot_state.channel_memory[msg.channel.id].append({"role": "assistant", "content": content})
        
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

async def main():
    """Main entry point for the bot"""
    if not config.discord_token:
        log_critical("DISCORD_TOKEN not found in environment variables!")
        sys.exit(1)

    # Run cleanup immediately on script execution
    cleanup_on_startup()
    
    stats_poller = None
    
    # Start dashboard in background
    # dashboard_task = # DISABLED: # DISABLED: asyncio.create_task(dashboard.run()) # REMOVED: DashboardUI runs in thread
    
    # 1. Fix news ingestion first
    print("📰 Checking news pipeline...")
    # diagnose_news_pipeline() # Deprecated
    # fix_news_ingestion() # Deprecated
    
    # Check proper news system
    from utils.proper_news_reader import ProperNewsReader
    news_reader = ProperNewsReader()
    news_reader.scan_news_files()
    total_items = sum(len(items) for items in news_reader.news_cache.values())
    categories = list(news_reader.news_cache.keys())
    log_info(f"News system initialized: {total_items} items in {len(categories)} categories")
    if total_items == 0:
        log_warning("⚠️ No news found! Add markdown files to knowledge_base/news/daily/")
    
    # 2. Initialize stats poller
    from utils.stats_poller import stats_poller
    stats_poller.start()
    
    # 3. Register with shutdown manager
    shutdown_manager.register_stats_poller(stats_poller)
    shutdown_manager.setup()
    
    # 4. News module is now updated directly in utils/kaia_news.py
    print("✅ News module loaded")
    
    # 5. Run dashboard
    print("🚀 Starting dashboard...")
    # DISABLED DASHBOARD - USING SIMPLE LOGGER
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
        async def run(self): pass

    dashboard = SimpleLogger()
    # DISABLED: asyncio.create_task(dashboard.run())
    
    # Clean shutdown
    # shutdown_manager.cleanup() is called in main finally block
        
    # Wait a bit for dashboard to initialize
    import time
    time.sleep(2)
    
    try:
        async with bot:
            await bot.start(config.discord_token)
    except KeyboardInterrupt:
        print("\n⚠️  Keyboard interrupt received")
    except Exception as e:
        print(f"\n❌ Error: {e}")
    finally:
        # CRITICAL: Reset terminal before printing shutdown messages
        print("\n" + "="*80)
        print("🔄 Resetting terminal state...")
        print("="*80 + "\n")
        
        # Manually reset terminal to ensure clean output
        import sys
        sys.stdout.write('\033[0m\033[?25h\033[?1049l\033[H\033[2J')
        sys.stdout.flush()
        
        # Clean shutdown
        if stats_poller:
            stats_poller.stop()
        
        shutdown_manager.cleanup()
        
        # Async cleanup (must be done here, not in dashboard thread)
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
            # Unload main model to free VRAM
            log_action("Unloading main model...")
            await ollama_client.generate(model=config.chat_model, keep_alive=0)
            
            # Close main client
            if hasattr(ollama_client, '_client'):
                await ollama_client._client.aclose()
            
            # Close vision client (imported from kaia_vision)
            from utils.kaia_vision import ollama_client as vision_ollama_client
            if hasattr(vision_ollama_client, '_client'):
                await vision_ollama_client._client.aclose()
            log_success("Ollama clients closed and models unloaded.")
        except Exception as e:
            log_warning(f"Failed to close Ollama clients: {e}")
            
        log_success("Shutdown complete.")

def run_dashboard(stdscr):
    """Dashboard runner with clean setup"""
    # Initialize dashboard
    dashboard = MinimalDashboard(stdscr, logger, stats_tracker)
    
    try:
        # Run dashboard
        dashboard.run()
    finally:
        # Clean up dashboard
        dashboard.cleanup()
        
        # Final cleanup
        shutdown_manager.restore_terminal_state()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass