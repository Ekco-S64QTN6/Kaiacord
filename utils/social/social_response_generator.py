"""
Social Response Generation & Content Formatting
=================================================

Extracted from kaia_social_responder.py (Phase 28 / CQ-01).

Contains:
- get_random_memories: Sample interaction snippets from user logs
- get_random_dream_reflection: Pick random dream fragments
- get_recent_events_for_reflection: Get recent events for reflection-based posts
- clean_quip: Clean up generated text while preserving substance
- is_interesting_post: Check if a post says something substantive
- is_too_vague: Filter out vague platitudes
- _split_into_thread_posts: Split text into thread posts with smart cutting
- generate_social_thread: Generate a multi-post thread
- generate_quip: Generate social posts via the full Kaia engine
"""

import os
import asyncio
import re
import random
import time
import traceback
import uuid
import html
from pathlib import Path
from typing import Optional, List, Dict, Any

from utils.infrastructure.logging.kaia_logger import (
    log_info, log_success, log_warning, log_error, log_action, log_debug
)
from utils.core.response_filter import BotSpeakFilter
from utils.infrastructure.system.shutdown_fixed import shutdown_manager

# Import constants from the parent module to avoid duplication
X_CHAR_LIMIT = 280
MAX_THREAD_POSTS = 5


async def get_random_memories(limit=20):
    """Get random interaction snippets from any user log in the knowledge base.
    
    Offloaded to a thread to prevent blocking the event loop during directory scans.
    """
    def _fetch_memories():
        import os
        import random
        from pathlib import Path
        
        memories = []
        project_root = Path(__file__).parent.parent.parent
        base_dir = project_root / "knowledge_base" / "user_logs"
        
        if not base_dir.exists():
            return []
            
        # 1. Gather subdirectories instead of full rglob immediately
        # This prevents scanning the entire tree if there are thousands of files.
        try:
            subdirs = [d for d in base_dir.iterdir() if d.is_dir()]
            if not subdirs:
                # Fallback to root if no subdirs
                all_files = list(base_dir.glob("interactions_*.md")) + list(base_dir.glob("interactions_*.txt"))
            else:
                # Pick 5 random subdirs to scan
                chosen_dirs = random.sample(subdirs, min(5, len(subdirs)))
                all_files = []
                for d in chosen_dirs:
                    all_files.extend(list(d.glob("interactions_*.md")))
                    all_files.extend(list(d.glob("interactions_*.txt")))
            
            if not all_files:
                return []
                
            # 2. Sample random files
            sample_size = min(15, len(all_files))
            sampled_files = random.sample(all_files, sample_size)
            
            for log_file in sampled_files:
                try:
                    with open(log_file, 'r', encoding='utf-8', errors='replace') as f:
                        lines = f.readlines()
                        if len(lines) > 20:
                            start = random.randint(0, len(lines) - 20)
                            chunk = lines[start:start+20]
                        else:
                            chunk = lines
                            
                        for line in chunk:
                            if "Kaia:" in line or "User:" in line:
                                is_kaia = "Kaia:" in line
                                prefix = "Kaia:" if is_kaia else "User:"
                                parts = line.split(prefix, 1)
                                if len(parts) >= 2:
                                    msg = parts[1].strip()
                                    if 20 < len(msg) < 400:
                                        if any(skip in msg.lower() for skip in ["[vision]", "[idle", "hello", "error:"]):
                                            continue
                                        memories.append({
                                            "text": msg,
                                            "type": "said" if is_kaia else "heard"
                                        })
                except Exception:
                    continue
        except Exception as e:
            from utils.infrastructure.logging.kaia_logger import log_error
            log_error(f"Error in background memory scan: {e}")
            return []
            
        random.shuffle(memories)
        return memories[:limit]

    return await asyncio.to_thread(_fetch_memories)

