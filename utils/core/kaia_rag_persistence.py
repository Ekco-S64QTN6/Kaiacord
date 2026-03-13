"""
RAG Persistence Mixin — Storage, Logging & State Management
=============================================================

Extracted from kaia_rag.py (Phase 28 / CQ-01).

Contains:
- add_memory / add_memory_async: Log remembered facts
- log_user_interaction / log_user_interaction_async: Interaction logging with rotation
- detect_hallucination: Hallucination detection wrapper
- flag_nodes: Data rot flagging
- get_audit_summary: Audit statistics
- persist / persist_async: Index persistence with atomic swap
- pre_warm: BM25 pre-warming
"""

import os
import re
import asyncio
import time
import json
import shutil
import traceback
import threading
from datetime import datetime
from typing import Optional, List, Dict, Any, Set

from utils.infrastructure.logging.kaia_logger import (
    log_success, log_info, log_warning, log_error, log_critical, log_action, log_debug
)
from utils.infrastructure.system.yaml_config import config
from utils.core.hallucination_detector import HallucinationDetector
from utils.core.kaia_rag_retriever import sanitize_log_content, SimpleBM25Retriever, thread_safe_rag_operation

from utils.social.kaia_identities import registry


class RAGPersistenceMixin:
    """Mixin class providing persistence, logging, and state management methods for KaiaRAG."""

    @thread_safe_rag_operation
    async def add_memory_async(self, user_id: int, user_name: str, text: str) -> bool:
        """Async wrapper for add_memory."""
        return await asyncio.to_thread(self.add_memory, user_id, user_name, text)

    def add_memory(self, user_id: int, user_name: str, text: str) -> bool:
        """Log a 'remembered' fact into a separate file AND the interaction log."""
        try:
            # 1. Standard interaction log (redundancy/perspective)
            self.log_user_interaction(
                user_id, 
                user_name, 
                f"[REMEMBER_COMMAND]: {text}", 
                "Logged it. I'll remember that."
            )
            
            # 2. SEPARATE INJECTED FILE (Legacy behavior for Dream Mode/Isolation)
            with self._data_lock:
                safe_user_name = "".join([c for c in user_name if c.isalnum() or c in (' ', '-', '_')]).strip().replace(' ', '_')
                user_dir_name = f"{safe_user_name}_{user_id}"
                user_log_dir = os.path.join(self.knowledge_base_dir, "user_logs", user_dir_name)
                
                os.makedirs(user_log_dir, exist_ok=True)
                
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                log_file = os.path.join(user_log_dir, f"injected_{timestamp}.txt")
                
                log_text = f"User ({user_name}): Remember this: {text}\nKaia: Logged it. I'll remember that.\n"
                
                with open(log_file, "w", encoding="utf-8") as f:
                    f.write(log_text)
                    
                log_success(f"Separate memory file created: injected_{timestamp}.txt")
                return True
                
        except Exception as e:
            log_error(f"Error adding memory: {e}")
            return False

    async def log_user_interaction_async(self, user_id: int, user_name: str, message_content: str, bot_response: str) -> bool:
        """Async wrapper for log_user_interaction."""
        return await asyncio.to_thread(self.log_user_interaction, user_id, user_name, message_content, bot_response)

    # Removed @thread_safe_rag_operation to ensure file writing always happens
    def log_user_interaction(self, user_id: int, user_name: str, message_content: str, bot_response: str) -> bool:
        """Log user interaction to a single file per user, rotating at 100MB.
        """
        # GUARD: Bot identity not yet initialized (on_ready hasn't fired)
        if self._bot_user_id is None:
            log_debug(f"Skipping log_user_interaction: bot_user_id not yet initialized")
            return True

        # ECHO CHAMBER PROTECTION: Prevent self-logging of bots and reflections.
        # This stops the 'Kaia' user logs folder from poisoning the identity core.
        # EXCEPTION: If user_name is "Kaia-Autonomous", it means an autonomous quip we WANT logged.
        _BOT_NAME_PREFIXES = ["Kaia", "KAIA", "Nexus", "System"]
        
        bot_ids = [self._bot_user_id, "KAIA_SYSTEM", "KAIA_DREAM"]
        is_autonomous = user_name == "Kaia-Autonomous"
        
        if (
            str(user_id) in [str(bid) for bid in bot_ids if bid] or 
            any(user_name.startswith(p) for p in _BOT_NAME_PREFIXES)
        ):
            log_debug(f"Skipping log_user_interaction for bot identity: {user_name} ({user_id})")
            return True

        # Acquire lock unconditionally to ensure we write to disk. 
        # Persistence is more important than non-blocking here.
        with self._data_lock:
            # 1. CANONICAL IDENTITY RESOLUTION
            # Check if this ID is linked to another (e.g. Forum <-> Discord)
            
            u_id_str = str(user_id)
            canonical_id = u_id_str
            
            # If it's a forum ID (forum_user_12345 or just digits), try to get linked Discord ID
            fid = None
            if u_id_str.startswith("forum_"):
                fid_parts = u_id_str.rsplit("_", 1)
                if len(fid_parts) > 1 and fid_parts[1].isdigit():
                    fid = int(fid_parts[1])
            elif u_id_str.isdigit() and len(u_id_str) < 15: # Forum IDs are typically shorter
                fid = int(u_id_str)
                
            if fid:
                linked_discord = registry.get_discord_id(fid)
                if linked_discord:
                    canonical_id = linked_discord
                    log_debug(f"Resolved forum ID {u_id_str} to canonical Discord ID {canonical_id}")
            
            # 2. SELECTION OF LOG DIRECTORY
            # Sanitize user_name for filesystem
            safe_user_name = "".join([c for c in user_name if c.isalnum() or c in (' ', '-', '_')]).strip().replace(' ', '_')
            
            if canonical_id != u_id_str:
                # Use the canonical (Discord) ID to unify logs
                user_dir_name = canonical_id
            elif u_id_str == "social_bluesky_michaelschellhorn.link":
                # Keep legacy hack for this specific user if not in registry yet
                user_dir_name = "Ekco_177011971818782721"
            elif u_id_str.startswith("social_"):
                user_dir_name = u_id_str
            else:
                user_dir_name = f"{safe_user_name}_{u_id_str}"
                
            user_log_dir = os.path.join(self.knowledge_base_dir, "user_logs", user_dir_name)
            
            try:
                # Create user directory if it doesn't exist
                if not os.path.exists(user_log_dir):
                    os.makedirs(user_log_dir)
                    log_success(f"Created user log directory")
                    log_info(user_log_dir)
                
                # Find existing log file for TODAY
                today_str = datetime.now().strftime("%Y%m%d")
                interaction_log_path = os.path.join(user_log_dir, f"interactions_{today_str}.md")
                
                # Check for existing log files and handle oversized logs
                MAX_SIZE = 100 * 1024 * 1024  # 100MB in bytes
                
                if os.path.exists(interaction_log_path):
                    # If today's log exists and is oversized, create a part 2
                    if os.path.getsize(interaction_log_path) >= MAX_SIZE:
                        # Find the next available part number
                        part = 2
                        while os.path.exists(os.path.join(user_log_dir, f"interactions_{today_str}_part{part}.md")):
                            part += 1
                        interaction_log_path = os.path.join(user_log_dir, f"interactions_{today_str}_part{part}.md")
                else:
                    # Check if there's a recent log from another day to potentially reference, 
                    # but we ALWAYS start a new file for a new day to keep RAG indexing clean.
                    log_info(f"Starting new interaction log for {today_str}")
                
                # Append interaction to the single file
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                
                # CLEAN HALLUCINATIONS FROM RESPONSE BEFORE LOGGING (Skip for Owners)
                if HallucinationDetector.contains_hallucination(bot_response):
                    if not config.is_owner(user_name, user_id=str(user_id)):
                        log_warning(f"Hallucination detected in response for {user_name}. Cleaning before logging.")
                        bot_response = HallucinationDetector.clean_response(bot_response)
                    else:
                        log_debug(f"Hallucination pattern detected in owner response ({user_name}), but skipping clean.")

                # BUG 1 FIX: Strip JSON wrapper from response before logging
                json_wrapper_pattern = r'^\s*\{[\s\S]*"response"\s*:\s*"([\s\S]*)"\s*\}\s*$'
                match = re.search(json_wrapper_pattern, bot_response)
                if match:
                    bot_response = match.group(1).replace('\\"', '"').replace('\\n', '\n')

                # Initialize frontmatter if file is new
                is_new_file = not os.path.exists(interaction_log_path)
                
                header_text = ""
                if is_new_file:
                    header_text = "---\nsummary: \"\"\nkeywords: []\ndocument_type: Transcript\n---\n\n"
                
                # Sanitize internal tags before logging to prevent RAG pollution
                message_content = sanitize_log_content(message_content)
                bot_response = sanitize_log_content(bot_response)
                
                interaction_text = f"User: {message_content}\nKaia: {bot_response}\n\n"
                
                # Get current size before appending for the offset
                # IF new file, offset is length of header (since we write header then interaction)
                file_offset = os.path.getsize(interaction_log_path) if not is_new_file else len(header_text)
                
                with open(interaction_log_path, "a", encoding="utf-8", errors="replace") as f:
                    if is_new_file:
                        f.write(header_text)
                    f.write(interaction_text)
                
                log_success(f"Logged interaction for {user_name} (Disk Only)")
                
                # OPTIMIZATION: Defer indexing to the periodic refresh cycle.
                # Doing insert_nodes() here triggers synchronous GPU embedding generation,
                # which blocks the event loop and competes with the detailed Intent Analysis.
                # Since short-term context handles "what did I just say", we don't need
                # milliseconds-fresh RAG for logs.
                
                # self.indices['logs'].insert_nodes(nodes) 
                
                return True

            except Exception as e:
                log_error(f"Error logging user interaction: {e}")
                traceback.print_exc()
                return False

    @thread_safe_rag_operation
    async def detect_hallucination(self, bot_response: str, context_text: Optional[str] = None) -> Dict[str, Any]:
        """Detect potential hallucinations in a bot response."""
        detector = HallucinationDetector()
        has_hallucination = detector.contains_hallucination(bot_response)
        
        return {
            "has_hallucination": has_hallucination,
            "patterns_detected": has_hallucination,
            "cleaned_response": detector.clean_response(bot_response) if has_hallucination else bot_response
        }


    def flag_nodes(self, node_ids: list, construct_name: str) -> int:
        """Flag nodes with a Data Rot construct label. Returns count of nodes flagged."""
        flagged = 0
        with self._data_lock: # Lock for modifying indices
            for itype, index in self.indices.items():
                docstore = index.storage_context.docstore
                for node_id in node_ids:
                    try:
                        node = docstore.get_node(node_id)
                        if node:
                            if 'audit_flags' not in node.metadata:
                                node.metadata['audit_flags'] = []
                            # Avoid duplicate flags of the same construct
                            if construct_name not in node.metadata['audit_flags']:
                                node.metadata['audit_flags'].append(construct_name)
                                flagged += 1
                    except Exception:
                        continue
            if flagged:
                self.persist_needed = True
        # Persist outside the lock
        if flagged:
            self.persist(force=True)
        return flagged

    def get_audit_summary(self) -> dict:
        """Scan all nodes for audit_flags metadata and return summary statistics."""
        from collections import Counter
        total_flagged = 0
        construct_counts = Counter()
        source_counts = Counter()

        with self._data_lock: # Lock for reading indices
            for itype, index in self.indices.items():
                docstore = index.storage_context.docstore
                for node in docstore.docs.values():
                    flags = node.metadata.get('audit_flags', [])
                    if flags:
                        total_flagged += 1
                        for flag in flags:
                            construct_counts[flag] += 1
                        file_path = node.metadata.get('file_path', 'unknown')
                        source_counts[file_path] += 1

        return {
            "total_flagged": total_flagged,
            "by_construct": dict(construct_counts),
            "top_sources": source_counts.most_common(10),
        }

    async def persist_async(self, force: bool = False):
        """Async wrapper for persist."""
        await asyncio.to_thread(self.persist, force)

    def persist(self, force: bool = False):
        """Persist all hierarchical indices to storage if needed."""
        # REQUIREMENT: Never wait on locks during shutdown
        if not force and not self.persist_needed:
            return
            
        # REQUIREMENT: Never wait indefinitely on locks during shutdown
        lock_timeout = 5.0 if force else 30.0
        acquired = self._data_lock.acquire(timeout=lock_timeout)
        if not acquired:
            log_error(f"Failed to acquire data lock for RAG persistence{' (SHUTDOWN)' if force else ''}")
            return

        try:
            for itype, index in self.indices.items():
                try:
                    itype_dir = os.path.join(self.persist_dir, itype)
                    temp_dir = f"{itype_dir}_tmp"
                    
                    # 1. Clean up stale temp dir if it exists
                    if os.path.exists(temp_dir):
                        shutil.rmtree(temp_dir)
                    
                    # 2. Persist to temporary location
                    index.storage_context.persist(persist_dir=temp_dir)
                    
                    # 3. Atomic swap (near-atomic on most filesystems)
                    old_dir = f"{itype_dir}_old"
                    if os.path.exists(old_dir):
                        shutil.rmtree(old_dir)
                    
                    if os.path.exists(itype_dir):
                        os.rename(itype_dir, old_dir)
                    
                    os.rename(temp_dir, itype_dir)
                    
                    if os.path.exists(old_dir):
                        shutil.rmtree(old_dir)
                        
                except Exception as e:
                    log_error(f"Failed to persist {itype} index: {e}")
        finally:
            self._data_lock.release()
        
        self.persist_needed = False
        log_success("RAG indices persisted.")

    async def pre_warm(self):
        """
        Warms up individual BM25 retrievers asynchronously.
        Replaces raw nodes with tokenized structures to save RAM.
        """
        try:
            import psutil
            import gc
            
            log_action("Pre-warming RAG BM25 indices (Async)...")
            index_list = list(self.indices.items())
            
            for itype, index in index_list:
                # 1. Resource Guard
                avail_mem_gb = psutil.virtual_memory().available / (1024**3)
                if avail_mem_gb < 1.0: # Lowered threshold slightly due to better efficiency
                    log_warning(f"Low RAM ({avail_mem_gb:.1f}GB). Skipping pre-warm for '{itype}'.")
                    continue

                # 2. Check cache (Memory or Disk)
                with self._data_lock:
                    if itype in self.bm25_cache and self.bm25_cache[itype] is not None:
                        continue
                
                # Try loading from disk first
                retriever = await asyncio.to_thread(self._load_bm25_cache, itype)
                
                if not retriever:
                    with self._data_lock:
                        nodes = list(index.storage_context.docstore.docs.values())
                    
                    if nodes:
                        log_debug(f"Async pre-warming '{itype}' ({len(nodes)} nodes) via full build...")
                        start = time.time()
                        
                        # 3. Use the new async-ready retriever
                        retriever = SimpleBM25Retriever(nodes)
                        await retriever.initialize_async()
                        
                        with self._data_lock:
                            self.bm25_cache[itype] = retriever
                            
                        # Persist to disk for faster next start
                        await asyncio.to_thread(self._save_bm25_cache, itype)
                        
                        gc.collect() 
                        log_success(f"Index '{itype}' pre-warmed in {time.time() - start:.2f}s")
                else:
                    # Successfully loaded from disk
                    with self._data_lock:
                        self.bm25_cache[itype] = retriever
                    
                    # Breath between indices
                    await asyncio.sleep(0.5)
            
            log_success("All RAG indices pre-warmed.")
        except Exception as e:
            log_error(f"RAG pre-warm failed: {e}")
            traceback.print_exc()

