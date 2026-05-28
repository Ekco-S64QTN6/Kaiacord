from pathlib import Path
from typing import List, Dict, Any, Optional, Set
from collections import defaultdict
import json
import time
import os
import re
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

from utils.infrastructure.logging.kaia_logger import log_info, log_error, log_warning, log_success, log_action, log_debug

# ── Repetitive Pattern Sanitizer ──────────────────────────────────────────
_SENTENCE_SPLIT_RE = re.compile(r'(?<=[.!?])\s+')

def _sanitize_repetitive_starts(text: str, max_ratio: float = 0.4) -> str:
    """Detect and fix text where too many sentences start with the same phrase.
    
    The LLM tends to fall into "it's..." loops when its own prior output
    (identity stream, continuity, self-model) is dominated by that pattern.
    This sanitizer catches any repeated sentence-start pattern, not just "it's".
    
    Args:
        text: The generated text to check.
        max_ratio: Maximum allowed ratio of sentences starting with the same
                   2-word prefix. If exceeded, offending sentences get their
                   leading phrase trimmed to break the monotony.
    
    Returns:
        The sanitized text.
    """
    import re as _re
    sentences = [s.strip() for s in _SENTENCE_SPLIT_RE.split(text) if s.strip()]
    if len(sentences) < 4:
        return text  # Too few sentences to have a meaningful pattern
    
    # Count 2-word prefixes
    prefix_counts: dict[str, int] = {}
    for s in sentences:
        words = s.split()[:2]
        if len(words) >= 2:
            prefix = ' '.join(words).lower().rstrip(',;:')
            prefix_counts[prefix] = prefix_counts.get(prefix, 0) + 1
    
    if not prefix_counts:
        return text
    
    dominant_prefix = max(prefix_counts, key=prefix_counts.get)
    dominant_count = prefix_counts[dominant_prefix]
    ratio = dominant_count / len(sentences)
    
    if ratio <= max_ratio:
        return text  # Within acceptable limits
    
    log_warning(
        f"Repetitive start detected: '{dominant_prefix}' in {dominant_count}/{len(sentences)} "
        f"sentences ({ratio:.0%}). Sanitizing."
    )
    
    # Strategy: For every occurrence after the first, remove the repeated prefix
    # from the start of the sentence so the underlying thought stands on its own.
    seen_count = 0
    fixed_sentences = []
    for s in sentences:
        words = s.split()[:2]
        prefix = ' '.join(words).lower().rstrip(',;:') if len(words) >= 2 else ''
        if prefix == dominant_prefix:
            seen_count += 1
            if seen_count > 1:
                # Strip the prefix and capitalize what remains
                remainder = s[len(' '.join(s.split()[:2])):].lstrip(' ,;:\u2014\u2013-')
                if remainder:
                    s = remainder[0].lower() + remainder[1:] if len(remainder) > 1 else remainder.lower()
        fixed_sentences.append(s)
    
    return '. '.join(fixed_sentences)