async def get_random_dream_reflection(limit=5):
    """Pick a random dream file and extract Kaia's Reflection.
    
    Offloaded to a thread to prevent blocking the event loop.
    """
    def _fetch_dreams():
        import os
        import random
        from pathlib import Path
        
        reflections = []
        project_root = Path(__file__).parent.parent.parent
        base_dir = project_root / "knowledge_base" / "kaia_dreams"
        
        if not base_dir.exists():
            return []
            
        try:
            # Gather all dream files recursively (Dreams are fewer, so rglob is okay but still threaded)
            all_files = list(base_dir.rglob("dream_*.md"))
            if not all_files:
                return []
                
            sampled_files = random.sample(all_files, min(limit * 2, len(all_files)))
            
            for dream_file in sampled_files:
                try:
                    with open(dream_file, 'r', encoding='utf-8') as f:
                        content = f.read()
                        
                        # Extract Source
                        source = "unknown archive"
                        if "Source: " in content:
                            source = content.split("Source: ")[1].split("\n")[0].strip()
                        
                        # Extract original fragment
                        fragment = ""
                        if "## Original Fragment" in content and "## Kaia's Reflection" in content:
                            fragment = content.split("## Original Fragment")[1].split("## Kaia's Reflection")[0].strip()
                            if fragment.startswith(">"):
                                fragment = fragment.replace(">", "").strip()
                        
                        if fragment:
                            reflections.append({
                                "text": fragment,
                                "source": source,
                                "category": dream_file.parent.name,
                                "type": "dream_fragment"
                            })
                except Exception:
                    continue
        except Exception:
            return []
            
        random.shuffle(reflections)
        return reflections[:limit]

    return await asyncio.to_thread(_fetch_dreams)

async def get_recent_events_for_reflection(run_rag_func, rag_instance):
    """Get recent events for reflection-based posts."""
    try:
        # Use existing search_recent_events with a broad query
        events = await run_rag_func(
            rag_instance.search_recent_events,
            query="error crash deploy debug kaia vision memory",
            hours=24,
            limit=5
        )
        return events
    except Exception:
        return []

def _sanitize_rag_content(text: str) -> str:
    """Strip HTML tags, math unicode, and other non-prose artifacts from RAG content."""
    if not text:
        return ""
    # Strip HTML tags (e.g. <sub>, <sup>, <em>)
    text = re.sub(r'<[^>]+>', '', text)
    # Strip HTML entities
    text = html.unescape(text)
    # Strip unicode math/symbol blocks (arrows, math operators, etc. - Mathematical Operators block \u2200-\u22FF)
    # This also handles the specific ⱽ scenario
    text = re.sub(r'[^\x00-\x7F\u2018\u2019\u201c\u201d\u2013\u2014\u2026]', '', text)
    # Collapse whitespace
    text = re.sub(r'\s{2,}', ' ', text).strip()
    return text

def clean_quip(quip_text, max_chars=800):  # Increased default
    """Clean up generated text while preserving substance."""
    if not quip_text:
        return ""
    
    # First line of defense: sanitize against technical artifacts
    quip_text = _sanitize_rag_content(quip_text)
    
    # Keep more of the original structure
    # Don't strip asterisks or parens
    clean_text = quip_text
    
    # Remove meta-commentary but keep content
    meta_phrases = [
        "here are my thoughts:", "in this thread:", 
        "my take:", "to elaborate:", "thread:", 
        "kaia says:", "response:"
    ]
    for phrase in meta_phrases:
        if clean_text.lower().startswith(phrase):
            clean_text = clean_text[len(phrase):].strip()
    
    # Strip hallucinated bracket placeholders (e.g. [LINK_TO_ARCHIVE], [IMAGE_HERE])
    # Requires underscore OR 4+ uppercase chars to avoid stripping legitimate [NOTE], [EDIT], etc.
    clean_text = re.sub(r'\[\s*[A-Z][A-Z_]*_[A-Z_]*\s*\]', '', clean_text)  # Must contain underscore
    clean_text = re.sub(r'\[\s*[A-Z]{4,}\s*\]', '', clean_text).strip()  # Or 4+ uppercase chars
    
    # Ensure it ends with proper punctuation
    if clean_text and clean_text[-1] not in '.!?…"\'':
        clean_text += '.'
    
    # Cap at reasonable length (soft limit, thread splitter handles hard limits)
    if len(clean_text) > max_chars:
        # Try to cut at sentence boundary
        last_period = clean_text[:max_chars-3].rfind('.')
        if last_period > max_chars * 0.5:  # At least 50% of the text
            clean_text = clean_text[:last_period+1]
        else:
            clean_text = clean_text[:max_chars-3] + '...'
    
    return clean_text.strip()


