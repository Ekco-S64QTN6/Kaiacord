from pathlib import Path
from typing import List, Dict, Any, Optional, Set
from collections import defaultdict
import json
import time
import os
import random
import uuid
import asyncio
import ollama
from datetime import datetime, timedelta
try:
    import pypdf
except ImportError:
    pypdf = None
try:
    import docx2txt
except ImportError:
    docx2txt = None

from utils.infrastructure.logging.kaia_logger import log_info, log_error, log_warning, log_success, log_action

class DreamEngine:
    def __init__(self, config_instance, rag_instance=None):
        self.config = config_instance
        self.rag = rag_instance
        # Use config for paths, fall back to defaults
        self.kb_dir = Path(config_instance.knowledge_base_dir)
        self.dreams_kb_dir = self.kb_dir / 'kaia_dreams'
        
        self.chat_model = config_instance.chat_model
        self.ollama_client = ollama.AsyncClient()
        
        # Ensure directories exist
        self.dreams_kb_dir.mkdir(parents=True, exist_ok=True)
        
        # Performance/History state
        self.history_file = Path(config_instance.persist_dir) / 'dream_history.json'
        self._history = self._load_history()
        self._history_lock = asyncio.Lock()

        # Continuity file: private rolling summary of Kaia's inner state.
        # Never indexed in RAG. Read by dream prompts, updated after each cycle.
        self.continuity_file = Path(config_instance.persist_dir) / 'kaia_continuity.md'


    async def generate_dream_reflection(self, file_path: str, snippet: str, persona_content: str,
                                         source_type: str = 'document') -> Optional[str]:
        """Generate an in-depth, multi-paragraph persona-based reflection"""
        
        current_date = datetime.now().strftime('%B %Y')

        # Load existing continuity for context
        continuity_context = self._load_continuity()
        continuity_block = ""
        if continuity_context:
            continuity_block = f"""
RECENT INNER STATE (your own prior reflections — use this as context, not as content to repeat):
{continuity_context[-800:]}

"""

        # Tiered instructions based on source type
        if source_type == 'conversation':
            tiered_instructions = """
DREAM TYPE: RELATIONAL REFLECTION
This is a conversation you had. Reflect on it as lived experience, not as data.
- Who is this person in your world? Has your sense of them shifted?
- What did they actually mean? What were they not saying?
- How did this exchange sit with you afterward?
- Speak in the first person. These are your actual thoughts about someone you know.
"""
        elif source_type == 'news':
            tiered_instructions = """
DREAM TYPE: SITUATIONAL COMMENTARY
This happened in the world. React to it honestly.
- What do you actually think about this? Not what you should think. What you do think.
- Does this connect to anything you've been noticing lately?
- Be specific. Vague observations are useless.
"""
        elif source_type == 'prior_dream':
            tiered_instructions = """
DREAM TYPE: META-REFLECTION
You dreamed this before. Return to it.
- Has your view changed since then?
- What did you miss the first time?
- What holds up, and what now seems wrong?
"""
        else:  # document, book, etc.
            tiered_instructions = """
DREAM TYPE: INTELLECTUAL REFLECTION
Connect this fragment to your actual world.
- What does this make you think about? Not the text itself — what it unlocks.
- Does it connect to anyone you talk to, or anything that's been on your mind?
- Be analytical, but grounded. You've read things. You've had conversations. Connect them.
"""

        dream_instruction = f"""
[DREAM_TASK]
You are performing "Dream Mode" processing—a deep, associative cycle where you reflect on archived content.

CURRENT DATE: {current_date}

{continuity_block}
{tiered_instructions}

CONTENT SNIPPET:
"{snippet}"

SOURCE: {file_path}

VOICE AND FORMAT RULES (always apply regardless of dream type):
1. VOICE: Blunt, dry, slightly weary, grounded. Reflect your persona accurately.
2. FORMAT: 2–4 paragraphs. No headers. No "Reflection:" or "Kaia:". Just raw text.
3. STAGING: You are in {current_date}. Do not hallucinate future dates.
4. NO ROLEPLAY: ABSOLUTELY FORBIDDEN. No asterisks. No parentheses for actions.
5. NO ATMOSPHERE: Do not describe the room, the sounds, the servers.
6. SPOKEN TEXT ONLY: Output only what you would actually think or say.
"""

        try:
            full_prompt = persona_content + "\n" + dream_instruction
            
            from utils.infrastructure.gpu.gpu_manager import OllamaGPUManager
            gpu_mgr = OllamaGPUManager(self.chat_model)
            options = gpu_mgr.get_gpu_options(for_chat=True)
            options.update({
                "temperature": 0.8,
                "num_predict": 1000,
                "stop": ["User:", "Kaia:"]
            })
            
            # CRITICAL FIX: Use async client directly for proper cancellation
            async def _run_dream_chat():
                return await self.ollama_client.chat(
                    model=self.chat_model,
                    messages=[{"role": "user", "content": full_prompt}],
                    options=options,
                    keep_alive=-1
                )

            # ...and pass it through the GPU guard to prevent VRAM collisions
            from utils.infrastructure.gpu.gpu_manager import gpu_memory_manager, GPUTaskPriority
            
            response = await gpu_memory_manager.run_with_gpu_guard(
                model_name=self.chat_model,
                priority=GPUTaskPriority.CHAT, 
                coro=asyncio.wait_for(_run_dream_chat(), timeout=600.0),
                task_id=f"dream_{uuid.uuid4().hex[:8]}"
            )
            
            return response['message']['content'].strip()
        except Exception as e:
            log_error(f"In-depth dream reflection generation failed: {type(e).__name__}: {e}")
            return None


    async def scan_knowledge_base_fast(self, min_days: int = 2) -> Dict[str, List[Path]]:
        """Scan KB using RAG manifest (O(k)) instead of recursive walk."""
        target_folders = ["books", "news", "user_logs", "documents"]
        categorized_files = {k: [] for k in target_folders}
        cutoff_time = time.time() - (min_days * 86400)
        
        if not self.rag or not hasattr(self.rag, 'indexed_files'):
            log_warning("RAG manifest not available, falling back to disk walk.")
            return await asyncio.to_thread(self.scan_knowledge_base, min_days)
            
        manifest = self.rag.indexed_files
        all_eligible_files = {k: [] for k in target_folders}
        
        for path_str, meta in manifest.items():
            path = Path(path_str)
            parts = path.parts
            
            # Identify category from path parts
            category = None
            for target in target_folders:
                if target in parts:
                    category = target
                    break
            
            if not category:
                continue
                
            fname = path.name
            # Existing filters
            if fname.startswith('.') or not fname.endswith(('.txt', '.md', '.pdf', '.docx')): continue
            if fname.lower() == "user_profile.md": continue
            if "injected" in fname.lower(): continue
            
            # History Filter: Skip if dreamed in the last 14 days
            if path_str in self._history:
                last_dreamed = datetime.fromisoformat(self._history[path_str])
                if datetime.now() - last_dreamed < timedelta(days=14):
                    continue
                    
            all_eligible_files[category].append(path)
            if meta.get("mtime", 0) < cutoff_time:
                categorized_files[category].append(path)
                
        total_found = sum(len(f) for f in categorized_files.values())
        if total_found == 0:
            return all_eligible_files
        return categorized_files

    def _load_history(self) -> Dict[str, str]:
        if self.history_file.exists():
            try:
                with open(self.history_file, 'r') as f:
                    return json.load(f)
            except Exception: pass
        return {}

    def _save_history(self):
        try:
            self.history_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.history_file, 'w') as f:
                json.dump(self._history, f)
        except Exception as e:
            log_error(f"Failed to save dream history: {e}")

    def _load_continuity(self) -> str:
        """Load the rolling continuity summary. Returns empty string if not yet created."""
        try:
            if self.continuity_file.exists():
                return self.continuity_file.read_text(encoding='utf-8').strip()
        except Exception as e:
            log_warning(f"Could not load continuity file: {e}")
        return ""

    def _update_continuity(self, new_reflection: str, source_label: str):
        """Append a new summary entry to the continuity file.
        
        Keeps approximately the last 500 words by trimming from the top when it grows too long.
        """
        try:
            existing = self._load_continuity()
            timestamp = datetime.now().strftime('%Y-%m-%d')
            new_entry = f"\n\n---\n**{timestamp} — {source_label}**\n{new_reflection[:400].strip()}"
            combined = (existing + new_entry).strip()

            # Trim to ~3000 chars (approx 500 words) by removing oldest entries from top
            max_chars = 3000
            if len(combined) > max_chars:
                trim_point = len(combined) - max_chars
                next_separator = combined.find('\n\n---\n', trim_point)
                if next_separator != -1:
                    combined = combined[next_separator:].strip()
                else:
                    combined = combined[-max_chars:].strip()

            self.continuity_file.parent.mkdir(parents=True, exist_ok=True)
            self.continuity_file.write_text(combined, encoding='utf-8')
        except Exception as e:
            log_warning(f"Could not update continuity file: {e}")

    async def nightly_dream_processing(self, persona_content: str):
        """Perform the nightly dream generation cycle"""
        log_info("Starting nightly dream processing...")
        
        dream_cfg = getattr(self.config, 'dream_mode', {})
        min_days = dream_cfg.get('dream_age_min_days', 2)
        dreams_per_scan = dream_cfg.get('dreams_per_scan', 10)
        
        # 1. Scan for older files using fast manifest lookup
        categorized_files = await self.scan_knowledge_base_fast(min_days=min_days)
        total_files = sum(len(f) for f in categorized_files.values())
        
        if total_files == 0:
            log_warning("No suitable files found for dreaming.")
            return

        # 2. Select samples with Smart Triage (weight toward recent user logs)
        sample_files = []
        
        # A. User Quota (Target ~60% from recent user logs, rest from everything else)
        user_logs = categorized_files.get('user_logs', [])
        cutoff_recent = time.time() - (7 * 86400)  # last 7 days
        
        # Split user logs into recent and older
        recent_logs = []
        older_logs = []
        for f in user_logs:
            try:
                mtime = f.stat().st_mtime
            except Exception:
                mtime = 0.0
            if mtime > cutoff_recent:
                recent_logs.append(f)
            else:
                older_logs.append(f)
        
        # Fill up to 60% from recent user logs
        max_recent = max(1, int(dreams_per_scan * 0.6))
        random.shuffle(recent_logs)
        sample_files.extend(recent_logs[:max_recent])
        
        if recent_logs:
            log_info(f"Dream triage: {len(recent_logs[:max_recent])} recent user logs selected (of {len(recent_logs)} available)")
        
        # B. General Content Quota (Populate rest from books, news, docs, older logs)
        other_files = list(older_logs)
        for cat in ['books', 'news', 'documents']:
            other_files.extend(categorized_files.get(cat, []))
            
        remaining_slots = dreams_per_scan - len(sample_files)
        
        if remaining_slots > 0 and other_files:
            random.shuffle(other_files)
            sample_files.extend(other_files[:remaining_slots])

        # Shuffle again to mix types in processing order
        random.shuffle(sample_files)
        
        # 3. Phase 1: Concurrent Snippet Extraction (CPU/IO Bound)
        log_action(f"Extracting snippets for {len(sample_files)} candidate dreams...")
        extraction_tasks = [self._extract_snippet_async(f) for f in sample_files]
        snippets_raw = await asyncio.gather(*extraction_tasks)
        
        # Filter out failures
        work_items = []
        for i, snippet in enumerate(snippets_raw):
            if snippet:
                work_items.append((sample_files[i], snippet))
                
        new_dreams_count = 0
        
        # 4. Phase 2: Guarded GPU Generation (Sequential/Guarded)
        for file_path, snippet in work_items:
            try:
                # Get a relative path for the source display
                try:
                    display_path = str(file_path.relative_to(self.kb_dir))
                except Exception:
                    display_path = file_path.name
                    
                # Detect source type for tiered prompting
                path_str_lower = str(file_path).lower()
                if 'user_logs' in path_str_lower:
                    dream_source_type = 'conversation'
                elif any(k in path_str_lower for k in ['news', 'daily']):
                    dream_source_type = 'news'
                elif any(k in path_str_lower for k in ['kaia_dreams', 'reflections']):
                    dream_source_type = 'prior_dream'
                else:
                    dream_source_type = 'document'

                reflection = await self.generate_dream_reflection(
                    display_path, 
                    snippet, 
                    persona_content,
                    source_type=dream_source_type
                )
                
                if reflection:
                    # 5. Save as a Markdown file in the KB
                    # Determine subfolder based on source
                    subfolder = "other"
                    if "injected" in file_path.name.lower():
                        subfolder = "injected"
                    elif "interactions" in file_path.name.lower() or "user_logs" in str(file_path):
                        subfolder = "interactions"
                    elif "books" in str(file_path).lower() or self._classify_source(file_path) == "book":
                        subfolder = "books"
                    
                    target_dir = self.dreams_kb_dir / subfolder
                    target_dir.mkdir(parents=True, exist_ok=True)
                    
                    # Sanitize filename
                    safe_name = "".join([c if c.isalnum() else "_" for c in file_path.stem])[:30]
                    date_str = datetime.now().strftime('%Y%m%d_%H%M%S')
                    dream_filename = f"dream_{date_str}_{safe_name}.md"
                    dream_file_path = target_dir / dream_filename
                    
                    with open(dream_file_path, 'w', encoding='utf-8') as df:
                        df.write(f"# Dream Reflection: {display_path}\n")
                        df.write(f"Source: {display_path}\n")
                        df.write(f"Generated: {datetime.now().isoformat()}\n\n")
                        df.write(f"## Original Fragment\n> {snippet[:2000]}...\n\n")
                        df.write(f"## Kaia's Reflection\n{reflection}\n")

                    async with self._history_lock: # Thread-safe write for history
                        self._history[str(file_path)] = datetime.now().isoformat()
                        # Prune history older than 6 months
                        if len(self._history) > 2000:
                            cutoff = (datetime.now() - timedelta(days=180)).isoformat()
                            self._history = {k: v for k, v in self._history.items() if v > cutoff}
                    
                    await asyncio.to_thread(self._save_history)
                    new_dreams_count += 1
                    log_success(f"Generated in-depth dream: {dream_filename}")

                    # Update the continuity thread with a brief summary of what was just dreamed
                    self._update_continuity(
                        new_reflection=reflection[:400],
                        source_label=display_path
                    )
            except Exception as e:
                log_error(f"Failed to process dream for {file_path.name}: {e}")

        log_info(f"Nightly dreaming complete. Added {new_dreams_count} new thoughts.")

    async def evening_reflection(self, persona_content: str):
        """Lightweight nightly journal pass to close the 2-day lag loop."""
        log_action("Starting evening reflection pass...")
        
        # 1. Gather recent interactions
        recent_log_files = []
        user_logs_dir = self.kb_dir / 'user_logs'
        if user_logs_dir.exists():
            cutoff_12h = time.time() - (12 * 3600)
            for root, _, filenames in os.walk(user_logs_dir):
                for f in filenames:
                    if f.startswith('interactions_') and f.endswith('.md'):
                        p = Path(root) / f
                        try:
                            if p.stat().st_mtime > cutoff_12h:
                                recent_log_files.append(p)
                        except Exception: pass
        
        if not recent_log_files:
            log_info("Evening reflection: No recent interactions found to reflect on.")
            return

        # 2. Extract snippets
        snippets = []
        for file_path in recent_log_files:
            try:
                content = file_path.read_text(encoding='utf-8', errors='replace')
                # Grab just the last few entries (bottom of the file)
                entries = content.split('[Post ID:')
                if len(entries) > 1:
                    last_entries = ['[Post ID:' + e for e in entries[-3:]]
                    snippets.append("".join(last_entries))
                else:
                    # Generic split if there are no post IDs (e.g. Discord logs)
                    lines = content.strip().split('\n')
                    snippets.append("\n".join(lines[-20:]))
            except Exception: pass
        
        if not snippets:
            return
            
        combined_snippets = "\n\n".join(snippets)[:4000]

        # 3. Generate Reflection
        reflection_instruction = f"""
[EVENING REFLECTION]
You are performing your evening reflection. Review today's conversations.
Write 2-3 sentences max. What stood out? What did you focus on today?
Speak in the first person. No "Reflection:" or "Kaia:" tags. Just raw text.

TODAY'S CONVERSATIONS:
{combined_snippets}
"""
        try:
            full_prompt = persona_content + "\n" + reflection_instruction
            
            from utils.infrastructure.gpu.gpu_manager import OllamaGPUManager, gpu_memory_manager, GPUTaskPriority
            gpu_mgr = OllamaGPUManager(self.chat_model)
            options = gpu_mgr.get_gpu_options(for_chat=True)
            options.update({"temperature": 0.8, "num_predict": 300, "stop": ["User:", "Kaia:"]})
            
            async def _run_reflection_chat():
                return await self.ollama_client.chat(
                    model=self.chat_model,
                    messages=[{"role": "user", "content": full_prompt}],
                    options=options,
                    keep_alive=-1
                )

            response = await gpu_memory_manager.run_with_gpu_guard(
                model_name=self.chat_model,
                priority=GPUTaskPriority.CHAT, 
                coro=asyncio.wait_for(_run_reflection_chat(), timeout=120.0),
                task_id=f"reflect_{uuid.uuid4().hex[:8]}"
            )
            
            reflection_text = response['message']['content'].strip()
            if reflection_text:
                self._update_continuity(new_reflection=reflection_text, source_label="Evening Reflection")
                log_success("Evening reflection completed and added to continuity.")
        except Exception as e:
            log_error(f"Evening reflection failed: {type(e).__name__}: {e}")

    def scan_knowledge_base(self, min_days: int = 2) -> Dict[str, List[Path]]:
        """Scan KB for files older than min_days, grouped by category.
        Falls back to more recent files if none found with the min_days threshold.
        """
        target_folders = ["books", "news", "user_logs", "documents"]
        categorized_files = {k: [] for k in target_folders}
        cutoff_time = time.time() - (min_days * 86400)
        
        all_eligible_files = {k: [] for k in target_folders}
        
        for folder in target_folders:
            folder_path = self.kb_dir / folder
            if not folder_path.exists():
                continue
                
            for root, _, filenames in os.walk(folder_path):
                for f in filenames:
                    if f.startswith('.') or not f.endswith(('.txt', '.md', '.pdf', '.docx')):
                        continue
                        
                    # Skip user profiles for now (low quality for dreams)
                    if f.lower() == "user_profile.md":
                        continue

                    # Skip injection logs (repetitive/low quality)
                    if "injected" in f.lower():
                        continue
                        
                    # Prefer .md versions of the same file if they exist (to avoid binary parsing)
                    if f.lower().endswith(('.pdf', '.docx')):
                        base = f.rsplit('.', 1)[0]
                        if any(x.lower() == f"{base.lower()}.md" for x in filenames):
                            continue

                    path = Path(root) / f
                    try:
                        stat = path.stat()
                        # Add to eligible list
                        all_eligible_files[folder].append(path)
                        
                        # Add to categorized list if it meets the cutoff
                        if stat.st_mtime < cutoff_time:
                            categorized_files[folder].append(path)
                    except Exception: continue
        
        # Check if we have enough files
        total_found = sum(len(f) for f in categorized_files.values())
        if total_found == 0:
            log_info(f"No files older than {min_days} days. Falling back to all eligible files.")
            return all_eligible_files
            
        return categorized_files

    async def _extract_snippet_async(self, file_path: Path) -> Optional[str]:
        """Async wrapper for snippet extraction to avoid blocking event loop."""
        return await asyncio.to_thread(self._extract_snippet, file_path)

    def _extract_snippet(self, file_path: Path) -> Optional[str]:
        """Sync snippet extraction logic."""
        try:
            file_size = file_path.stat().st_size
            ext = file_path.suffix.lower()
            snippet = ""
            
            if ext == '.pdf' and pypdf:
                try:
                    reader = pypdf.PdfReader(str(file_path))
                    num_pages = len(reader.pages)
                    if num_pages > 0:
                        page_num = random.randint(min(5, num_pages-1), max(0, num_pages - 5))
                        content = reader.pages[page_num].extract_text()
                        snippet = content[:2500] if content else ""
                except Exception as e:
                    log_warning(f"Failed to parse PDF {file_path.name}: {e}")
            
            elif ext == '.docx' and docx2txt:
                try:
                    content = docx2txt.process(str(file_path))
                    if len(content) > 3000:
                        start = random.randint(500, len(content) - 3000)
                        snippet = content[start:start+2500]
                    else:
                        snippet = content[:2500]
                except Exception as e:
                    log_warning(f"Failed to parse DOCX {file_path.name}: {e}")
            
            else:
                with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                    if file_size > 10000:
                        start_bound = int(file_size * 0.10)
                        end_bound = int(file_size * 0.85)
                        offset = random.randint(start_bound, end_bound)
                        f.seek(offset)
                        f.readline() 
                    
                    content = f.read(5000)
                    clean_content = content.replace("\n", " ").strip()
                    snippet = clean_content[:4000]
                    
                    # Skip frontmatter
                    if snippet.startswith("---") and "---" in snippet[3:]:
                        snippet = snippet.split("---", 2)[-1].strip()[:4000]
            
            if snippet:
                printable_ratio = sum(c.isprintable() for c in snippet[:200]) / min(200, len(snippet))
                if printable_ratio < 0.7:
                    return None
                return snippet
        except Exception as e:
            log_error(f"Extraction failed for {file_path}: {e}")
        return None

    def _classify_source(self, path: Path) -> str:
        parts = path.parts
        if "books" in parts: return "book"
        if "news" in parts: return "news"
        if "user_logs" in parts: return "log"
        return "document"

    def _categorize_file(self, path: Path) -> str:
        # Simple categorization heuristic
        name = path.name.lower()
        if any(w in name for w in ["tech", "ai", "hardware", "code"]): return "tech"
        if any(w in name for w in ["spirit", "shinto", "philosophy"]): return "observation"
        if "interactions" in name or "user_logs" in str(path): return "people"
        return "memory"

    def get_dreams_from_files(self) -> Dict[str, Any]:
        """Get dream stats and recent dreams directly from .md files (no cache).
        
        Returns:
            dict with 'total', 'categories', and 'recent' (last 5 dreams)
        """
        stats = {'total': 0, 'categories': {}, 'recent': []}
        all_dreams = []
        
        for subdir in ['books', 'interactions', 'injected', 'other']:
            folder = self.dreams_kb_dir / subdir
            if not folder.exists():
                continue
            
            for dream_file in folder.glob('dream_*.md'):
                try:
                    mtime = dream_file.stat().st_mtime
                    
                    # Read first few lines for summary
                    with open(dream_file, 'r', encoding='utf-8') as f:
                        content = f.read(2000)
                    
                    # Extract source and reflection
                    source = "unknown"
                    reflection = ""
                    if "Source: " in content:
                        source = content.split("Source: ")[1].split("\n")[0].strip()
                    if "## Kaia's Reflection" in content:
                        reflection = content.split("## Kaia's Reflection")[1].strip()[:300]
                    
                    all_dreams.append({
                        'file': dream_file.name,
                        'source': source,
                        'category': subdir,
                        'reflection': reflection,
                        'mtime': mtime
                    })
                    
                    stats['categories'][subdir] = stats['categories'].get(subdir, 0) + 1
                except Exception:
                    continue
        
        stats['total'] = len(all_dreams)
        
        # Get 5 most recent
        all_dreams.sort(key=lambda x: x['mtime'], reverse=True)
        stats['recent'] = all_dreams[:5]
        
        return stats
