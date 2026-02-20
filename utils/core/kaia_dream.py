from pathlib import Path
from typing import List, Dict, Any, Optional, Set
from collections import defaultdict
import json
import uuid
import ollama
try:
    import pypdf
except ImportError:
    pypdf = None
try:
    import docx2txt
except ImportError:
    docx2txt = None

from utils.infrastructure.logging.kaia_logger import log_info, log_error, log_warning, log_success

class DreamEngine:
    def __init__(self, config_instance, rag_instance=None):
        self.config = config_instance
        self.rag = rag_instance
        # Use config for paths, fall back to defaults
        # Accessing nested config keys via .get() or attribute access if implemented
        self.kb_dir = Path(getattr(config_instance, 'paths', {}).get('knowledge_base', './knowledge_base'))
        self.dreams_kb_dir = self.kb_dir / 'kaia_dreams'
        
        self.chat_model = getattr(config_instance, 'models', {}).get('chat', 'gemma3:12b')
        
        # Ensure directories exist
        self.dreams_kb_dir.mkdir(parents=True, exist_ok=True)
        
        # Performance/History state
        self.history_file = Path(getattr(config_instance, 'paths', {}).get('memory', './memory')) / 'dream_history.json'
        self._history = self._load_history()
        


    async def generate_dream_reflection(self, file_path: str, snippet: str, persona_content: str) -> Optional[str]:
        """Generate an in-depth, multi-paragraph persona-based reflection"""
        
        current_date = datetime.now().strftime('%B %Y')
        dream_instruction = f"""
[DREAM_TASK]
You are performing "Dream Mode" processing—a deep, associative cycle where you reflect on archived knowledge.
Based on the provided persona, generate an in-depth, multi-paragraph reflection on this fragment.

CURRENT DATE: {current_date}
IMPORTANT: You are living in February 2026. This data is part of your local archive. 

CONTENT SNIPPET:
"{snippet}"

SOURCE: {file_path}

INSTRUCTIONS:
1. VOICE: Blunt, dry, slightly weary, and grounded. (Reflect your persona accurately).
2. FORMAT: Multiple paragraphs (2-4). 
3. DEPTH: Do not summarize. Connect this fragment to broader themes (infrastructure, human error, the passage of time, the nature of memory).
4. ANALYTICAL BENT: Be clear-eyed, amused, or curious, but always grounded in physical reality.
5. NO HEADERS: No "Reflection:" or "Kaia:". Just the raw text.
6. STAGING: Do NOT hallucinate that you are in the year 2030, 2040, or any future date. You are reflecting in the present (2026).
7. NO ROLEPLAY: ABSOLUTELY FORBIDDEN. Do not use asterisks (*nods*) or parentheses (types).
8. NO ATMOSPHERE: Do not describe the room, the sounds, the servers, or any "atmospheric" flavor text. 
9. SPOKEN TEXT ONLY: Output only what you would actually say.

YOUR IN-DEPTH REFLECTION:"""

        try:
            full_prompt = persona_content + "\n" + dream_instruction
            
            # CRITICAL FIX: Wrap the sync ollama call in an async function...
            async def _run_dream_chat():
                return await asyncio.to_thread(
                    ollama.chat,
                    model=self.chat_model,
                    messages=[{"role": "user", "content": full_prompt}],
                    options={
                        "temperature": 0.8, 
                        "num_predict": 1000,
                        "num_ctx": 8192,
                        "stop": ["User:", "Kaia:"]
                    }
                )

            # ...and pass it through the GPU guard to prevent VRAM collisions
            from utils.infrastructure.gpu.gpu_manager import gpu_memory_manager, GPUTaskPriority
            import time
            
            response = await gpu_memory_manager.run_with_gpu_guard(
                model_name=self.chat_model,
                priority=GPUTaskPriority.CHAT, 
                coro=asyncio.wait_for(_run_dream_chat(), timeout=600.0),
                task_id=f"dream_{uuid.uuid4().hex[:8]}"
            )
            
            return response['message']['content'].strip()
        except Exception as e:
            log_error(f"In-depth dream reflection generation failed: {e}")
            return None

    async def scan_knowledge_base_fast(self, min_days: int = 2) -> Dict[str, List[Path]]:
        """Scan KB using RAG manifest (O(k)) instead of recursive walk."""
        target_folders = ["Books", "news", "user_logs", "documents"]
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
            except: pass
        return {}

    def _save_history(self):
        try:
            self.history_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.history_file, 'w') as f:
                json.dump(self._history, f)
        except Exception as e:
            log_error(f"Failed to save dream history: {e}")

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

        # 2. Select samples with Fair User Representation
        sample_files = []
        
        # A. User Quota (Target ~40% of dreams from interactions)
        user_logs = categorized_files.get('user_logs', [])
        user_quota = dream_cfg.get('user_quota', 0.4)
        target_user_dreams = int(dreams_per_scan * user_quota)
        if target_user_dreams < 1 and user_quota > 0: target_user_dreams = 1
        
        if user_logs:
            # Group by User ID (parent folder) to ensure fair representation
            user_map = defaultdict(list)
            for f in user_logs:
                user_map[f.parent.name].append(f)
            
            users = list(user_map.keys())
            
            for _ in range(target_user_dreams):
                # Pick a random user, then a random file from them
                # (This gives equal weight to 'Ekco' (few files) and 'gnownm' (many files))
                selected_user = random.choice(users)
                selected_file = random.choice(user_map[selected_user])
                sample_files.append(selected_file)
                
        # B. General Content Quota (Populate rest from books, news, docs)
        other_files = []
        for cat in ['Books', 'news', 'documents']:
            other_files.extend(categorized_files.get(cat, []))
            
        remaining_slots = dreams_per_scan - len(sample_files)
        
        if remaining_slots > 0 and other_files:
            # Randomly sample from the rest
            count = min(len(other_files), remaining_slots)
            sample_files.extend(random.sample(other_files, count))
            
        # If we still have slots (e.g., no other files), fill with more user logs if possible
        remaining_slots = dreams_per_scan - len(sample_files)
        if remaining_slots > 0 and user_logs:
             # Sample without replacement
             count = min(len(user_logs), remaining_slots)
             sample_files.extend(random.sample(user_logs, count))

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
                    
                reflection = await self.generate_dream_reflection(
                    display_path, 
                    snippet, 
                    persona_content
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

                    async with asyncio.Lock(): # Thread-safe write for history
                        self._history[str(file_path)] = datetime.now().isoformat()
                        # Prune history older than 6 months
                        if len(self._history) > 2000:
                            cutoff = (datetime.now() - timedelta(days=180)).isoformat()
                            self._history = {k: v for k, v in self._history.items() if v > cutoff}
                    
                    self._save_history()
                    new_dreams_count += 1
                    log_success(f"Generated in-depth dream: {dream_filename}")
            except Exception as e:
                log_error(f"Failed to process dream for {file_path.name}: {e}")

        log_info(f"Nightly dreaming complete. Added {new_dreams_count} new thoughts.")

    def scan_knowledge_base(self, min_days: int = 2) -> Dict[str, List[Path]]:
        """Scan KB for files older than min_days, grouped by category.
        Falls back to more recent files if none found with the min_days threshold.
        """
        target_folders = ["Books", "news", "user_logs", "documents"]
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
        if "Books" in parts: return "book"
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