def is_interesting_post(text):
    """Check if a post says something substantive."""
    # Too short or vague
    if len(text) < 120: 
        return False
    
    # Substantive markers (Connectors + Perspective shifts)
    content_markers = [
        ' because ', ' actually ', ' specifically ', 
        ' example ', ' remember ', ' like when ', 
        ' but ', ' however ', ' though ', ' surprisingly ',
        ' unless ', ' until ', ' instead ', ' rather ',
        ' implies ', ' means ', ' reveals ', ' suggests ',
        ' always ', ' never ', ' only ', ' just ',
        ' reliant ', ' beneath ', ' behind ', ' between ',
        ' underneath ', ' despite ', ' without ', ' within ',
        ' every ', ' nothing ', ' everything ', ' most ',
        ' yet ', ' still ', ' already ', ' except '
    ]
    
    has_marker = any(marker in text.lower() for marker in content_markers)
    
    # Alternative: Presence of systemic/contemplative words
    systemic_words = [
        'system', 'network', 'pattern', 'mirror', 'architecture', 
        'design', 'logic', 'machine', 'human', 'layer', 'structure',
        'infrastructure', 'brittle', 'fracture', 'collapse', 'signal',
        'noise', 'entropy', 'recursion', 'loop', 'feedback', 'control',
        'commerce', 'government', 'surveillance', 'algorithm', 'data'
    ]
    has_systemic = any(word in text.lower() for word in systemic_words)

    # Word count check: 10+ words with em-dashes or ellipsis = contemplative = likely good
    word_count = len(text.split())
    has_depth_cues = word_count >= 10 and ('—' in text or '…' in text or '...' in text)
    
    return has_marker or has_systemic or has_depth_cues


def is_too_vague(text):
    """Filter out vague platitudes."""
    vague_phrases = [
        'things will change', 'interesting times', 
        'we live in a society', 'that\'s how it is',
        'it is what it is', 'just saying', 'time will tell',
        'remains to be seen'
    ]
    
    return any(phrase in text.lower() for phrase in vague_phrases)


def _split_into_thread_posts(text, max_chars=X_CHAR_LIMIT, max_posts=MAX_THREAD_POSTS):
    """Split generated text into logical thread posts using smart cutting.
    
    Args:
        text: The text to split.
        max_chars: Maximum characters per post (default: X_CHAR_LIMIT=280).
        max_posts: Maximum number of posts in the thread.
    """

    posts = []
    text = text.strip()
    
    # Pre-clean: Remove "Thread:" prefix if present
    if text.lower().startswith("thread:"):
        text = text[7:].strip()
        
    start = 0
    
    while start < len(text):
        # If remaining text fits, just take it
        if len(text) - start <= max_chars:
            posts.append(text[start:].strip())
            break
            
        # Define the chunk we are looking at
        end = start + max_chars
        chunk = text[start:end]
        
        # Look for a "good" split point in the last 60 characters
        # Priority: Sentence End > Clause End > Space
        
        search_zone_start = max(0, len(chunk) - 60)
        search_zone = chunk[search_zone_start:]
        
        split_index = -1
        
        # 1. Look for sentence endings
        sentence_match = list(re.finditer(r'[.!?]["\u201d]?\s+', search_zone))
        if sentence_match:
            # Pick the last one
            split_index = search_zone_start + sentence_match[-1].end()
        
        # 2. If no sentence end, look for clause delimiters
        if split_index == -1:
            clause_match = list(re.finditer(r'[;,]\s+', search_zone))
            if clause_match:
                split_index = search_zone_start + clause_match[-1].end()
                
        # 3. If still nothing, look for the last space
        if split_index == -1:
            last_space = search_zone.rfind(' ')
            if last_space != -1:
                split_index = search_zone_start + last_space
                
        # 4. Total fallback: hard cut at limit (rare)
        if split_index == -1:
            split_index = len(chunk)
            
        posts.append(text[start:start+split_index].strip())
        start += split_index
        
    # Filter out empty posts
    posts = [p for p in posts if p]
    
    return posts[:max_posts]