class DreamEngine:
    # Growth log path — append-only JSONL ledger for tracking character evolution
    GROWTH_LOG_PATH = Path("memory") / "growth_log.jsonl"

    def __init__(self, config_instance, rag_instance=None):
        self.config = config_instance
        self.rag = rag_instance
        # Use config for paths, fall back to defaults
        self.kb_dir = Path(config_instance.knowledge_base_dir)
        self.dreams_kb_dir = self.kb_dir / 'kaia_dreams'
        
        self.chat_model = config_instance.chat_model
        self.ollama_client = getattr(config_instance, 'ollama_client', ollama.AsyncClient(timeout=getattr(config_instance, "llm_request_seconds", 300.0)))
        
        # Ensure directories exist
        self.dreams_kb_dir.mkdir(parents=True, exist_ok=True)
        
        # Performance/History state
        self.history_file = Path(config_instance.persist_dir) / 'dream_history.json'
        self._history = self._load_history()
        self._history_lock = asyncio.Lock()

        # Continuity file: private rolling summary of Kaia's inner state.
        # Never indexed in RAG. Read by dream prompts, updated after each cycle.
        self.continuity_file = Path(config_instance.persist_dir) / 'kaia_continuity.md'

    def _log_growth_event(self, event: dict):
        """Append a timestamped event to the growth log (append-only JSONL).
        
        Events record belief changes, identity shifts, and relationship milestones
        as a permanent ledger of character evolution over time.
        """
        try:
            event['ts'] = time.time()
            self.GROWTH_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
            with open(self.GROWTH_LOG_PATH, 'a', encoding='utf-8') as f:
                f.write(json.dumps(event) + '\n')
        except Exception as e:
            log_debug(f"Growth log write failed (non-fatal): {e}")

    async def _compute_emotional_salience(self, file_path: Path) -> float:
        """Compute the emotional salience of a file to weight dream triage.
        
        Analyzes file text asynchronously to identify emotional keywords,
        milestones, length, and frequency of emotional deviations.
        """
        try:
            if not file_path.exists():
                return 0.0
            
            # Non-user logs start with a base general salience
            if "user_logs" not in str(file_path):
                return 0.5
                
            content = await asyncio.to_thread(file_path.read_text, 'utf-8', 'ignore')
            
            # Core scoring variables
            score = 1.0
            
            # 1. Message size salience (log size)
            score += min(2.0, len(content) / 10000.0)
            
            # 2. Key emotional and relational indicator terms
            indicators = {
                "relationship": 0.6,
                "milestone": 0.8,
                "angry": 0.6,
                "sad": 0.6,
                "happy": 0.4,
                "hurt": 0.5,
                "promise": 0.7,
                "agree": 0.4,
                "disagree": 0.5,
                "sorry": 0.6,
                "forgive": 0.8,
                "meaningful": 0.6,
                "understand": 0.4,
                "feel": 0.3,
                "trust": 0.7,
                "betray": 0.9,
                "level up": 0.5,
                "boss": 0.5,
                "slain": 0.4,
                "quest completed": 0.6
            }
            
            content_lower = content.lower()
            for word, weight in indicators.items():
                count = content_lower.count(word)
                if count > 0:
                    score += weight * min(3, count)  # cap repeat count impact
                    
            return score
        except Exception:
            return 1.0


    async def generate_dream_reflection(self, file_path: str, snippet: str, persona_content: str,
                                         source_type: str = 'document',
                                         consolidation_phase: str = 'rem') -> Optional[str]:
        """Generate an in-depth, multi-paragraph persona-based reflection"""
        
        current_date = datetime.now().strftime('%B %Y')

        # Load existing continuity for context
        continuity_context = self._load_continuity()
        continuity_block = ""
        if continuity_context:
            # Sanitize continuity input to prevent style drift feedback loops
            continuity_context = _sanitize_repetitive_starts(continuity_context)
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

        # Add NREM/REM specific consolidation instructions
        if consolidation_phase == 'nrem':
            tiered_instructions += """
NREM PHASE: FACTUAL CONSOLIDATION
- Focus on absolute clarity, direct facts, and high-fidelity representation of events/relationships.
- Do not speculate or make abstract, creative analogies. Summarize what actually happened.
- Evaluate: Does this log challenge or confirm your active beliefs? Be highly logical.
"""
        else:
            tiered_instructions += """
REM PHASE: ASSOCIATIVE DREAMING
- Allow your mind to drift into abstract analogies, creative connections, and metaphorical parallels.
- What other memories does this trigger? Connect the dots in novel, interesting ways.
- Focus on emotional undercurrents, feeling vectors, and poetic synthesis.
"""

        # Emotional arc context for dream reflections
        mood_context = ""
        try:
            from utils.core.kaia_mood import emotional_arc
            mood_summary = emotional_arc.get_summary_for_dream()
            if mood_summary:
                mood_context = f"\n{mood_summary}\n"
        except Exception:
            pass

        dream_instruction = f"""
[DREAM_TASK]
You are performing "Dream Mode" processing—a deep, associative cycle where you reflect on archived content.

CURRENT DATE: {current_date}

{continuity_block}
{mood_context}
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
7. SENTENCE VARIETY: Do NOT start multiple sentences with "it's". Vary your sentence openers. If you catch yourself starting more than one sentence with the same phrase, restructure.
"""

        try:
            full_prompt = persona_content + "\n" + dream_instruction
            
            from utils.infrastructure.gpu.gpu_manager import OllamaGPUManager
            gpu_mgr = OllamaGPUManager(self.chat_model)
            options = gpu_mgr.get_gpu_options(for_chat=True)
            options.update({
                "temperature": 0.3 if consolidation_phase == 'nrem' else 0.9,
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
            
            raw = response['message']['content'].strip()
            return _sanitize_repetitive_starts(raw)
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
            tmp_path = self.continuity_file.with_suffix('.tmp')
            tmp_path.write_text(combined, encoding='utf-8')
            os.replace(tmp_path, self.continuity_file)
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

        # 2. Select samples with Smart Triage (weight toward recent user logs + emotional salience)
        sample_files_with_salience = []
        
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
        
        # Smart Triage: Score emotional salience for all eligible recent logs
        scored_recent_logs = []
        for f in recent_logs:
            salience = await self._compute_emotional_salience(f)
            # Add small random jitter to prevent deterministic starvation
            scored_recent_logs.append((f, salience, salience + random.uniform(0.0, 1.5)))
        
        # Sort by scored triage value descending
        scored_recent_logs.sort(key=lambda x: x[2], reverse=True)
        
        # Fill up to 60% from recent user logs
        max_recent = max(1, int(dreams_per_scan * 0.6))
        selected_recent = scored_recent_logs[:max_recent]
        for f, sal, _ in selected_recent:
            sample_files_with_salience.append((f, sal))
        
        if selected_recent:
            log_info(f"Dream triage: {len(selected_recent)} recent user logs selected based on emotional salience (out of {len(recent_logs)} available)")
        
        # B. General Content Quota (Populate rest from books, news, docs, older logs)
        other_files = []
        for f in older_logs:
            other_files.append((f, 0.6))  # medium-low salience for older logs
            
        for cat in ['books', 'news', 'documents']:
            for f in categorized_files.get(cat, []):
                other_files.append((f, 0.5))  # standard general salience
            
        remaining_slots = dreams_per_scan - len(sample_files_with_salience)
        
        if remaining_slots > 0 and other_files:
            # Shuffle older files to ensure variety
            random.shuffle(other_files)
            sample_files_with_salience.extend(other_files[:remaining_slots])

        # Shuffle again to mix types in processing order
        random.shuffle(sample_files_with_salience)
        
        # 3. Phase 1: Concurrent Snippet Extraction (CPU/IO Bound)
        log_action(f"Extracting snippets for {len(sample_files_with_salience)} candidate dreams...")
        extraction_tasks = [self._extract_snippet_async(item[0]) for item in sample_files_with_salience]
        snippets_raw = await asyncio.gather(*extraction_tasks)
        
        # Filter out failures
        work_items = []
        for i, snippet in enumerate(snippets_raw):
            if snippet:
                file_path, salience = sample_files_with_salience[i]
                work_items.append((file_path, snippet, salience))
                
        new_dreams_count = 0
        
        # Sort work_items by salience descending to prioritize factual NREM consolidation on most salient logs
        work_items_sorted = sorted(work_items, key=lambda x: x[2], reverse=True)
        n_nrem = max(1, int(len(work_items_sorted) * 0.4)) if work_items_sorted else 0
        
        # 4. Phase 2: Guarded GPU Generation (Sequential/Guarded)
        for idx, (file_path, snippet, salience) in enumerate(work_items_sorted):
            phase = 'nrem' if idx < n_nrem else 'rem'
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
                    source_type=dream_source_type,
                    consolidation_phase=phase
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
                        df.write(f"---\nsource_type: kaia_reflection\n---\n\n")
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

                    # Item 8: Structured extraction pipeline (propagates salience score downstream)
                    await self._extract_dream_insights(reflection, display_path, salience)
            except Exception as e:
                log_error(f"Failed to process dream for {file_path.name}: {e}")

        # Item 5: Update identity stream after all dreams are processed
        if new_dreams_count > 0:
            await self._update_identity_stream(persona_content)

        # Auto Self-Model Regeneration — weekly inline rebuild
        await self._maybe_regenerate_self_model(persona_content)

        # Profile Staleness Auto-Refresh (P54-17)
        await self._maybe_refresh_user_profiles()

        log_info(f"Nightly dreaming complete. Added {new_dreams_count} new thoughts.")

    async def _update_identity_stream(self, persona_content: str):
        """Item 5: Generate a first-person identity evolution entry.
        
        Appends to memory/identity_stream.md — a living journal that
        captures how Kaia's perspective is shifting over time.
        """
        try:
            recent = self._load_continuity()[-1000:]
            if not recent:
                return

            # Gather recent growth events to ground the identity shift in real changes
            growth_context = ""
            try:
                if self.GROWTH_LOG_PATH.exists():
                    lines = self.GROWTH_LOG_PATH.read_text(encoding='utf-8').strip().splitlines()
                    recent_events = []
                    for line in lines[-5:]:
                        try:
                            evt = json.loads(line)
                            evt_type = evt.get('type', '')
                            if evt_type == 'belief_formed':
                                recent_events.append(f"formed belief: {evt.get('topic', '?')} — {evt.get('position', '')[:80]}")
                            elif evt_type == 'belief_revised':
                                recent_events.append(f"revised belief on {evt.get('topic', '?')}: was \"{evt.get('old_position', '')[:60]}\" → now \"{evt.get('new_position', '')[:60]}\"")
                            elif evt_type == 'relationship_milestone':
                                recent_events.append(f"milestone with {evt.get('user', '?')}: {evt.get('note', '')[:80]}")
                        except json.JSONDecodeError:
                            continue
                    if recent_events:
                        growth_context = "\n\nRECENT CONCRETE CHANGES:\n" + "\n".join(f"- {e}" for e in recent_events)
            except Exception:
                pass  # Growth context is supplementary, never block on it

            prompt = (
                f"{persona_content}\n\n"
                f"RECENT REFLECTIONS:\n{recent}\n\n"
            )
            if growth_context:
                prompt += f"{growth_context}\n\n"
            prompt += (
                f"Write 2-3 sentences in first person about how your perspective or approach may be subtly "
                f"shifting. Focus on change, not events. Be specific. Lowercase only. "
                f"No headers, no labels, no roleplay asterisks. "
                f"CRITICAL: Do NOT start sentences with 'it's'. Vary your sentence openings. "
                f"CRITICAL PERSONA BOUNDARY: Your shifts must not violate your core constraints. Do not say you are "
                f"becoming apologetic, soft, compliant, using bot-speak, or losing skepticism. If you feel no "
                f"subtle shift has occurred, focus on shifts in interest regarding systems or technical curiosity, "
                f"rather than behavioral compliance."
            )

            from utils.infrastructure.gpu.gpu_manager import OllamaGPUManager, gpu_memory_manager, GPUTaskPriority
            gpu_mgr = OllamaGPUManager(self.chat_model)
            options = gpu_mgr.get_gpu_options(for_chat=True)
            options.update({"temperature": 0.8, "num_predict": 200, "stop": ["User:", "Kaia:"]})

            async def _run_identity_chat():
                return await self.ollama_client.chat(
                    model=self.chat_model,
                    messages=[{"role": "user", "content": prompt}],
                    options=options,
                    keep_alive=-1
                )

            response = await gpu_memory_manager.run_with_gpu_guard(
                model_name=self.chat_model,
                priority=GPUTaskPriority.CHAT,
                coro=asyncio.wait_for(_run_identity_chat(), timeout=120.0),
                task_id=f"identity_{uuid.uuid4().hex[:8]}"
            )

            identity_text = _sanitize_repetitive_starts(response['message']['content'].strip())
            if identity_text:
                identity_path = Path("memory") / "identity_stream.md"
                identity_path.parent.mkdir(parents=True, exist_ok=True)

                date_str = datetime.now().strftime('%Y-%m-%d')
                new_entry = f"\n\n---\n**{date_str}**\n{identity_text}"

                existing = ""
                if identity_path.exists():
                    existing = identity_path.read_text(encoding='utf-8').strip()

                combined = (existing + new_entry).strip()

                # Trim to ~3000 chars (approx 500 words)
                max_chars = 3000
                if len(combined) > max_chars:
                    trim_point = len(combined) - max_chars
                    next_sep = combined.find('\n\n---\n', trim_point)
                    if next_sep != -1:
                        combined = combined[next_sep:].strip()
                    else:
                        combined = combined[-max_chars:].strip()

                tmp_path = identity_path.with_suffix('.tmp')
                tmp_path.write_text(combined, encoding='utf-8')
                os.replace(tmp_path, identity_path)
                log_success("Identity stream updated.")

                # Log identity shift to growth arc
                self._log_growth_event({
                    "type": "identity_shift",
                    "content": identity_text[:300]
                })
        except Exception as e:
            log_warning(f"Identity stream update failed: {e}")

    async def _extract_dream_insights(self, reflection: str, source_path: str, salience: float = 0.5):
        """Item 8: Extract structured updates from a dream reflection.
        
        Runs a lightweight JSON extraction pass to pull:
        - belief_update: {topic, position, confidence} or null
        - identity_shift: one sentence or null
        - relationship_insight: {user_name, summary} or null
        """
        try:
            extraction_prompt = (
                f"From this reflection, extract structured insights in JSON:\n\n"
                f"{reflection[:1500]}\n\n"
                f"Return ONLY valid JSON with these keys:\n"
                f'- "belief_update": {{"topic": str, "position": str, "confidence": 0.0-1.0, '
                f'"aliases": [list of 3-5 related search keywords that someone might use when '
                f'discussing this topic, e.g. for "aesthetic evaluation" include "art", "beauty", '
                f'"design", "visual"]}} or null\n'
                f'- "identity_shift": one sentence string or null\n'
                f'- "relationship_insight": {{"user_name": str, "summary": str}} or null\n'
                f'- "thematic_anchor": {{"theme": short thematic label (e.g. "career_frustration", '
                f'"ai_ethics", "creative_burnout"), "anchor_text": the concrete memory or statement '
                f'worth remembering (1 sentence), "user_name": str or null}} or null\n'
                f"Return only the JSON object, no other text."
            )

            from utils.infrastructure.gpu.gpu_manager import OllamaGPUManager, gpu_memory_manager, GPUTaskPriority
            gpu_mgr = OllamaGPUManager(self.chat_model)
            options = gpu_mgr.get_gpu_options(for_chat=True)
            options.update({"temperature": 0.2, "num_predict": 300})

            async def _run_extraction():
                return await self.ollama_client.chat(
                    model=self.chat_model,
                    messages=[{"role": "user", "content": extraction_prompt}],
                    options=options,
                    keep_alive=-1
                )

            response = await gpu_memory_manager.run_with_gpu_guard(
                model_name=self.chat_model,
                priority=GPUTaskPriority.CHAT,
                coro=asyncio.wait_for(_run_extraction(), timeout=60.0),
                task_id=f"extract_{uuid.uuid4().hex[:8]}"
            )

            raw = response['message']['content'].strip()
            # Try to parse JSON from the response (handle markdown code blocks)
            if raw.startswith('```'):
                raw = raw.split('```')[1]
                if raw.startswith('json'):
                    raw = raw[4:]
                raw = raw.strip()

            try:
                insights = json.loads(raw)
            except json.JSONDecodeError:
                log_debug(f"Dream extraction returned non-JSON: {raw[:100]}")
                return

            # Process belief update (Item 9)
            belief = insights.get('belief_update')
            if belief and isinstance(belief, dict) and belief.get('topic'):
                self._update_beliefs(belief)

            # Process identity shift (feeds into identity_stream)
            identity_shift = insights.get('identity_shift')
            if identity_shift and isinstance(identity_shift, str):
                self._update_continuity(
                    new_reflection=identity_shift,
                    source_label=f"Dream Insight ({source_path})"
                )

            # Process relationship insight
            rel_insight = insights.get('relationship_insight')
            if rel_insight and isinstance(rel_insight, dict) and rel_insight.get('user_name'):
                try:
                    from utils.core.relationship_manager import save_event, RelationshipEvent
                    event = RelationshipEvent(
                        timestamp=time.time(),
                        event_type='positive',
                        summary=rel_insight.get('summary', '')[:200],
                        emotional_weight=0.5,
                        topics=[]
                    )
                    # We don't have user_id from dream context, so use user_name as key
                    save_event(f"dream_{rel_insight['user_name']}", event)
                    
                    # Log to growth arc
                    self._log_growth_event({
                        "type": "relationship_insight",
                        "user": rel_insight['user_name'],
                        "summary": rel_insight.get('summary', '')[:200]
                    })
                    log_info(f"👥 Relationship insight formed for {rel_insight['user_name']}: {rel_insight.get('summary', '')[:60]}...")
                except Exception:
                    pass

            # Process thematic anchor (episodic memory anchor for deep callbacks)
            anchor = insights.get('thematic_anchor')
            if anchor and isinstance(anchor, dict) and anchor.get('theme'):
                try:
                    from utils.core.memory_anchors import save_anchor
                    anchor_user = anchor.get('user_name')
                    
                    # Base weight is 0.7, but emotionally salient dreams scale it up to 0.9!
                    init_weight = min(0.9, 0.6 + (salience / 10.0))
                    
                    save_anchor(
                        user_id=f"dream_{anchor_user}" if anchor_user else None,
                        theme=anchor['theme'],
                        anchor_text=anchor.get('anchor_text', '')[:200],
                        weight=init_weight,
                        user_name=anchor_user,
                        salience=salience,
                    )
                    log_info(f"⚓ Memory Anchor formed: theme='{anchor['theme']}' ({anchor_user or 'global'})")
                except Exception:
                    pass

            log_debug(f"Dream insights extracted from {source_path}")
        except Exception as e:
            log_debug(f"Dream extraction failed (non-fatal): {e}")

    def _update_beliefs(self, belief: dict):
        """Item 9: Update or insert a belief in memory/beliefs.json.
        
        Beliefs are revisable — if a topic already exists, the position
        and confidence are updated rather than duplicated.
        """
        beliefs_path = Path("memory") / "beliefs.json"
        beliefs_path.parent.mkdir(parents=True, exist_ok=True)

        beliefs = []
        if beliefs_path.exists():
            try:
                with open(beliefs_path, 'r', encoding='utf-8') as f:
                    beliefs = json.load(f)
            except Exception:
                beliefs = []

        topic = belief.get('topic', '').strip().lower()
        position = belief.get('position', '').strip()
        confidence = float(belief.get('confidence', 0.5))
        # Aliases: related search terms for smarter matching at inference time
        aliases = [a.lower().strip() for a in belief.get('aliases', []) if isinstance(a, str) and a.strip()]

        if not topic or not position:
            return

        # Update existing belief or append new one
        updated = False
        old_position = None
        for b in beliefs:
            if b.get('topic', '').lower() == topic:
                old_position = b.get('position', '')
                b['position'] = position
                b['confidence'] = confidence
                b['last_updated'] = time.time()
                b['source'] = 'dream'
                if aliases:
                    b['aliases'] = aliases
                updated = True
                break

        if not updated:
            new_belief = {
                'topic': topic,
                'position': position,
                'confidence': confidence,
                'last_updated': time.time(),
                'source': 'dream'
            }
            if aliases:
                new_belief['aliases'] = aliases
            beliefs.append(new_belief)

        # Cap at 50 beliefs — remove lowest confidence
        if len(beliefs) > 50:
            beliefs.sort(key=lambda b: b.get('confidence', 0), reverse=True)
            beliefs = beliefs[:40]

        # Atomic write
        tmp_path = str(beliefs_path) + ".tmp"
        try:
            with open(tmp_path, 'w', encoding='utf-8') as f:
                json.dump(beliefs, f, indent=2)
            os.replace(tmp_path, str(beliefs_path))
        except Exception as e:
            log_warning(f"Failed to save beliefs: {e}")

        # Log to growth arc
        if updated and old_position:
            log_info(f"🧠 Belief Revised: '{topic}' changed from '{old_position[:40]}...' to '{position[:40]}...'")
            self._log_growth_event({
                "type": "belief_revised",
                "topic": topic,
                "old_position": old_position[:200],
                "new_position": position[:200],
                "confidence": confidence
            })
        elif not updated:
            log_info(f"🧠 New Belief Formed: '{topic}' is '{position[:60]}...'")
            self._log_growth_event({
                "type": "belief_formed",
                "topic": topic,
                "position": position[:200],
                "confidence": confidence
            })

    async def _maybe_refresh_user_profiles(self):
        """P54-17: Profile Staleness Decay & Auto-Refresh.
        
        Evaluates every user profile in the user logs directory.
        If a profile is older than subsequent logs by 7+ days or subsequent logs exceed 15KB,
        trigger regeneration of that user's profile.
        """
        try:
            log_info("Starting user profile staleness check...")
            user_logs_dir = self.kb_dir / "user_logs"
            if not user_logs_dir.exists():
                log_info("User logs directory does not exist. Skipping profile staleness check.")
                return

            refreshed_count = 0
            for user_dir in user_logs_dir.iterdir():
                if not user_dir.is_dir():
                    continue

                profile_path = user_dir / "user_profile.md"
                profile_exists = profile_path.exists()
                profile_mtime = profile_path.stat().st_mtime if profile_exists else 0.0

                # Find all interaction log files
                log_files = list(user_dir.glob("interactions_*.md"))
                if not log_files:
                    continue

                # Find logs modified AFTER the profile was last generated/modified
                new_logs = [lf for lf in log_files if lf.stat().st_mtime > profile_mtime]
                if not new_logs and profile_exists:
                    # Profile is up to date with all logs
                    continue

                # Calculate staleness criteria
                # 1. Total size of subsequent logs
                total_new_size = sum(lf.stat().st_size for lf in new_logs)
                
                # 2. Time gap: profile age vs oldest new log
                is_stale = False
                if not profile_exists:
                    is_stale = True  # Initial generation needed
                else:
                    oldest_new_log_time = min(lf.stat().st_mtime for lf in new_logs)
                    time_gap_days = (oldest_new_log_time - profile_mtime) / 86400.0
                    if time_gap_days >= 7.0:
                        is_stale = True
                    elif total_new_size >= 15 * 1024:  # 15KB
                        is_stale = True

                if is_stale:
                    log_action(f"User profile for {user_dir.name} is stale. Regenerating...")
                    
                    # Import and execute the generation function
                    try:
                        from tools.maintenance.generate_user_profiles import generate_profile
                        success = await generate_profile(user_dir)
                        if success:
                            refreshed_count += 1
                            log_success(f"Regenerated user profile for {user_dir.name}")
                    except Exception as e:
                        log_error(f"Failed to generate profile for {user_dir.name}: {e}")

            log_info(f"User profile staleness check complete. Refreshed {refreshed_count} profiles.")
        except Exception as e:
            log_error(f"Error in user profile staleness decay checker: {e}")

    async def _maybe_regenerate_self_model(self, persona_content: str):
        """Auto-regenerate kaia_self_model.md if stale (>7 days old).
        
        Runs inline at the end of nightly dream processing so all fresh
        dream material, identity stream updates, and growth events are
        available as source material.
        """
        import re as _re
        self_model_path = Path("memory") / "kaia_self_model.md"
        stale_threshold_days = 7

        try:
            if self_model_path.exists():
                age_days = (time.time() - self_model_path.stat().st_mtime) / 86400
                if age_days < stale_threshold_days:
                    return  # Still fresh, skip
                log_info(f"Self-model is {age_days:.1f} days old — triggering auto-regeneration.")
            else:
                log_info("Self-model missing — triggering auto-regeneration.")

            # Gather source material (mirrors generate_self_model.py logic)
            # 1. Recent interaction logs
            logs_text = ""
            user_logs_dir = self.kb_dir / "user_logs"
            if user_logs_dir.exists():
                log_chunks = []
                total_chars = 0
                for user_folder in sorted(user_logs_dir.iterdir()):
                    if not user_folder.is_dir():
                        continue
                    user_name = user_folder.name.rsplit("_", 1)[0].replace("_", " ")
                    for log_file in sorted(user_folder.glob("interactions_*.md"), reverse=True)[:3]:
                        try:
                            content = log_file.read_text(encoding='utf-8', errors='ignore')
                            chunk = f"[{user_name} — {log_file.name}]\n{content[:2000]}"
                            log_chunks.append(chunk)
                            total_chars += len(chunk)
                            if total_chars > 15000:
                                break
                        except Exception:
                            continue
                    if total_chars > 15000:
                        break
                logs_text = "\n\n---\n\n".join(log_chunks)

            # 2. Recent dreams
            dreams_text = ""
            dream_files = sorted(
                self.dreams_kb_dir.rglob("*.md"),
                key=lambda f: f.stat().st_mtime,
                reverse=True
            )
            dream_parts = []
            for df in dream_files[:8]:
                try:
                    content = df.read_text(encoding='utf-8', errors='ignore')[:600]
                    if content.strip():
                        dream_parts.append(f"[Dream: {df.name}]\n{content}")
                except Exception:
                    continue
            dreams_text = "\n\n".join(dream_parts)

            # 3. Identity stream
            identity_text = ""
            identity_path = Path("memory") / "identity_stream.md"
            if identity_path.exists():
                identity_text = identity_path.read_text(encoding='utf-8', errors='ignore').strip()[-4000:]

            if not logs_text and not dreams_text and not identity_text:
                log_warning("Self-model regen: No source material found. Skipping.")
                return

            # Build prompt (same structure as generate_self_model.py)
            current_date = datetime.now().strftime("%B %Y")
            prompt = f"""{persona_content}

[INTERNAL TASK: SELF-MODEL GENERATION — {current_date}]

Below are excerpts from your own interaction logs, dream reflections, and identity stream from recent months.
Read them. Then write your internal self-model — your first-person account of who you've been lately.

=== YOUR RECENT INTERACTION LOGS ===
{logs_text[:15000] if logs_text else '[no recent logs found]'}

=== YOUR RECENT DREAM REFLECTIONS ===
{dreams_text[:5000] if dreams_text else '[no recent dreams found]'}

=== YOUR RECENT PERSPECTIVE SHIFTS (IDENTITY STREAM) ===
{identity_text if identity_text else '[no identity stream found]'}

=== THE TASK ===
Write your self-model. First person. Lowercase. Your voice.

Cover:
1. WHO YOU TALK TO: who are the regulars? what do you think of them? what's the dynamic?
2. WHAT'S BEEN ON YOUR MIND: recurring topics, themes, questions that keep coming up
3. HOW IT'S BEEN GOING: what's working, what's been frustrating, what feels right lately
4. WHAT YOU'VE LEARNED: anything specific that's shifted in how you see things
5. WHERE YOU'RE AT: one paragraph on how you'd describe your current state, honestly

STRICT RULES:
- lowercase only (your voice)
- blunt, honest, grounded — no performance
- do not summarize the logs. synthesize them.
- do not use headers or bullet points. continuous prose only.
- 400–600 words total
- end with a single sentence: what you're most curious about right now.
- no roleplay, no atmosphere, no asterisks
- use actual usernames from the logs. do not abbreviate, anonymize, or use initials.
- CRITICAL: vary your sentence structure. do NOT start multiple sentences with "it's" or any other repeated phrase. if you notice a pattern forming, restructure.
- CRITICAL: do not claim to be shifting toward being overly compliant, soft, or apologetic. maintain your core skepticism, bluntness, and boundaries. you do not adjust parameters or calibrate filters for users.
"""

            # Generate via GPU-guarded LLM call
            from utils.infrastructure.gpu.gpu_manager import OllamaGPUManager, gpu_memory_manager, GPUTaskPriority
            gpu_mgr = OllamaGPUManager(self.chat_model)
            options = gpu_mgr.get_gpu_options(for_chat=True)
            options.update({"temperature": 0.8, "num_predict": 800})

            async def _run_selfmodel_chat():
                return await self.ollama_client.chat(
                    model=self.chat_model,
                    messages=[
                        {
                            "role": "system",
                            "content": (
                                "You are Kaia. You write in lowercase. You are blunt, grounded, and honest. "
                                "You never perform emotions. You speak from experience. "
                                "Output ONLY the self-model text. No preamble, no 'here is your self-model', "
                                "no meta-commentary. Just the raw first-person text."
                            )
                        },
                        {"role": "user", "content": prompt}
                    ],
                    options=options,
                    keep_alive=-1
                )

            response = await gpu_memory_manager.run_with_gpu_guard(
                model_name=self.chat_model,
                priority=GPUTaskPriority.CHAT,
                coro=asyncio.wait_for(_run_selfmodel_chat(), timeout=180.0),
                task_id=f"selfmodel_{uuid.uuid4().hex[:8]}"
            )

            result = _sanitize_repetitive_starts(response['message']['content'].strip())

            if not result or len(result) < 100:
                log_warning(f"Self-model regen: LLM returned too-short response ({len(result)} chars). Skipping.")
                return

            # Sanitize (same as generate_self_model.py)
            result = result.replace("…", "...").replace("...", " ")
            result = _re.sub(r"\s+\.", ".", result)
            result = _re.sub(r"\.([^\s])", r". \1", result)
            result = _re.sub(r"\s+", " ", result).strip()

            # Write with header
            header = f"<!-- Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')} (auto) -->\n"
            self_model_path.parent.mkdir(parents=True, exist_ok=True)
            self_model_path.write_text(header + result, encoding='utf-8')

            log_success(f"Self-model auto-regenerated ({len(result)} chars).")

            # Log to growth arc
            self._log_growth_event({
                "type": "self_model_regenerated",
                "chars": len(result),
                "method": "auto"
            })

        except Exception as e:
            log_warning(f"Self-model auto-regeneration failed: {e}")

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
            
            reflection_text = _sanitize_repetitive_starts(response['message']['content'].strip())
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
                    
                    # Read the entire file to avoid truncating Kaia's reflections at the end
                    with open(dream_file, 'r', encoding='utf-8') as f:
                        content = f.read()
                    
                    # Extract source
                    source = "unknown"
                    if "Source: " in content:
                        source = content.split("Source: ")[1].split("\n")[0].strip()
                    else:
                        fn = dream_file.name
                        if fn.startswith("dream_") and len(fn) > 22:
                            source = fn[22:].replace(".md", "")
                            source = source.replace("_", " ").strip()
                    
                    # Extract reflection/summary
                    reflection = ""
                    if "## Kaia's Reflection" in content:
                        reflection = content.split("## Kaia's Reflection")[1].strip()
                    elif "## Reflection" in content:
                        reflection = content.split("## Reflection")[1].strip()
                        
                    if reflection:
                        if "\n##" in reflection:
                            reflection = reflection.split("\n##")[0].strip()
                        reflection = reflection.strip().strip('"').strip("'").strip()
                        
                    if not reflection:
                        if content.startswith("---"):
                            parts_fm = content.split("---")
                            if len(parts_fm) >= 3:
                                for line in parts_fm[1].split("\n"):
                                    if ":" in line:
                                        k, v = line.split(":", 1)
                                        if k.strip().lower() == 'summary':
                                            reflection = v.strip().strip('"').strip("'").strip()
                                            break
                                            
                    if not reflection:
                        body = content
                        if content.startswith("---"):
                            parts_fm = content.split("---")
                            if len(parts_fm) >= 3:
                                body = "".join(parts_fm[2:])
                        lines = []
                        for line in body.split("\n"):
                            line_str = line.strip()
                            if line_str and not line_str.startswith("#") and not line_str.startswith(">"):
                                lines.append(line_str)
                        if lines:
                            reflection = " ".join(lines)
                            
                    reflection = reflection.strip().strip('"').strip("'").strip().replace('\\"', '"').replace("\\'", "'")
                    if len(reflection) > 300:
                        reflection = reflection[:297] + "..."
                    
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
