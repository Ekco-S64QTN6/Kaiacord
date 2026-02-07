import os
import random
import time
import asyncio
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Any, Optional
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

YOUR IN-DEPTH REFLECTION:"""

        try:
            full_prompt = persona_content + "\n" + dream_instruction
            
            response = await asyncio.to_thread(
                    ollama.chat,
                    model=self.chat_model,
                    messages=[{"role": "user", "content": full_prompt}],
                    options={
                        "temperature": 0.8, 
                        "num_predict": 1000, # Increased for length
                        "stop": ["User:", "Kaia:"]
                    }
                )
            return response['message']['content'].strip()
        except Exception as e:
            log_error(f"In-depth dream reflection generation failed: {e}")
            return None

    def scan_knowledge_base(self, min_days: int = 2) -> List[Path]:
        """Scan KB for files older than min_days"""
        target_folders = ["Books", "news", "user_logs", "documents"]
        all_files = []
        cutoff_time = time.time() - (min_days * 86400)
        
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
                        
                    # Prefer .md versions of the same file if they exist (to avoid binary parsing)
                    if f.lower().endswith(('.pdf', '.docx')):
                        base = f.rsplit('.', 1)[0]
                        if any(x.lower() == f"{base.lower()}.md" for x in filenames):
                            continue

                    path = Path(root) / f
                    try:
                        if path.stat().st_mtime < cutoff_time:
                            all_files.append(path)
                    except: continue
        
        return all_files

    async def nightly_dream_processing(self, persona_content: str):
        """Perform the nightly dream generation cycle"""
        log_info("Starting nightly dream processing...")
        
        dream_cfg = getattr(self.config, 'dream_mode', {})
        min_days = dream_cfg.get('dream_age_min_days', 2)
        dreams_per_scan = dream_cfg.get('dreams_per_scan', 10)
        
        # 1. Scan for older files
        all_files = self.scan_knowledge_base(min_days=min_days)
        if not all_files:
            log_warning("No suitable files found for dreaming.")
            return

        # 2. Select random sample
        sample_size = min(dreams_per_scan, len(all_files))
        sample_files = random.sample(all_files, sample_size)
        
        new_dreams_count = 0
        
        for file_path in sample_files:
            try:
                # 3. Extract snippet (Smart retrieval for Books/Logs)
                snippet = ""
                file_size = file_path.stat().st_size
                ext = file_path.suffix.lower()
                
                if ext == '.pdf' and pypdf:
                    try:
                        reader = pypdf.PdfReader(str(file_path))
                        num_pages = len(reader.pages)
                        if num_pages > 0:
                            # Pick a random page, skipping potential cover/index
                            page_num = random.randint(min(5, num_pages-1), max(0, num_pages - 5))
                            content = reader.pages[page_num].extract_text()
                            snippet = content[:2500] if content else ""
                    except Exception as e:
                        log_warning(f"Failed to parse PDF {file_path.name}: {e}")
                
                elif ext == '.docx' and docx2txt:
                    try:
                        content = docx2txt.process(str(file_path))
                        # Random offset in docx text
                        if len(content) > 3000:
                            start = random.randint(500, len(content) - 3000)
                            snippet = content[start:start+2500]
                        else:
                            snippet = content[:2500]
                    except Exception as e:
                        log_warning(f"Failed to parse DOCX {file_path.name}: {e}")
                
                else:
                    # Text/Markdown handling
                    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                        if file_size > 10000: # Large file protection
                            # Pick a random offset, avoiding the exact beginning (metadata)
                            # and exact end (likely bibliography or blank)
                            start_bound = int(file_size * 0.10) # Skip first 10%
                            end_bound = int(file_size * 0.85)  # Stop before last 15%
                            offset = random.randint(start_bound, end_bound)
                            f.seek(offset)
                            # Read and then find next newline to avoid mid-sentence start
                            f.readline() 
                        
                        content = f.read(5000) # Read enough to get deep narrative context
                        
                        # Clean up the snippet
                        clean_content = content.replace("\n", " ").strip()
                        if len(clean_content) > 4000:
                            snippet = clean_content[:4000]
                        else:
                            snippet = clean_content
                        
                        # Fallback check for metadata pollution at the start
                        if snippet.startswith("---") or "identifier:" in snippet:
                            # Try to skip the frontmatter if we hit it
                            if "---" in snippet[3:]:
                                snippet = snippet.split("---", 2)[-1].strip()[:4000]
                
                # Check for gibberish (mostly non-printable characters)
                if snippet:
                    printable_ratio = sum(c.isprintable() for c in snippet[:200]) / min(200, len(snippet))
                    if printable_ratio < 0.7:
                        log_warning(f"Skipping potential gibberish snippet from {file_path.name}")
                        continue

                # 4. Generate reflection
                # Get a relative path for the source display
                try:
                    display_path = str(file_path.relative_to(self.kb_dir))
                except:
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

                    new_dreams_count += 1
                    log_success(f"Generated in-depth dream: {dream_filename}")
            except Exception as e:
                log_error(f"Failed to process dream for {file_path.name}: {e}")

        log_info(f"Nightly dreaming complete. Added {new_dreams_count} new thoughts.")

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