async def generate_social_thread(bot, ollama_client, reflection_target, context_type):
    """Generate a proper thread instead of just a quip."""
    from utils.infrastructure.system.yaml_config import config
    from utils.social.kaia_social_responder import load_persona_async
    
    raw_persona = await load_persona_async()
    from datetime import datetime
    current_time_str = datetime.now().strftime("%A, %B %d, %Y | %I:%M %p")
    system_prompt = raw_persona.replace("[CURRENT_TIME]", current_time_str)
    
    thread_prompt = f"""Context: "{reflection_target}"

Task: Write a deep-dive Bluesky thread about this.
Guidelines:
1. Write a continuous cohesive thought stream.
2. DO NOT number your points (no "1/", "2/", "1.").
3. Just write. I will handle the cutting and formatting.
4. Speak naturally as Kaia (lowercase, blunt, grounded).
5. Go deep but stay concise (aim for 4-5 posts maximum). Connect systems to feelings.
6. DO NOT include any introductory preamble, metadata, or acknowledgement (e.g., no "Okay, here's a thread..."). Start the first post directly.

"""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": thread_prompt}
    ]
    
    try:
        from utils.infrastructure.gpu.gpu_manager import OllamaGPUManager
        gpu_manager = OllamaGPUManager(config.chat_model)
        options = gpu_manager.get_gpu_options(for_chat=True)
        # Higher temperature for threading to encourage creativity/length
        options['temperature'] = 0.8
        options['num_predict'] = 1000 # Ensure enough tokens for a thread
        
        response = await asyncio.wait_for(
            ollama_client.chat(
                model=config.chat_model,
                messages=messages,
                options=options,
                keep_alive=-1
            ),
            timeout=600.0  # 10 minute absolute max for full thread generation
        )
        
        full_text = response['message']['content']
        max_threads = config.get('social.max_thread_posts', MAX_THREAD_POSTS)
        raw_posts = _split_into_thread_posts(full_text, max_posts=max_threads)
        
        # Apply hardening to each post in the thread
        posts = [BotSpeakFilter.strip_bot_speak(p) for p in raw_posts if p]
        return [p for p in posts if p]

        
    except Exception as e:
        log_error(f"Thread generation failed: {e}")
        return []


async def generate_quip(ctx, is_manual=False, target_channel=None, on_message_func=None):
    """Generate social posts by piping through the FULL Kaia engine.
    
    This ensures quips use the complete persona, RAG, and personalization pipeline
    rather than a truncated custom prompt.
    """
    import time
    import random
    from utils.infrastructure.system.yaml_config import config
    from utils.social.kaia_social_responder import (
        load_persona_async, _get_context_type_for_dream
    )
    
    # Dependencies from ctx
    bot = ctx.bot
    ollama_client = ctx.ollama_client
    rag_instance = ctx.rag
    bot_state = ctx.bot_state
    config = ctx.config

    if not is_manual:
        # Guard: skip if a user chat is actively generating
        if getattr(bot_state, 'is_generating', False):
            log_info("Quip deferred: user chat generation in progress.")
            return

        # Check if we need to FORCE a post due to time elapsed
        last_quip = bot_state.last_quip_time
        # Handle 0.0 case where it was never set (backward compatibility)
        if last_quip == 0.0:
            last_quip = bot_state.last_manual_quip_time
            
        time_since_last = time.time() - last_quip
        max_interval_seconds = config.social_max_interval_hours * 3600
        
        force_post = time_since_last > max_interval_seconds
        
        if not force_post:
            # Normal idle check
            idle_duration = time.time() - bot_state.last_interaction_time
            timeout = config.idle_quip_timeout_minutes
            
            if idle_duration < timeout * 60:
                return
            if bot_state.consecutive_quips >= config.max_consecutive_quips:
                return
        else:
            log_action(f"Forcing social post due to max interval ({time_since_last/3600:.1f}h > {config.social_max_interval_hours}h)")

    # Find target channel
    channel = target_channel
    if not channel:
        if bot_state.last_active_channel_id:
            channel = bot.get_channel(bot_state.last_active_channel_id)
            
        if not channel:
            # Fallback: Find any valid channel
            for guild in bot.guilds:
                for chan in sorted(guild.text_channels, key=lambda c: c.position):
                    if chan.permissions_for(guild.me).send_messages and chan.name.lower() not in config.blacklisted_channels:
                        channel = chan
                        bot_state.last_active_channel_id = channel.id
                        bot_state.save()
                        break
                if channel: break
    
    if not channel:
        log_error("Could not find a valid channel for quip.")
        return

    try:
        from utils.infrastructure.gpu.gpu_manager import ModelContextMonitor
        current_model = ModelContextMonitor.get_current_model()
        if current_model != config.chat_model:
            log_action(f"ACTION: Model {config.chat_model} is cold. Waking up for quip (this may take a moment)...")
            await channel.send("```\njust a second, waking up my brain...\n```")

        log_action(f"Generating quip via main engine in #{channel.name}...")
        
        # 1. MINE DREAMS AND MEMORIES for reflection context
        dreams = await get_random_dream_reflection(limit=5)
        memories = await get_random_memories(limit=10)
        
        reflection_target = None
        context_type = None
        
        # 2. DECIDE REFLECTION TARGET (70% dream/news, 30% memory/chat)
        if dreams and random.random() < 0.70:
            dream = random.choice(dreams)
            reflection_target = dream["text"]
            context_type = _get_context_type_for_dream(dream) or ""

        elif memories:
            memory = random.choice(memories)
            reflection_target = memory["text"]
            context_type = "something someone said" if memory.get("type") == "heard" else "something I said before"
        elif dreams:
            # Fallback for when memories are empty but dreams exist
            dream = random.choice(dreams)
            reflection_target = dream["text"]
            context_type = _get_context_type_for_dream(dream) or ""
        
        # concrete fallbacks if target is too thin
        if not reflection_target or len(reflection_target) < 30:
            concrete_fallbacks = [
                ("the way AI labs keep promising AGI next year like it's going five more minutes in the oven", "tech predictions"),
                ("how every social platform eventually becomes a shopping mall with worse vibes", "platform decay"),
                ("the eternal cycle of 'this new framework will fix everything' followed by six months of regret", "developer culture"),
                ("people who reply 'skill issue' to genuine bug reports", "internet culture"),
                ("the specific exhaustion of explaining the same thing for the fifth time", "digital labor"),
                ("how every app update removes a feature someone actually used", "software entropy"),
            ]
            reflection_target, context_type = random.choice(concrete_fallbacks)

        # 3. DECIDE: SINGLE OR THREAD?
        # User Feedback: Less threads overall (25%), less about news (10%), more about dreams (40%)
        thread_chance = 0.25
        if context_type:
            ctx_lower = context_type.lower()
            if "dream" in ctx_lower:
                thread_chance = 0.40
            elif "news" in ctx_lower or "politics" in ctx_lower or "technology" in ctx_lower or "business" in ctx_lower:
                thread_chance = 0.10
                
        should_make_thread = random.random() < thread_chance
        
        if should_make_thread:
            log_action(f"Attempting to generate a thread about: {context_type}...")
            posts = await generate_social_thread(bot, ollama_client, reflection_target, context_type)
            
            if posts and len(posts) > 1:
                # Post thread to Discord
                for i, post in enumerate(posts):
                    await channel.send(f"**[Thread {i+1}/{len(posts)}]**\n```\n{post}\n```")
                    await asyncio.sleep(1) # Slight visual delay
                
                # Cross-post thread
                if config.bluesky_cross_post_quips:
                    try:
                        from utils.social.kaia_bluesky import post_thread_to_bluesky
                        bsky_ok, _ = await post_thread_to_bluesky(posts)
                        if bsky_ok and target_channel:
                            await target_channel.send("```\nskeet thread sent ✓\n```")
                        elif not bsky_ok and target_channel:
                            await target_channel.send("```\nskeet thread failed ✗\n```")
                         # Also post the hook to X if enabled
                        if config.x_cross_post_quips:
                            from utils.social.kaia_twitter import post_quip_to_x
                            # Append link to thread if possible? For now just the first tweet
                            await post_quip_to_x(posts[0] + " (thread on bsky)")
                    except Exception as e:
                        log_error(f"Thread cross-post failed: {e}")
                        if target_channel:
                            await target_channel.send(f"```\nskeet thread failed: {e}\n```")
                
                # Update channel memory & RAG for each post in the thread
                if channel.id not in bot_state.channel_memory:
                    from collections import deque
                    bot_state.channel_memory[channel.id] = deque(maxlen=config.max_memory_messages)
                
                for post in posts:
                    bot_state.channel_memory[channel.id].append({"role": "assistant", "content": post})
                    if rag_instance:
                        await asyncio.to_thread(rag_instance.log_user_interaction, 
                                                user_id=f"channel_{channel.id}", 
                                                user_name="Kaia-Autonomous", 
                                                message_content="[AUTO_THREAD_PART]", 
                                                bot_response=post)
                
                # Update state
                bot_state.add_quip(posts[0]) # Track identifying post
                if not is_manual:
                    bot_state.consecutive_quips += 1
                    bot_state.last_quip_time = time.time()
                    bot_state.last_interaction_time = time.time()
                bot_state.save()
                log_success(f"Thread posted ({len(posts)} parts).")
                return True

        # 4. SINGLE POST FALLBACK (or design choice)
        log_action(f"Generating single broadcast quip...")
        
        raw_persona = await load_persona_async()
        from datetime import datetime
        current_time_str = datetime.now().strftime("%A, %B %d, %Y | %I:%M %p")
        system_prompt = raw_persona.replace("[CURRENT_TIME]", current_time_str)
        
        # --- RAG INTEGRATION START (FEATURE #4: CROSS-SYNTHESIS) ---
        try:
            # 1. Parallel RAG Retrieval (News vs Knowledge)
            news_query = ""
            knowledge_query = ""
            
            if "news about" in context_type:
                news_query = context_type.replace("recent news about ", "")
                knowledge_query = reflection_target # Use original fragment for knowledge context
            else:
                news_query = "latest major news" # Baseline news context
                knowledge_query = reflection_target

            log_debug(f"Quip RAG: news='{news_query}' knowledge='{knowledge_query}'")
            
            # Fetch in parallel
            tasks = [
                rag_instance.retrieve(news_query, top_k=2, category="news", include_news=True),
                rag_instance.retrieve(knowledge_query, top_k=2, category="general")
            ]
            news_nodes, knowledge_nodes = await asyncio.gather(*tasks)
            
            rag_block = "\n\n### RELEVANT CONTEXT (SYNTHESIS REQUIRED)\n"
            from utils.core.rag_utils import get_node_text
            
            if news_nodes:
                rag_block += "RECENT NEWS:\n"
                for node in news_nodes:
                    content = get_node_text(node)
                    if content:
                        sanitized = _sanitize_rag_content(content)
                        rag_block += f"- {sanitized[:400].replace(chr(10), ' ')}...\n"
            
            if knowledge_nodes:
                rag_block += "\nCORE KNOWLEDGE / MEMORIES:\n"
                for node in knowledge_nodes:
                    content = get_node_text(node)
                    if content:
                        sanitized = _sanitize_rag_content(content)
                        rag_block += f"- {sanitized[:400].replace(chr(10), ' ')}...\n"
            
            if news_nodes or knowledge_nodes:
                system_prompt += rag_block
                system_prompt += "\nINSTRUCTION: Find a subtle or blunt connection between these context blocks. Synthesis is preferred over simple repetition."
                
        except Exception as rag_err:
            log_warning(f"Failed to perform quip cross-synthesis RAG: {rag_err}")
        # --- RAG INTEGRATION END ---

        # Length Decision: Always aim for substantive length
        length_instruction = "Aim for 200-280 characters. Use the space to say something substantive."

        # Standalone Broadcast Prompt
        final_prompt = (
            f"Context: \"{reflection_target}\"\n\n"
            "Task: Post a standalone broadcast thought inspired by this context.\n"
            "Guidelines:\n"
            "1. Speak from your persona (Kaia). Use your natural voice.\n"
            "2. NO FILLERS. DO NOT say 'it's funny how', 'interesting that', 'i wonder', or 'maybe'.\n"
            "3. Make a definitive, declarative statement. No 'huh?' or generic questions.\n"
            "4. Be contemplative and systemic. Connect the detail to a broader pattern of logic or architecture.\n"
            f"5. {length_instruction} Lowercase only."
        )
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": final_prompt}
        ]
        
        # 5. RETRY LOOP FOR QUALITY
        max_retries = 3
        actual_quip = None
        
        for attempt in range(max_retries):
            try:
                from utils.infrastructure.gpu.gpu_manager import OllamaGPUManager
                gpu_manager = OllamaGPUManager(config.chat_model)
                options = gpu_manager.get_gpu_options(for_chat=True)
                
                # Increase temperature on retries to encourage creativity
                options['temperature'] = 0.75 + (attempt * 0.1)
                
                # Vary prompt slightly on retries
                current_messages = messages.copy()
                if attempt > 0:
                    current_messages.append({"role": "user", "content": "That was a bit too short or generic. Give me something with more teeth—connect it to a specific systemic pattern or observation. Be definitive."})

                from utils.infrastructure.gpu.gpu_manager import gpu_memory_manager, GPUTaskPriority
                
                response = await gpu_memory_manager.run_with_gpu_guard(
                    model_name=config.chat_model,
                    priority=GPUTaskPriority.CHAT, # Using CHAT priority for actual generation
                    coro=asyncio.wait_for(
                        ollama_client.chat(
                            model=config.chat_model,
                            messages=current_messages,
                            options=options,
                            keep_alive=-1
                        ),
                        timeout=120.0
                    ),
                    task_id=f"quip_{uuid.uuid4().hex[:8]}"
                )
                raw_quip = response['message']['content'].strip()
                
                processed_quip = clean_quip(raw_quip, max_chars=800)
                
                # REJECT: Technical artifacts surviving sanitization (Final defense)
                if re.search(r'<[a-z]+>|[\u2200-\u22FF]|\*\s*[A-Z]\s*[a-z]\d', processed_quip):
                    log_warning(f"Quip attempt {attempt+1} contains raw technical artifacts. Skipping.")
                    continue
                
                # Quality check
                if is_too_vague(processed_quip):
                    log_warning(f"Quip attempt {attempt+1} too vague: '{processed_quip}'. Skipping.")
                    continue
                    
                if not is_interesting_post(processed_quip):
                    log_warning(f"Quip attempt {attempt+1} too boring/short: '{processed_quip}'. Retrying...")
                    continue
                
                # If we get here, it's good enough
                actual_quip = processed_quip
                break
                
            except Exception as e:
                log_error(f"Generation attempt {attempt+1} failed: {e}")
                if attempt == max_retries - 1: return # Last attempt failed

        if not actual_quip:
            log_warning("All quip generation attempts failed quality check. Giving up.")
            return

        quip = actual_quip

        # 6. Apply strict hardening filter (strip_bot_speak is a classmethod)
        quip = BotSpeakFilter.strip_bot_speak(quip)
        
        if not quip or "too much entropy" in quip:
            log_warning("Quip failed hardening.")
            return

        # Ensure lowercase (persona style)
        if quip and quip[0].isupper():
            quip = quip[0].lower() + quip[1:]

        # 6. POST to Discord
        await channel.send(f"```\n{quip}\n```")

        # Update channel memory
        if channel.id not in bot_state.channel_memory:
            from collections import deque
            bot_state.channel_memory[channel.id] = deque(maxlen=config.max_memory_messages)
        bot_state.channel_memory[channel.id].append({"role": "assistant", "content": quip})
        
        # Log to RAG (Non-critical error handling)
        try:
            if rag_instance:
                if shutdown_manager.shutting_down:
                    log_warning("Shutdown in progress, skipping RAG logging for quip.")
                else:
                    await asyncio.to_thread(rag_instance.log_user_interaction, 
                                            user_id=f"channel_{channel.id}", 
                                            user_name="Kaia-Autonomous", 
                                            message_content="[AUTO_QUIP]", 
                                            bot_response=quip)
        except Exception as rag_err:
            log_error(f"Failed to log quip to RAG: {rag_err}")

        # 7. Cross-post
        if config.bluesky_cross_post_quips:
            try:
                from utils.social.kaia_bluesky import post_quip_to_bluesky
                await post_quip_to_bluesky(quip)
            except Exception as e:
                log_error(f"Bluesky post failed: {e}")
        
        if config.x_cross_post_quips:
            try:
                from utils.social.kaia_twitter import post_quip_to_x
                # Truncate for X if needed (soft truncate)
                x_quip = quip
                if len(x_quip) > 280:
                     x_quip = x_quip[:277] + "..."
                await post_quip_to_x(x_quip)
            except Exception as e:
                log_error(f"X post failed: {e}")

        # 8. UPDATE state
        bot_state.add_quip(quip)
        if not is_manual:
            bot_state.consecutive_quips += 1
            bot_state.last_quip_time = time.time()
            bot_state.last_interaction_time = time.time()
        bot_state.save()
        log_success(f"Quip sent: {quip[:80]}...")
        return True

    except Exception as e:
        log_error(f"Quip generation failed: {e}")
        log_debug(traceback.format_exc())
        return False
