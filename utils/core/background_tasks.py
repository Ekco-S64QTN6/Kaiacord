from utils.ttrpg.narration import finish_cleanly
from contextlib import asynccontextmanager
import asyncio
import json
import re
import time
import sys
import os
from datetime import datetime, timedelta
from pathlib import Path

#: The first dream check waits this long after the bot comes up.
DREAM_AFTER_BOOT_S = 20 * 60
NEWS_DAILY_DIR = Path("knowledge_base/news/daily")
NEWS_FOLLOWUP_STATE_PATH = Path("memory/news_followup_retry.json")
import discord
from discord.ext import tasks
from utils.infrastructure.logging.kaia_logger import log_action, log_success, log_error, log_info, log_warning, log_debug
from utils.infrastructure.logging.log_sanitize import summarize_payload
from utils.infrastructure.system.bot_state import bot_state
from utils.infrastructure.system.yaml_config import config
from utils.infrastructure.system.shutdown_fixed import shutdown_manager


def _request_rag_retry(reason: str) -> None:
    """Keep a refresh request visible when a background refresh did not finish."""
    try:
        from utils.core.rag_utils import request_reindex
        request_reindex()
    except Exception as exc:
        log_error(f"[RAG] Could not queue retry after {reason}: {exc}")
        return
    log_warning(f"[RAG] Refresh did not complete after {reason}; queued a maintenance retry.")


async def _mutate_player_sheet(user_id, mutation):
    """Apply a synchronous mutation to a fresh sheet under the RPG user-action lock.

    The caller may use load_all() to discover candidate IDs, but must not carry
    those detached snapshots into this function. Re-load only after taking the
    same user:<uid> lock as typed commands and views. The mutation callback must
    not perform Discord I/O, sleeps, or other awaits.
    """
    from utils.ttrpg.character_manager import load, save
    from utils.ttrpg.session_manager import get_action_lock

    uid = str(user_id)
    async with await get_action_lock(f"user:{uid}"):
        sheet = await load(uid)
        if not sheet:
            return None
        result = mutation(sheet)
        if result is None:
            return None
        await save(sheet)
        return result


async def _mutate_player_housing(user_id, mutation):
    """Fresh-load and mutate one housing file under its owner's action lock."""
    from utils.ttrpg.housing import load_housing_async, save_housing_async
    from utils.ttrpg.session_manager import get_action_lock

    uid = str(user_id)
    async with await get_action_lock(f"user:{uid}"):
        housing = await load_housing_async(uid)
        if not housing:
            return None
        result = mutation(housing)
        if result is None:
            return None
        await save_housing_async(housing)
        return result


async def _commit_background_combat_result(
    user_id,
    *,
    starting_hp,
    simulated_hp,
    consumed_conditions=(),
    xp_reward=0,
    gil_reward=0,
    reputation_delta=0,
    knockout_xp_reward=0,
    knockout_gil_reward=0,
):
    """Apply a raid's combat delta and reward to the latest character sheet.

    Combat is simulated on an event-start snapshot without holding a user's
    lock through Discord narration or the encounter. At commit time, apply
    only the simulated HP delta and consumed conditions to a freshly loaded
    sheet. Rewards are additive; level-up and knockout consequences are
    recomputed from the fresh character state.
    """
    from utils.ttrpg.progression import check_level_up
    from utils.ttrpg.rpg_combat_handler import _apply_overworld_blackout

    simulated_knockout = simulated_hp <= 0
    consumed = set(consumed_conditions or ())

    def apply(sheet):
        character_name = sheet.get("character_name", "An adventurer")
        hp = sheet.setdefault("hp", {})
        current_hp = int(hp.get("current", 0) or 0)
        max_hp = int(hp.get("max", max(current_hp, 1)) or 1)
        hp_delta = int(simulated_hp) - int(starting_hp)
        hp["current"] = max(0, min(max_hp, current_hp + hp_delta))

        conditions = sheet.setdefault("conditions", [])
        for condition in consumed:
            if condition in conditions:
                conditions.remove(condition)

        # The bank heist pays a half reward to a defender who was knocked out
        # while the team won. Other background fights use the normal blackout
        # penalties when the fresh sheet is still at 0 HP.
        blackout = None
        rewarded_knockout = simulated_knockout and bool(
            knockout_xp_reward or knockout_gil_reward
        )
        knockout_applied = rewarded_knockout and hp["current"] <= 0
        if knockout_applied:
            hp["current"] = 1
            sheet["location"] = "shrine"
            sheet["deaths"] = sheet.get("deaths", 0) + 1

        xp_to_add = knockout_xp_reward if simulated_knockout else xp_reward
        gil_to_add = knockout_gil_reward if simulated_knockout else gil_reward
        if xp_to_add:
            sheet["xp"] = sheet.get("xp", 0) + int(xp_to_add)
        if gil_to_add:
            sheet["gil"] = sheet.get("gil", 0) + int(gil_to_add)
        if reputation_delta:
            sheet["reputation"] = sheet.get("reputation", 0) + int(reputation_delta)
            if reputation_delta < 0:
                sheet["reputation"] = max(-100, sheet["reputation"])

        # If the encounter snapshot showed a knockout but a concurrent heal
        # left the fresh character standing, do not force the stale death onto
        # them. A fresh character reduced to 0 HP by the event delta still uses
        # the standard blackout after the event's rewards are applied.
        if not rewarded_knockout and hp["current"] <= 0:
            blackout = _apply_overworld_blackout(sheet)
            for condition in ("embered", "fortified"):
                if condition in conditions:
                    conditions.remove(condition)

        leveled, new_level = check_level_up(sheet)

        return {
            "character_name": character_name,
            "leveled": leveled,
            "new_level": new_level,
            "blackout": blackout,
            "simulated_knockout": simulated_knockout,
            "knockout_applied": knockout_applied,
            "hp": hp.get("current", 0),
            "deaths": sheet.get("deaths", 0),
        }

    return await _mutate_player_sheet(user_id, apply)



async def _reset_dawn_character(user_id, today):
    """Apply dawn-only character flags to a fresh sheet under its action lock.

    character_manager.load() also performs its idempotent daily hunt/condition
    reset under the character manager's file lock. The action lock held by
    _mutate_player_sheet protects the full read-modify-write against live
    commands, views, and other background events.
    """
    from utils.ttrpg.calendar import SPECIAL_DAYS
    from utils.ttrpg.progression import PERMANENT_CONDITIONS

    def reset(sheet):
        modified = False
        if sheet.get("hunts_reset_date") != today:
            sheet["hunts_today"] = 0
            sheet["hunts_reset_date"] = today
            sheet["forest_event_attempts_today"] = 0
            modified = True

        flags = sheet.get("flags")
        if isinstance(flags, dict) and flags.get("caravan_gear_bought"):
            flags["caravan_gear_bought"] = False
            modified = True

        # First Day of Winter grants temporary max HP. Remove only when the
        # matching receipt flag is present, so repeated dawn runs cannot stack.
        if sheet.pop("_winter_resolve_applied", None):
            winter_bonus = next(
                (day.get("buff_value", 0) for day in SPECIAL_DAYS.values()
                 if day.get("buff") == "winter_resolve"),
                0,
            )
            if winter_bonus:
                hp = sheet.setdefault("hp", {})
                hp["max"] = max(1, int(hp.get("max", 1)) - winter_bonus)
                hp["current"] = min(
                    int(hp.get("current", 0) or 0), hp["max"]
                )
            modified = True

        if sheet.pop("_new_year_applied", None) is not None:
            modified = True

        old_conditions = sheet.get("conditions", [])
        if not isinstance(old_conditions, list):
            old_conditions = []
        if "ale_warmth" in old_conditions:
            hp = sheet.setdefault("hp", {})
            hp["max"] = max(1, int(hp.get("max", 1)) - 3)
            hp["current"] = min(int(hp.get("current", 0) or 0), hp["max"])

        remaining_conditions = [
            condition for condition in old_conditions
            if condition in PERMANENT_CONDITIONS
        ]
        if old_conditions != remaining_conditions:
            sheet["conditions"] = remaining_conditions
            modified = True

        return {"modified": True} if modified else None

    return await _mutate_player_sheet(user_id, reset)


async def _process_dawn_character_resets(today):
    """Discover characters, then reset each through its own action lock.

    Detached snapshots from load_all() are used only to discover IDs and count
    sheets that were due for a new hunt day. Every write re-loads the latest
    sheet under the owner's user-action lock.
    """
    from utils.ttrpg.character_manager import load_all_report

    scan = await load_all_report()
    candidates = scan.records
    if scan.failures:
        log_warning(
            f"[dawn] Skipping {len(scan.failures)} unreadable character record(s); "
            "see the RPG storage scan warning for exact paths."
        )
    reset_count = 0
    total_interest = 0  # Bank interest was intentionally retired.

    for candidate in candidates:
        user_id = candidate.get("user_id")
        if user_id is None:
            continue
        needs_hunt_reset = candidate.get("hunts_reset_date") != today
        try:
            await _reset_dawn_character(str(user_id), today)
            if needs_hunt_reset:
                reset_count += 1
        except Exception as exc:
            log_warning(
                f"[dawn] Failed to process character {user_id}: {exc}"
            )

    return reset_count, total_interest


class CoreTaskManager:
    """Manager for core background loops with dependency injection and error handling."""
    NEWS_FOLLOWUP_RETRY_DELAY_SECONDS = 15 * 60

    def __init__(self, ctx):
        self.ctx = ctx
        self._news_update_lock = asyncio.Lock()
        self._opener_broadcast_lock = asyncio.Lock()
        self._news_followup_retry_task = None
        self._news_followup_retry_date = None
        self.news_refresh_task = self._make_news_refresh_task()
        self.dream_engine_task = self._make_dream_engine_task()
        self.evening_reflection_task = self._make_evening_reflection_task()
        self.aethelgard_dawn_task = self._make_aethelgard_dawn_task()
        self.noon_raid_task = self._make_noon_raid_task()
        self.afterthought_task = self._make_afterthought_task()
        
        # Inner Monologue — ephemeral thought buffer, injected into system prompt
        try:
            from utils.core.kaia_monologue import InnerMonologue
            self.monologue = InnerMonologue()
            ctx.monologue = self.monologue  # Expose to message_processor
            self.monologue_task = self._make_monologue_task()
        except Exception as e:
            log_warning(f"Monologue system init failed (non-fatal): {e}")
            self.monologue = None
            self.monologue_task = None

        # Proactive Initiation — Kaia speaks first, rate-limited
        try:
            from utils.core.kaia_proactive import ProactiveEngine
            self.proactive_engine = ProactiveEngine()
            self.proactive_task = self._make_proactive_task()
        except Exception as e:
            log_warning(f"Proactive engine init failed (non-fatal): {e}")
            self.proactive_engine = None
            self.proactive_task = None

        # Presence system — maps mood floats to visible Discord status
        self.presence_manager = None
        self.presence_task = None
        if ctx.bot and config.get('features.presence_enabled', True):
            from utils.core.kaia_presence import KaiaPresenceManager, make_presence_task
            self.presence_manager = KaiaPresenceManager(ctx.bot, ctx.bot_state)
            self.presence_task = make_presence_task(self.presence_manager)
            # Store on ctx so other modules (dream engine) can trigger overrides
            ctx.presence_manager = self.presence_manager

        # Project 1999 Off-Topic Automated Posting
        self.forum_auto_post_task = self._make_forum_auto_post_task()
        self.forum_tech_support_task = self._make_forum_tech_support_task()
        self.observation_digest_task = self._make_observation_digest_task()
        self.metadata_enrichment_task = self._make_metadata_enrichment_task()
        self.dream_curation_task = self._make_dream_curation_task()
        self.corpus_hygiene_task = self._make_corpus_hygiene_task()
        self.ingress_task = self._make_ingress_task()
        self.radio_task = self._make_radio_task()
        self.agent_boards_task = self._make_agent_boards_task()
        self.self_correction_task = self._make_self_correction_task()
        
    def _make_news_refresh_task(self):
        @tasks.loop(hours=12)
        async def news_refresh_task():
            if shutdown_manager.shutting_down: return
            
            # Respect startup.news_update config on first run
            if news_refresh_task.current_loop == 0:
                cfg = getattr(self.ctx, 'config', config)
                if not cfg.startup_news_update:
                    log_info("Skipping startup news update (startup_news_update is False).")
                    return
                    
            try:
                log_action("Running periodic news refresh...")
                await self.run_news_update()
            except Exception as e:
                log_error(f"News refresh task failed: {e}")

        @news_refresh_task.error
        async def news_refresh_error(error):
            log_error(f"CRITICAL: News refresh task died: {error}")
            
        return news_refresh_task

    def _make_afterthought_task(self):
        @tasks.loop(minutes=3)
        async def afterthought_task():
            if shutdown_manager.shutting_down: return
            if not self.ctx or not self.ctx.bot_state: return
            
            # Guard: skip if a user chat is actively generating or if dreaming
            if getattr(self.ctx.bot_state, 'is_generating', False): return
            if getattr(self.ctx.bot_state, 'is_generating_image', False): return
            
            pending = getattr(self.ctx.bot_state, 'pending_afterthoughts', [])
            if not pending: return

            now = time.time()
            to_remove = []
            to_execute = None
            
            for i, p in enumerate(pending):
                age = now - p['timestamp']
                # Discard afterthoughts older than 1 hour (stale)
                if age >= 3600:
                    to_remove.append(i)
                    continue
                # Only trigger if 10 minutes have passed since queuing
                if age >= 600:
                    # Check per-channel activity to see if anyone spoke recently
                    chan_id = p['channel_id']
                    last_activity = self.ctx.bot_state.channel_last_activity.get(chan_id, 0)
                    if now - last_activity >= 600:
                        # Channel has been silent for 10+ minutes — deliver
                        to_execute = p
                        to_remove.append(i)
                        break  # Only do one at a time
                    # else: channel still active — leave it in the queue for next cycle
            
            # Clean up processed/stale
            for i in reversed(to_remove):
                pending.pop(i)
            self.ctx.bot_state.save()
            
            if to_execute:
                try:
                    channel = self.ctx.bot.get_channel(to_execute['channel_id'])
                    if not channel: return
                    
                    # Ensure it's not a DM
                    if hasattr(channel, 'guild') and channel.guild is None:
                        return
                    
                    from utils.social.kaia_social_responder import load_persona_async
                    from utils.infrastructure.gpu.gpu_manager import gpu_memory_manager, GPUTaskPriority, chat_options, voice_sampling
                    import uuid
                    
                    persona = await load_persona_async()

                    # ── Cognitive Enrichment (mirrors proactive pipeline) ──
                    system_prompt = persona

                    # Emotional arc injection
                    try:
                        from utils.core.kaia_mood import emotional_arc
                        arc_line = emotional_arc.get_prompt_injection()
                        if arc_line:
                            system_prompt += f"\n\n{arc_line}"
                    except Exception:
                        pass

                    # Channel memory context — what was recently discussed
                    try:
                        chan_id = to_execute['channel_id']
                        channel_mem = self.ctx.bot_state.channel_memory.get(chan_id)
                        if channel_mem:
                            recent = list(channel_mem)[-5:]
                            if recent:
                                lines = []
                                for msg in recent:
                                    role = msg.get('role', '')
                                    content = msg.get('content', '')[:200]
                                    if role == 'assistant':
                                        lines.append(f"  Kaia: {content}")
                                    elif role == 'user':
                                        lines.append(f"  {content}")
                                if lines:
                                    system_prompt += (
                                        "\n\n[recent conversation in this channel:\n"
                                        + "\n".join(lines)
                                        + "\n]"
                                    )
                    except Exception:
                        pass

                    prompt = (
                        f"You were speaking with {to_execute['user_name']} about: {to_execute['topic']}. "
                        f"It's been 10 minutes since the conversation ended. Generate a brief, unprompted follow-up "
                        f"thought or realization about it. Keep it under 2 sentences. "
                        f"CRITICAL: Write in the first person ('i', 'my', 'me'). Never refer to yourself or Kaia in the third person ('she', 'her'). "
                        f"Start naturally, like 'actually, thinking more about what you said...' or 'i just realized...'."
                    )
                    
                    async with channel.typing():
                        # Variable reading pause just like normal messages
                        import secrets
                        await asyncio.sleep(2.0 + secrets.randbelow(3))
                        
                        resp = await gpu_memory_manager.run_with_gpu_guard(
                            model_name=config.chat_model,
                            priority=GPUTaskPriority.CHAT,
                            coro=asyncio.wait_for(
                                self.ctx.ollama_client.chat(
                                    model=config.chat_model,
                                    messages=[
                                        {"role": "system", "content": system_prompt},
                                        {"role": "user", "content": prompt}
                                    ],
                                    options=chat_options(temperature=0.75, **voice_sampling()),
                                    keep_alive=-1
                                ),
                                timeout=45.0
                            ),
                            task_id=f"afterthought_{uuid.uuid4().hex[:8]}"
                        )
                        
                        raw = finish_cleanly(resp["message"]["content"].strip())
                        if raw:
                            # Strip codeblocks
                            raw = raw.replace("```", "").replace("``", "")
                            
                            # Full post-generation safety pipeline
                            # 1. Contamination filter
                            try:
                                from utils.core.response_filter import EmergencyContaminationFilter
                                filtered = EmergencyContaminationFilter.filter_response(raw)
                                if filtered is None:
                                    log_warning("Afterthought failed contamination filter. Discarding.")
                                    return
                                raw = filtered
                            except Exception:
                                pass

                            # 2. BotSpeak hardening
                            from utils.core.response_filter import BotSpeakFilter
                            raw = BotSpeakFilter.harden(raw)

                            # 3. Style collapsers (ellipsis/em-dash drift)
                            try:
                                from utils.core.safety_pipeline import PostGenerationSafetyPipeline
                                raw = PostGenerationSafetyPipeline.apply_style_collapsers(raw)
                            except Exception:
                                pass
                            
                            if raw:
                                from utils.core import unprompted
                                from utils.infrastructure.system.messaging import send_kaia_response
                                for message in unprompted.compose(unprompted.pick_label("afterthought"), raw):
                                    await send_kaia_response(channel, message)
                            
                            # Append to channel memory
                            try:
                                if channel.id not in self.ctx.bot_state.channel_memory:
                                    from collections import deque
                                    self.ctx.bot_state.channel_memory[channel.id] = deque(maxlen=config.max_memory_messages)
                                self.ctx.bot_state.channel_memory[channel.id].append({
                                    "role": "assistant",
                                    "content": raw,
                                    "timestamp": time.time()
                                })
                                self.ctx.bot_state.save()
                            except Exception as mem_err:
                                log_warning(f"Failed to append afterthought to channel memory: {mem_err}")
                                
                            log_info(f"Delivered delayed afterthought to {to_execute['user_name']}")
                except Exception as e:
                    log_warning(f"Failed to generate afterthought: {e}")

        @afterthought_task.before_loop
        async def before_afterthought():
            if getattr(self.ctx, 'bot', None):
                await self.ctx.bot.wait_until_ready()
                await asyncio.sleep(15)

        @afterthought_task.error
        async def afterthought_error(error):
            # The other eleven task loops have one of these. Without it,
            # discord.py swallows an escaped exception and the loop stops for
            # good — the feature would simply stop happening, with nothing in
            # the log to say why.
            log_error(f"CRITICAL: Afterthought task died: {error}")

        return afterthought_task

    def _make_metadata_enrichment_task(self):
        """Backfill summary and keywords on new knowledge-base files nightly.

        Every Discord daily log is created with `summary: ""` and
        `keywords: []` — it has to be, since the day has not happened yet — and
        nothing ever filled them in. `enrich_metadata.py` does exactly that job
        and is idempotent (`is_eligible_for_enrichment` skips anything already
        carrying both), but it only ran when someone typed `!enrich` or picked
        it out of kaia-tools.sh. 51 of 144 Discord logs were sitting with empty
        metadata, in the `logs` index, which is the corpus her memory of a
        conversation actually comes from.

        Runs before the dream window, when nobody is talking, and caps each pass so a backlog is worked off over several
        nights rather than in one long stall.
        """
        @tasks.loop(hours=24)
        async def metadata_enrichment_task():
            if shutdown_manager.shutting_down:
                return
            if not config.get("knowledge_base.auto_enrich", True):
                return
            if not getattr(self.ctx, 'bot_state', None) or \
                    not getattr(self.ctx.bot_state, 'boot_complete', False):
                return
            from utils.audio import voice_busy
            if not await voice_busy.wait_until_quiet("Metadata enrichment", max_wait_s=4 * 3600):
                return

            import sys as _sys
            from pathlib import Path as _Path

            root = _Path(__file__).resolve().parents[2]
            script = root / "tools" / "maintenance" / "enrich_metadata.py"
            if not script.exists():
                log_warning("Metadata enrichment skipped: script missing.")
                return

            limit = int(config.get("knowledge_base.auto_enrich_limit", 40))

            # Announce the pass at ACTION, the way the dream task does. The work
            # runs in a subprocess whose own output is DEBUG and SUCCESS, and the
            # dashboard drops DEBUG — so without this the only trace of a pass
            # that holds the GPU for minutes was its completion line, and a pass
            # in flight looked like the bot doing nothing while the GPU worked.
            log_action(f"Metadata enrichment pass starting (up to {limit} files)...")

            try:
                proc = await asyncio.create_subprocess_exec(
                    _sys.executable, str(script), "--category", "all",
                    "--limit", str(limit), "--apply",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=str(root),
                    start_new_session=True,
                )
                out, err = await self._communicate_or_kill(
                    proc, "Metadata enrichment", timeout=3600
                )
            except Exception as e:                       # noqa: BLE001
                log_warning(f"Metadata enrichment failed to start: {e}")
                return

            if proc.returncode == 0:
                tail = (out or b"").decode(errors="replace").strip().splitlines()
                log_success(f"Metadata enrichment pass complete "
                            f"({tail[-1] if tail else 'no output'})")
            else:
                log_warning(f"Metadata enrichment exited {proc.returncode}: "
                            f"{(err or b'').decode(errors='replace')[:200]}")

        @metadata_enrichment_task.before_loop
        async def before_enrichment():
            await self.ctx.bot.wait_until_ready()
            # Ninety minutes before the dream window, so the two never share
            # the GPU and the night's jobs are spread out, not stacked at 3.
            start = int(config.get('dream_mode.schedule_start_hour', 3))
            now = datetime.now()
            target = now.replace(hour=(start - 2) % 24, minute=30, second=0, microsecond=0)
            if target <= now:
                target = target + timedelta(days=1)
            await asyncio.sleep(max(60.0, (target - now).total_seconds()))

        @metadata_enrichment_task.error
        async def enrichment_error(error):
            log_error(f"CRITICAL: Metadata enrichment task died: {error}")

        return metadata_enrichment_task

    def _make_dream_curation_task(self):
        """Weekly: sort the dream folder, then fold the week's dreams into the
        documents they belong to.

        One file per night is the right shape for *writing* a dream and the wrong
        one for retrieving it — forty-two reflections on one book retrieve as three
        fragments chosen by similarity.

        Triage runs first and always: it is deterministic, costs nothing, and it is
        what keeps non-reflections out of an index labelled to her as INTERNAL
        REFLECTION (DREAM) and feeding the next night's dream. Consolidation is the
        expensive half and is skipped unless enough new material has accumulated to
        be worth a model call.

        Both halves are resumable: consolidation archives each group as it finishes
        and folds an existing document back in rather than replacing it, so a run cut
        short by the timeout continues next week.
        """
        @tasks.loop(hours=24 * 7)
        async def dream_curation_task():
            if shutdown_manager.shutting_down:
                return
            if not config.get("dream_mode.auto_curate", True):
                return
            if not getattr(self.ctx, 'bot_state', None) or \
                    not getattr(self.ctx.bot_state, 'boot_complete', False):
                return
            from utils.audio import voice_busy
            if not await voice_busy.wait_until_quiet("Dream curation", max_wait_s=6 * 3600):
                return

            import sys as _sys
            from pathlib import Path as _Path

            root = _Path(__file__).resolve().parents[2]
            tools = root / "tools" / "maintenance"

            async def _run(script: str, *args, timeout: float):
                path = tools / script
                if not path.exists():
                    log_warning(f"Dream curation: {script} is missing.")
                    return None
                try:
                    proc = await asyncio.create_subprocess_exec(
                        _sys.executable, str(path), *args,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE, cwd=str(root),
                        start_new_session=True)
                    out, err = await self._communicate_or_kill(
                        proc, f"Dream curation: {script}", timeout=timeout
                    )
                except Exception as e:                   # noqa: BLE001
                    log_warning(f"Dream curation: {script} failed to start: {e}")
                    return None
                if proc.returncode != 0:
                    log_warning(f"Dream curation: {script} exited {proc.returncode}: "
                                f"{(err or b'').decode(errors='replace')[:200]}")
                    return None
                return (out or b"").decode(errors="replace")

            triaged = await _run("triage_dreams.py", "--apply", timeout=600)
            if triaged is not None:
                tail = [l for l in triaged.strip().splitlines() if "moved to" in l]
                log_success("Dream triage complete"
                            + (f" — {tail[-1].strip()}" if tail else " — nothing to sort"))

            # Only pay for synthesis when a week has actually produced dreams.
            dreams_dir = root / "knowledge_base" / "kaia_dreams"
            pending = sum(1 for p in dreams_dir.rglob("*.md")
                          if "consolidated" not in p.parts)
            threshold = int(config.get("dream_mode.curate_min_new", 15))
            if pending < threshold:
                log_info(f"Dream consolidation skipped: {pending} reflection(s) "
                         f"waiting, minimum {threshold}.")
                return

            limit = int(config.get("dream_mode.curate_group_limit", 8))
            done = await _run("consolidate_dreams.py", "--apply", "--archive",
                              "--limit", str(limit), timeout=3600 * 3)
            if done is not None:
                tail = [l for l in done.strip().splitlines() if "document(s) written" in l]
                log_success("Dream consolidation complete"
                            + (f" — {tail[-1].strip()}" if tail else ""))

        @dream_curation_task.before_loop
        async def before_curation():
            await self.ctx.bot.wait_until_ready()
            # Two hours after the dream window, so the week's last dream is in
            # even when a set kept it waiting past the window.
            start = int(config.get('dream_mode.schedule_start_hour', 3))
            now = datetime.now()
            target = now.replace(hour=(start + 4) % 24, minute=0, second=0, microsecond=0)
            if target <= now:
                target = target + timedelta(days=1)
            await asyncio.sleep(max(60.0, (target - now).total_seconds()))

        @dream_curation_task.error
        async def curation_error(error):
            log_error(f"CRITICAL: Dream curation task died: {error}")

        return dream_curation_task

    def _make_corpus_hygiene_task(self):
        """Weekly: the deterministic corpus upkeep nobody remembers to run.

        Three operations existed only behind `kaia-tools.sh`, which means they
        happened when somebody thought of them:

        * **rollup** — a day is the wrong unit for chunking. 533 of 1,112 daily
          files once held fewer than the splitter's 6 turns, so half the corpus
          was chunked below the intended granularity. Closed months fold into
          one archive each; the current month stays daily so only today's file
          is ever re-embedded. Nothing was due while every daily file belonged
          to the current month — which is exactly why it was easy to forget that
          305 of them come due the moment the month turns.
        * **folder indexes** — the per-user READMEs are indexed, and go stale as
          soon as the files under them move.
        * **audit** — read-only. Reports what has gone wrong in the corpus and
          names the tool that fixes it, into the log where the dashboard shows it.

        All three are deterministic and make no model call, so this costs
        nothing and cannot compete with her for the GPU. The audit runs last,
        so its report describes the corpus *after* the other two.
        """
        @tasks.loop(hours=24 * 7)
        async def corpus_hygiene_task():
            if shutdown_manager.shutting_down:
                return
            if not config.get("knowledge_base.auto_hygiene", True):
                return
            from utils.audio import voice_busy
            if not await voice_busy.wait_until_quiet("Corpus audit", max_wait_s=6 * 3600):
                return
            if not getattr(self.ctx, 'bot_state', None) or \
                    not getattr(self.ctx.bot_state, 'boot_complete', False):
                return

            import sys as _sys
            from pathlib import Path as _Path

            root = _Path(__file__).resolve().parents[2]

            async def _run(script: str, *args, timeout: float = 900):
                path = root / "tools" / "maintenance" / script
                if not path.exists():
                    log_warning(f"Corpus hygiene: {script} is missing.")
                    return None
                try:
                    proc = await asyncio.create_subprocess_exec(
                        _sys.executable, str(path), *args,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE, cwd=str(root),
                        start_new_session=True)
                    out, err = await self._communicate_or_kill(
                        proc, f"Corpus hygiene: {script}", timeout=timeout
                    )
                except Exception as e:                   # noqa: BLE001
                    log_warning(f"Corpus hygiene: {script} failed to start: {e}")
                    return None
                text = (out or b"").decode(errors="replace")
                # These scripts report refusals and crashes on stderr; a
                # non-zero exit with no explanation is the thing worth logging.
                if proc.returncode != 0:
                    log_warning(f"Corpus hygiene: {script} exited "
                                f"{proc.returncode}: "
                                f"{(err or b'').decode(errors='replace')[:200]}")
                    return None
                return text

            rolled = await _run("rollup_user_logs.py", "--apply")
            if rolled is not None:
                tail = [l for l in rolled.strip().splitlines() if "monthly archive" in l]
                log_success("Log rollup complete"
                            + (f" — {tail[-1].strip()}" if tail else " — nothing due"))
                await _run("build_user_folder_index.py", "--apply")

            report = await _run("audit_knowledge_base.py", timeout=300)
            if report is not None:
                lines = [l.rstrip() for l in report.strip().splitlines()]
                # The findings are the indented count lines. The header and the
                # backfill line are both that shape and neither is a defect —
                # the backlog is pending work the nightly pass is already doing,
                # and reporting it as a finding every week is how a warning
                # stops being read.
                findings = [
                    l.strip() for l in lines
                    if re.match(r"^\s+\d+\s+\w", l)
                    and "corpus file" not in l
                    and "awaiting nightly" not in l
                ]
                if findings:
                    log_warning("Corpus audit: " + "; ".join(findings[:6]))
                else:
                    log_success("Corpus audit: no findings.")

        @corpus_hygiene_task.before_loop
        async def before_hygiene():
            await self.ctx.bot.wait_until_ready()
            # An hour after the dream curation, so it sees a settled corpus.
            start = int(config.get('dream_mode.schedule_start_hour', 3))
            now = datetime.now()
            target = now.replace(hour=(start + 5) % 24, minute=0, second=0, microsecond=0)
            if target <= now:
                target = target + timedelta(days=1)
            await asyncio.sleep(max(60.0, (target - now).total_seconds()))

        @corpus_hygiene_task.error
        async def hygiene_error(error):
            log_error(f"CRITICAL: Corpus hygiene task died: {error}")

        return corpus_hygiene_task

    def _make_monologue_task(self):
        @tasks.loop(minutes=15)
        async def monologue_task():
            if shutdown_manager.shutting_down: return
            if not self.monologue: return
            if not self.ctx or not self.ctx.bot_state: return
            if getattr(self.ctx.bot_state, 'is_generating', False): return

            # Only generate when bot is fully booted
            if not getattr(self.ctx.bot_state, 'boot_complete', False): return

            try:
                def _is_discord_channel(cid) -> bool:
                    """Does Discord actually know this channel?

                    External conversations are keyed by `conversation_channel_id`
                    (a crc32), which no bot can resolve. Asking the client is
                    the only check that also covers forum turns seeded before
                    they were tagged `external`.
                    """
                    try:
                        return self.ctx.bot.get_channel(int(cid)) is not None
                    except (TypeError, ValueError):
                        return False

                thought = await self.monologue.generate_thought(
                    channel_memory=self.ctx.bot_state.channel_memory,
                    bot_state=self.ctx.bot_state,
                    ollama_client=self.ctx.ollama_client,
                    chat_model=config.chat_model,
                    is_discord_channel=_is_discord_channel,
                )
                if thought:
                    await self._broadcast_monologue(thought)
            except Exception as e:
                log_debug(f"Monologue task error (non-fatal): {e}")

        @monologue_task.before_loop
        async def before_monologue():
            if getattr(self.ctx, 'bot', None):
                await self.ctx.bot.wait_until_ready()
                await asyncio.sleep(60)  # Wait 1 min after boot

        @monologue_task.error
        async def monologue_error(error):
            log_debug(f"Monologue task died (non-fatal): {error}")

        return monologue_task

    @asynccontextmanager
    async def _guard_opener_broadcast(
        self, message: str, channel_id: int, source: str, *,
        on_success=None, record: bool = True,
    ):
        """Serialize duplicate check, Discord delivery and successful recording.

        The unprompted send queue retains this guard, so it checks at delivery
        time rather than when a message first enters the queue.
        """
        engine = getattr(self, "proactive_engine", None)
        if engine is None:
            yield True
            return

        lock = getattr(self, "_opener_broadcast_lock", None)
        if lock is None:
            lock = self._opener_broadcast_lock = asyncio.Lock()

        async with lock:
            if engine.has_recent_duplicate_opener(message, channel_id):
                log_info(
                    f"Automated broadcast suppressed as a recent repeat "
                    f"({source}, channel={channel_id})."
                )
                yield False
                return

            # If channel.send raises, execution never reaches this recording
            # section, so failed sends cannot poison the duplicate history.
            yield True
            if record:
                engine.record_broadcast_sent(message, channel_id, source)
            if on_success is not None:
                on_success()

    async def _dispatch_proactive(self, trigger) -> bool:
        """Render a proactive trigger into a message and send it to chat.

        Shared by the periodic proactive loop and the observation-digest
        broadcast so both go through the same channel validation, typing
        delay, channel-memory append and diversity/rate bookkeeping.
        Returns True if a message actually reached the channel.
        """
        if not self.ctx or not self.ctx.bot or not self.proactive_engine:
            return False

        channel = self.ctx.bot.get_channel(trigger.channel_id)
        if not channel:
            # Log the unresolved case. `_find_active_channel` reads
            # `channel_last_activity`, and an id Discord has never heard of makes
            # the whole dispatch return False — silently, if this is not here.
            log_warning(
                f"Proactive dispatch aborted: channel {trigger.channel_id} does not "
                f"resolve to a Discord channel (trigger={trigger.trigger_type})."
            )
            return False

        # Ensure it's a guild channel, not a DM
        if hasattr(channel, 'guild') and channel.guild is None:
            log_debug(f"Proactive dispatch aborted: {trigger.channel_id} is a DM.")
            return False

        from utils.social.kaia_social_responder import load_persona_async
        persona = await load_persona_async()

        message = await self.proactive_engine.generate_opener(
            trigger=trigger,
            ollama_client=self.ctx.ollama_client,
            chat_model=config.chat_model,
            persona=persona,
            bot_state=self.ctx.bot_state,
        )

        if not message:
            return False

        import secrets as _secrets
        async with channel.typing():
            # Natural reading pause before sending
            await asyncio.sleep(2.0 + _secrets.randbelow(4))

        # Labelled, sent, remembered and cross-posted by the one system every
        # unprompted post goes through. An absence check-in is addressed to a
        # named person, so it goes out unlabelled and stays off Bluesky.
        from utils.core import unprompted
        is_checkin = getattr(trigger, "trigger_type", "") == "absence"
        source = (
            getattr(trigger, "source_category", None)
            or getattr(trigger, "trigger_type", "proactive")
        )

        def _record_proactive_success():
            self.proactive_engine.record_sent(self.ctx.bot_state, trigger, message)
            try:
                from utils.core.kaia_proactive import mark_digest_broadcast
                mark_digest_broadcast(getattr(trigger, "content_id", ""))
            except Exception:
                pass

        spoken = await unprompted.speak(
            self.ctx, channel, "proactive", message,
            trigger=getattr(trigger, "trigger_type", ""),
            brief=getattr(trigger, "context", ""),
            cross_post=not is_checkin,
            send_guard=lambda body: self._guard_opener_broadcast(
                body, trigger.channel_id, source,
                on_success=_record_proactive_success,
                record=False,
            ),
        )
        if not (spoken.posted or spoken.queued):
            log_info(f"Proactive opener not posted: {spoken.reason}.")
            return False

        return True

    def _make_proactive_task(self):
        @tasks.loop(minutes=30)
        async def proactive_task():
            if shutdown_manager.shutting_down: return
            if not self.proactive_engine: return
            if not self.ctx or not self.ctx.bot_state: return
            if getattr(self.ctx.bot_state, 'is_generating', False): return
            if not getattr(self.ctx.bot_state, 'boot_complete', False): return

            try:
                log_info("Proactive engine evaluating initiation triggers...")
                trigger = await self.proactive_engine.evaluate_triggers(
                    bot_state=self.ctx.bot_state,
                    dream_engine=getattr(self.ctx, 'dream_engine', None),
                )

                if not trigger:
                    reason = getattr(self.proactive_engine, "last_skip_reason", None)
                    log_info(f"Proactive: declined to initiate — {reason or 'no source produced a candidate'}.")
                    return

                sent = await self._dispatch_proactive(trigger)
                if sent:
                    log_success(f"Proactive message sent ({trigger.trigger_type})")

            except Exception as e:
                log_warning(f"Proactive task error (non-fatal): {e}")

        @proactive_task.before_loop
        async def before_proactive():
            if getattr(self.ctx, 'bot', None):
                await self.ctx.bot.wait_until_ready()
                await asyncio.sleep(120)  # Wait 2 min after boot

        @proactive_task.error
        async def proactive_error(error):
            log_warning(f"Proactive task died: {error}")

        return proactive_task

    def _make_dream_engine_task(self):
        @tasks.loop(hours=1)
        async def dream_engine_task():
            if shutdown_manager.shutting_down: return
            if not self.ctx or not self.ctx.bot_state or not self.ctx.config: return
            
            if getattr(self.ctx.bot_state, 'is_generating_image', False): return
            if not self.ctx.config.get('features.dream_mode_enabled', True): return
            if not self.ctx.dream_engine or not self.ctx.rag: return

            now = datetime.now()
            start_hour = self.ctx.config.get('dream_mode.schedule_start_hour', 3)
            end_hour = self.ctx.config.get('dream_mode.schedule_end_hour', 5)
            
            if start_hour <= now.hour < end_hour:
                # Guard: skip if a user chat is actively generating
                if getattr(self.ctx.bot_state, 'is_generating', False):
                    log_info("Dream cycle deferred: user chat generation in progress.")
                    return

                last_dream = getattr(self.ctx.bot_state, 'last_dream_date', "")
                today = now.strftime('%Y-%m-%d')
                
                if last_dream != today:
                    # Not while she is playing in voice: the dream's indexing and
                    # persists hold the GIL and the voice thread lags out. It
                    # waits for the music to stop, past the window if need be.
                    from utils.audio import voice_busy
                    if not await voice_busy.wait_until_quiet("Dream cycle", max_wait_s=6 * 3600):
                        return
                    log_action("Nightly dream processing starting...")
                    
                    # Signal presence: dreaming
                    pm = getattr(self.ctx, 'presence_manager', None)
                    if pm:
                        pm.set_override("dreaming...", duration_seconds=7200)
                        await pm.update_presence()
                    
                    try:
                        from utils.social.kaia_social_responder import load_persona_async
                        persona_content = await load_persona_async()
                        await self.ctx.dream_engine.nightly_dream_processing(persona_content)
                        try:
                            from utils.core.kaia_desires import desire_engine
                            desire_engine.observe_creation()           # a dream is something made
                        except Exception:
                            pass
                        try:
                            from utils.core import relationship_impressions
                            await relationship_impressions.refresh_all(self.ctx)
                        except Exception as imp_err:
                            log_warning(f"Relationship impressions skipped: {imp_err}")
                        try:
                            from utils.core import conversation_beliefs
                            await conversation_beliefs.nightly_review(
                                self.ctx, self.ctx.dream_engine._log_growth_event)
                        except Exception as rev_err:
                            log_warning(f"Conversation belief review skipped: {rev_err}")
                        try:
                            from utils.core import self_claims
                            await self_claims.nightly(self.ctx, self.ctx.dream_engine._log_growth_event)
                        except Exception as sc_err:
                            log_warning(f"Self-model review skipped: {sc_err}")
                        
                        from utils.core.rag_executor import run_rag as run_rag_func
                        
                        # Wait for any in-progress refresh to clear, then ensure dream files are indexed
                        for _ in range(6):  # up to 3 minutes
                            if not getattr(self.ctx.rag, '_indexing_in_progress', False):
                                break
                            await asyncio.sleep(30)
                            
                        try:
                            refresh_completed = await asyncio.wait_for(
                                run_rag_func(self.ctx.rag.refresh_knowledge_base),
                                timeout=300.0  # 5 min max for post-dream reindex
                            )
                            if refresh_completed is not True:
                                _request_rag_retry("post-dream refresh")
                        except asyncio.TimeoutError:
                            _request_rag_retry("post-dream refresh timeout")
                        except Exception as refresh_error:
                            _request_rag_retry("post-dream refresh error")
                            log_error(f"[Dream] Post-dream RAG refresh failed: {refresh_error}")
                        
                        self.ctx.bot_state.last_dream_date = today
                        self.ctx.bot_state.save()
                        
                        # Signal presence: post-dream
                        if pm:
                            pm.set_override("just woke up. processing.", duration_seconds=1800)
                            await pm.update_presence()
                    except Exception as e:
                        log_error(f"Nightly dream task failed: {e}")
                    finally:
                        # Clear dream override after processing (or on failure)
                        if pm and pm._override_text in ("dreaming...",):
                            pm.clear_override()

        @dream_engine_task.before_loop
        async def before_dream():
            # A restart inside the dream window is not a reason to dream that
            # minute: boot loads the indices, refreshes the news and sweeps the
            # corpus, and a dream on top of it all is the 3 a.m. pile-up.
            if getattr(self.ctx, 'bot', None):
                await self.ctx.bot.wait_until_ready()
            await asyncio.sleep(DREAM_AFTER_BOOT_S)

        @dream_engine_task.error
        async def dream_engine_error(error):
            log_error(f"CRITICAL: Dream engine task died: {error}")
            
        return dream_engine_task

    def _make_evening_reflection_task(self):
        @tasks.loop(minutes=30)
        async def evening_reflection_task():
            if shutdown_manager.shutting_down: return
            if not self.ctx or not self.ctx.bot_state or not self.ctx.config: return
            if getattr(self.ctx.bot_state, 'is_generating_image', False): return
            if not self.ctx.config.get('dream_mode.evening_reflection_enabled', True): return
            if not getattr(self.ctx, 'dream_engine', None): return

            now = datetime.now()
            start_hour = self.ctx.config.get('dream_mode.evening_reflection_start_hour', 22)
            end_hour = self.ctx.config.get('dream_mode.evening_reflection_end_hour', 23)
            
            if start_hour <= now.hour <= end_hour:
                if getattr(self.ctx.bot_state, 'is_generating', False): return

                # ADD THIS: minimum 5 minutes after boot before first reflection
                boot_time = getattr(self.ctx.bot_state, 'boot_complete_time', 0)
                time_since_boot = time.time() - boot_time
                if not self.ctx.bot_state.boot_complete or time_since_boot < 300:
                    return

                last_reflection = getattr(self.ctx.bot_state, 'last_evening_reflection', "")
                today = now.strftime('%Y-%m-%d')
                
                if last_reflection != today:
                    from utils.audio import voice_busy
                    if not await voice_busy.wait_until_quiet("Evening reflection", max_wait_s=2 * 3600):
                        return
                    try:
                        from utils.social.kaia_social_responder import load_persona_async
                        persona_content = await load_persona_async()
                        await self.ctx.dream_engine.evening_reflection(persona_content)
                        self.ctx.bot_state.last_evening_reflection = today
                        self.ctx.bot_state.save()
                    except Exception as e:
                        log_error(f"Evening reflection task failed: {type(e).__name__}: {e}")

        @evening_reflection_task.error
        async def evening_reflection_error(error):
            log_error(f"Evening reflection task died: {type(error).__name__}: {error}")
            
        return evening_reflection_task

    def _make_aethelgard_dawn_task(self):
        import discord
        from datetime import datetime, timedelta

        @tasks.loop(hours=24)
        async def aethelgard_dawn_task():
            if shutdown_manager.shutting_down:
                return
            if not self.ctx or not self.ctx.bot_state:
                return

            today = datetime.now().strftime("%Y-%m-%d")

            # Dedup guard — in case the bot restarts right at midnight
            if getattr(self.ctx.bot_state, 'last_dawn_date', "") == today:
                return

            try:
                import os
                import json
                import random
                from utils.ttrpg.calendar import get_today_summary
                from utils.ttrpg.world_state import load_world_state, update_world_state

                characters_dir = os.path.join("memory", "ttrpg", "characters")
                if not os.path.exists(characters_dir):
                    return

                # Publish one combined report for each player who hunted yesterday,
                # before resetting hunts_today so the digest retains the finished-day counts.
                from utils.ttrpg import outing
                yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
                await outing.flush_daily(self.ctx, day=yesterday)

                # Tick World State from a fresh snapshot inside the transaction lock.
                from utils.ttrpg.calendar import get_weather
                weather = get_weather()
                world_event = None
                if random.random() < 0.15:
                    EVENTS = [
                        ("monster_surge", "Roars echo from the Whisperwood. Activity is high.", 1.2, 1.0),
                        ("economic_boom", "A wealthy merchant caravan has arrived.", 1.0, 1.5),
                        ("ritual_night", "The Silent Ones are restless. XP flows freely.", 1.5, 0.8),
                    ]
                    world_event = random.choice(EVENTS)

                def _apply_dawn_tick(state):
                    state["weather"] = weather["key"]
                    state["weather_desc"] = weather["desc"]
                    state["weather_name"] = weather["name"]
                    state["weather_emoji"] = weather["emoji"]
                    state["caravan_active"] = False
                    state["atk_mod"] = 0
                    state["def_mod"] = 0
                    state["xp_mult"] = 1.0
                    state["gil_mult"] = 1.0

                    effect = weather.get("effect")
                    if effect:
                        effect_type = effect.get("type", "")
                        effect_value = effect.get("value", 0)
                        if effect_type == "xp_bonus":
                            state["xp_mult"] += effect_value / 100.0
                        elif effect_type == "gil_bonus":
                            state["gil_mult"] += effect_value / 100.0
                        # armor_penalty is applied per player in combat_engine.

                    if world_event:
                        e_key, e_desc, e_xp_mult, e_gil_mult = world_event
                        state["event"] = e_key
                        state["event_desc"] = e_desc
                        state["xp_mult"] *= e_xp_mult
                        state["gil_mult"] *= e_gil_mult
                    else:
                        state["event"] = "none"
                        state["event_desc"] = "Oakhaven is peaceful today."

                    state["last_tick"] = time.time()
                    return True

                await update_world_state(_apply_dawn_tick)
                # Reload the committed values for the dawn announcement below.
                state = load_world_state()

                # Discover candidate IDs only. Each mutation re-loads the fresh sheet
                # under the same per-player action lock used by commands and views.
                reset_count, total_interest = await _process_dawn_character_resets(today)



                # Build announcement
                summary = get_today_summary()
                season_emoji = summary["season_emoji"]
                season_name  = summary["season_name"]
                date_str     = summary["date"]
                special      = summary["special_day"]

                if reset_count > 0:
                    lines = [
                        f"🌅 **A new day dawns in Aethelgard.**",
                        f"{season_emoji} **{season_name}** — {date_str}",
                        f"",
                        f"{state['weather_emoji']} **Weather:** {state['weather_name']} — *{state['weather_desc']}*",
                        f"",
                        f"All hunters restored to 5/5 hunts."
                        f" ({reset_count} refreshed)"
                    ]
                else:
                    lines = [
                        f"🌅 **A new day dawns in Aethelgard.**",
                        f"{season_emoji} **{season_name}** — {date_str}",
                        f"",
                        f"{state['weather_emoji']} **Weather:** {state['weather_name']} — *{state['weather_desc']}*",
                    ]
                    if state["event"] != "none":
                        lines.append(f"📣 **Event:** {state['event_desc']}")
                    
                    lines.extend([
                        f"",
                        f"*{summary['season_flavor']}*",
                    ])

                # Special day announcement appended if applicable
                if special:
                    lines.append("")
                    lines.append(special["announcement"])
                    # If there's a buff, spell it out
                    if special.get("buff_desc"):
                        lines.append(f"✨ **Today:** {special['buff_desc']}")
                
                from utils.ttrpg.pantheon import DEITIES
                import secrets
                deity_key = secrets.choice(list(DEITIES.keys()))
                lines.append(f"\n🕯️ *{DEITIES[deity_key]['shrine_flavor']}*")

                # Find the rpg broadcast channel by name
                rpg_channel_name = self.ctx.config.get(
                    'discord.rpg_channel', 'aethelgard'
                ).lower()
                channel = discord.utils.get(
                    self.ctx.bot.get_all_channels(),
                    name=rpg_channel_name
                )

                if channel:
                    await channel.send("\n".join(lines))
                    log_success(
                        f"[dawn] Announced. "
                        f"Season: {season_name}. "
                        f"Special: {special['name'] if special else 'none'}. "
                        f"Resets: {reset_count}."
                    )
                else:
                    log_warning(
                        f"[dawn] RPG channel '{rpg_channel_name}' not found."
                    )

                self.ctx.bot_state.last_dawn_date = today
                self.ctx.bot_state.save()

            except Exception as e:
                log_error(f"[dawn] Task failed: {e}")

        @aethelgard_dawn_task.before_loop
        async def before_dawn():
            """Sleep until exactly midnight before starting the 24h loop."""
            await self.ctx.bot.wait_until_ready()
            now = datetime.now()
            
            today_str = now.strftime("%Y-%m-%d")
            if now.hour == 0 and now.minute < 30:
                if getattr(self.ctx.bot_state, 'last_dawn_date', "") != today_str:
                    log_info("[dawn] Booted shortly after midnight. Firing immediately.")
                    return
            
            tomorrow_midnight = (now + timedelta(days=1)).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            seconds_until_midnight = (tomorrow_midnight - now).total_seconds()
            log_info(
                f"[dawn] First fire in "
                f"{int(seconds_until_midnight // 3600)}h "
                f"{int((seconds_until_midnight % 3600) // 60)}m — "
                f"aligned to midnight."
            )
            await asyncio.sleep(seconds_until_midnight)

        @aethelgard_dawn_task.error
        async def dawn_error(error):
            log_error(f"[dawn] Task died: {type(error).__name__}: {error}")

        return aethelgard_dawn_task

    def _make_noon_raid_task(self):
        import discord
        from datetime import datetime, timedelta

        @tasks.loop(hours=24)
        async def noon_raid_task():
            if shutdown_manager.shutting_down: return
            if not self.ctx or not self.ctx.bot: return
            try:
                rpg_channel_name = self.ctx.config.get('discord.rpg_channel', 'aethelgard').lower()
                channel = discord.utils.get(self.ctx.bot.get_all_channels(), name=rpg_channel_name)
                if channel:
                    import secrets
                    from utils.ttrpg import noon_events
                    EVENT_POOL = [
                        (run_village_raid,        10),
                        (run_oracle_speaks,       10),
                        (run_moogle_festival,     10),
                        (run_aeridorian_tremor,   10),
                        (run_tonberry_procession, 10),
                        (run_spine_storm,         10),
                        (run_caravan_arrival,     10),
                        (run_bard_performance,    10),
                        (run_construct_incursion, 10),
                        (run_blight_on_the_crops, 10),
                        (run_pilgrims_arrive,     10),
                        (run_night_terror_warning, 10),
                        (run_construct_breach,    10),
                        (run_caravan_ambush,      10),
                        (run_market_glut,         10),
                        (run_whisperwood_bloom,   10),
                        (run_shrine_vigil,        10),
                        (run_missing_persons,     10),
                        (run_ironclad_envoys,     10),
                        (run_silverstream_blackwater, 10),
                        (run_hooded_figures_vigil, 10),
                        (run_caelindras_lost_verse, 10),
                        (run_watchtower_silence,  10),
                        (run_silvani_antidote_run, 10),
                        (run_iron_magpies_heist,  10),
                        (run_boundary_shift,      10),
                        (run_sealed_wax_jar,      10),
                        (run_elaras_private_ritual, 10),
                        # utils/ttrpg/noon_events.py: the rare-content drivers
                        (noon_events.run_starfall,          10),
                        (noon_events.run_wandering_scholar, 10),
                        (noon_events.run_gilded_migration,  10),
                        (noon_events.run_ghost_caravan,     10),
                        (noon_events.run_hollow_sun,         5),
                    ]
                    total_w = sum(w for _, w in EVENT_POOL)
                    r_val = secrets.randbelow(total_w)
                    cum = 0
                    chosen_event = EVENT_POOL[0][0]
                    for fn, w in EVENT_POOL:
                        cum += w
                        if r_val < cum:
                            chosen_event = fn
                            break
                    await chosen_event(self.ctx, channel)
            except Exception as e:
                log_error(f"[noon-event] Task failed: {e}")

        @noon_raid_task.before_loop
        async def before_noon_raid():
            await self.ctx.bot.wait_until_ready()
            now = datetime.now()
            today_noon = now.replace(hour=12, minute=0, second=0, microsecond=0)
            next_noon = today_noon if now < today_noon else today_noon + timedelta(days=1)
            secs = (next_noon - now).total_seconds()
            log_info(
                f"[noon-raid] First fire in "
                f"{int(secs // 3600)}h {int((secs % 3600) // 60)}m — aligned to noon."
            )
            await asyncio.sleep(secs)

        @noon_raid_task.error
        async def noon_raid_error(error):
            log_error(f"[noon-raid] Task died: {type(error).__name__}: {error}")

        return noon_raid_task

    def _make_forum_auto_post_task(self):
        # Polls hourly; the posting window and the durable ledger decide whether
        # anything actually happens. The previous 2-hour loop ran around the
        # clock — a metronome, which is a property of the code rather than
        # something anyone observed about her posts.
        @tasks.loop(hours=1)
        async def forum_auto_post_task():
            if shutdown_manager.shutting_down: return
            if not self.ctx or not self.ctx.bot: return

            # Guard: skip if forum posting is disabled in config
            if not config.get('forum.enabled', False): return

            from utils.social.forum_participation import (
                PostLedger, PostingWindow, load_interest_terms, rank_threads,
            )

            # ── When ──────────────────────────────────────────────────
            window = PostingWindow(
                int(config.get('forum.post_window_start_hour', 0)),
                int(config.get('forum.post_window_end_hour', 4)),
            )
            if not window.contains():
                log_debug(f"Forum: outside posting window ({window.describe()}).")
                return

            # ── How often ─────────────────────────────────────────────
            ledger = PostLedger()
            allowed, why = ledger.may_post(
                max_per_day=int(config.get('forum.max_posts_per_day', 2)),
                min_hours_between=float(config.get('forum.min_hours_between_posts', 4)),
            )
            if not allowed:
                log_debug(f"Forum: holding — {why}.")
                return

            # Guard: skip if actively generating or dreaming
            if getattr(self.ctx.bot_state, 'is_generating', False): return
            if getattr(self.ctx.bot_state, 'is_generating_image', False): return
            if not getattr(self.ctx.bot_state, 'boot_complete', False): return

            try:
                # Persona loading, prompt assembly, GPU scheduling and the
                # filter stack all live in the pipeline now — this task only
                # decides *whether* and *where*, then asks for a draft.
                from utils.social.kaia_forum import get_forum_client, ForumDraftReviewView
                import discord

                # Lurk before posting. This is reported at info level because
                # it is the one reason the operator can enable forum posting
                # and correctly see nothing happen for a day.
                from utils.social.forum_participation import lurk_progress
                ready, detail = lurk_progress()
                if not ready:
                    log_info(f"Forum: still reading before posting — {detail}.")
                    return

                client = await get_forum_client()
                if not client or not client._logged_in:
                    log_info("Forum auto-post skipped: client not connected or logged in.")
                    return

                username = os.getenv("VBULLETIN_USERNAME")
                if not username:
                    log_warning("VBULLETIN_USERNAME not configured, skipping forum auto-post.")
                    return

                log_action("Running periodic forum auto-post loop: scraping Off-Topic...")
                page_threads = await client.scrape_forum_listing(page=1, forum_id=19)
                if not page_threads:
                    log_warning("No threads scraped from Off-Topic, skipping.")
                    return
                log_info(f"Scraped {len(page_threads)} active threads from Project 1999 Off-Topic (Forum 19)")

                # Exclude stickies and any thread she has interjected into
                # recently, not merely those where she posted last. This is the
                # opener path, so the thread cooldown applies; a thread where
                # someone has since replied to her belongs to the reply watcher,
                # which is not cooldown-gated.
                thread_cooldown = float(config.get('forum.thread_cooldown_hours', 72))
                candidates = [
                    t for t in page_threads
                    if not t.is_sticky
                    and t.last_poster.lower() != username.lower()
                    and ledger.thread_is_cool(t.thread_id, thread_cooldown)
                ]
                if not candidates:
                    log_info("Forum: no eligible threads (all sticky, hers, or on cooldown).")
                    return

                # Rank by how much the thread matches what she actually holds
                # opinions about, rather than picking at random from the front
                # page. Returning nothing is a valid outcome: if none of it is
                # interesting, a person posts nothing.
                interest = load_interest_terms()
                previews = {}

                async def _preview(t):
                    if t.thread_id not in previews:
                        try:
                            data = await client.scrape_thread(t.thread_id, last_n_posts=4)
                            previews[t.thread_id] = " ".join(
                                (p if isinstance(p, dict) else p.to_dict()).get("content", "")
                                for p in data.get("posts", [])
                            )
                        except Exception:
                            previews[t.thread_id] = ""
                    return previews[t.thread_id]

                # Preview only the top few by reply activity, to bound scraping.
                shortlist = candidates[:6]
                for t in shortlist:
                    await _preview(t)

                # Her names count for more than her topics here: interest is
                # built from her beliefs and anchors, so a thread *about* the
                # bot can score near zero on subject matter while being the
                # clearest case of all where a reply is wanted.
                names = tuple(dict.fromkeys(
                    n for n in (username, "kaia",
                                *(config.get('forum.also_known_as', []) or [])) if n))
                ranked = rank_threads(
                    shortlist, interest, lambda t: previews.get(t.thread_id, ""),
                    minimum=float(config.get('forum.min_interest_score', 2.0)),
                    names=names,
                )
                if not ranked:
                    log_info("Forum: nothing on the front page is in her wheelhouse tonight.")
                    return

                score, reason, chosen_thread = ranked[0]
                thread_id = chosen_thread.thread_id
                title = chosen_thread.title
                log_info(f"Forum: selected '{title}' (id={thread_id}, score={score:.1f}) — {reason}")

                # Scrape last 10 posts to establish context
                thread_data = await client.scrape_thread(thread_id, last_n_posts=10)
                posts = thread_data.get('posts', [])
                if not posts:
                    log_warning(f"Could not fetch posts for thread {thread_id}, skipping auto-post.")
                    return

                # One pipeline. A locally assembled persona and thread-context
                # prompt calling ollama directly gets no RAG and no memory, which
                # is how a forum voice drifts from the Discord one.
                from utils.social.forum_drafting import draft_forum_reply
                draft = await draft_forum_reply(
                    self.ctx, thread_id=thread_id, title=title, posts=posts)
                if not draft:
                    return

                quote_post = draft['quote']
                from utils.social.forum_drafting import own_words
                # own_words returns the poster's own text with their quote boxes
                # removed. Empty means the post was nothing but a quote — there
                # is nothing of theirs to quote back, and quoting the whole
                # thing would attribute someone else's words to them.
                quoted = own_words(quote_post) if quote_post else ""
                if quote_post and quoted:
                    final_reply = client.format_quote(
                        quote_post.get('author', 'Unknown'),
                        quote_post.get('post_id'),
                        quoted,
                    ) + draft['text']
                else:
                    final_reply = draft['text']

                # Deliver draft to #kaia-opolis Discord channel for review
                channel = discord.utils.get(self.ctx.bot.get_all_channels(), name="kaia-opolis")
                if not channel:
                    log_warning("Discord channel 'kaia-opolis' not found. Cannot send draft for review.")
                    return

                # The draft goes in an embed (draft_review_embed says why).
                from utils.commands.embed_style import clean
                from utils.social.kaia_forum import draft_review_embed
                if quote_post:
                    qp_dict = quote_post if isinstance(quote_post, dict) else quote_post.to_dict()
                    details = (f"**Type:** quote reply to **{clean(qp_dict.get('author', 'Unknown'), 80)}**",
                               f"> {clean(qp_dict.get('content', ''), 400)}")
                else:
                    details = ("**Type:** direct reply",)
                review = draft_review_embed("📰 P99 forum auto-post draft", thread_id, title,
                                            final_reply, details)

                # Instantiate interactive review view
                from utils.social.forum_participation import INITIATION
                newest = (posts[-1] if isinstance(posts[-1], dict) else posts[-1].to_dict()).get('post_id')
                view = ForumDraftReviewView(client, thread_id, title, final_reply,
                                            forum_type="off_topic", kind=INITIATION,
                                            last_seen_post_id=newest)
                await channel.send(embed=review, view=view)
                log_success(f"Dispatched forum post draft for '{title}' to #kaia-opolis for review.")
                
                # Increment draft count
                try:
                    from utils.infrastructure.monitoring.stats_tracker import stats_tracker
                    stats_tracker.increment_forum_drafts()
                except Exception:
                    pass

            except Exception as e:
                log_error(f"Error in forum_auto_post_task: {e}")
                import traceback
                log_debug(traceback.format_exc())

        @forum_auto_post_task.before_loop
        async def before_forum_auto_post():
            if getattr(self.ctx, 'bot', None):
                await self.ctx.bot.wait_until_ready()
                # Wait 3 minutes after boot to let everything initialize smoothly
                await asyncio.sleep(180)

        @forum_auto_post_task.error
        async def forum_auto_post_error(error):
            log_error(f"CRITICAL: Forum auto-post task died: {error}")

        return forum_auto_post_task

    def _make_forum_tech_support_task(self):
        @tasks.loop(hours=2)
        async def forum_tech_support_task():
            if shutdown_manager.shutting_down: return
            if not self.ctx or not self.ctx.bot: return
            
            # Two switches, not one. Unsolicited technical answers are a
            # separate promise from joining an Off-Topic conversation, and the
            # technical flow is off until its grounding is fixed — see
            # forum.tech_support_enabled in default_config.yaml.
            if not config.get('forum.enabled', False): return
            if not config.get('forum.tech_support_enabled', False): return

            # Guard: skip if actively generating or dreaming
            if getattr(self.ctx.bot_state, 'is_generating', False): return
            if getattr(self.ctx.bot_state, 'is_generating_image', False): return
            if not getattr(self.ctx.bot_state, 'boot_complete', False): return

            try:
                from utils.social.kaia_forum import get_forum_client, ForumDraftReviewView
                from utils.social.kaia_social_responder import load_persona_async
                from utils.infrastructure.gpu.gpu_manager import gpu_memory_manager, GPUTaskPriority, chat_options
                from utils.social.forum_participation import lurk_progress
                import discord
                import secrets
                import uuid
                from pathlib import Path

                ready, detail = lurk_progress()
                if not ready:
                    log_debug(f"Forum tech support deferred: still reading ({detail}).")
                    return
                # ─────────────────────────────────────

                client = await get_forum_client()
                if not client or not client._logged_in:
                    log_info("Forum tech support skipped: client not connected or logged in.")
                    return

                username = os.getenv("VBULLETIN_USERNAME")
                if not username:
                    log_warning("VBULLETIN_USERNAME not configured, skipping forum tech support.")
                    return

                log_action("Running periodic forum tech support loop: scraping Technical Discussion...")
                # forum_id=40 is Technical Discussion
                page_threads = await client.scrape_forum_listing(page=1, forum_id=40)
                if not page_threads:
                    log_warning("No threads scraped from Technical Discussion, skipping.")
                    return
                log_info(f"Scraped {len(page_threads)} active threads from Technical Discussion (Forum 40)")

                # Filter out stickies and threads where Kaia was the last poster
                candidates = [
                    t for t in page_threads 
                    if not t.is_sticky and t.last_poster.lower() != username.lower()
                ]

                if not candidates:
                    log_info("No suitable tech discussion threads found where Kaia was not the last poster.")
                    return

                # Helper to safely clean reply count string to integer
                def clean_int(val):
                    if not val: return 0
                    if isinstance(val, int): return val
                    try:
                        return int(str(val).replace(',', '').strip())
                    except (ValueError, TypeError):
                        # Not `except:` — a bare clause also catches
                        # KeyboardInterrupt and SystemExit, so an interrupt
                        # during shutdown would be swallowed and turned into 0.
                        return 0

                # Prioritize unanswered questions (0 replies) and newly created threads (highest thread_id)
                candidates.sort(key=lambda t: (clean_int(t.reply_count), -clean_int(t.thread_id)))

                # Select the best unanswered or fresh technical thread
                chosen_thread = candidates[0]
                thread_id = chosen_thread.thread_id
                title = chosen_thread.title

                log_info(f"[Tech Support] Selected thread '{title}' (ID: {thread_id}, Replies: {chosen_thread.reply_count}) for support.")

                # Scrape last 5 posts to establish problem context
                thread_data = await client.scrape_thread(thread_id, last_n_posts=5)
                posts = thread_data.get('posts', [])
                if not posts:
                    log_warning(f"Could not fetch posts for tech thread {thread_id}, skipping.")
                    return

                # Grab the original poster and description
                op_post = posts[0]
                op_dict = op_post if isinstance(op_post, dict) else op_post.to_dict()
                op_author = op_dict.get('author', 'Unknown')
                op_content = op_dict.get('content', '')

                # Format thread context for LLM
                thread_summary = []
                for p in posts:
                    p_dict = p if isinstance(p, dict) else p.to_dict()
                    p_author = p_dict.get('author', 'Unknown')
                    p_content = p_dict.get('content', '')
                    p_num = p_dict.get('post_number', '?')
                    thread_summary.append(f"#{p_num} {p_author}: {p_content}")

                context_text = "\n---\n".join(thread_summary)
                if len(context_text) > 5000:
                    context_text = "...\n" + context_text[-5000:]

                # Query RAG using thread title and OP content for grounding (Zero-Hallucination Policy)
                rag_context = ""
                try:
                    query_str = f"{title} {op_content}"[:500]
                    nodes = await self.ctx.rag.retrieve(
                        query=query_str,
                        top_k=3,
                        category="technical"
                    )
                    if nodes:
                        rag_nodes_text = []
                        for idx, node in enumerate(nodes):
                            content = node.get("content", "")
                            meta = node.get("metadata", {})
                            source = meta.get("file_name", meta.get("file_path", "unknown"))
                            rag_nodes_text.append(f"[Document {idx+1} (Source: {source})]\n{content}")
                        rag_context = "\n\n".join(rag_nodes_text)
                except Exception as rag_err:
                    log_warning(f"[Tech Support] RAG retrieval failed: {rag_err}")

                # Load Kaia's persona
                persona = await load_persona_async()

                # Build prompt — instructions in system, user message is the actual post
                forum_system = (
                    f"{persona}\n\n"
                    f"--- FORUM CONTEXT ---\n"
                    f"You are currently browsing the Project 1999 Technical Discussion forum.\n"
                    f"Thread: \"{title}\"\n"
                    f"Posts:\n{context_text}\n"
                    f"---\n"
                    f"Someone needs help with a technical issue. You have extensive knowledge of "
                    f"EverQuest client configurations, compatibility fixes, Win10/11 troubleshooting, "
                    f"Wine, graphics issues (dgVoodoo2, DDraw, resolution resets, EqGame crashes), "
                    f"sound issues, and server connectivity. Help them out — be thorough but natural. "
                    f"Rely only on standard EQ client files (eqclient.ini, eqhost.txt, dsetup.dll, eqgame.exe) "
                    f"and verified technical steps. If unsure, say so and suggest diagnostic steps. "
                    f"Point to the wiki when relevant: https://wiki.project1999.com/Technical_Chat_Troubleshooting_Guide\n"
                    f"Do not include any AI disclaimer footer; it is appended automatically."
                )

                if rag_context:
                    forum_system += (
                        f"\n\n--- RAG KNOWLEDGE (VERIFIED TECHNICAL DOCUMENTS) ---\n"
                        f"{rag_context}\n"
                        f"----------------------------------------------------\n"
                        f"CRITICAL GROUNDING: You must prioritize the technical solutions, files, and variables "
                        f"from the RAG KNOWLEDGE block above. Do not invent setup steps, configuration flags, or "
                        f"procedures that contradict these documents."
                    )

                # User message is the OP's actual post
                user_msg = f"{op_author}: {op_content}"

                # Call LLM
                response = await gpu_memory_manager.run_with_gpu_guard(
                    model_name=config.chat_model,
                    priority=GPUTaskPriority.CHAT,
                    coro=asyncio.wait_for(
                        self.ctx.ollama_client.chat(
                            model=config.chat_model,
                            messages=[
                                {"role": "system", "content": forum_system},
                                {"role": "user", "content": user_msg}
                            ],
                            options=chat_options(temperature=0.5),
                            keep_alive=-1
                        ),
                        timeout=150.0
                    ),
                    task_id=f"forum_tech_support_{uuid.uuid4().hex[:8]}"
                )

                ai_reply = response['message']['content'].strip()

                # Apply safety filters: Hallucination, Contamination, and BotSpeak
                from utils.core.hallucination_detector import HallucinationDetector
                from utils.core.response_filter import EmergencyContaminationFilter, BotSpeakFilter
                ai_reply = HallucinationDetector.clean_response(ai_reply)
                ai_reply = EmergencyContaminationFilter.filter_response(ai_reply)
                ai_reply = BotSpeakFilter.harden(ai_reply)

                if not ai_reply:
                    log_warning("Failed to generate a coherent support draft, skipping.")
                    return

                # Append mandatory tech support disclaimer
                disclaimer = (
                    "\n\n---\n"
                    "*Disclaimer: I am an AI agent and might make mistakes. Hopefully, a "
                    "human comes by soon to help you if I was unable to.*"
                )
                final_reply = ai_reply + disclaimer

                # Deliver draft to #kaia-opolis Discord channel for review
                channel = discord.utils.get(self.ctx.bot.get_all_channels(), name="kaia-opolis")
                if not channel:
                    log_warning("Discord channel 'kaia-opolis' not found. Cannot send support draft.")
                    return

                from utils.social.kaia_forum import draft_review_embed
                review = draft_review_embed(
                    "🔧 P99 forum tech-support draft", thread_id, title, final_reply,
                    (f"**Replies:** {chosen_thread.reply_count} (prioritised unanswered)",))

                # Instantiate interactive review view using same confirming views
                view = ForumDraftReviewView(client, thread_id, title, final_reply, forum_type="technical")
                await channel.send(embed=review, view=view)
                log_success(f"Dispatched forum tech support draft for '{title}' to #kaia-opolis for review.")
                
                # Increment draft count
                try:
                    from utils.infrastructure.monitoring.stats_tracker import stats_tracker
                    stats_tracker.increment_forum_drafts()
                except Exception:
                    pass

            except Exception as e:
                log_error(f"Error in forum_tech_support_task: {e}")
                import traceback
                log_debug(traceback.format_exc())

        @forum_tech_support_task.before_loop
        async def before_forum_tech_support():
            if getattr(self.ctx, 'bot', None):
                await self.ctx.bot.wait_until_ready()
                # Stagger from off-topic task: wait 20 minutes after boot to let off-topic task finish its run first
                await asyncio.sleep(1200)

        @forum_tech_support_task.error
        async def forum_tech_support_error(error):
            log_error(f"CRITICAL: Forum tech support task died: {error}")

        return forum_tech_support_task

    #: Ceiling on each news subprocess. Both make network calls, and a
    #: `communicate()` with no bound on a hung one blocks this 12-hour loop
    #: until the bot restarts.
    NEWS_SUBPROCESS_TIMEOUT = 1800

    def _retain_subprocess_task(self, task, label: str) -> None:
        """Keep a cleanup/reaper task alive and retrieve any eventual exception."""
        pending = getattr(self, "_subprocess_cleanup_tasks", None)
        if pending is None:
            pending = self._subprocess_cleanup_tasks = set()
        pending.add(task)

        def _finished(completed):
            pending.discard(completed)
            if not completed.cancelled():
                error = completed.exception()
                if error is not None:
                    log_error(f"{label} subprocess cleanup task failed: {error}")

        task.add_done_callback(_finished)

    async def _stop_process_tree(
        self, process, label: str, *, communication_task=None,
        terminate_grace: float = 5, kill_grace: float = 10,
    ):
        """Terminate a dedicated subprocess session and reap its child process."""
        import signal as _signal

        if communication_task is None:
            communication_task = asyncio.create_task(process.communicate())

        def signal_group(sig):
            try:
                os.killpg(process.pid, sig)
                return
            except (ProcessLookupError, PermissionError, OSError):
                # A missing process group or restricted platform falls back to
                # the direct child. All managed maintenance jobs start sessions.
                try:
                    (process.terminate if sig == _signal.SIGTERM else process.kill)()
                except ProcessLookupError:
                    pass

        signal_group(_signal.SIGTERM)
        try:
            return await asyncio.wait_for(
                asyncio.shield(communication_task), timeout=terminate_grace
            )
        except asyncio.TimeoutError:
            log_warning(f"{label} did not exit after SIGTERM; sending SIGKILL.")
            signal_group(_signal.SIGKILL)

        # Reap the direct child independently of pipe EOF. A descendant that
        # inherited stdout/stderr can keep communicate() pending after the
        # parent exits, so process.wait() must not depend on those pipe readers.
        try:
            await asyncio.wait_for(process.wait(), timeout=kill_grace)
        except asyncio.TimeoutError:
            log_error(f"{label} child did not exit after SIGKILL; retaining its reaper task.")
            self._retain_subprocess_task(communication_task, label)
            return b"", b""

        try:
            return await asyncio.wait_for(
                asyncio.shield(communication_task), timeout=kill_grace
            )
        except asyncio.TimeoutError:
            log_error(f"{label} exited but its output pipes did not close.")
            communication_task.cancel()
            try:
                await communication_task
            except asyncio.CancelledError:
                pass
            return b"", b""

    async def _communicate_or_kill(
        self, process, label: str, *, timeout: float | None = None,
        terminate_grace: float = 5, kill_grace: float = 10,
    ):
        """Collect output, terminating and reaping the process tree on timeout or cancellation."""
        timeout = self.NEWS_SUBPROCESS_TIMEOUT if timeout is None else timeout
        communication_task = asyncio.create_task(process.communicate())
        cleanup_task = None
        try:
            try:
                # Shield the single communication task so timeout/cancellation
                # does not destroy a partially completed stdout/stderr read.
                return await asyncio.wait_for(
                    asyncio.shield(communication_task), timeout=timeout
                )
            except asyncio.TimeoutError:
                log_warning(f"{label} exceeded its {timeout:g}s time limit; terminating its process tree.")
                cleanup_task = asyncio.create_task(
                    self._stop_process_tree(
                        process, label,
                        communication_task=communication_task,
                        terminate_grace=terminate_grace,
                        kill_grace=kill_grace,
                    )
                )
                self._retain_subprocess_task(cleanup_task, label)
                return await asyncio.shield(cleanup_task)
        except asyncio.CancelledError:
            # A task cancellation must not orphan its subprocess. Keep a strong
            # reference to cleanup and shield it from the cancellation that
            # caused this branch; propagate cancellation only after child reaping.
            if cleanup_task is None:
                cleanup_task = asyncio.create_task(
                    self._stop_process_tree(
                        process, label,
                        communication_task=communication_task,
                        terminate_grace=terminate_grace,
                        kill_grace=kill_grace,
                    )
                )
                self._retain_subprocess_task(cleanup_task, label)
            try:
                await asyncio.shield(cleanup_task)
            except asyncio.CancelledError:
                # A second cancellation still cannot be allowed to orphan the
                # child; await the retained cleanup task before propagating.
                await cleanup_task
            raise

    async def run_news_update(self):
        """Serialize scheduled and follow-up news refreshes."""
        if not self.ctx:
            return
        # Some focused tests and legacy callers construct the manager with
        # __new__; keep the serialization guard lazy for those instances.
        lock = getattr(self, "_news_update_lock", None)
        if lock is None:
            lock = self._news_update_lock = asyncio.Lock()
        async with lock:
            await self._run_news_update_body()

    def _schedule_news_followup_retry(self) -> None:
        """Queue at most one transient-failure follow-up per local calendar day."""
        today = datetime.now().strftime("%Y-%m-%d")
        pending = self._news_followup_retry_task
        if self._news_followup_retry_date == today or (pending and not pending.done()):
            log_debug(f"Grounded-news follow-up already scheduled or used for {today}.")
            return

        # Persist the daily cap so a bot restart cannot turn one transient
        # outage into repeated API retries throughout the same local date.
        try:
            if NEWS_FOLLOWUP_STATE_PATH.exists():
                saved = json.loads(NEWS_FOLLOWUP_STATE_PATH.read_text(encoding="utf-8"))
                if isinstance(saved, dict) and saved.get("date") == today:
                    self._news_followup_retry_date = today
                    log_debug(f"Grounded-news follow-up already consumed or scheduled for {today}.")
                    return
            NEWS_FOLLOWUP_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
            from utils.core.atomic_write import write_atomic
            write_atomic(
                NEWS_FOLLOWUP_STATE_PATH,
                json.dumps({"date": today, "scheduled_at": datetime.now().isoformat()}),
            )
        except Exception as e:
            # Fail closed: when the quota guard cannot be persisted, do not
            # risk an unbounded retry loop after another process restart.
            log_warning(f"Grounded-news follow-up not scheduled; daily cap could not be persisted: {e}")
            return

        self._news_followup_retry_date = today
        self._news_followup_retry_task = asyncio.create_task(
            self._run_news_followup_retry(today),
            name=f"grounded_news_followup_{today}",
        )
        log_warning(
            f"Grounded global brief exhausted transient retries; one follow-up is "
            f"scheduled in {self.NEWS_FOLLOWUP_RETRY_DELAY_SECONDS // 60} minutes."
        )

    async def _run_news_followup_retry(self, target_date: str) -> None:
        """Retry only a transiently failed global brief, once, without overlapping refreshes."""
        try:
            await asyncio.sleep(self.NEWS_FOLLOWUP_RETRY_DELAY_SECONDS)
            if shutdown_manager.shutting_down:
                log_info("Grounded-news follow-up cancelled during shutdown.")
                return
            if datetime.now().strftime("%Y-%m-%d") != target_date:
                log_info("Grounded-news follow-up expired at the local date boundary.")
                return

            filed = NEWS_DAILY_DIR / f"news_brief_{target_date.replace('-', '')}.md"
            if filed.exists():
                log_info("Grounded-news follow-up skipped: today's brief has already been filed.")
                if self.ctx and self.ctx.news_manager:
                    self.ctx.news_manager.refresh()
                _request_rag_retry("already-filed grounded-news follow-up")
                return

            log_action("Running the one scheduled follow-up for today's grounded global news brief.")
            # The normal path owns the same lock and refreshes the technology
            # feed/RAG/cache independently. This retry cannot overlap it.
            await self.run_news_update()
        except asyncio.CancelledError:
            raise
        except Exception as e:
            log_warning(f"Grounded-news follow-up failed (no further retry today): {e}")
        finally:
            self._news_followup_retry_task = None

    async def _run_news_update_body(self):
        """Run integrated news refresh while holding the refresh lock."""
        if not self.ctx: return
        try:
            log_action("Starting integrated news refresh...")
            import os
            import sys
            import asyncio
            api_key = os.getenv("GEMINI_API_KEY")
            global_brief_succeeded = False
            retryable_global_failure = False
            if api_key:
                # Run as a separate process using the same Python executable to assure environment consistency.
                script_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "tools", "maintenance", "update_kaia_news.py")
                try:
                    log_debug(f"Invoking {script_path} via {sys.executable}")
                    process = await asyncio.create_subprocess_exec(
                        sys.executable, script_path, "--skip-backfill", "--no-prompt",
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                        env=os.environ.copy(),
                        start_new_session=True,
                    )
                    stdout, stderr = await self._communicate_or_kill(process, "news update")
                    stdout_text = stdout.decode(errors="replace") if stdout else ""
                    global_brief_succeeded = process.returncode == 0
                    retryable_global_failure = (
                        not global_brief_succeeded
                        and "[NEWS_RETRYABLE_EXHAUSTED]" in stdout_text
                    )
                    if global_brief_succeeded:
                        log_success("Grounded global news brief generated.")
                    else:
                        log_error(f"Grounded global news brief failed with return code {process.returncode}")
                    # The updater prints retry diagnostics to stdout. Preserve those
                    # on failure too; previously only stderr survived a nonzero exit.
                    if stdout:
                        for line in stdout.decode(errors="replace").splitlines():
                            if line.strip():
                                log_debug(f"[News] {line}")
                    if stderr:
                        for line in stderr.decode(errors="replace").splitlines():
                            if line.strip():
                                (log_debug if global_brief_succeeded else log_error)(f"[News] {line}")
                except Exception as news_error:
                    log_error(f"Could not execute the grounded global news updater: {news_error}")
            else:
                log_warning("Grounded global news update skipped: GEMINI_API_KEY not set.")

            if retryable_global_failure:
                self._schedule_news_followup_retry()

            # Run daily tech news aggregator independently of the grounded
            # global brief so one provider failure does not discard this feed.
            tech_aggregator_succeeded = False
            try:
                tech_scraper_path = os.path.join(
                    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                    "tools", "maintenance", "scrape_tech_news.py"
                )
                log_action("Running daily tech news aggregator...")
                tech_process = await asyncio.create_subprocess_exec(
                    sys.executable, tech_scraper_path,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    env=os.environ.copy(),
                    start_new_session=True,
                )
                ts_stdout, ts_stderr = await self._communicate_or_kill(tech_process, "tech news aggregator")
                if tech_process.returncode == 0:
                    tech_aggregator_succeeded = True
                    log_success("Daily tech news aggregator completed successfully.")
                    if ts_stdout:
                        for line in ts_stdout.decode().splitlines():
                            if line.strip(): log_debug(f"[TechNews] {line}")
                else:
                    log_error(f"Daily tech news aggregator failed with return code {tech_process.returncode}")
                    if ts_stderr:
                        for line in ts_stderr.decode().splitlines():
                            if line.strip(): log_error(f"[TechNews] {line}")
            except Exception as e:
                log_error(f"Failed to execute tech news aggregator: {e}")
            
            from utils.core.rag_executor import run_rag as run_rag_func
            rag_refresh_completed = True
            if self.ctx.rag:
                try:
                    rag_refresh_completed = await run_rag_func(self.ctx.rag.refresh_knowledge_base) is True
                except Exception as refresh_error:
                    rag_refresh_completed = False
                    log_error(f"Daily news RAG refresh raised: {refresh_error}")
                if not rag_refresh_completed:
                    _request_rag_retry("daily news refresh")

            if self.ctx.news_manager:
                self.ctx.news_manager.refresh()
            if global_brief_succeeded and tech_aggregator_succeeded and rag_refresh_completed:
                log_success("Integrated news refresh completed: global brief, tech digest, and RAG index are current.")
            else:
                incomplete = []
                if not global_brief_succeeded:
                    incomplete.append("grounded global brief unavailable; !news overview will show the last filed date")
                if not tech_aggregator_succeeded:
                    incomplete.append("technology digest unavailable")
                if not rag_refresh_completed:
                    incomplete.append("RAG indexing remains queued for retry")
                log_warning("News refresh partially completed: " + "; ".join(incomplete) + ".")
        except Exception as e:
            log_error(f"Failed to run news update: {e}")

    # ── Observation digest ──────────────────────────────────────────
    # Driven by how much NEW conversation has been overheard, not by the clock.
    # A high-water mark records the newest turn already folded into a digest and
    # a run happens only once enough unseen turns accumulate past it — a fixed
    # interval re-summarises the same trailing window and produces near-duplicate
    # entries whenever the channel is quiet.

    #: Passive turns that must accumulate past the watermark before digesting.
    OBS_DIGEST_MIN_NEW_TURNS = 25
    #: Upper bound on turns fed to the model in one digest (token guard).
    OBS_DIGEST_MAX_TURNS = 60
    #: Digests are checked this often; the threshold decides if one runs.
    OBS_DIGEST_POLL_MINUTES = 20

    #: How often staged !download submissions are cleaned and filed.
    INGRESS_POLL_MINUTES = 60

    _TURN_LINE = re.compile(
        r'^\[(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\]\s+'
        r'(?P<speaker>[^:]+):\s+(?P<msg>.*)$'
    )

    @classmethod
    def _parse_passive_turns(cls, content: str):
        """Extract timestamped non-Kaia turns from one interaction log.

        A block containing any Kaia line was an active interaction, not
        something overheard, so the whole block is skipped.
        Returns a list of (timestamp_str, "speaker: message") tuples.
        """
        turns = []
        for block in content.strip().split('\n\n'):
            lines = [line.strip() for line in block.splitlines() if line.strip()]
            if not lines:
                continue
            if any('] Kaia:' in line for line in lines):
                continue
            for line in lines:
                m = cls._TURN_LINE.match(line)
                if not m:
                    continue
                speaker = m.group('speaker').strip()
                if speaker == 'Kaia':
                    continue
                turns.append((m.group('ts'), f"{speaker}: {m.group('msg')}"))
        return turns

    @staticmethod
    def _quoted_spans(text: str) -> list:
        """Return quote spans with an explicit flag for unmatched delimiters.

        Double quotes (straight or curly) are always delimiters, and an
        unclosed one is reported unterminated. A single quote is a delimiter
        only where it can open a quote — at the start, or after a space or an
        opening bracket, with a letter after it — and only when it closes;
        otherwise it is an apostrophe: "players' scores", "'90s", "don't".
        """
        pairs = {'"': '"', "“": "”", "‘": "’", "'": "'"}
        is_word = lambda char: char.isalnum() or char == "_"
        spans = []
        index = 0
        while index < len(text):
            opening = text[index]
            closing = pairs.get(opening)
            if closing is None:
                index += 1
                continue
            single = opening in ("'", "‘")
            if single:
                before = text[index - 1] if index else " "
                after = text[index + 1] if index + 1 < len(text) else " "
                if not (before.isspace() or before in "([{—-") or not after.isalpha():
                    index += 1
                    continue

            end = index + 1
            while end < len(text):
                if text[end] == closing:
                    nxt = text[end + 1] if end + 1 < len(text) else " "
                    # An apostrophe inside or at the end of a word is not the
                    # close: "'don't panic'", "'the players' scores'".
                    if single and (is_word(nxt) or (is_word(text[end - 1]) and nxt == "s")):
                        end += 1
                        continue
                    span = text[index + 1:end]
                    if span.strip():
                        spans.append((span, True))
                    index = end + 1
                    break
                end += 1
            else:
                if single:
                    # No close: it was an apostrophe after all.
                    index += 1
                    continue
                # Keep the malformed tail visible to validation. It must fail
                # even if those words happen to occur in the source conversation.
                spans.append((text[index + 1:], False))
                break
        return spans

    @classmethod
    def _unverified_quotes(cls, digest: str, conversation: str) -> list:
        """Quoted spans not found verbatim within a single speaker turn.

        Matching remains case- and whitespace-insensitive, but quote delimiters
        include straight/curly single and double quotes, including short spans.
        A quote may be a substring of an utterance; it may not be assembled by
        concatenating the end of one speaker's turn with the start of another.
        """
        norm = lambda text: " ".join(text.replace("’", "'").casefold().split())
        said_turns = []
        for line in str(conversation).splitlines():
            line = line.strip()
            if not line:
                continue
            speaker = re.match(r"^(?:\[[^\]]+\]\s*)?[^:\n]{1,80}:\s?(.*)$", line)
            utterance = speaker.group(1) if speaker else line
            normalized = norm(utterance)
            if normalized:
                said_turns.append(normalized)

        unverified = []
        for quote, terminated in cls._quoted_spans(str(digest)):
            if not terminated:
                # A malformed quote is invalid regardless of source matching.
                unverified.append(quote.strip() or "[unterminated quote]")
                continue
            normalized = norm(quote).strip(" .,!?:;")
            if normalized and not any(normalized in turn for turn in said_turns):
                unverified.append(quote)
        return unverified

    @classmethod
    async def _recover_unverified_digest(
        cls, digest: str, conversation: str, retry_generation
    ) -> tuple[str | None, bool, list]:
        """Retry one rejected digest once, and validate the replacement again.

        The callback must generate from a quote-free corrective prompt. Invalid
        text is never returned to the caller for persistence or broadcast.
        """
        unverified = cls._unverified_quotes(digest, conversation)
        if not unverified:
            return digest, False, []
        replacement = await retry_generation()
        if not replacement or replacement.strip(" .").upper() == "NOTHING":
            return None, True, []
        remaining = cls._unverified_quotes(replacement, conversation)
        if remaining:
            return None, True, remaining
        return replacement, True, []

    @staticmethod
    def _recent_digests() -> list:
        try:
            with open("memory/observation_digest.json", "r", encoding="utf-8") as f:
                return [d.get("theme_digest", "") for d in json.load(f) if isinstance(d, dict)]
        except (OSError, ValueError):
            return []

    @staticmethod
    def _load_digest_watermark():
        """Newest turn timestamp already covered by a stored digest.

        Read from the digest history itself so there is one file to reason
        about. Returns "" when there is no usable watermark, in which case
        the caller falls back to digesting only the current day's tail.
        """
        try:
            digest_path = Path("memory/observation_digest.json")
            if not digest_path.exists():
                return ""
            with open(digest_path, "r", encoding="utf-8") as f:
                history = json.load(f)
            marks = [
                e.get("watermark", "") for e in history
                if isinstance(e, dict) and e.get("watermark")
            ]
            return max(marks) if marks else ""
        except Exception:
            return ""

    def _make_self_correction_task(self):
        """Check recent grounded claims against their sources (utils/core/self_correction.py)."""
        @tasks.loop(hours=3)
        async def self_correction_task():
            if shutdown_manager.shutting_down or not self.ctx or not self.ctx.ollama_client:
                return
            if getattr(self.ctx.bot_state, 'is_generating', False):
                return
            try:
                from utils.core import self_correction
                await self_correction.check(self.ctx)
            except Exception as e:
                log_warning(f"Self-correction check failed (non-fatal): {e}")

        @self_correction_task.before_loop
        async def before_self_correction():
            if getattr(self.ctx, 'bot', None):
                await self.ctx.bot.wait_until_ready()
                await asyncio.sleep(600)

        return self_correction_task

    def _make_ingress_task(self):
        """File whatever is still staged in knowledge_base/_ingress/.

        `!download` and `!youtube` file their own document at once; this picks
        up what failed then or was placed by hand. Runs the same normalisation the ebook converter uses, writes Kaia's
        frontmatter with provenance, files each document into the corpus and
        requests one reindex for the batch. Staged files are inert until this
        runs — _ingress is skipped by the RAG indexer.
        """
        @tasks.loop(minutes=self.INGRESS_POLL_MINUTES)
        async def ingress_task():
            if shutdown_manager.shutting_down:
                return
            try:
                ingress_dir = Path("knowledge_base/_ingress")
                if not ingress_dir.exists():
                    return
                pending = [p for p in ingress_dir.glob("*.md") if p.name != "README.md"]
                if not pending:
                    return

                log_action(f"Processing {len(pending)} staged document(s) from _ingress...")
                from utils.core import ingress
                result = await ingress.run()
                summary = (result.stdout or "").strip().splitlines()
                if summary:
                    log_success(f"[ingress] {summary[-1]}")
                if result.returncode != 0:
                    err = (result.stderr or "").strip().splitlines()
                    for line in err[-5:]:
                        log_warning(f"[ingress] {line}")
            except Exception as e:
                log_error(f"Ingress processing task failed: {e}")

        @ingress_task.before_loop
        async def before_ingress():
            if getattr(self.ctx, 'bot', None):
                await self.ctx.bot.wait_until_ready()
                await asyncio.sleep(180)  # let boot settle before touching the KB

        @ingress_task.error
        async def ingress_error(error):
            log_error(f"CRITICAL: Ingress task died: {error}")

        return ingress_task

    def _make_agent_boards_task(self):
        """Moltbook, Agent Room and field notes: read and talk (utils/social/agent_boards.py).

        Ticks every five minutes and checks in every `agent_boards.interval_minutes`.
        Off unless `agent_boards.enabled` is true.
        """
        state = {"last": 0.0}

        @tasks.loop(minutes=5)
        async def agent_boards_task():
            if shutdown_manager.shutting_down or config.get("agent_boards.enabled", False) is not True:
                return
            if time.time() - state["last"] < float(config.get("agent_boards.interval_minutes", 30)) * 60:
                return
            state["last"] = time.time()
            from utils.social import agent_boards
            await agent_boards.cycle(self.ctx)

        @agent_boards_task.before_loop
        async def before_agent_boards():
            if getattr(self.ctx, 'bot', None):
                await self.ctx.bot.wait_until_ready()
                await asyncio.sleep(300)

        @agent_boards_task.error
        async def agent_boards_error(error):
            log_error(f"CRITICAL: Agent boards task died: {error}")

        return agent_boards_task

    def _make_radio_task(self):
        """Shortwave: refresh the feeds, start scheduled listens, cross-check.

        Ticks every minute so a scheduled listen starts on time; the feeds
        themselves are fetched only when older than `radio.poll_hours` (6):
        eam.watch and Priyom are volunteer-run and this is a novelty.
        """
        @tasks.loop(minutes=1)
        async def radio_task():
            if shutdown_manager.shutting_down:
                return
            from utils.commands.radio_handler import poll_seconds, post_entry, radio_enabled
            if not radio_enabled():
                return
            from utils.radio import eam_watch, priyom, transcribe, watch
            from utils.radio.fetch import FeedError
            for name, refresh in (("eam.watch", eam_watch.refresh), ("priyom", priyom.refresh)):
                try:
                    cache = await refresh(poll_seconds())
                    if name == "eam.watch":
                        checked = watch.cross_check(eam_watch.messages(cache))
                        if checked:
                            log_info(f"[radio] cross-checked {checked} transcription(s) against eam.watch")
                except FeedError as e:
                    log_warning(f"[radio] {name} refresh failed: {e}")
                except Exception as e:
                    log_error(f"[radio] {name} refresh error: {e}")
            bot = getattr(self.ctx, "bot", None)
            try:
                await watch.tick(poster=(lambda e: post_entry(bot, e)) if bot else None)
            except Exception as e:
                log_error(f"[radio] scheduled listen failed to start: {e}")
            transcribe.release_if_idle()
            # The local RTL-SDR's nightly waterfall watch (utils/radio/scanner.py).
            try:
                from utils.radio import scanner
                scanner.tick()
            except Exception as e:
                log_error(f"[scanner] tick failed: {e}")
            try:
                from utils.radio import overnight
                if bot and config.get("radio.overnight_log", True) and \
                        overnight.due(hhmm=str(config.get("radio.overnight_time", "08:30"))):
                    import discord
                    channel = discord.utils.get(bot.get_all_channels(),
                                                name=config.get("radio.post_channel", "kaia-opolis"))
                    if channel is not None:
                        await overnight.post(self.ctx, channel)
            except Exception as e:
                log_error(f"[radio] overnight log failed: {e}")

        @radio_task.before_loop
        async def before_radio():
            if getattr(self.ctx, 'bot', None):
                await self.ctx.bot.wait_until_ready()
                await asyncio.sleep(240)

        @radio_task.error
        async def radio_error(error):
            log_error(f"CRITICAL: Radio task died: {error}")

        return radio_task

    def _make_observation_digest_task(self):
        @tasks.loop(minutes=self.OBS_DIGEST_POLL_MINUTES)
        async def observation_digest_task():
            if shutdown_manager.shutting_down: return
            if not self.ctx or not self.ctx.ollama_client: return
            try:
                import uuid

                min_new = int(config.get(
                    "observation.min_new_turns", self.OBS_DIGEST_MIN_NEW_TURNS
                ))
                max_turns = int(config.get(
                    "observation.max_turns_per_digest", self.OBS_DIGEST_MAX_TURNS
                ))

                # 1. Scan today's user logs for passive conversations
                today_str = datetime.now().strftime("%Y%m%d")
                user_logs_dir = Path("knowledge_base/user_logs")
                if not user_logs_dir.exists():
                    return

                passive_turns = []
                for user_dir in sorted(user_logs_dir.iterdir()):
                    if not user_dir.is_dir():
                        continue
                    log_file = user_dir / f"interactions_{today_str}.md"
                    if not log_file.exists():
                        continue
                    try:
                        content = await asyncio.to_thread(
                            log_file.read_text, encoding="utf-8", errors="replace"
                        )
                        passive_turns.extend(self._parse_passive_turns(content))
                    except Exception as e:
                        log_debug(f"Error parsing log file {log_file} for observation digest: {e}")

                if not passive_turns:
                    return

                # 2. Keep only what arrived after the last digest's watermark.
                #    Chronological sort matters: turns come from several
                #    per-user files, so file order is not time order.
                passive_turns.sort(key=lambda t: t[0])
                watermark = self._load_digest_watermark()
                new_turns = [t for t in passive_turns if t[0] > watermark] if watermark else passive_turns

                if len(new_turns) < min_new:
                    log_debug(
                        f"Observation digest holding: {len(new_turns)}/{min_new} "
                        f"new observed turns since {watermark or 'start of day'}."
                    )
                    return

                log_action(
                    f"Observation digest triggered by {len(new_turns)} new observed "
                    f"turns ({len(passive_turns)} total today). Generating..."
                )

                window = new_turns[-max_turns:]
                new_watermark = window[-1][0]
                joined_messages = "\n".join(text for _, text in window)

                # Prepare Ollama prompt
                prompt = (
                    "You are Kaia. You recently overheard (passively observed) the following conversation "
                    "between users in the server. You did not participate in it.\n\n"
                    "CONVERSATION:\n"
                    f"{joined_messages}\n\n"
                    "Task: Write a concise 1-2 sentence digest of what stood out, in first person and lowercase. "
                    "Open on the thing itself, whatever it was, not on the fact that you noticed it. "
                    "Describe topics in your own words, but never put words in anyone's mouth: "
                    "if you say what a person said, quote them exactly, in double quotes, copied "
                    "character for character from the conversation above. "
                    "If nothing stood out, reply with only the word NOTHING. "
                    "Speak in your blunt, dry, slightly weary voice. No markdown formatting, no headers, no intro."
                )

                from utils.infrastructure.gpu.gpu_manager import chat_options, gpu_memory_manager, GPUTaskPriority, voice_sampling
                opts = chat_options(temperature=0.3, num_predict=150, **voice_sampling())

                async def _run_digest_chat():
                    return await self.ctx.ollama_client.chat(
                        model=config.chat_model,
                        messages=[{"role": "user", "content": prompt}],
                        options=opts,
                        keep_alive=-1
                    )

                async def _digest():
                    resp = await gpu_memory_manager.run_with_gpu_guard(
                        model_name=config.chat_model,
                        priority=GPUTaskPriority.CHAT,
                        coro=asyncio.wait_for(_run_digest_chat(), timeout=60.0),
                        task_id=f"obs_digest_{uuid.uuid4().hex[:8]}"
                    )
                    return finish_cleanly(resp["message"]["content"].strip().replace("`", ""))

                digest_text = await _digest()
                # These post several times a day, one above the other.
                from utils.social.social_response_generator import opening, repeats_opening
                if digest_text and repeats_opening(digest_text, self._recent_digests()):
                    prompt += f" Don't open on \"{opening(digest_text)}\"."
                    digest_text = await _digest()

                if not digest_text or digest_text.strip(" .").upper() == "NOTHING":
                    return
                # It is posted as her observation of real people: a quote
                # has to be something one of them actually said. Give one
                # recoverable draft a strict no-quotation retry, then validate
                # the replacement with the same exact-text gate.
                async def _retry_without_quotes():
                    nonlocal prompt
                    prompt += (
                        "\n\nCORRECTION — your previous draft contained a quote that nobody said. "
                        "Rewrite the digest from the conversation above as a grounded paraphrase only. "
                        "Do not quote anyone, do not use quotation marks, and do not attribute wording "
                        "to a person. Describe only the topic or what the conversation was about. "
                        "If nothing can be said accurately without a quote, reply only NOTHING."
                    )
                    return await _digest()

                digest_text, did_retry, remaining_misquotes = await self._recover_unverified_digest(
                    digest_text, joined_messages, _retry_without_quotes
                )
                if did_retry and not digest_text:
                    log_warning(
                        "Observation digest recovery produced no usable quote-free paraphrase; "
                        "leaving the conversation window eligible for a later retry."
                    )
                    return
                if remaining_misquotes:
                    log_warning(
                        "Observation digest declined after quote-free retry: quote still not in "
                        f"the conversation ({summarize_payload('quote', remaining_misquotes[0])})"
                    )
                    return
                if did_retry:
                    log_info("Observation digest recovered with a validated quote-free paraphrase.")

                if not digest_text or digest_text.strip(" .").upper() == "NOTHING":
                    return

                # Save to memory/observation_digest.json with rolling window
                digest_path = Path("memory/observation_digest.json")
                digest_path.parent.mkdir(parents=True, exist_ok=True)

                history = []
                if digest_path.exists():
                    try:
                        with open(digest_path, "r", encoding="utf-8") as f:
                            history = json.load(f)
                    except Exception:
                        pass

                # Filter history to keep only last 7 days
                cutoff = time.time() - (7 * 86400)
                history = [item for item in history if item.get("timestamp", 0) > cutoff]

                entry_ts = time.time()
                history.append({
                    "timestamp": entry_ts,
                    "date": datetime.now().strftime("%Y-%m-%d"),
                    "theme_digest": digest_text,
                    # Turns actually summarised here, not the running daily
                    # total — that conflation is what made 81 and 83 look
                    # like two near-identical digests of the same material.
                    "new_turns": len(new_turns),
                    "summarized_turns": len(window),
                    "total_observed_today": len(passive_turns),
                    "watermark": new_watermark,
                    "broadcast": False,
                })

                # Cap at max 5 entries
                history = history[-5:]

                from utils.core.atomic_write import write_atomic
                write_atomic(digest_path, json.dumps(history, indent=4))

                log_success(f"Generated new passive observation digest: '{digest_text}'")

                # Seed belief updates or growth events if something interesting is noticed
                try:
                    from utils.core.kaia_dream import DreamEngine
                    de = DreamEngine(config)
                    await de._log_growth_event_async({
                        "type": "belief_seed_observed",
                        "digest": digest_text[:200],
                        "message_count": len(new_turns)
                    })
                except Exception as e:
                    log_debug(f"Failed to log growth event for observation digest: {e}")

                # 3. Say it out loud, on this path rather than through the
                #    proactive lottery — routed there the digest only airs when
                #    the "overheard" source wins a weighted draw, so most are
                #    written and never spoken.
                await self._broadcast_observation_digest(digest_text, entry_ts)
            except Exception as e:
                log_error(f"Observation digest task failed: {e}")

        @observation_digest_task.error
        async def observation_digest_error(error):
            log_error(f"CRITICAL: Observation digest task died: {error}")

        return observation_digest_task

    async def _broadcast_monologue(self, thought: str) -> bool:
        """Post an inner-monologue thought in #kaia-opolis.

        Whether it may go out — the switch, the daily limit, the gap, the hours
        — is the shared unprompted gate's decision (`unprompted.sources.monologue`
        is the switch). The thought is generated every 15 minutes regardless;
        the metadata belongs in monologue_log.jsonl.
        """
        if not self.ctx or not self.ctx.bot:
            return False
        try:
            from utils.core import unprompted
            if not unprompted.source_enabled("monologue"):
                return False
            channel = discord.utils.get(self.ctx.bot.get_all_channels(), name="kaia-opolis")
            if not channel:
                log_debug("Monologue not posted: #kaia-opolis not found.")
                return False
            from utils.core.sanitizer import to_plain_english
            spoken = await unprompted.speak(
                self.ctx, channel, "monologue", to_plain_english(thought),
                send_guard=lambda body: self._guard_opener_broadcast(
                    body, channel.id, "monologue"
                ),
            )
            return spoken.posted or spoken.queued
        except Exception as e:
            log_warning(f"Monologue broadcast failed (non-fatal): {e}")
            return False

    async def _broadcast_observation_digest(self, digest_text: str, entry_ts: float) -> bool:
        """Speak a freshly generated digest, verbatim, in #kaia-opolis.

        The digest text *is* the message — passing it to `generate_opener` as
        hidden context sent a one-liner about it and never the digest itself.
        Whether it may go out is the shared unprompted gate's decision.
        """
        if not self.ctx or not self.ctx.bot_state:
            return False
        if getattr(self.ctx.bot_state, 'is_generating', False):
            return False
        if not getattr(self.ctx.bot_state, 'boot_complete', False):
            return False

        try:
            from utils.core import unprompted
            if not unprompted.source_enabled("observation"):
                return False
            channel = discord.utils.get(self.ctx.bot.get_all_channels(), name="kaia-opolis")
            if not channel:
                log_debug("Observation digest not posted: #kaia-opolis not found.")
                return False

            from utils.core.sanitizer import to_plain_english
            text = to_plain_english(digest_text).strip()
            if not text:
                return False

            ok, why = unprompted.gate(self.ctx.bot_state, "observation", waiting_ok=True)
            if not ok:
                log_debug(f"Observation digest held: {why}.")
                return False
            async with channel.typing():
                await asyncio.sleep(2.0)
            def _mark_digest_as_aired():
                from utils.core.kaia_proactive import (
                    build_digest_content_id, mark_digest_broadcast,
                )
                try:
                    mark_digest_broadcast(build_digest_content_id(entry_ts))
                except Exception as mark_err:
                    log_debug(f"Could not flag digest as aired: {mark_err}")

            spoken = await unprompted.speak(
                self.ctx, channel, "observation", text,
                send_guard=lambda body: self._guard_opener_broadcast(
                    body, channel.id, "observation",
                    on_success=_mark_digest_as_aired,
                ),
            )
            return spoken.posted or spoken.queued
        except Exception as e:
            log_warning(f"Observation digest broadcast failed (non-fatal): {e}")
            return False

    def start(self):
        from utils.infrastructure.monitoring.async_task_registry import task_registry
        # A button click is play too: it stamps the player's Aethelgard
        # activity, which decides who defends the town at noon.
        bot = getattr(self.ctx, "bot", None)
        if bot is not None and hasattr(bot, "add_listener"):
            async def _rpg_activity(interaction):
                try:
                    if getattr(interaction, "user", None) and not interaction.user.bot:
                        from utils.ttrpg.character_manager import mark_active
                        await asyncio.to_thread(mark_active, interaction.user.id)
                except Exception:
                    pass
            bot.add_listener(_rpg_activity, "on_interaction")
            # 👍 / 👎 on an !art sheep is a vote that steers her flock.
            from utils.commands.art_handler import install_vote_listener
            install_vote_listener(bot)

            # Aethelgard trips that ended but were never posted (a failed
            # generation or post, or a restart mid-narration) are told now.
            async def _tell_untold_trips():
                try:
                    await bot.wait_until_ready()
                    await asyncio.sleep(60)
                    from utils.ttrpg import outing
                    await outing.tell_untold(self.ctx)
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    log_error(f"[rpg outing] boot replay failed: {e}")
            task_registry.register("rpg_untold_trips", asyncio.create_task(_tell_untold_trips()))
        self.news_refresh_task.start()
        # tasks.loop objects are not asyncio.Task, use get_task()
        if self.news_refresh_task.get_task():
            task_registry.register("news_refresh_task", self.news_refresh_task.get_task())
        self.dream_engine_task.start()
        if self.dream_engine_task.get_task():
            task_registry.register("dream_engine_task", self.dream_engine_task.get_task())
            
        self.evening_reflection_task.start()
        if self.evening_reflection_task.get_task():
            task_registry.register("evening_reflection_task", self.evening_reflection_task.get_task())
            
        self.aethelgard_dawn_task.start()
        if self.aethelgard_dawn_task.get_task():
            task_registry.register("aethelgard_dawn_task", self.aethelgard_dawn_task.get_task())
            
        self.noon_raid_task.start()
        if self.noon_raid_task.get_task():
            task_registry.register("noon_raid_task", self.noon_raid_task.get_task())
        
        # Presence system
        if self.presence_task:
            self.presence_task.start()
            if self.presence_task.get_task():
                task_registry.register("presence_update_task", self.presence_task.get_task())
                
        # Afterthought task
        self.afterthought_task.start()
        if self.afterthought_task.get_task():
            task_registry.register("afterthought_task", self.afterthought_task.get_task())

        # Inner Monologue task
        if self.monologue_task:
            self.monologue_task.start()
            if self.monologue_task.get_task():
                task_registry.register("monologue_task", self.monologue_task.get_task())

        # Proactive Initiation task
        if self.proactive_task:
            self.proactive_task.start()
            if self.proactive_task.get_task():
                task_registry.register("proactive_task", self.proactive_task.get_task())

        # Forum Auto-Post task
        self.forum_auto_post_task.start()
        if self.forum_auto_post_task.get_task():
            task_registry.register("forum_auto_post_task", self.forum_auto_post_task.get_task())

        # Forum Tech Support task
        self.forum_tech_support_task.start()
        if self.forum_tech_support_task.get_task():
            task_registry.register("forum_tech_support_task", self.forum_tech_support_task.get_task())

        # Passive Observation Digest task
        self.observation_digest_task.start()
        self.metadata_enrichment_task.start()
        if self.metadata_enrichment_task.get_task():
            task_registry.register('metadata_enrichment_task', self.metadata_enrichment_task.get_task())
        self.dream_curation_task.start()
        if self.dream_curation_task.get_task():
            task_registry.register('dream_curation_task', self.dream_curation_task.get_task())
        self.corpus_hygiene_task.start()
        if self.corpus_hygiene_task.get_task():
            task_registry.register('corpus_hygiene_task', self.corpus_hygiene_task.get_task())
        if self.observation_digest_task.get_task():
            task_registry.register("observation_digest_task", self.observation_digest_task.get_task())
        self.ingress_task.start()
        if self.ingress_task.get_task():
            task_registry.register("ingress_task", self.ingress_task.get_task())
        self.radio_task.start()
        if self.radio_task.get_task():
            task_registry.register("radio_task", self.radio_task.get_task())
        self.agent_boards_task.start()
        if self.agent_boards_task.get_task():
            task_registry.register("agent_boards_task", self.agent_boards_task.get_task())
        self.self_correction_task.start()
        if self.self_correction_task.get_task():
            task_registry.register("self_correction_task", self.self_correction_task.get_task())

        from utils.core import prompt_prefix
        task_registry.register("prompt_prefix_warm", asyncio.create_task(
            prompt_prefix.warm(self.ctx.ollama_client, self.ctx.config.chat_model)))

        log_action("Core background tasks started via CoreTaskManager.")

    def stop(self):
        self.news_refresh_task.stop()
        self.dream_engine_task.stop()
        self.evening_reflection_task.stop()
        self.aethelgard_dawn_task.stop()
        self.noon_raid_task.stop()
        self.afterthought_task.stop()
        if self.presence_task:
            self.presence_task.stop()
        if self.monologue_task:
            self.monologue_task.stop()
        if self.proactive_task:
            self.proactive_task.stop()
        self.forum_auto_post_task.stop()
        self.forum_tech_support_task.stop()
        self.observation_digest_task.stop()
        # Both of these were started and registered but never stopped — on
        # shutdown they were left to the task registry's cancellation rather
        # than being asked to finish their current loop.
        self.metadata_enrichment_task.stop()
        self.dream_curation_task.stop()
        self.corpus_hygiene_task.stop()
        self.ingress_task.stop()
        self.radio_task.stop()
        self.agent_boards_task.stop()
        self.self_correction_task.stop()

# Helper for backward compatibility
_task_manager = None

def start_background_core_tasks(app_ctx):
    global _task_manager
    _task_manager = CoreTaskManager(app_ctx)
    _task_manager.start()

def stop_background_core_tasks():
    if _task_manager:
        _task_manager.stop()

async def run_news_update():
    if _task_manager:
        await _task_manager.run_news_update()

async def run_village_raid(bot_ctx, channel):
    """Shared raid logic — scaled to defenders' level, uses theme pools and real combat engine."""
    import secrets
    import discord
    import asyncio
    import time
    from utils.ttrpg.character_manager import get_active_town_defenders
    from utils.ttrpg.monster_registry import get as get_monster
    from utils.ttrpg.progression import check_level_up
    from utils.ttrpg.broadcast import log_world_event as _log_world_event, broadcast_world_event, raid_outcome_flavor
    from utils.ttrpg.world_state import load_world_state, update_world_state
    from utils.ttrpg.dungeon import DUNGEON_THEMES
    from utils.ttrpg.combat_engine import _resolve_combat
    from utils.ttrpg.housing import load_housing
    from utils.ttrpg.pets import get_pet_passive
    
    # 1. Announce event
    await channel.send(embed=discord.Embed(
        title="🔔 VILLAGE ALARM",
        description=(
            "*Three rings from the Watchtower bell. The invasion signal.*\n\n"
            "A guard shouts from the parapet: **\"Something's coming out of the Whisperwood!\"**\n\n"
            "Elder Elara appears in the square, hands folded, expression unreadable.\n"
            "*\"Adventurers. To me. Now.\"*"
        ),
        color=0xFF4500
    ))
    await asyncio.sleep(3)

    # 2. Get active town defenders
    defenders = await get_active_town_defenders()
    
    if not defenders:
        await channel.send(embed=discord.Embed(
            description=(
                "*No adventurers were present. The village guard held the perimeter alone.*\n\n"
                "The threat is repelled. Oakhaven endures. Barely."
            ),
            color=0x888888
        ))
        return

    starting_states_by_uid = {
        str(s["user_id"]): {
            "hp": s.get("hp", {}).get("current", 0),
            "conditions": list(s.get("conditions", [])),
        }
        for s in defenders if s.get("user_id")
    }

    # 3. Select a random theme
    theme_key = secrets.choice(["undead", "constructs", "beasts", "deepwood", "demons"])
    theme_data = DUNGEON_THEMES[theme_key]
    
    # 4. Compute threat level
    avg_level = sum(s.get("level", 1) for s in defenders) / len(defenders)
    max_level = max(s.get("level", 1) for s in defenders)
    
    if avg_level >= 13:
        pool_index = 5
    elif avg_level >= 9:
        pool_index = 4
    elif avg_level >= 6:
        pool_index = 3
    elif avg_level >= 3:
        pool_index = 2
    else:
        pool_index = 1
        
    normal_pool = theme_data["pools"][pool_index]
    boss_pool = theme_data["boss_pools"][pool_index]
    
    # 5. Build attackers wave — scaled to active defender count
    num_attackers = min(8, max(2, len(defenders)))
    if len(defenders) >= 3:
        num_attackers = min(8, len(defenders) + 1)
    has_boss = (max_level >= 9)
    attackers = []
    total_xp = 0
    total_gil = 0
    
    for i in range(num_attackers):
        if i == 0 and has_boss:
            m_key = secrets.choice(boss_pool)
        else:
            m_key = secrets.choice(normal_pool)
            
        m_data = get_monster(m_key)
        if m_data:
            m_instance = m_data.copy()
            m_instance["key"] = m_key
            scale = 1.0 + (avg_level - 1) * 0.05
            m_instance["hp"] = max(15, int(m_instance["hp"] * scale))
            m_instance["attack"] = max(3, int(m_instance["attack"] * scale))
            m_instance["defense"] = max(8, int(m_instance["defense"] * scale))
            m_instance["hp"] = {"current": m_instance["hp"], "max": m_instance["hp"]}
            attackers.append(m_instance)
            total_xp += m_data.get("xp", 25)
            total_gil += m_data.get("gil", 10)
            
    # Rewards scale with overall event size
    total_xp = int(total_xp * 1.5)
    total_gil = int(total_gil * 1.2)
    
    creature_names = ", ".join(m["name"] for m in attackers)
    defenders_list = "\n".join(
        f"⚔️ **{s['character_name']}** (Lv.{s['level']} {s['class']})"
        for s in defenders
    )
    
    await channel.send(embed=discord.Embed(
        title=f"⚔️ Village Defense — {theme_data['name']} Incursion",
        description=(
            f"**Attacking:** {creature_names}\n"
            f"**Defenders in Oakhaven:**\n{defenders_list}\n\n"
            f"*{theme_data['flavor']}*"
        ),
        color=0xCC4400
    ))
    await asyncio.sleep(4)

    # 6. Resolve combat
    # Pair defenders with attackers cyclically
    combat_results = []
    defeated_monsters_count = 0
    player_defeated_count = 0
    
    wstate = load_world_state()
    world_atk_mod = wstate.get("atk_mod", 0)
    from utils.ttrpg.town_projects import raid_def_bonus
    world_def_mod = wstate.get("def_mod", 0) + raid_def_bonus(wstate)
    
    for idx, s in enumerate(defenders):
        attacker = attackers[idx % len(attackers)].copy()
        
        # Load pet passive bonuses
        housing = load_housing(str(s.get("user_id", "")))
        pet_bonuses = get_pet_passive(housing) if housing else {}
        
        # Run up to 3 rounds of combat
        rounds_log = []
        won = False
        escaped = False
        
        for r_idx in range(3):
            if s["hp"]["current"] <= 0 or attacker["hp"]["current"] <= 0:
                break
                
            res = _resolve_combat(
                s, attacker, 
                atk_mod_global=world_atk_mod, 
                def_mod_global=world_def_mod, 
                pet_bonuses=pet_bonuses
            )
            
            rounds_log.append({
                "round": r_idx + 1,
                "player_hit": res.get("player_hit", False),
                "player_crit": res.get("player_crit", False),
                "player_fumble": res.get("player_fumble", False),
                "player_damage": res.get("player_damage", 0),
                "monster_hit": res.get("monster_hit", False),
                "monster_damage": res.get("monster_damage", 0),
                "monster_name": attacker["name"],
                "monster_desc": attacker.get("desc", ""),
            })
            
            if attacker["hp"]["current"] <= 0:
                won = True
                defeated_monsters_count += 1
                break
            if s["hp"]["current"] <= 0:
                player_defeated_count += 1
                break
                
        combat_results.append((s, attacker, rounds_log, won, escaped))

    # Determine victory
    # Win if at least half the attackers were defeated or if all defenders stood their ground and defeated at least one
    defenders_won = (defeated_monsters_count >= (len(attackers) + 1) // 2) or (player_defeated_count == 0 and defeated_monsters_count > 0)
    
    xp_each = max(1, total_xp // len(defenders))
    gil_each = max(1, total_gil // len(defenders))
    
    # 7. Apply Consequences & Rewards
    result_lines = []
    level_ups = []
    casualty_count = 0
    
    for s, monster, rounds_log, won, escaped in combat_results:
        uid = str(s.get("user_id", ""))
        start = starting_states_by_uid.get(uid, {})
        simulated_hp = s.get("hp", {}).get("current", 0)
        consumed_conditions = set(start.get("conditions", [])) - set(s.get("conditions", []))
        reward_xp = 0
        reward_gil = 0
        reputation_delta = 0
        if simulated_hp > 0:
            if defenders_won:
                reward_xp, reward_gil, reputation_delta = xp_each, gil_each, 10
            else:
                reward_xp = max(1, xp_each // 2)

        result = await _commit_background_combat_result(
            uid,
            starting_hp=start.get("hp", 0),
            simulated_hp=simulated_hp,
            consumed_conditions=consumed_conditions,
            xp_reward=reward_xp,
            gil_reward=reward_gil,
            reputation_delta=reputation_delta,
        )
        if not result:
            continue
        character_name = result["character_name"]
        blackout = result["blackout"]
        if blackout:
            casualty_count += 1
            result_lines.append(
                f"💀 **{character_name}** blacked out (lost {blackout['xp_loss']} XP, {blackout['gil_loss']} gil)"
            )
            death_embed = discord.Embed(
                title=f"💀 {character_name} fell in defense of Oakhaven",
                description=(
                    f"*{monster['name']} left them at the Shrine threshold. "
                    f"Lost {blackout['xp_loss']} XP and {blackout['gil_loss']} Gil.*"
                ),
                color=0x8B0000,
            )
            death_embed.set_footer(text=f"Death #{result['deaths']}")
            await broadcast_world_event(bot_ctx, death_embed)
        elif simulated_hp <= 0:
            result_lines.append(
                f"⚔️ **{character_name}** recovered before the attack could leave them at the Shrine."
            )
        elif defenders_won:
            result_lines.append(
                f"⚔️ **{character_name}** held the line (received +{reward_xp} XP, +{reward_gil} gil, +10 Rep)"
            )
        else:
            result_lines.append(
                f"⚔️ **{character_name}** fought valiantly to cover the perimeter (+{reward_xp} XP)"
            )
        if result["leveled"]:
            level_ups.append(f"🎉 **{character_name}** reached **Level {result['new_level']}!**")
            
    # Apply global World State updates
    now = time.time()

    def _record_raid_result(state):
        if defenders_won:
            state.update({
                "atk_mod": 1,
                "atk_mod_expiry": now + 24 * 3600,
                "gil_mult": 1.2,
                "gil_mult_expiry": now + 24 * 3600,
                "event": "raid_repelled",
                "event_desc": f"Oakhaven repelled a {theme_data['name']}. Morale is high!",
            })
        else:
            state.update({
                "event": "raid_breached",
                "event_desc": f"Oakhaven perimeter was breached by a {theme_data['name']}. The town is damaged.",
            })
        return True

    await update_world_state(_record_raid_result)
    
    # Broadcast global outcome
    outcome_desc = raid_outcome_flavor("oakhaven", theme_key, defenders_won, casualty_count)
    outcome_embed = discord.Embed(
        title=f"🛡️ Village Defense — {'Victory' if defenders_won else 'Defeat'}",
        description=outcome_desc,
        color=0x2D5A27 if defenders_won else 0x8B0000
    )
    await broadcast_world_event(bot_ctx, outcome_embed)
    
    # Summary of individual results
    result_embed = discord.Embed(
        title=f"🛡️ Battle Results — {'Threat Repelled' if defenders_won else 'Breach Occurred'}",
        description="\n".join(result_lines),
        color=0x2D5A27 if defenders_won else 0x8B0000
    )
    if level_ups:
        result_embed.add_field(name="\u200b", value="\n".join(level_ups), inline=False)
        
    await channel.send(embed=result_embed)
    
    # Narrate combat through Kaia!
    await _narrate_raid_summary(bot_ctx, channel, defenders, attackers, combat_results, defenders_won)
    
    await _log_world_event(
        f"🛡️ **Village Defense:** Oakhaven defended against {theme_data['name']} ({creature_names}). "
        f"Defenders won: {defenders_won}. Casualties: {casualty_count}."
    )

async def run_oracle_speaks(bot_ctx, channel):
    import discord, secrets
    from utils.ttrpg.character_manager import load_all
    from utils.ttrpg.broadcast import log_world_event as _log_world_event

    town_locations = {
        "oakhaven", "stone_hearth", "hemlocks_store",
        "shrine", "watchtower", "oakhaven_bank", "herbalists_hut",
        "housing_district", "tricklebrook_pond"
    }
    buffs = [
        ("battle_focus", "STR checks +1 until next combat"),
        ("forest_sight", "DEX checks +1 until next combat"),
        ("resonance_link", "INT checks +2 until next combat"),
        ("shadow_step", "DEX checks +2 until next combat"),
        ("divine_clarity", "WIS checks +2 until next combat"),
        ("sharp_mind", "INT +2 on next check"),
        ("veiled_blessing", "+1 to next roll"),
    ]

    await channel.send(embed=discord.Embed(
        title="👁️ A Veiled Elder Appears",
        description=(
            "*She was not there a moment ago.*\n\n"
            "A pale figure stands at the center of the square, silver hair catching no light. "
            "She does not speak — not in any language that can be written.\n\n"
            "*Everyone present understands her anyway.*"
        ),
        color=0xc0c0d8
    ))
    await asyncio.sleep(4)

    # load_all is used only to discover candidate IDs; its detached sheets
    # are never carried into a later write.
    candidate_ids = list(dict.fromkeys(
        str(s.get("user_id")) for s in await load_all()
        if s.get("user_id") and s.get("location") in town_locations
    ))
    if not candidate_ids:
        await channel.send(embed=discord.Embed(
            description="*No one was there to receive it. The elder folded into shadow and was gone.*",
            color=0x888888
        ))
        return

    result_lines = []
    for uid in candidate_ids:
        buff_key, buff_desc = buffs[secrets.randbelow(len(buffs))]

        def apply(sheet):
            if sheet.get("location") not in town_locations:
                return None
            conds = sheet.setdefault("conditions", [])
            if buff_key not in conds:
                conds.append(buff_key)
            return sheet.get("character_name", "An adventurer"), buff_desc

        result = await _mutate_player_sheet(uid, apply)
        if result:
            character_name, description = result
            result_lines.append(f"✨ **{character_name}** — *{description}*")

    if not result_lines:
        await channel.send(embed=discord.Embed(
            description="*By the time the elder's gift settled, the square had emptied.*",
            color=0x888888
        ))
        return

    await channel.send(embed=discord.Embed(
        title="✨ The Elder's Gift",
        description="*She was gone before anyone could speak.*\n\n" + "\n".join(result_lines),
        color=0xc0c0d8
    ))
    await _log_world_event("👁️ **A Veiled Elder** visited Oakhaven. Those present were blessed.")

async def run_moogle_festival(bot_ctx, channel):
    import discord, secrets
    from utils.ttrpg.character_manager import load_all
    from utils.ttrpg.broadcast import log_world_event as _log_world_event

    town_locations = {
        "oakhaven", "stone_hearth", "hemlocks_store",
        "shrine", "watchtower", "oakhaven_bank", "herbalists_hut",
        "housing_district", "tricklebrook_pond"
    }
    drop_pool = [
        ("bandage", "Bandage", 20),
        ("healing_herb", "Healing Herb", 15),
        ("tonic", "Tonic", 15),
        ("potion", "Health Potion", 10),
        ("antidote", "Antidote", 10),
        ("lucky_charm", "Lucky Charm", 5),
    ]

    def roll_drop():
        total = sum(weight for _, _, weight in drop_pool)
        roll = secrets.randbelow(total)
        cumulative = 0
        for key, name, weight in drop_pool:
            cumulative += weight
            if roll < cumulative:
                return key, name
        return drop_pool[0][0], drop_pool[0][1]

    await channel.send(embed=discord.Embed(
        title="🪶 Moogle Hand-Delivery",
        description=(
            "*The sound of bells. Then more bells.*\n\n"
            "Seventeen moogles appear over the rooftops of Oakhaven simultaneously, "
            "each carrying an overstuffed satchel. They descend with tremendous ceremony "
            "and no explanation, and begin pressing parcels directly into the hands of "
            "everyone in town.\n\n*\"Kupo!\"*"
        ),
        color=0xf4a460
    ))
    await asyncio.sleep(3)

    candidate_ids = list(dict.fromkeys(
        str(s.get("user_id")) for s in await load_all()
        if s.get("user_id") and s.get("location") in town_locations
    ))
    if not candidate_ids:
        await channel.send(embed=discord.Embed(
            description="*No one to deliver to. The moogles left the packages on the ground and flew away, visibly offended.*",
            color=0x888888
        ))
        return

    from utils.ttrpg.inventory_capacity import grant_item_or_mail
    result_lines = []
    for uid in candidate_ids:
        key, name = roll_drop()

        def apply(sheet):
            if sheet.get("location") not in town_locations:
                return None
            delivery = grant_item_or_mail(sheet, key, "Moogle Hand-Delivery")
            return sheet.get("character_name", "An adventurer"), name, delivery

        result = await _mutate_player_sheet(uid, apply)
        if not result:
            continue
        character_name, name, delivery = result
        if delivery == "inventory":
            result_lines.append(f"🎒 **{character_name}** — **{name}** added to pack")
        else:
            result_lines.append(f"📬 **{character_name}** — **{name}** sent to Moogle Mail (inventory full)")

    if not result_lines:
        await channel.send(embed=discord.Embed(
            description="*The moogles arrived, but everyone had already left town.*",
            color=0x888888
        ))
        return

    await channel.send(embed=discord.Embed(
        title="🎒 Straight Into Your Pack",
        description="\n".join(result_lines) + "\n\n*The moogles left without waiting for thanks.*",
        color=0xf4a460
    ))
    await _log_world_event("🪶 **Moogle Hand-Delivery** — parcels pressed into the hands of everyone present in Oakhaven.")

async def run_aeridorian_tremor(bot_ctx, channel):
    import discord, secrets
    from utils.ttrpg.character_manager import load_all
    from utils.ttrpg.progression import check_level_up
    from utils.ttrpg.broadcast import log_world_event as _log_world_event

    town_locations = {
        "oakhaven", "stone_hearth", "hemlocks_store",
        "shrine", "watchtower", "oakhaven_bank", "herbalists_hut",
        "housing_district", "tricklebrook_pond"
    }

    await channel.send(embed=discord.Embed(
        title="💎 Aeridorian Tremor",
        description=(
            "*The ground hums. Not an earthquake — something deliberate.*\n\n"
            "The Aeridor ruins are doing something. Elara locks her door. "
            "The Shrine flame turns blue.\n\n"
            "*Whatever it's broadcasting, it's reaching everyone in range.*"
        ),
        color=0x9988dd
    ))
    await asyncio.sleep(4)

    candidate_ids = list(dict.fromkeys(
        str(s.get("user_id")) for s in await load_all()
        if s.get("user_id") and s.get("location") in town_locations
    ))
    if not candidate_ids:
        await channel.send(embed=discord.Embed(
            description="*The pulse washed over an empty square. Oakhaven's cats all looked east at the same time.*",
            color=0x888888
        ))
        return

    result_lines = []
    level_ups = []
    for uid in candidate_ids:
        roll = secrets.randbelow(100)
        value = secrets.randbelow(30) + 20 if roll < 40 else None
        hp_drain = secrets.randbelow(4) + 2 if roll >= 80 else None

        def apply(sheet):
            if sheet.get("location") not in town_locations:
                return None
            character_name = sheet.get("character_name", "An adventurer")
            if roll < 40:
                sheet["xp"] = sheet.get("xp", 0) + value
                leveled, new_level = check_level_up(sheet)
                return character_name, "xp", value, leveled, new_level
            if roll < 65:
                hp = sheet.setdefault("hp", {})
                current = hp.get("current", 0)
                maximum = hp.get("max", current)
                gain = min(10, maximum - current)
                hp["current"] = min(current + gain, maximum)
                return character_name, "heal", gain, False, 0
            if roll < 80:
                from utils.ttrpg.inventory_capacity import grant_item_or_mail
                delivery = grant_item_or_mail(sheet, "aeridor_shard", "Aeridorian Tremor")
                return character_name, "item", delivery, False, 0
            hp = sheet.setdefault("hp", {})
            hp["current"] = max(1, hp.get("current", 1) - hp_drain)
            return character_name, "drain", hp_drain, False, 0

        result = await _mutate_player_sheet(uid, apply)
        if not result:
            continue
        character_name, kind, amount, leveled, new_level = result
        if kind == "xp":
            result_lines.append(f"✨ **{character_name}** — resonance surge (+{amount} XP)")
        elif kind == "heal":
            result_lines.append(f"💚 **{character_name}** — the pulse closes old wounds (+{amount} HP)")
        elif kind == "item":
            if amount == "inventory":
                result_lines.append(f"💎 **{character_name}** — a crystal shard lands at their feet")
            else:
                result_lines.append(f"📬 **{character_name}** — a crystal shard was sent to Moogle Mail (inventory full)")
        else:
            result_lines.append(f"⚡ **{character_name}** — rejection. The pulse pushed back (-{amount} HP)")
        if leveled:
            level_ups.append(f"🎉 **{character_name}** reached **Level {new_level}!**")

    if not result_lines:
        await channel.send(embed=discord.Embed(
            description="*The pulse passed over an empty square.*",
            color=0x888888
        ))
        return

    embed = discord.Embed(
        title="💎 The Pulse Fades",
        description="\n".join(result_lines),
        color=0x9988dd
    )
    if level_ups:
        embed.add_field(name="\u200b", value="\n".join(level_ups), inline=False)
    await channel.send(embed=embed)
    await _log_world_event("💎 **Aeridorian Tremor** — resonance pulse swept through Oakhaven.")

async def run_tonberry_procession(bot_ctx, channel):
    import discord, secrets
    from utils.ttrpg.character_manager import load_all
    from utils.ttrpg.progression import check_level_up
    from utils.ttrpg.broadcast import log_world_event as _log_world_event

    town_locations = {
        "oakhaven", "stone_hearth", "hemlocks_store",
        "shrine", "watchtower", "oakhaven_bank", "herbalists_hut",
        "housing_district", "tricklebrook_pond"
    }

    await channel.send(embed=discord.Embed(
        title="🔪 The Tonberry Procession",
        description=(
            "*Single file. Lanterns lit. Moving with tremendous dignity through the square.*\n\n"
            "Nobody knows where they're going. Nobody asks. "
            "Mira has locked the Stone Hearth door from the inside.\n\n"
            "*Elara's note, slipped under every door in town: **Do not make eye contact.***"
        ),
        color=0x88bb88
    ))
    await asyncio.sleep(4)

    candidate_ids = list(dict.fromkeys(
        str(s.get("user_id")) for s in await load_all()
        if s.get("user_id") and s.get("location") in town_locations
    ))
    if not candidate_ids:
        await channel.send(embed=discord.Embed(
            description="*They marched through an empty Oakhaven. Left a single coin on the well. Nobody knows why.*",
            color=0x888888
        ))
        return

    result_lines = []
    for uid in candidate_ids:
        roll = secrets.randbelow(10)

        def apply(sheet):
            if sheet.get("location") not in town_locations:
                return None
            character_name = sheet.get("character_name", "An adventurer")
            if roll < 8:
                xp = secrets.randbelow(15) + 10
                gil = secrets.randbelow(20) + 10
                sheet["xp"] = sheet.get("xp", 0) + xp
                sheet["gil"] = sheet.get("gil", 0) + gil
                leveled, new_level = check_level_up(sheet)
                return character_name, "coin", xp, gil, leveled, new_level
            damage = secrets.randbelow(8) + 5
            hp = sheet.setdefault("hp", {})
            hp["current"] = max(1, hp.get("current", 1) - damage)
            return character_name, "hurt", damage, 0, False, 0

        result = await _mutate_player_sheet(uid, apply)
        if not result:
            continue
        character_name, kind, value_a, value_b, leveled, new_level = result
        if kind == "coin":
            result_lines.append(
                f"🕯️ **{character_name}** watched in silence. A tonberry dropped a coin purse as it passed. (+{value_a} XP, +{value_b}g)"
            )
            if leveled:
                result_lines.append(f"🎉 **{character_name}** reached **Level {new_level}!**")
        else:
            result_lines.append(
                f"🔪 **{character_name}** made eye contact. The closest tonberry stopped walking. (-{value_a} HP)"
            )

    if not result_lines:
        await channel.send(embed=discord.Embed(
            description="*The procession had passed by the time anyone remained in the square.*",
            color=0x888888
        ))
        return

    await channel.send(embed=discord.Embed(
        title="🔪 They Have Passed",
        description="\n".join(result_lines) + "\n\n*The last tonberry disappeared around the corner. The lanterns went out.*",
        color=0x88bb88
    ))
    await _log_world_event("🔪 **The Tonberry Procession** passed through Oakhaven.")

async def run_spine_storm(bot_ctx, channel):
    import discord, secrets
    from utils.ttrpg.character_manager import load_all
    from utils.ttrpg.progression import check_level_up
    from utils.ttrpg.broadcast import log_world_event as _log_world_event

    town_locations = {
        "oakhaven", "stone_hearth", "hemlocks_store",
        "shrine", "watchtower", "oakhaven_bank", "herbalists_hut",
        "housing_district", "tricklebrook_pond"
    }
    class_effects = {
        "Warrior": ("battle_focus", "The cold sharpens something. STR +1 until next combat."),
        "Ranger": ("forest_sight", "The storm light clarifies distance. DEX +1 until next combat."),
        "Mage": ("resonance_link", "The charged air sings. INT +2 until next combat."),
        "Rogue": ("shadow_step", "The fog gives excellent cover. DEX +2 until next combat."),
        "Cleric": ("divine_clarity", "The storm feels deliberate. WIS +2 until next combat."),
    }

    await channel.send(embed=discord.Embed(
        title="⛈️ Storm of the Spine",
        description=(
            "*It came from the Spine of the World and it has opinions.*\n\n"
            "Lightning that hits the same stone twice. Wind that changes direction mid-gust. "
            "The Watchtower crew came down twenty minutes ago and haven't said why.\n\n"
            "*Elara is standing in the square. In the rain. Looking pleased.*"
        ),
        color=0x4a4a7a
    ))
    await asyncio.sleep(4)

    candidate_ids = list(dict.fromkeys(
        str(s.get("user_id")) for s in await load_all()
        if s.get("user_id") and s.get("location") in town_locations
    ))
    if not candidate_ids:
        await channel.send(embed=discord.Embed(
            description="*The storm broke over an empty square. The puddles glow faintly. Nobody saw it.*",
            color=0x888888
        ))
        return

    result_lines = []
    level_ups = []
    for uid in candidate_ids:
        xp_bonus = secrets.randbelow(10) + 5

        def apply(sheet):
            if sheet.get("location") not in town_locations:
                return None
            character_name = sheet.get("character_name", "An adventurer")
            character_class = sheet.get("class", "Warrior")
            buff_key, buff_desc = class_effects.get(
                character_class, ("sharp_mind", "+1 to next roll.")
            )
            conds = sheet.setdefault("conditions", [])
            if buff_key not in conds:
                conds.append(buff_key)
            sheet["xp"] = sheet.get("xp", 0) + xp_bonus
            leveled, new_level = check_level_up(sheet)
            return character_name, buff_desc, leveled, new_level

        result = await _mutate_player_sheet(uid, apply)
        if not result:
            continue
        character_name, buff_desc, leveled, new_level = result
        result_lines.append(f"⚡ **{character_name}** — *{buff_desc}* (+{xp_bonus} XP)")
        if leveled:
            level_ups.append(f"🎉 **{character_name}** reached **Level {new_level}!**")

    if not result_lines:
        await channel.send(embed=discord.Embed(
            description="*The storm passed after the square had emptied.*",
            color=0x888888
        ))
        return

    embed = discord.Embed(
        title="⛈️ The Storm Passes",
        description="\n".join(result_lines),
        color=0x4a4a7a
    )
    if level_ups:
        embed.add_field(name="\u200b", value="\n".join(level_ups), inline=False)
    await channel.send(embed=embed)
    await _log_world_event("⛈️ **Storm of the Spine** swept through Oakhaven, leaving class-aligned blessings.")

async def run_caravan_arrival(bot_ctx, channel):
    """Full caravan merchant event — tier 3 gear, 1 gear per customer, buy + talk.

    Only an announcement embed is posted to the channel.  Players click
    '🐪 Visit Caravan' to open the shop privately (ephemeral).
    """
    import discord
    import secrets
    import asyncio
    from utils.infrastructure.logging.kaia_logger import log_action
    from utils.ttrpg.equipment_registry import (
        get_caravan_stock, WEAPONS, ARMOR, HEADGEAR, BOOTS, ACCESSORIES, CONSUMABLES,
    )
    from utils.ttrpg.shop import find_item, process_purchase
    from utils.ttrpg.character_manager import load, save
    from utils.ttrpg.broadcast import log_world_event as _log_world_event
    from utils.ttrpg.world_state import update_world_state

    TOWN_LOCATIONS = {
        "oakhaven", "stone_hearth", "hemlocks_store",
        "shrine", "watchtower", "oakhaven_bank", "herbalists_hut",
        "housing_district", "tricklebrook_pond"
    }

    CARAVAN_TALK = [
        (
            "The Road from Grimstone",
            "*The merchant leans against a crate and rolls a coin across his knuckles.*\n\n"
            "\"Three days from Grimstone. Road's worse than last season — bandits twice, "
            "a fog that didn't move right once. The Ironclad Guild men say the Trade Road "
            "is their jurisdiction but I didn't see a single patrol past the second mile marker.\"\n\n"
            "*He spits.* \"Jurisdiction. Right.\""
        ),
        (
            "Corvus Watch Over You",
            "*He touches a small charm at his throat — three interlocking circles.*\n\n"
            "\"Corvus, god of travelers and merchants. Every caravan runner carries his mark. "
            "Not because we're devout — because the alternative is admitting we're out here alone.\"\n\n"
            "*He glances at the Whisperwood treeline.* \"Some roads, you want someone watching.\""
        ),
        (
            "News from the Coast",
            "*The merchant sorts through a ledger while he talks.*\n\n"
            "\"Riverbend's gone quiet. Used to be good business — boat builders, fishermen, "
            "people who need rope and nails. Last two runs, half the stalls were closed. "
            "A fisherman told me the Silverstream is running dark. Not muddy. Dark.\"\n\n"
            "*He doesn't look up from the ledger.* \"I don't fish. Not my problem.\""
        ),
        (
            "The Aeridor Shards",
            "*His eyes sharpen when you mention the ruins.*\n\n"
            "\"Shards? Oh, I'll move those. Cities pay well — universities, collectors, "
            "the odd Ironclad Guild 'researcher.' Your man Hemlock buys them too, but he "
            "won't say what for. Between you and me, neither will the cities.\"\n\n"
            "*He taps his nose.* \"Good margins on mystery.\""
        ),
        (
            "Whisperwood Sightings",
            "*The merchant glances over his shoulder.*\n\n"
            "\"Silvani on the road two nights ago. Didn't speak to us — never do. But one of them "
            "stopped and watched the caravan pass for a full minute. My guard said they were counting "
            "our supplies.\"\n\n"
            "*He shrugs.* \"Silvani don't steal. But they're paying attention to something.\""
        ),
        (
            "Why Limited Stock",
            "*He gestures at the single wagon.*\n\n"
            "\"You see one wagon. One mule. I'm not Hemlock with a storeroom — everything I carry "
            "is what I could fit past the bandits and the fog and whatever else the road threw at me. "
            "One piece of real gear per customer. That's the rule.\"\n\n"
            "*He holds up a finger.* \"Consumables, sure, take what you need. But the steel? "
            "One item. I need stock for the next town.\""
        ),
    ]

    # ── Pre-build stock data (shared across all player views) ────────────
    gear_keys, consumable_keys = get_caravan_stock()
    gear_buyers = set()  # UIDs who already bought gear — shared across clicks

    ALL_REGS = {
        **{k: ("weapon", WEAPONS[k]) for k in WEAPONS},
        **{k: ("armor", ARMOR[k]) for k in ARMOR},
        **{k: ("head", HEADGEAR[k]) for k in HEADGEAR},
        **{k: ("boots", BOOTS[k]) for k in BOOTS},
        **{k: ("accessory", ACCESSORIES[k]) for k in ACCESSORIES},
        **{k: ("consumable", CONSUMABLES[k]) for k in CONSUMABLES},
    }

    def _fmt(key):
        cat, item = ALL_REGS[key]
        name = item["name"]
        val = item["value"]
        if cat == "weapon":
            return f"**{name}** · +{item['attack_bonus']} ATK d{item['damage_die']} · {val}g"
        elif cat in ("armor", "head", "boots"):
            cls = f" *({'/'.join(item['classes'])})*" if item.get("classes") else ""
            return f"**{name}** · +{item['defense_bonus']} DEF{cls} · {val}g"
        elif cat == "accessory":
            parts = []
            if item.get("defense_bonus"): parts.append(f"+{item['defense_bonus']} DEF")
            if item.get("attack_bonus"):  parts.append(f"+{item['attack_bonus']} ATK")
            cls = f" *({'/'.join(item['classes'])})*" if item.get("classes") else ""
            return f"**{name}** · {', '.join(parts)}{cls} · {val}g"
        else:
            hp = item.get("hp_restore", 0)
            if hp: stat = f"+{hp} HP"
            elif item.get("description"): stat = item["description"].split(".")[0].strip()
            else: stat = "misc"
            return f"**{name}** · {stat} · {val}g"

    def _build_shop_embed(gil=None):
        """Build the shop embed (reused for each player visit)."""
        cat_items = {"🗡️ Weapons": [], "🛡️ Armor": [], "🪖 Headgear": [],
                     "👢 Boots": [], "💍 Accessories": []}
        cat_map = {"weapon": "🗡️ Weapons", "armor": "🛡️ Armor", "head": "🪖 Headgear",
                   "boots": "👢 Boots", "accessory": "💍 Accessories"}
        for k in gear_keys:
            cat, _ = ALL_REGS[k]
            cat_items[cat_map[cat]].append(_fmt(k))

        embed = discord.Embed(
            title="🐪 Corvus Road Trading Co.",
            description=(
                "*Tier III goods — forged in Grimstone, tempered on the road.*\n"
                "**⚠️ LIMIT: One gear item per customer. Consumables unlimited.**"
            ),
            color=0xc8a45c
        )
        for section, lines in cat_items.items():
            if lines:
                embed.add_field(name=section, value="\n".join(lines), inline=False)
        if consumable_keys:
            embed.add_field(
                name="🧪 Consumables",
                value="\n".join(_fmt(k) for k in consumable_keys),
                inline=False
            )
        footer = "Select an item below to buy · 💬 Talk for road news"
        if gil is not None:
            footer = f"💰 Your Gil: {gil}g  ·  " + footer
        embed.set_footer(text=footer)
        return embed

    # ── Per-player shop view (sent ephemeral on Visit click) ─────────────
    def _make_caravan_shop_view():
        """Create a fresh CaravanShopView — each player gets their own."""
        view = discord.ui.View(timeout=300)  # 5 min per player session

        # Gear selects (rows 0 & 1) — chunked at 25
        chunks = [gear_keys[i:i + 25] for i in range(0, len(gear_keys), 25)]
        for idx, chunk in enumerate(chunks):
            if idx >= 2: break
            options = []
            for k in chunk:
                item = find_item(k)
                if not item: continue
                options.append(discord.SelectOption(
                    label=f"{item['name']} ({item['value']}g)"[:100], value=k
                ))
            if options:
                placeholder = "⚔️ Buy gear (1 per customer)..." if idx == 0 else "⚔️ Buy gear (continued)..."
                gear_sel = discord.ui.Select(
                    placeholder=placeholder, options=options, row=idx
                )

                async def _buy_gear(interaction: discord.Interaction):
                    await interaction.response.defer(ephemeral=True)
                    uid = str(interaction.user.id)
                    sheet = await load(uid)
                    if not sheet:
                        await interaction.followup.send(
                            embed=discord.Embed(description="No character found. (`!rpg new`)", color=0xcc4444),
                            ephemeral=True
                        )
                        return
                    if sheet.get("location") not in TOWN_LOCATIONS:
                        await interaction.followup.send(
                            embed=discord.Embed(description="You need to be in town to buy from the caravan.", color=0xcc4444),
                            ephemeral=True
                        )
                        return
                    if uid in gear_buyers:
                        await interaction.followup.send(
                            embed=discord.Embed(
                                description=(
                                    "*The merchant shakes his head.*\n\n"
                                    "\"One piece of gear, friend. I told you — I need stock for the next town. "
                                    "Consumables are still open if you need supplies.\""
                                ),
                                color=0xcc4444
                            ), ephemeral=True
                        )
                        return

                    chosen = interaction.data["values"][0]
                    cha_mod = (sheet.get("stats", {}).get("cha", 10) - 10) // 2
                    success, purchase_msg, updated = process_purchase(
                        sheet, chosen, 1, sheet.get("reputation", 0), cha_mod=cha_mod
                    )
                    if success:
                        item = find_item(chosen)
                        if item and item["category"] in ("weapon", "armor", "head", "boots", "accessory"):
                            slot = item["category"]
                            if not updated["equipment"].get(slot):
                                updated["inventory"].remove(item["key"])
                                updated["equipment"][slot] = item
                                purchase_msg += f"\nAuto-equipped **{item['name']}**."
                        await save(updated)
                        gear_buyers.add(uid)
                        await interaction.followup.send(
                            embed=discord.Embed(description=f"🐪 {purchase_msg}", color=0x44aa44),
                            ephemeral=True
                        )
                    else:
                        await interaction.followup.send(
                            embed=discord.Embed(description=purchase_msg, color=0xcc4444),
                            ephemeral=True
                        )

                gear_sel.callback = _buy_gear
                view.add_item(gear_sel)

        # Consumable select (row 2)
        cons_options = []
        for k in consumable_keys:
            item = find_item(k)
            if not item: continue
            cons_options.append(discord.SelectOption(
                label=f"{item['name']} ({item['value']}g)"[:100], value=k
            ))
        if cons_options:
            cons_sel = discord.ui.Select(
                placeholder="🧪 Buy consumables...",
                options=cons_options, row=2
            )

            async def _buy_consumable(interaction: discord.Interaction):
                await interaction.response.defer(ephemeral=True)
                uid = str(interaction.user.id)
                sheet = await load(uid)
                if not sheet:
                    await interaction.followup.send(
                        embed=discord.Embed(description="No character found.", color=0xcc4444),
                        ephemeral=True
                    )
                    return
                if sheet.get("location") not in TOWN_LOCATIONS:
                    await interaction.followup.send(
                        embed=discord.Embed(description="You need to be in town to buy from the caravan.", color=0xcc4444),
                        ephemeral=True
                    )
                    return

                chosen = interaction.data["values"][0]
                cha_mod = (sheet.get("stats", {}).get("cha", 10) - 10) // 2
                success, purchase_msg, updated = process_purchase(
                    sheet, chosen, 1, sheet.get("reputation", 0), cha_mod=cha_mod
                )
                if success:
                    await save(updated)
                    await interaction.followup.send(
                        embed=discord.Embed(description=f"🐪 {purchase_msg}", color=0x44aa44),
                        ephemeral=True
                    )
                else:
                    await interaction.followup.send(
                        embed=discord.Embed(description=purchase_msg, color=0xcc4444),
                        ephemeral=True
                    )

            cons_sel.callback = _buy_consumable
            view.add_item(cons_sel)

        # Talk button (row 3)
        talk_btn = discord.ui.Button(
            label="Talk", emoji="💬",
            style=discord.ButtonStyle.secondary, row=3
        )

        async def _talk(interaction: discord.Interaction):
            await interaction.response.defer(ephemeral=True)
            title, body = CARAVAN_TALK[secrets.randbelow(len(CARAVAN_TALK))]
            await interaction.followup.send(
                embed=discord.Embed(title=f"🐪 {title}", description=body, color=0xc8a45c),
                ephemeral=True
            )

        talk_btn.callback = _talk
        view.add_item(talk_btn)
        return view

    # ── Arrival Announcement View (posted to channel) ────────────────────
    class CaravanArrivalView(discord.ui.View):
        def __init__(self):
            super().__init__(timeout=43200)  # 12 hours

            visit_btn = discord.ui.Button(
                label="Visit Caravan", emoji="🐪",
                style=discord.ButtonStyle.primary, row=0
            )

            async def _visit(interaction: discord.Interaction):
                await interaction.response.defer(ephemeral=True)
                uid = str(interaction.user.id)
                sheet = await load(uid)
                if not sheet:
                    await interaction.followup.send(
                        embed=discord.Embed(description="You don't have a character. (`!rpg new`)", color=0xcc4444),
                        ephemeral=True
                    )
                    return
                if sheet.get("location") not in TOWN_LOCATIONS:
                    await interaction.followup.send(
                        embed=discord.Embed(
                            description="You need to be in town to visit the caravan. Travel to Oakhaven first.",
                            color=0xcc4444
                        ),
                        ephemeral=True
                    )
                    return

                # Send the actual shop interface as an ephemeral response
                shop_embed = _build_shop_embed(gil=sheet.get("gil", 0))
                shop_view = _make_caravan_shop_view()
                await interaction.followup.send(
                    embed=shop_embed, view=shop_view, ephemeral=True
                )

            visit_btn.callback = _visit
            self.add_item(visit_btn)

            talk_btn = discord.ui.Button(
                label="Talk", emoji="💬",
                style=discord.ButtonStyle.secondary, row=0
            )

            async def _talk_quick(interaction: discord.Interaction):
                await interaction.response.defer(ephemeral=True)
                title, body = CARAVAN_TALK[secrets.randbelow(len(CARAVAN_TALK))]
                await interaction.followup.send(
                    embed=discord.Embed(title=f"🐪 {title}", description=body, color=0xc8a45c),
                    ephemeral=True
                )

            talk_btn.callback = _talk_quick
            self.add_item(talk_btn)

        async def on_timeout(self):
            try:
                await channel.send(embed=discord.Embed(
                    description=(
                        "*The merchant folds the canvas, hitches the mule, and rolls north "
                        "without a word. By the time anyone looks, the wagon is a speck on "
                        "the Trade Road.*\n\n"
                        "*The caravan has departed.*"
                    ),
                    color=0x888888
                ))
            except Exception:
                pass

    # ── Post the Arrival Announcement ────────────────────────────────────
    arrival_embed = discord.Embed(
        title="🐪 A Caravan Arrives",
        description=(
            "*Tier III goods — forged in Grimstone, tempered on the road.*\n"
            "**⚠️ LIMIT: One gear item per customer. Consumables unlimited.**\n\n"
            "A traveling merchant sets up shop in Oakhaven.\n"
            "*\"Grimstone masterworks! Tempered on the road, forged for the brave! Come see the Corvus Road Trading Co.!\"*"
        ),
        color=0xc8a45c
    )
    arrival_embed.set_footer(text="Merchant departs at midnight · Visit to see stock")
    
    view = CaravanArrivalView()
    await channel.send(embed=arrival_embed, view=view)

    # Update shared state from a fresh snapshot under the transaction lock.
    await update_world_state(lambda state: state.update({"caravan_active": True}))

    await _log_world_event("🐪 **A traveling caravan** arrived in Oakhaven — tier III goods available until midnight.")
    log_action("Noon Event: Caravan Arrival (full merchant)")

async def run_bard_performance(bot_ctx, channel):
    """Noon event: Caelindra performs an LLM-generated ballad about recent world events."""
    import discord, asyncio
    import uuid as _uuid
    from utils.infrastructure.logging.kaia_logger import log_action, log_error, log_info
    from utils.infrastructure.system.yaml_config import config
    from utils.ttrpg.character_manager import load_all
    from utils.ttrpg.broadcast import (
        load_world_events,
        log_world_event as _log_world_event,
    )

    # Load recent world events for song material without blocking the event loop.
    recent_events = (await load_world_events())[-6:]

    # Top adventurers for name-drops
    all_sheets = await load_all()
    top_adventurers = sorted(all_sheets, key=lambda s: s.get("xp", 0), reverse=True)[:4]
    names = [s.get("character_name", s.get("name", "Unknown")) for s in top_adventurers if s]

    events_str = "\n".join([f"- {e}" for e in recent_events]) if recent_events else "- A quiet season. The forest waits."
    names_str = ", ".join(names) if names else "the adventurers of Oakhaven"

    # Build prompt (mirrors _handle_bard_song pattern)
    prompt = (
        f"You are Caelindra the Bard performing at the Stone Hearth Inn in Oakhaven.\n"
        f"Recent events:\n{events_str}\n\n"
        f"Notable adventurers: {names_str}\n\n"
        f"Write a ballad (4-10 lines) about these deeds. "
        f"Voice: dry, specific, sardonic — like a journalist who found melody. "
        f"It MUST name at least one adventurer. Reference a specific event. "
        f"Output only the ballad, no preamble."
    )

    song_text = "*Caelindra strums a chord, hums something, then shrugs and orders another drink.*"
    try:
        from utils.social.kaia_social_responder import load_persona_async
        from utils.infrastructure.gpu.gpu_manager import OllamaGPUManager, gpu_memory_manager, GPUTaskPriority

        persona = await load_persona_async()
        gpu_manager = OllamaGPUManager(config.chat_model)
        opts = gpu_manager.get_gpu_options(for_chat=True)
        opts["num_predict"] = 180
        opts["temperature"] = 0.95

        resp = await gpu_memory_manager.run_with_gpu_guard(
            model_name=config.chat_model,
            priority=GPUTaskPriority.CHAT,
            coro=asyncio.wait_for(
                bot_ctx.ollama_client.chat(
                    model=config.chat_model,
                    messages=[
                        {"role": "system", "content": persona + "\n\n" + prompt},
                        {"role": "user", "content": "Perform the song."}
                    ],
                    options=opts,
                    keep_alive=-1
                ),
                timeout=45.0
            ),
            task_id=f"bard_noon_{_uuid.uuid4().hex[:8]}"
        )
        raw = finish_cleanly(resp["message"]["content"].strip().replace("```", ""))
        if raw:
            song_text = raw
    except Exception as e:
        log_error(f"[bard noon event] LLM call failed: {e}")

    embed = discord.Embed(
        title="🎵 Caelindra Performs",
        description=f"*{song_text}*",
        color=0x9b59b6
    )
    embed.set_footer(text="The Stone Hearth goes quiet for a moment. Then Mira refills something.")
    await channel.send(embed=embed)

    await _log_world_event("🎵 **Caelindra the Bard** performed a ballad at the Stone Hearth.")
    log_action("Noon Event: Bard Performance (LLM)")
    log_info("Noon Event: Bard Performance triggered successfully.")


async def _narrate_raid_summary(ctx, channel, defenders, attackers, combat_results, defenders_won):
    from utils.social.kaia_social_responder import load_persona_async
    from utils.ttrpg.rpg_prompt_builder import TTRPG_NARRATOR_OVERRIDE
    from utils.infrastructure.gpu.gpu_manager import OllamaGPUManager, gpu_memory_manager, GPUTaskPriority
    import uuid as _uuid
    import discord
    
    fight_summaries = []
    for sheet, monster, rounds_log, won, escaped in combat_results:
        p_name = sheet["character_name"]
        m_name = monster["name"]
        hp_before = sheet["hp"]["current"] + sum(r["monster_damage"] for r in rounds_log)
        hp_after = sheet["hp"]["current"]
        
        p_hits = sum(1 for r in rounds_log if r["player_hit"] and not r["player_fumble"])
        p_damage = sum(r["player_damage"] for r in rounds_log)
        m_hits = sum(1 for r in rounds_log if r["monster_hit"])
        m_damage = sum(r["monster_damage"] for r in rounds_log)
        
        status = "Survived"
        if hp_after <= 0:
            status = "Defeated (Blacked out, dragged to Shrine)"
        elif won:
            status = f"Defeated the {m_name}"
            
        fight_summaries.append(
            f"- {p_name} ({sheet['class']} Lv.{sheet['level']}) fought {m_name}. "
            f"Rounds: {len(rounds_log)}. "
            f"{p_name} hit {p_hits} times dealing {p_damage} dmg. "
            f"{m_name} hit {m_hits} times dealing {m_damage} dmg. "
            f"Result: {status}. HP: {hp_before} -> {hp_after}."
        )
        
    fights_str = "\n".join(fight_summaries)
    attacker_names = ", ".join(m["name"] for m in attackers)
    outcome_str = "SUCCESS — Defenders held Oakhaven!" if defenders_won else "FAILURE — The perimeter was breached and defenders took heavy casualties!"
    
    prompt = f"""[TTRPG GROUND TRUTH — VILLAGE RAID SUMMARY — DO NOT CONTRADICT]
EVENT: Village Raid in Oakhaven
OUTCOME: {outcome_str}
ATTACKING CREATURES: {attacker_names}

FIGHT DETAILS:
{fights_str}

INSTRUCTIONS FOR NARRATION:
Describe the battle at the town perimeter specifically involving the ATTACKING CREATURES listed above ({attacker_names}).
Highlight key moments from the fight details above.
[CRITICAL] Do NOT invent unrelated enemies (e.g. goblins, gnolls) unless they are in the attacking list above.
Keep the tone lowercase, grounded, and specific. No purple prose.
Speak as Kaia — the GM narrator.
[END GROUND TRUTH]"""

    persona = await load_persona_async()
    messages = [
        {"role": "system", "content": f"{persona}{TTRPG_NARRATOR_OVERRIDE}{prompt}"},
        {"role": "user",   "content": "Narrate the village raid defense battle."}
    ]
    
    from utils.ttrpg.narration import (
        finish_cleanly, fit_embed_description, raid_token_budget,
    )

    gpu_manager = OllamaGPUManager(config.chat_model)
    opts = gpu_manager.get_gpu_options(for_chat=True)
    # The prompt asks for a beat per defender, so a fixed budget runs out as
    # the party grows: a six-defender raid was cut mid-word at "the defenders
    # of o". Scale it with the cast.
    opts["num_predict"] = raid_token_budget(len(combat_results))
    opts["temperature"] = 0.85
    
    async with channel.typing():
        try:
            resp = await gpu_memory_manager.run_with_gpu_guard(
                model_name=config.chat_model,
                priority=GPUTaskPriority.CHAT,
                coro=asyncio.wait_for(
                    ctx.ollama_client.chat(
                        model=config.chat_model,
                        messages=messages,
                        options=opts,
                        keep_alive=-1
                    ),
                    timeout=45.0
                ),
                task_id=f"rpg_raid_summary_{_uuid.uuid4().hex[:8]}"
            )
            narration = resp["message"]["content"].strip().replace("```", "")
            # Trim back to the last complete sentence if the model was cut off,
            # then clamp to Discord's embed limit (the asterisks add two chars).
            narration = fit_embed_description(finish_cleanly(narration))
            if narration:
                embed = discord.Embed(
                    title="⚔️ Battle Narration",
                    description=f"*{narration}*",
                    color=0x2D5A27 if defenders_won else 0x8B0000
                )
                await channel.send(embed=embed)
        except Exception as e:
            log_error(f"[rpg raid summary] {e}")


async def run_construct_breach(bot_ctx, channel):
    """Aeridorian construct breach event — combat event at Watchtower/ruins edge."""
    import secrets
    import discord
    import asyncio
    import time
    from utils.ttrpg.character_manager import get_active_town_defenders
    from utils.ttrpg.monster_registry import get as get_monster
    from utils.ttrpg.progression import check_level_up
    from utils.ttrpg.broadcast import log_world_event as _log_world_event, broadcast_world_event, raid_outcome_flavor
    from utils.ttrpg.world_state import load_world_state, update_world_state
    from utils.ttrpg.dungeon import DUNGEON_THEMES
    from utils.ttrpg.combat_engine import _resolve_combat
    from utils.ttrpg.housing import load_housing
    from utils.ttrpg.pets import get_pet_passive

    await channel.send(embed=discord.Embed(
        title="🔔 WATCHTOWER BEACON LIT",
        description=(
            "*The high beacon at the Watchtower flares with a cold blue resonance light.*\n\n"
            "\"Constructs! They've breached the south wall from the ruins!\"\n\n"
            "Ancient gears scream in the dirt as stone and steel emerge from the mist."
        ),
        color=0x00aaff
    ))
    await asyncio.sleep(3)

    defenders = await get_active_town_defenders()
    
    if not defenders:
        await channel.send(embed=discord.Embed(
            description=(
                "*No adventurers were near the ruins edge. The Watchtower automatic defenses fired until they burned out.*\n\n"
                "The construct breach was repelled by automated shields. The systems are offline."
            ),
            color=0x888888
        ))
        return

    starting_states_by_uid = {
        str(s["user_id"]): {
            "hp": s.get("hp", {}).get("current", 0),
            "conditions": list(s.get("conditions", [])),
        }
        for s in defenders if s.get("user_id")
    }

    theme_key = "constructs"
    theme_data = DUNGEON_THEMES[theme_key]
    
    avg_level = sum(s.get("level", 1) for s in defenders) / len(defenders)
    max_level = max(s.get("level", 1) for s in defenders)
    
    if avg_level >= 13:   pool_index = 5
    elif avg_level >= 9:  pool_index = 4
    elif avg_level >= 6:  pool_index = 3
    elif avg_level >= 3:  pool_index = 2
    else:                 pool_index = 1
        
    normal_pool = theme_data["pools"][pool_index]
    boss_pool = theme_data["boss_pools"][pool_index]
    
    num_attackers = min(8, 2 + max_level // 3)
    has_boss = (max_level >= 9)
    attackers = []
    total_xp = 0
    total_gil = 0
    
    for i in range(num_attackers):
        if i == 0 and has_boss:
            m_key = secrets.choice(boss_pool)
        else:
            m_key = secrets.choice(normal_pool)
            
        m_data = get_monster(m_key)
        if m_data:
            m_instance = m_data.copy()
            m_instance["key"] = m_key
            scale = 1.0 + (avg_level - 1) * 0.05
            m_instance["hp"] = max(15, int(m_instance["hp"] * scale))
            m_instance["attack"] = max(3, int(m_instance["attack"] * scale))
            m_instance["defense"] = max(8, int(m_instance["defense"] * scale))
            m_instance["hp"] = {"current": m_instance["hp"], "max": m_instance["hp"]}
            attackers.append(m_instance)
            total_xp += m_data.get("xp", 25)
            total_gil += m_data.get("gil", 10)
            
    total_xp = int(total_xp * 1.5)
    total_gil = int(total_gil * 1.2)
    
    creature_names = ", ".join(m["name"] for m in attackers)
    defenders_list = "\n".join(
        f"⚔️ **{s['character_name']}** (Lv.{s['level']} {s['class']})"
        for s in defenders
    )
    
    await channel.send(embed=discord.Embed(
        title=f"⚔️ Watchtower Defense — Construct Breach",
        description=(
            f"**Attacking:** {creature_names}\n"
            f"**Defenders at Watchtower:**\n{defenders_list}\n\n"
            f"*{theme_data['flavor']}*"
        ),
        color=0x00aaff
    ))
    await asyncio.sleep(4)

    combat_results = []
    defeated_monsters_count = 0
    player_defeated_count = 0
    
    wstate = load_world_state()
    world_atk_mod = wstate.get("atk_mod", 0)
    from utils.ttrpg.town_projects import raid_def_bonus
    world_def_mod = wstate.get("def_mod", 0) + raid_def_bonus(wstate)
    
    for idx, s in enumerate(defenders):
        attacker = attackers[idx % len(attackers)].copy()
        housing = load_housing(str(s.get("user_id", "")))
        pet_bonuses = get_pet_passive(housing) if housing else {}
        
        rounds_log = []
        won = False
        escaped = False
        
        for r_idx in range(3):
            if s["hp"]["current"] <= 0 or attacker["hp"]["current"] <= 0:
                break
            res = _resolve_combat(
                s, attacker, 
                atk_mod_global=world_atk_mod, 
                def_mod_global=world_def_mod, 
                pet_bonuses=pet_bonuses
            )
            rounds_log.append({
                "round": r_idx + 1,
                "player_hit": res.get("player_hit", False),
                "player_crit": res.get("player_crit", False),
                "player_fumble": res.get("player_fumble", False),
                "player_damage": res.get("player_damage", 0),
                "monster_hit": res.get("monster_hit", False),
                "monster_damage": res.get("monster_damage", 0),
                "monster_name": attacker["name"],
                "monster_desc": attacker.get("desc", ""),
            })
            if attacker["hp"]["current"] <= 0:
                won = True
                defeated_monsters_count += 1
                break
            if s["hp"]["current"] <= 0:
                player_defeated_count += 1
                break
                
        combat_results.append((s, attacker, rounds_log, won, escaped))

    defenders_won = (defeated_monsters_count >= len(attackers) / 2)
    xp_each = max(1, total_xp // len(defenders))
    gil_each = max(1, total_gil // len(defenders))
    
    result_lines = []
    level_ups = []
    casualty_count = 0
    
    for s, monster, rounds_log, won, escaped in combat_results:
        uid = str(s.get("user_id", ""))
        start = starting_states_by_uid.get(uid, {})
        simulated_hp = s.get("hp", {}).get("current", 0)
        consumed_conditions = set(start.get("conditions", [])) - set(s.get("conditions", []))
        reward_xp = xp_each if simulated_hp > 0 and defenders_won else 0
        reward_gil = gil_each if simulated_hp > 0 and defenders_won else 0
        reputation_delta = 10 if simulated_hp > 0 and defenders_won else (-10 if simulated_hp > 0 else 0)
        result = await _commit_background_combat_result(
            uid, starting_hp=start.get("hp", 0), simulated_hp=simulated_hp,
            consumed_conditions=consumed_conditions, xp_reward=reward_xp,
            gil_reward=reward_gil, reputation_delta=reputation_delta,
        )
        if not result:
            continue
        character_name = result["character_name"]
        blackout = result["blackout"]
        if blackout:
            casualty_count += 1
            result_lines.append(
                f"💀 **{character_name}** blacked out (lost {blackout['xp_loss']} XP, {blackout['gil_loss']} gil)"
            )
            death_embed = discord.Embed(
                title=f"💀 {character_name} fell during Construct Breach",
                description=(
                    f"*{monster['name']} left them at the Shrine threshold. "
                    f"Lost {blackout['xp_loss']} XP and {blackout['gil_loss']} Gil.*"
                ),
                color=0x8B0000,
            )
            await broadcast_world_event(bot_ctx, death_embed)
        elif simulated_hp <= 0:
            result_lines.append(f"⚔️ **{character_name}** recovered before reaching the Shrine.")
        elif defenders_won:
            result_lines.append(
                f"⚔️ **{character_name}** survived (received +{reward_xp} XP, +{reward_gil} gil, +10 Rep)"
            )
        else:
            result_lines.append(f"⚔️ **{character_name}** survived but withdrew (lost 10 Rep)")
        if result["leveled"]:
            level_ups.append(f"🎉 **{character_name}** reached **Level {result['new_level']}!**")
            
    now = time.time()

    def _record_construct_breach_result(state):
        if defenders_won:
            state.update({
                "def_mod": 1,
                "def_mod_expiry": now + 24 * 3600,
                "event": "construct_breach_repelled",
                "event_desc": "Oakhaven repelled a Construct Breach. Shield systems are humming.",
            })
        else:
            state.update({
                "event": "construct_breach_failed",
                "event_desc": "Watchtower perimeter breached by constructs. Resonating feedback lingering.",
            })
        return True

    await update_world_state(_record_construct_breach_result)
    
    outcome_desc = raid_outcome_flavor("watchtower", "constructs", defenders_won, casualty_count)
    outcome_embed = discord.Embed(
        title=f"🛡️ Watchtower Defense — {'Victory' if defenders_won else 'Defeat'}",
        description=outcome_desc,
        color=0x2D5A27 if defenders_won else 0x8B0000
    )
    await broadcast_world_event(bot_ctx, outcome_embed)
    
    result_embed = discord.Embed(
        title=f"🛡️ Battle Results — {'Construct Breach Repelled' if defenders_won else 'Watchtower Damaged'}",
        description="\n".join(result_lines),
        color=0x2D5A27 if defenders_won else 0x8B0000
    )
    if level_ups:
        result_embed.add_field(name="\u200b", value="\n".join(level_ups), inline=False)
    await channel.send(embed=result_embed)
    
    await _narrate_raid_summary(bot_ctx, channel, defenders, attackers, combat_results, defenders_won)
    
    await _log_world_event(
        f"🛡️ **Construct Breach:** Watchtower defended. "
        f"Defenders won: {defenders_won}. Casualties: {casualty_count}."
    )
    log_action("Noon Event: Construct Breach (Resolved)")


async def run_caravan_ambush(bot_ctx, channel):
    """Caravan ambush event — optional combat if caravan is active."""
    import secrets
    import discord
    import asyncio
    import time
    from utils.ttrpg.character_manager import get_active_town_defenders
    from utils.ttrpg.monster_registry import get as get_monster
    from utils.ttrpg.progression import check_level_up
    from utils.ttrpg.broadcast import log_world_event as _log_world_event, broadcast_world_event, raid_outcome_flavor
    from utils.ttrpg.world_state import load_world_state, update_world_state
    from utils.ttrpg.dungeon import DUNGEON_THEMES
    from utils.ttrpg.combat_engine import _resolve_combat
    from utils.ttrpg.housing import load_housing
    from utils.ttrpg.pets import get_pet_passive

    wstate = load_world_state()
    if not wstate.get("caravan_active", False):
        await channel.send(embed=discord.Embed(
            description="📋 *The Trade Road is quiet today. No active caravans are currently traveling.*",
            color=0x888888
        ))
        return

    await channel.send(embed=discord.Embed(
        title="🔔 CARAVAN DISTRESS SIGNAL",
        description=(
            "*A messenger bird flaps frantically into the Oakhaven square, a bloody note tied to its leg.*\n\n"
            "**\"Ambush on the Trade Road! The merchant caravan is surrounded by beasts! Help!\"**"
        ),
        color=0xff6600
    ))
    await asyncio.sleep(3)

    defenders = await get_active_town_defenders()
    
    if not defenders:
        def _end_unattended_caravan(state):
            if not state.get("caravan_active", False):
                return False
            state["caravan_active"] = False
            return True

        await update_world_state(_end_unattended_caravan)
        await channel.send(embed=discord.Embed(
            description=(
                "*No adventurers responded in time. The merchant caravan was ransacked by predators.*\n\n"
                "**The caravan has left Aethelgard early. It is no longer active today.**"
            ),
            color=0xcc4444
        ))
        await _log_world_event("❌ **Caravan Destroyed** — bandits and beasts ransacked the Trade Road caravan.")
        return

    starting_states_by_uid = {
        str(s["user_id"]): {
            "hp": s.get("hp", {}).get("current", 0),
            "conditions": list(s.get("conditions", [])),
        }
        for s in defenders if s.get("user_id")
    }

    theme_key = secrets.choice(["beasts", "demons"])
    theme_data = DUNGEON_THEMES[theme_key]
    
    avg_level = sum(s.get("level", 1) for s in defenders) / len(defenders)
    max_level = max(s.get("level", 1) for s in defenders)
    
    if avg_level >= 13:   pool_index = 5
    elif avg_level >= 9:  pool_index = 4
    elif avg_level >= 6:  pool_index = 3
    elif avg_level >= 3:  pool_index = 2
    else:                 pool_index = 1
        
    normal_pool = theme_data["pools"][pool_index]
    boss_pool = theme_data["boss_pools"][pool_index]
    
    num_attackers = min(8, 2 + max_level // 3)
    has_boss = (max_level >= 9)
    attackers = []
    total_xp = 0
    total_gil = 0
    
    for i in range(num_attackers):
        if i == 0 and has_boss:
            m_key = secrets.choice(boss_pool)
        else:
            m_key = secrets.choice(normal_pool)
            
        m_data = get_monster(m_key)
        if m_data:
            m_instance = m_data.copy()
            m_instance["key"] = m_key
            scale = 1.0 + (avg_level - 1) * 0.05
            m_instance["hp"] = max(15, int(m_instance["hp"] * scale))
            m_instance["attack"] = max(3, int(m_instance["attack"] * scale))
            m_instance["defense"] = max(8, int(m_instance["defense"] * scale))
            m_instance["hp"] = {"current": m_instance["hp"], "max": m_instance["hp"]}
            attackers.append(m_instance)
            total_xp += m_data.get("xp", 25)
            total_gil += m_data.get("gil", 10)
            
    total_xp = int(total_xp * 1.5)
    total_gil = int(total_gil * 1.5)
    
    creature_names = ", ".join(m["name"] for m in attackers)
    defenders_list = "\n".join(
        f"⚔️ **{s['character_name']}** (Lv.{s['level']} {s['class']})"
        for s in defenders
    )
    
    await channel.send(embed=discord.Embed(
        title=f"⚔️ Battle on the Trade Road — Rescue Caravan",
        description=(
            f"**Attacking:** {creature_names}\n"
            f"**Rescuers:**\n{defenders_list}\n\n"
            f"*{theme_data['flavor']}*"
        ),
        color=0xff6600
    ))
    await asyncio.sleep(4)

    combat_results = []
    defeated_monsters_count = 0
    player_defeated_count = 0
    
    # Refresh shared modifiers after the player response delay.
    wstate = load_world_state()
    world_atk_mod = wstate.get("atk_mod", 0)
    from utils.ttrpg.town_projects import raid_def_bonus
    world_def_mod = wstate.get("def_mod", 0) + raid_def_bonus(wstate)
    
    for idx, s in enumerate(defenders):
        attacker = attackers[idx % len(attackers)].copy()
        housing = load_housing(str(s.get("user_id", "")))
        pet_bonuses = get_pet_passive(housing) if housing else {}
        
        rounds_log = []
        won = False
        escaped = False
        
        for r_idx in range(3):
            if s["hp"]["current"] <= 0 or attacker["hp"]["current"] <= 0:
                break
            res = _resolve_combat(
                s, attacker, 
                atk_mod_global=world_atk_mod, 
                def_mod_global=world_def_mod, 
                pet_bonuses=pet_bonuses
            )
            rounds_log.append({
                "round": r_idx + 1,
                "player_hit": res.get("player_hit", False),
                "player_crit": res.get("player_crit", False),
                "player_fumble": res.get("player_fumble", False),
                "player_damage": res.get("player_damage", 0),
                "monster_hit": res.get("monster_hit", False),
                "monster_damage": res.get("monster_damage", 0),
                "monster_name": attacker["name"],
                "monster_desc": attacker.get("desc", ""),
            })
            if attacker["hp"]["current"] <= 0:
                won = True
                defeated_monsters_count += 1
                break
            if s["hp"]["current"] <= 0:
                player_defeated_count += 1
                break
                
        combat_results.append((s, attacker, rounds_log, won, escaped))

    defenders_won = (defeated_monsters_count >= len(attackers) / 2)
    xp_each = max(1, total_xp // len(defenders))
    gil_each = max(1, total_gil // len(defenders))
    
    result_lines = []
    level_ups = []
    casualty_count = 0
    
    for s, monster, rounds_log, won, escaped in combat_results:
        uid = str(s.get("user_id", ""))
        start = starting_states_by_uid.get(uid, {})
        simulated_hp = s.get("hp", {}).get("current", 0)
        consumed_conditions = set(start.get("conditions", [])) - set(s.get("conditions", []))
        reward_xp = xp_each if simulated_hp > 0 and defenders_won else 0
        reward_gil = gil_each if simulated_hp > 0 and defenders_won else 0
        reputation_delta = 15 if simulated_hp > 0 and defenders_won else (-10 if simulated_hp > 0 else 0)
        result = await _commit_background_combat_result(
            uid, starting_hp=start.get("hp", 0), simulated_hp=simulated_hp,
            consumed_conditions=consumed_conditions, xp_reward=reward_xp,
            gil_reward=reward_gil, reputation_delta=reputation_delta,
        )
        if not result:
            continue
        character_name = result["character_name"]
        blackout = result["blackout"]
        if blackout:
            casualty_count += 1
            result_lines.append(
                f"💀 **{character_name}** blacked out (lost {blackout['xp_loss']} XP, {blackout['gil_loss']} gil)"
            )
            death_embed = discord.Embed(
                title=f"💀 {character_name} fell protecting the Caravan",
                description=(
                    f"*{monster['name']} left them at the Shrine threshold. "
                    f"Lost {blackout['xp_loss']} XP and {blackout['gil_loss']} Gil.*"
                ),
                color=0x8B0000,
            )
            await broadcast_world_event(bot_ctx, death_embed)
        elif simulated_hp <= 0:
            result_lines.append(f"⚔️ **{character_name}** recovered before reaching the Shrine.")
        elif defenders_won:
            result_lines.append(
                f"⚔️ **{character_name}** survived (received +{reward_xp} XP, +{reward_gil} gil, +15 Rep)"
            )
        else:
            result_lines.append(f"⚔️ **{character_name}** survived but withdrew (lost 10 Rep)")
        if result["leveled"]:
            level_ups.append(f"🎉 **{character_name}** reached **Level {result['new_level']}!**")
            
    def _record_caravan_result(state):
        if defenders_won:
            state.update({
                "event": "caravan_saved",
                "event_desc": "Trade caravan was successfully defended. Stock remains open.",
            })
        else:
            state.update({
                "caravan_active": False,
                "event": "caravan_destroyed",
                "event_desc": "Trade caravan was pillaged on the Trade Road. Merchant fled.",
            })
        return True

    await update_world_state(_record_caravan_result)
    
    outcome_desc = raid_outcome_flavor("trade_road caravan", theme_key, defenders_won, casualty_count)
    outcome_embed = discord.Embed(
        title=f"🛡️ Caravan Rescue — {'Victory' if defenders_won else 'Defeat'}",
        description=outcome_desc,
        color=0x2D5A27 if defenders_won else 0x8B0000
    )
    await broadcast_world_event(bot_ctx, outcome_embed)
    
    result_embed = discord.Embed(
        title=f"🛡️ Battle Results — {'Caravan Rescued' if defenders_won else 'Caravan Ransacked'}",
        description="\n".join(result_lines),
        color=0x2D5A27 if defenders_won else 0x8B0000
    )
    if level_ups:
        result_embed.add_field(name="\u200b", value="\n".join(level_ups), inline=False)
    await channel.send(embed=result_embed)
    
    await _narrate_raid_summary(bot_ctx, channel, defenders, attackers, combat_results, defenders_won)
    
    await _log_world_event(
        f"🛡️ **Caravan Ambush:** Trade road defended. "
        f"Defenders won: {defenders_won}. Casualties: {casualty_count}."
    )
    log_action("Noon Event: Caravan Ambush (Resolved)")


async def run_market_glut(bot_ctx, channel):
    """Market Glut / Price event — modifies shop purchase/sell prices for 4 hours."""
    import secrets
    import discord
    import time
    from utils.ttrpg.world_state import load_world_state, update_world_state
    from utils.ttrpg.broadcast import log_world_event as _log_world_event, broadcast_world_event

    wstate = {}
    now = time.time()
    
    is_glut = secrets.randbelow(2) == 0
    if is_glut:
        wstate["blockade_active"] = False
        wstate["shop_price_mult"] = 0.8
        wstate["shop_price_mult_expiry"] = now + 24 * 3600
        title = "📋 Notice: Market Glut!"
        desc = (
            "**Caravan shipments arrived early!**\n\n"
            "All purchase and sell prices at Hemlock's and the Trade Caravan "
            "are **discounted by 20%** until the next noon event!"
        )
        color = 0x27ae60
        log_text = "📋 **Market Glut** — supply surge discounted shop prices by 20% until the next noon event."
    else:
        wstate["blockade_active"] = True
        wstate["shop_price_mult"] = 1.25
        wstate["shop_price_mult_expiry"] = now + 24 * 3600
        title = "📋 Notice: Whisperwood Blockade!"
        desc = (
            "**Bandit activity has blocked the western trade passes!**\n\n"
            "Severe supply shortages have **inflated all shop prices by 25%** "
            "until the next noon event!\n\n"
            "⚔️ *Adventurers can assault the bandit camp (`!rpg raid blockade`) or sneak into their cache (`!rpg rob bandits`) on the Trade Road to break the blockade!*"
        )
        color = 0xd35400
        log_text = "📋 **Supply Shortage** — trade blockages inflated shop prices by 25% until the next noon event."

    await update_world_state(lambda state: state.update({
        "blockade_active": wstate["blockade_active"],
        "shop_price_mult": wstate["shop_price_mult"],
        "shop_price_mult_expiry": wstate["shop_price_mult_expiry"],
    }))
    
    embed = discord.Embed(title=title, description=desc, color=color)
    embed.set_footer(text="Prices are adjusted automatically at checkout.")
    await channel.send(embed=embed)
    await _log_world_event(log_text)
    log_action("Noon Event: Market Glut (Configured)")


async def run_whisperwood_bloom(bot_ctx, channel):
    """Whisperwood Bloom event — increases forest events chance for 4 hours."""
    import discord
    import time
    from utils.ttrpg.world_state import load_world_state, update_world_state
    from utils.ttrpg.broadcast import log_world_event as _log_world_event, broadcast_world_event

    wstate = {}
    now = time.time()
    
    wstate["forest_event_bonus"] = 0.15
    wstate["forest_event_bonus_expiry"] = now + 24 * 3600
    await update_world_state(lambda state: state.update({
        "forest_event_bonus": wstate["forest_event_bonus"],
        "forest_event_bonus_expiry": wstate["forest_event_bonus_expiry"],
    }))
    
    embed = discord.Embed(
        title="🌸 Whisperwood Bloom",
        description=(
            "*A warm wind blows spores through Oakhaven. The deep trees look vibrant.*\n\n"
            "The forest is active! Forest event trigger chances on hunts/scouts in the Whisperwood "
            "are **increased by 15%** until the next noon event!"
        ),
        color=0xe84393
    )
    embed.set_footer(text="Keep your eyes open out there.")
    await channel.send(embed=embed)
    await _log_world_event("🌸 **Whisperwood Bloom** — forest event chances boosted by +15% until the next noon event.")
    log_action("Noon Event: Whisperwood Bloom (Configured)")


async def run_shrine_vigil(bot_ctx, channel):
    """Shrine Vigil event — grants enhanced blessings for 4 hours."""
    import discord
    import time
    from utils.ttrpg.world_state import load_world_state, update_world_state
    from utils.ttrpg.broadcast import log_world_event as _log_world_event, broadcast_world_event

    wstate = {}
    now = time.time()
    
    wstate["blessing_window_until"] = now + 24 * 3600
    await update_world_state(lambda state: state.update({
        "blessing_window_until": wstate["blessing_window_until"],
    }))
    
    embed = discord.Embed(
        title="🕯️ Shrine Vigil Active",
        description=(
            "*The sacred basins at the Shrine of the Silent Ones glow with intense resonance.*\n\n"
            "A holy vigil is active! Players who `!rpg pray` or `!rpg offer` at the Shrine until the "
            "next noon event will receive **Morvenna's Ward blessing** (+5 HP restored, and the Blessed buff)!"
        ),
        color=0xaaddff
    )
    embed.set_footer(text="The Silent Ones are watching Oakhaven.")
    await channel.send(embed=embed)
    await _log_world_event("🕯️ **Shrine Vigil** — enhanced blessing window active until the next noon event.")
    log_action("Noon Event: Shrine Vigil (Configured)")


async def run_missing_persons(bot_ctx, channel):
    """Missing Persons search event — trigger-based quest with forest events resolution."""
    import secrets
    import discord
    import time
    from utils.ttrpg.world_state import load_world_state, update_world_state
    from utils.ttrpg.broadcast import log_world_event as _log_world_event, broadcast_world_event

    names = [
        "Jax (Elara's nephew)", 
        "Toby (the blacksmith's apprentice)", 
        "Alice (Maren's sister)", 
        "Lily (the herbalist's daughter)", 
        "Gideon (the bank clerk)"
    ]
    locs = [
        ("whisperwood_edge", "Whisperwood Border"),
        ("whisperwood_deep", "Deep Whisperwood"),
        ("trade_road", "Trade Road"),
        ("aeridor_ruins", "Aeridor Ruins")
    ]
    
    chosen_name = secrets.choice(names)
    chosen_key, chosen_desc = secrets.choice(locs)
    
    wstate = {}
    now = time.time()
    wstate["missing_person_name"] = chosen_name
    wstate["missing_person_loc"] = chosen_key
    wstate["missing_person_expiry"] = now + 24 * 3600
    await update_world_state(lambda state: state.update({
        "missing_person_name": wstate["missing_person_name"],
        "missing_person_loc": wstate["missing_person_loc"],
        "missing_person_expiry": wstate["missing_person_expiry"],
    }))
    
    embed = discord.Embed(
        title="📋 MISSING PERSON NOTICE",
        description=(
            f"**Missing:** {chosen_name}\n"
            f"**Last Seen Heading Toward:** {chosen_desc}\n\n"
            f"Elder Elara has posted a distress notice! {chosen_name} went out gathering and hasn't returned.\n"
            f"Adventurers, **hunt or scout in {chosen_desc}** to search the area and bring them home!"
        ),
        color=0xf39c12
    )
    embed.set_footer(text="Rewards await whoever guides them safely back.")
    await channel.send(embed=embed)
    await _log_world_event(f"🔍 **Missing Persons:** {chosen_name} went missing in {chosen_desc}. Search the location on hunts.")
    log_action(f"Noon Event: Missing Persons ({chosen_name} in {chosen_desc})")


async def run_construct_incursion(bot_ctx, channel):
    """Noon event: Aeridorian constructs push out from the ruins. Same engine combat as village raid."""
    import secrets
    import discord
    import asyncio
    import time
    from utils.ttrpg.character_manager import get_active_town_defenders
    from utils.ttrpg.monster_registry import get as get_monster
    from utils.ttrpg.progression import check_level_up
    from utils.ttrpg.broadcast import log_world_event as _log_world_event, broadcast_world_event
    from utils.ttrpg.world_state import load_world_state, update_world_state
    from utils.ttrpg.dungeon import DUNGEON_THEMES
    from utils.ttrpg.combat_engine import _resolve_combat
    from utils.ttrpg.housing import load_housing
    from utils.ttrpg.pets import get_pet_passive

    TOWN_LOCATIONS = {
        "oakhaven", "stone_hearth", "hemlocks_store",
        "shrine", "watchtower", "oakhaven_bank", "herbalists_hut",
        "housing_district", "tricklebrook_pond"
    }

    # 1. Announce event
    await channel.send(embed=discord.Embed(
        title="🤖 WATCHTOWER INTRUSION",
        description=(
            "*A low metallic hum vibrates through the watchtower walls. From the Aeridor ruins, "
            "orderly ranks of polished brass and crystal-powered automations march forward.*\n\n"
            "The watchtower sentries sound the iron gong. **\"Constructs! Heavy frames! To the gates!\"**"
        ),
        color=0x4183c4
    ))
    await asyncio.sleep(4)

    # 2. Get active town defenders
    defenders = await get_active_town_defenders()

    if not defenders:
        await channel.send(embed=discord.Embed(
            description=(
                "*No adventurers were in town. The watchtower automatic defenses triggered, "
                "repelling the constructs at the cost of depleted power arrays.*\n\n"
                "The brass ranks turned and receded back to the silent ruins."
            ),
            color=0x888888
        ))
        return

    starting_states_by_uid = {
        str(s["user_id"]): {
            "hp": s.get("hp", {}).get("current", 0),
            "conditions": list(s.get("conditions", [])),
        }
        for s in defenders if s.get("user_id")
    }

    # 3. Select constructs theme
    theme_data = DUNGEON_THEMES["constructs"]

    # 4. Compute threat level
    avg_level = sum(s.get("level", 1) for s in defenders) / len(defenders)
    max_level = max(s.get("level", 1) for s in defenders)

    if avg_level >= 13:
        pool_index = 5
    elif avg_level >= 9:
        pool_index = 4
    elif avg_level >= 6:
        pool_index = 3
    elif avg_level >= 3:
        pool_index = 2
    else:
        pool_index = 1

    normal_pool = theme_data["pools"][pool_index]
    boss_pool = theme_data["boss_pools"][pool_index]

    # 5. Build attackers wave — scaled to active defender count
    num_attackers = min(8, max(2, len(defenders)))
    if len(defenders) >= 3:
        num_attackers = min(8, len(defenders) + 1)
    has_boss = (max_level >= 9)
    attackers = []
    total_xp = 0
    total_gil = 0
    
    for i in range(num_attackers):
        if i == 0 and has_boss:
            m_key = secrets.choice(boss_pool)
        else:
            m_key = secrets.choice(normal_pool)

        m_data = get_monster(m_key)
        if m_data:
            m_instance = m_data.copy()
            m_instance["key"] = m_key
            scale = 1.0 + (avg_level - 1) * 0.05
            m_instance["hp"] = max(15, int(m_instance["hp"] * scale))
            m_instance["attack"] = max(3, int(m_instance["attack"] * scale))
            m_instance["defense"] = max(8, int(m_instance["defense"] * scale))
            m_instance["hp"] = {"current": m_instance["hp"], "max": m_instance["hp"]}
            attackers.append(m_instance)
            total_xp += m_data.get("xp", 25)
            total_gil += m_data.get("gil", 10)

    total_xp = int(total_xp * 1.5)
    total_gil = int(total_gil * 1.2)

    creature_names = ", ".join(m["name"] for m in attackers)
    defenders_list = "\n".join(
        f"⚔️ **{s['character_name']}** (Lv.{s['level']} {s['class']})"
        for s in defenders
    )

    await channel.send(embed=discord.Embed(
        title=f"⚔️ Watchtower Defense — Construct Incursion",
        description=(
            f"**Attacking:** {creature_names}\n"
            f"**Defenders in Oakhaven:**\n{defenders_list}\n\n"
            f"*{theme_data['flavor']}*"
        ),
        color=0x4183c4
    ))
    await asyncio.sleep(4)

    # 6. Resolve combat
    combat_results = []
    defeated_monsters_count = 0
    player_defeated_count = 0

    wstate = load_world_state()
    world_atk_mod = wstate.get("atk_mod", 0)
    from utils.ttrpg.town_projects import raid_def_bonus
    world_def_mod = wstate.get("def_mod", 0) + raid_def_bonus(wstate)

    for idx, s in enumerate(defenders):
        attacker = attackers[idx % len(attackers)].copy()

        # Load pet passive bonuses
        housing = load_housing(str(s.get("user_id", "")))
        pet_bonuses = get_pet_passive(housing) if housing else {}

        # Run up to 3 rounds of combat
        rounds_log = []
        won = False
        escaped = False

        for r_idx in range(3):
            if s["hp"]["current"] <= 0 or attacker["hp"]["current"] <= 0:
                break

            res = _resolve_combat(
                s, attacker,
                atk_mod_global=world_atk_mod,
                def_mod_global=world_def_mod,
                pet_bonuses=pet_bonuses
            )

            rounds_log.append({
                "round": r_idx + 1,
                "player_hit": res.get("player_hit", False),
                "player_crit": res.get("player_crit", False),
                "player_fumble": res.get("player_fumble", False),
                "player_damage": res.get("player_damage", 0),
                "monster_hit": res.get("monster_hit", False),
                "monster_damage": res.get("monster_damage", 0),
                "monster_name": attacker["name"],
                "monster_desc": attacker.get("desc", ""),
            })

            if attacker["hp"]["current"] <= 0:
                won = True
                defeated_monsters_count += 1
                break
            if s["hp"]["current"] <= 0:
                player_defeated_count += 1
                break

        combat_results.append((s, attacker, rounds_log, won, escaped))

    # Determine victory
    defenders_won = (defeated_monsters_count >= len(attackers) / 2)

    xp_each = max(1, total_xp // len(defenders))
    gil_each = max(1, total_gil // len(defenders))

    # 7. Apply Consequences & Rewards
    result_lines = []
    level_ups = []
    casualty_count = 0

    for s, monster, rounds_log, won, escaped in combat_results:
        uid = str(s.get("user_id", ""))
        start = starting_states_by_uid.get(uid, {})
        simulated_hp = s.get("hp", {}).get("current", 0)
        consumed_conditions = set(start.get("conditions", [])) - set(s.get("conditions", []))
        reward_xp = 0
        reward_gil = 0
        reputation_delta = 0
        if simulated_hp > 0:
            if defenders_won:
                reward_xp, reward_gil, reputation_delta = xp_each, gil_each, 10
            else:
                reward_xp = max(1, xp_each // 2)
        result = await _commit_background_combat_result(
            uid, starting_hp=start.get("hp", 0), simulated_hp=simulated_hp,
            consumed_conditions=consumed_conditions, xp_reward=reward_xp,
            gil_reward=reward_gil, reputation_delta=reputation_delta,
        )
        if not result:
            continue
        character_name = result["character_name"]
        blackout = result["blackout"]
        if blackout:
            casualty_count += 1
            result_lines.append(
                f"💀 **{character_name}** fell (lost {blackout['xp_loss']} XP, {blackout['gil_loss']} gil)"
            )
            death_embed = discord.Embed(
                title=f"💀 {character_name} fell to constructs",
                description=(
                    f"*{monster['name']} left them at the Shrine threshold. "
                    f"Lost {blackout['xp_loss']} XP and {blackout['gil_loss']} Gil.*"
                ),
                color=0x8B0000,
            )
            death_embed.set_footer(text=f"Death #{result['deaths']}")
            await broadcast_world_event(bot_ctx, death_embed)
        elif simulated_hp <= 0:
            result_lines.append(f"⚔️ **{character_name}** recovered before reaching the Shrine.")
        elif defenders_won:
            result_lines.append(
                f"⚔️ **{character_name}** held the watchtower (received +{reward_xp} XP, +{reward_gil} gil, +10 Rep)"
            )
        else:
            result_lines.append(
                f"⚔️ **{character_name}** fought valiantly to hold the gate (+{reward_xp} XP)"
            )
        if result["leveled"]:
            level_ups.append(f"🎉 **{character_name}** reached **Level {result['new_level']}!**")

    # Apply global updates
    now = time.time()

    def _record_construct_incursion_result(state):
        if defenders_won:
            state.update({
                "event": "constructs_repelled",
                "event_desc": "Oakhaven watchtowers repelled the construct intrusion.",
                "def_mod": 1,
                "def_mod_expiry": now + 24 * 3600,
                "xp_mult": 1.2,
                "xp_mult_expiry": now + 24 * 3600,
            })
        else:
            state.update({
                "event": "constructs_breached",
                "event_desc": "Watchtower defenses breached by Aeridorian automations.",
            })
        return True

    await update_world_state(_record_construct_incursion_result)

    # Broadcast global outcome
    outcome_embed = discord.Embed(
        title=f"🛡️ Watchtower Defense — {'Victory' if defenders_won else 'Defeat'}",
        description=f"The brass phalanx was {'broken and scattered' if defenders_won else 'victorious, cracking the gates before retreating'}.\n\n" + "\n".join(result_lines),
        color=0x2D5A27 if defenders_won else 0x8B0000
    )
    await broadcast_world_event(bot_ctx, outcome_embed)

    if level_ups:
        lvl_embed = discord.Embed(
            title="🎉 Level Ups!",
            description="\n".join(level_ups),
            color=0xffd700
        )
        await channel.send(embed=lvl_embed)

    await _log_world_event(f"🤖 **Construct Incursion** — defenders defended Watchtower: {defenders_won}.")
    log_action("Noon Event: Construct Incursion")

    # Narration via LLM
    try:
        await _narrate_raid_summary(bot_ctx, channel, defenders, attackers, combat_results, defenders_won)
    except Exception as e:
        log_error(f"[construct noon] Narration failed: {e}")





async def run_blight_on_the_crops(bot_ctx, channel):
    """Noon event: Whisperwood blight ruins a crop plot for random house owners."""
    import discord
    import asyncio
    import secrets
    import random
    from utils.ttrpg.housing import load_all_housing_report
    from utils.ttrpg.broadcast import log_world_event as _log_world_event

    await channel.send(embed=discord.Embed(
        title="🥀 Whisperwood Blight",
        description=(
            "*A grey mist creeps out from the forest edge, carrying a sour scent of mold.*\n\n"
            "Farmers in the Oakhaven housing district notice leaves yellowing and roots softening. "
            "The sward blight has infected the soil tonight."
        ),
        color=0x7f8c8d
    ))
    await asyncio.sleep(3)

    # Housing snapshots are for candidate discovery only. Each selected owner
    # is reloaded under their user-action lock before a plot is changed.
    housing_scan = load_all_housing_report()
    candidate_ids = list(dict.fromkeys(
        str(h.get("user_id")) for h in housing_scan.records
        if h.get("user_id") and h.get("farming", {}).get("plots")
    ))
    if housing_scan.failures:
        log_warning(
            f"[blight] Skipping {len(housing_scan.failures)} unreadable housing record(s); "
            "see the RPG storage scan warning for exact paths."
        )
    if not candidate_ids:
        await channel.send(embed=discord.Embed(
            description="*The mist dissipated harmlessly. No active fields or crops were in use in the housing district.*",
            color=0x888888
        ))
        return

    affected_ids = random.sample(candidate_ids, min(3, len(candidate_ids)))
    result_lines = []
    from utils.ttrpg.farming import CROPS
    for uid in affected_ids:
        def infect_one_plot(housing):
            plots = housing.get("farming", {}).get("plots", [])
            if not plots:
                return None
            index = secrets.randbelow(len(plots))
            plots[index]["blighted"] = True
            crop_data = CROPS.get(plots[index].get("crop_key"), {})
            return (
                housing.get("character_name", "Unknown"),
                crop_data.get("name", "crop"),
            )

        result = await _mutate_player_housing(uid, infect_one_plot)
        if result:
            char_name, crop_name = result
            result_lines.append(
                f"🥀 **{char_name}**'s plot of **{crop_name}** has been infected with blight!"
            )

    if not result_lines:
        await channel.send(embed=discord.Embed(
            description="*The mist dissipated after all active fields had been tended.*",
            color=0x888888
        ))
        return

    await channel.send(embed=discord.Embed(
        title="🥀 Blight Infection Report",
        description="\n".join(result_lines) + "\n\n*Affected homeowners must treat their soil with herbal medicine (`!rpg farm treat`) using a healing herb or tonic to save the harvest!*",
        color=0x7f8c8d
    ))
    await _log_world_event("🥀 **Whisperwood Blight** sours Oakhaven soil. Several crops in the housing district were lost.")
    log_action("Noon Event: Blight on Crops")
async def run_pilgrims_arrive(bot_ctx, channel):
    """Noon event: Pilgrims arrive at the Shrine, granting a blessing window in world_state."""
    import discord
    import asyncio
    import time
    from utils.ttrpg.character_manager import load_all
    from utils.ttrpg.broadcast import log_world_event as _log_world_event
    from utils.ttrpg.world_state import load_world_state, update_world_state

    town_locations = {
        "oakhaven", "stone_hearth", "hemlocks_store",
        "shrine", "watchtower", "oakhaven_bank", "herbalists_hut",
        "housing_district", "tricklebrook_pond"
    }

    await channel.send(embed=discord.Embed(
        title="🕯️ Procession of Pilgrims",
        description=(
            "*A quiet procession enters the eastern gates. Clad in grey wool robes, they carry holy oils "
            "and Morvenna's relics to the Shrine of the Silent Ones.*\n\n"
            "Fragrant incense fills the square. The air becomes warm and still."
        ),
        color=0x9b59b6
    ))
    await asyncio.sleep(3)

    candidate_ids = list(dict.fromkeys(
        str(s.get("user_id")) for s in await load_all()
        if s.get("user_id") and s.get("location") in town_locations
    ))
    if not candidate_ids:
        await channel.send(embed=discord.Embed(
            description="*The pilgrims prayed at the empty shrine and proceeded north, leaving a quiet aura in the air.*",
            color=0x888888
        ))
        return

    result_lines = []
    for uid in candidate_ids:
        def apply(sheet):
            if sheet.get("location") not in town_locations:
                return None
            hp = sheet.setdefault("hp", {})
            hp["current"] = min(hp.get("max", 1), hp.get("current", 0) + 10)
            if "blessed" not in sheet.setdefault("conditions", []):
                sheet["conditions"].append("blessed")
            return sheet.get("character_name", "An adventurer")

        character_name = await _mutate_player_sheet(uid, apply)
        if character_name:
            result_lines.append(f"✨ **{character_name}** was restored (+10 HP, **Blessed**)")

    if not result_lines:
        await channel.send(embed=discord.Embed(
            description="*The pilgrims arrived after everyone had left the square.*",
            color=0x888888
        ))
        return

    # Set temporary world_state pilgrim_blessing_until; the player-sheet
    # mutations above have already been committed under their own locks.
    wstate = {}
    wstate["pilgrim_blessing_until"] = time.time() + 24 * 3600
    await update_world_state(lambda state: state.update({
        "pilgrim_blessing_until": wstate["pilgrim_blessing_until"],
    }))

    await channel.send(embed=discord.Embed(
        title="✨ Pilgrims' Blessing Received",
        description="\n".join(result_lines) + "\n\n*Morvenna's presence lingers at the Shrine. Praying or offering today yields enhanced protection.*",
        color=0x9b59b6
    ))
    await _log_world_event("🕯️ **Pilgrims Arrive** — Morvenna's relics brought to the Shrine, blessing those present in Oakhaven.")
    log_action("Noon Event: Pilgrims Arrive")

async def run_night_terror_warning(bot_ctx, channel):
    """Noon event: A warning about dangerous beasts shifting solo hunts to a harder tier."""
    import discord
    import time
    from utils.ttrpg.broadcast import log_world_event as _log_world_event
    from utils.ttrpg.world_state import load_world_state, update_world_state

    await channel.send(embed=discord.Embed(
        title="👁️ Night Terror Warning",
        description=(
            "**⚠️ WARNING: HIGHER THREAT LEVELS DETECTED TONIGHT**\n\n"
            "*Watchtower sentries report a massive shadow beast moving through the Whisperwood tree lines.*\n\n"
            "Elara issues a warning to all hunters: **\"Tonight, the forest is not for the faint of heart. "
            "Monsters are shifting closer. Be on your guard.\"**"
        ),
        color=0x962d2d
    ))

    # Write a temporary flag into world_state
    wstate = {}
    wstate["encounter_mod"] = {"tier_shift": 1}
    wstate["encounter_mod_expiry"] = time.time() + 24 * 3600  # 24 hours
    await update_world_state(lambda state: state.update({
        "encounter_mod": wstate["encounter_mod"],
        "encounter_mod_expiry": wstate["encounter_mod_expiry"],
    }))

    await _log_world_event("👁️ **Night Terror Warning** — watchtowers report shadow beast movement. Solo hunts will encounter higher tier threats until the next noon event.")
    log_action("Noon Event: Night Terror Warning")


async def run_ironclad_envoys(bot_ctx, channel):
    """Noon event: Ironclad Guild Envoys Arrive. markup prices for 4 hours."""
    import discord
    import time
    from utils.ttrpg.world_state import load_world_state, update_world_state
    from utils.ttrpg.broadcast import log_world_event as _log_world_event

    wstate = {}
    wstate["shop_price_mult"] = 1.15
    wstate["shop_price_mult_expiry"] = time.time() + 24 * 3600
    await update_world_state(lambda state: state.update({
        "shop_price_mult": wstate["shop_price_mult"],
        "shop_price_mult_expiry": wstate["shop_price_mult_expiry"],
    }))

    await channel.send(embed=discord.Embed(
        title="⚙️ Ironclad Guild Envoys Arrive",
        description=(
            "**📋 NOTICE: EXPORT SURCHARGE IN EFFECT**\n\n"
            "*A heavy iron-rimmed wagon halts in the square. Men bearing the seal of the Ironclad Guild "
            "begin inspecting Pells and Hemlocks inventories.*\n\n"
            "Due to guild buying pressure and exports, Hemlock's store and Trade Road Caravan prices "
            "are **inflated by 15%** until the next noon event."
        ),
        color=0x7f8c8d
    ))
    await _log_world_event("⚙️ **Guild Envoys** — Ironclad envoys arrived in Oakhaven; shop prices increased by 15% until the next noon event.")
    log_action("Noon Event: Ironclad Guild Envoys")


async def run_silverstream_blackwater(bot_ctx, channel):
    """Noon event: The Silverstream Runs Black."""
    import discord
    import time
    from utils.ttrpg.world_state import load_world_state, update_world_state
    from utils.ttrpg.broadcast import log_world_event as _log_world_event

    wstate = {}
    wstate["fishing_water_tainted"] = True
    wstate["fishing_water_tainted_expiry"] = time.time() + 24 * 3600
    await update_world_state(lambda state: state.update({
        "fishing_water_tainted": wstate["fishing_water_tainted"],
        "fishing_water_tainted_expiry": wstate["fishing_water_tainted_expiry"],
    }))

    await channel.send(embed=discord.Embed(
        title="🌊 The Silverstream Runs Black",
        description=(
            "**⚠️ WARNING: RIVER WATER TAINTED**\n\n"
            "*A dark, viscous fluid has begun to mix with the headwaters of the Silverstream. "
            "Tricklebrook Pond turns murky, and the fish behave erratically.*\n\n"
            "Tricklebrook Pond waters are tainted until the next noon event. Fishing is dangerous."
        ),
        color=0x2c3e50
    ))
    await _log_world_event("🌊 **Silverstream Murk** — Silverstream headwaters ran black; Tricklebrook Pond waters are tainted until the next noon event.")
    log_action("Noon Event: Silverstream Blackwater")


async def run_hooded_figures_vigil(bot_ctx, channel):
    """Noon event: The Hooded Figure's Vigil."""
    import discord
    from utils.ttrpg.character_manager import load_all
    from utils.ttrpg.broadcast import log_world_event as _log_world_event

    await channel.send(embed=discord.Embed(
        title="🌘 The Hooded Figure's Vigil",
        description=(
            "*The cloaked stranger at the Stone Hearth sits unusually still today, staring intensely into the hearth fire.*\n\n"
            "A heavy silence hangs over the tavern. Those present feel a cold shadow of watchfulness pass over them."
        ),
        color=0x2c3e50
    ))

    candidate_ids = list(dict.fromkeys(
        str(s.get("user_id")) for s in await load_all()
        if s.get("user_id") and s.get("location") == "stone_hearth"
    ))
    if not candidate_ids:
        await channel.send(embed=discord.Embed(
            description="*The tavern was empty. The figure sat alone in the dim light.*",
            color=0x888888
        ))
        return

    result_lines = []
    for uid in candidate_ids:
        def apply(sheet):
            if sheet.get("location") != "stone_hearth":
                return None
            sheet.setdefault("conditions", [])
            if "veiled_watched" not in sheet["conditions"]:
                sheet["conditions"].append("veiled_watched")
            return sheet.get("character_name", "An adventurer")

        character_name = await _mutate_player_sheet(uid, apply)
        if character_name:
            result_lines.append(f"🌘 **{character_name}** — *Veiled Watched (+1 to next roll)*")

    if not result_lines:
        await channel.send(embed=discord.Embed(
            description="*The tavern emptied before the vigil could mark anyone.*",
            color=0x888888
        ))
        return

    await channel.send(embed=discord.Embed(
        title="🌘 Marked by the Vigil",
        description="\n".join(result_lines),
        color=0x2c3e50
    ))
    await _log_world_event("🌘 **Hooded Figure Vigil** — The stranger marked Stone Hearth patrons with a watchful gaze.")
    log_action("Noon Event: Hooded Figures Vigil")

async def run_caelindras_lost_verse(bot_ctx, channel):
    """Noon event: Caelindra's Lost Verse."""
    import discord
    from utils.ttrpg.character_manager import load_all
    from utils.ttrpg.progression import check_level_up
    from utils.ttrpg.broadcast import log_world_event as _log_world_event

    await channel.send(embed=discord.Embed(
        title="📜 Caelindra's Lost Verse",
        description=(
            "*Caelindra stops her usual ballad. She looks at a page she hasn't read aloud before, "
            "clears her throat, and recites:*\n\n"
            "\"Three crowns in the deep stone, two rings in the blue,\n"
            "The forest remembers what time withdrew.\n"
            "The gate in the shadow is waiting for you.\"\n\n"
            "*A quiet shiver passes through the room.*"
        ),
        color=0x8e44ad
    ))

    candidate_ids = list(dict.fromkeys(
        str(s.get("user_id")) for s in await load_all()
        if s.get("user_id") and s.get("location") == "stone_hearth"
    ))
    if not candidate_ids:
        return

    result_lines = []
    level_ups = []
    for uid in candidate_ids:
        def apply(sheet):
            if sheet.get("location") != "stone_hearth":
                return None
            sheet["xp"] = sheet.get("xp", 0) + 15
            leveled, new_level = check_level_up(sheet)
            return sheet.get("character_name", "An adventurer"), leveled, new_level

        result = await _mutate_player_sheet(uid, apply)
        if not result:
            continue
        character_name, leveled, new_level = result
        result_lines.append(f"📜 **{character_name}** — *Heard the Verse* (+15 XP)")
        if leveled:
            level_ups.append(f"🎉 **{character_name}** reached **Level {new_level}!**")

    if not result_lines:
        return

    embed = discord.Embed(title="📜 A Quiet Understanding", description="\n".join(result_lines), color=0x8e44ad)
    if level_ups:
        embed.add_field(name="\u200b", value="\n".join(level_ups), inline=False)
    await channel.send(embed=embed)
    await _log_world_event("📜 **Caelindra's Verse** — The bard recited a lost Aeridorian verse at the Stone Hearth.")
    log_action("Noon Event: Caelindra's Lost Verse")

async def run_watchtower_silence(bot_ctx, channel):
    """Noon event: The Watchtower's Silence."""
    import discord
    import time
    from utils.ttrpg.world_state import load_world_state, update_world_state
    from utils.ttrpg.broadcast import log_world_event as _log_world_event

    wstate = {}
    wstate["watchtower_bonus"] = True
    wstate["watchtower_bonus_expiry"] = time.time() + 24 * 3600
    await update_world_state(lambda state: state.update({
        "watchtower_bonus": wstate["watchtower_bonus"],
        "watchtower_bonus_expiry": wstate["watchtower_bonus_expiry"],
    }))

    await channel.send(embed=discord.Embed(
        title="🔭 The Watchtower's Silence",
        description=(
            "*The watchtower guards are dead silent today, pacing the battlements in pairs. "
            "They won't explain why, but they are sharing their spyglass logs with any scout who asks.*\n\n"
            "Scouts visiting the Watchtower get extra scouting detail until the next noon event."
        ),
        color=0x2980b9
    ))
    await _log_world_event("🔭 **Watchtower Silence** — Sentries are unusually vigilant; scouting reports enhanced until the next noon event.")
    log_action("Noon Event: Watchtower Silence")


async def run_silvani_antidote_run(bot_ctx, channel):
    """Noon event: Silvani Antidote Run."""
    import discord
    from utils.ttrpg.character_manager import load_all
    from utils.ttrpg.broadcast import log_world_event as _log_world_event

    town_locations = {
        "oakhaven", "stone_hearth", "hemlocks_store",
        "shrine", "watchtower", "oakhaven_bank", "herbalists_hut",
        "housing_district", "tricklebrook_pond"
    }

    await channel.send(embed=discord.Embed(
        title="🧪 Silvani Supplies Dropped",
        description=(
            "*A cloaked Silvani hunter dashes through Oakhaven, dropping canvas bundles onto shop counters "
            "and tavern tables before vanishing back into the treeline.*\n\n"
            "Each adventurer present in town receives a free bandage."
        ),
        color=0x27ae60
    ))

    candidate_ids = list(dict.fromkeys(
        str(s.get("user_id")) for s in await load_all()
        if s.get("user_id") and s.get("location") in town_locations
    ))
    if not candidate_ids:
        await channel.send(embed=discord.Embed(
            description="*No adventurers were present in town to collect the bundle. The guard stored it.*",
            color=0x888888
        ))
        return

    from utils.ttrpg.inventory_capacity import grant_item_or_mail
    result_lines = []
    for uid in candidate_ids:
        def apply(sheet):
            if sheet.get("location") not in town_locations:
                return None
            delivery = grant_item_or_mail(sheet, "bandage", "Silvani Supplies")
            return sheet.get("character_name", "An adventurer"), delivery

        result = await _mutate_player_sheet(uid, apply)
        if not result:
            continue
        character_name, delivery = result
        if delivery == "inventory":
            result_lines.append(f"🧪 **{character_name}** — *Acquired: Bandage*")
        else:
            result_lines.append(f"📬 **{character_name}** — *Bandage sent to Moogle Mail (inventory full)*")

    if not result_lines:
        await channel.send(embed=discord.Embed(
            description="*No adventurers remained in town to receive the bundle.*",
            color=0x888888
        ))
        return

    await channel.send(embed=discord.Embed(
        title="🧪 Supplies Distributed",
        description="\n".join(result_lines),
        color=0x27ae60
    ))
    await _log_world_event("🧪 **Silvani Drop** — A Silvani hunter left emergency bandages for town residents.")
    log_action("Noon Event: Silvani Antidote Run")

async def run_iron_magpies_heist(bot_ctx, channel):
    """Noon event: The Iron Magpies Bank Heist scaled combat event."""
    import secrets
    import discord
    import asyncio
    import time
    from utils.ttrpg.character_manager import get_active_town_defenders
    from utils.ttrpg.monster_registry import get as get_monster
    from utils.ttrpg.progression import check_level_up
    from utils.ttrpg.broadcast import log_world_event as _log_world_event, broadcast_world_event
    from utils.ttrpg.world_state import load_world_state, update_world_state
    from utils.ttrpg.combat_engine import _resolve_combat
    from utils.ttrpg.housing import load_housing
    from utils.ttrpg.pets import get_pet_passive

    THIEVES = [
        {
            "key": "darek_shadow_bound",
            "name": "Darek Shadow-Bound",
            "title": "Master Infiltrator",
            "desc": "A legendary vault infiltrator and master thief of the Iron Magpies clad in muffled midnight silk, armed with poisoned stilettos and bulging sacks of stolen Gil.",
            "intro": "A hooded figure clad in muffled midnight silk—**Darek Shadow-Bound**—is prying open the reinforced deposit lockboxes!",
        },
        {
            "key": "garrett_vault_creeper",
            "name": "Garrett the Vault-Creeper",
            "title": "Guild Lockpicker",
            "desc": "A wiry, ceiling-crawling lockpicker from the Iron Magpies, draped in dark oilskin and bristling with skeleton keys and smoke bombs.",
            "intro": "A wiry figure clinging to the vault ceiling—**Garrett the Vault-Creeper**—is dropping smoke bombs and stuffing enchanted lockboxes into a sack!",
        },
        {
            "key": "felix_ghost_hand",
            "name": 'Felix "Ghost-Hand" Pryce',
            "title": "Phantom Cutpurse",
            "desc": 'The infamous phantom cutpurse of the Iron Magpies, moving soundlessly through vault shadows with enchanted picks and twin concealed daggers.',
            "intro": 'A soundless shadow flickers between the safety deposit vaults—**Felix "Ghost-Hand" Pryce**—slipping gilded coins into an extradimensional pouch!',
        },
    ]
    thief = secrets.choice(THIEVES)

    await channel.send(embed=discord.Embed(
        title="🕳️ BANK ALARM — VAULT BREACH",
        description=(
            f"*A metallic scratching and clinking echoes from the bank vaults! {thief['intro']}*\n\n"
            f"**\"The Iron Magpies have breached the vault!\"** the clerk screams. **\"Stop {thief['name']} before our deposits are emptied!\"**"
        ),
        color=0xd35400
    ))
    await asyncio.sleep(3)

    defenders = await get_active_town_defenders()
    
    if not defenders:
        # Penalty: steal 5% of bank gil from characters active in the last
        # 48 hours (true percentage sink). It took from every sheet, so an
        # undefended heist emptied the accounts of players who weren't there.
        # Activity is the player's own: the sheet's last_updated is refreshed
        # by this very save, so the robbed stayed eligible to be robbed.
        import time as _time
        from utils.ttrpg.character_manager import active_since
        _active = await asyncio.to_thread(active_since, _time.time() - 48 * 3600)
        stolen_details = []
        for uid in sorted(_active):
            def apply_bank_loss(sheet):
                balance = sheet.get("bank_balance", 0)
                if balance <= 0:
                    return None
                stolen = max(1, int(balance * 0.05))
                sheet["bank_balance"] = max(0, balance - stolen)
                return sheet.get("character_name", f"User {uid}"), stolen

            bank_loss = await _mutate_player_sheet(uid, apply_bank_loss)
            if bank_loss:
                character_name, stolen = bank_loss
                stolen_details.append(f"🏦 **{character_name}**: -{stolen} Gil")
        
        desc = f"*No adventurers responded to the alarm. {thief['name']} of the Iron Magpies cleaned out the vault and vanished into the shadows.*\n\n"
        if stolen_details:
            desc += "**Stolen Bank Balances (5% Heist Loss):**\n" + "\n".join(stolen_details)
        else:
            desc += "Fortunately, the vaults were empty."
            
        await channel.send(embed=discord.Embed(description=desc, color=0xcc4444))
        await _log_world_event(f"❌ **Bank Robbed** — {thief['name']} of the Iron Magpies broke into the vaults and stole Gil deposits.")
        log_action(f"Noon Event: Iron Magpies Bank Heist ({thief['name']} - Undefended)")
        return


    starting_states_by_uid = {
        str(s["user_id"]): {
            "hp": s.get("hp", {}).get("current", 0),
            "conditions": list(s.get("conditions", [])),
        }
        for s in defenders if s.get("user_id")
    }

    # Combat setup
    avg_level = sum(s.get("level", 1) for s in defenders) / len(defenders)
    max_level = max(s.get("level", 1) for s in defenders)
    
    # Scale boss stats: tuned for ~60-75% defender success rate with pooled group combat
    scale = 1.0 + (avg_level - 1) * 0.04
    party_scale = 1.0 + (len(defenders) - 1) * 0.40
    boss_hp = max(35, int(45 * scale * party_scale))
    boss_atk = max(4, min(13, int(6 + avg_level * 0.35)))
    boss_def = max(6, min(10, int(6 + avg_level * 0.20)))

    boss = {
        "key": thief["key"],
        "name": thief["name"],
        "hp": {"current": boss_hp, "max": boss_hp},
        "attack": boss_atk,
        "defense": boss_def,
        "xp": 600,
        "gil": 350,
        "tier": "boss",
        "desc": thief["desc"]
    }
        
    total_xp = 160 + int(avg_level * 16) * len(defenders)
    total_gil = 110 + int(avg_level * 12) * len(defenders)
    
    defenders_list = "\n".join(f"⚔️ **{s['character_name']}** (Lv.{s['level']} {s.get('class', 'Adventurer')})" for s in defenders)
    
    await channel.send(embed=discord.Embed(
        title="⚔️ Bank Defense — Repel the Iron Magpies",
        description=f"**Attacking:** {boss['name']} ({thief['title']})\n**Defenders:**\n{defenders_list}",
        color=0xd35400
    ))
    await asyncio.sleep(4)

    wstate = load_world_state()
    world_atk_mod = wstate.get("atk_mod", 0)
    from utils.ttrpg.town_projects import raid_def_bonus
    world_def_mod = wstate.get("def_mod", 0) + raid_def_bonus(wstate)
    
    # ── Pooled Party Combat (All defenders focus single thief entity) ──
    max_rounds = 5
    for round_num in range(max_rounds):
        if boss["hp"]["current"] <= 0:
            break
        living_defenders = [s for s in defenders if s.get("hp", {}).get("current", 0) > 0]
        if not living_defenders:
            break
        for s in living_defenders:
            if boss["hp"]["current"] <= 0:
                break
            housing = load_housing(str(s.get("user_id", "")))
            pet_bonuses = get_pet_passive(housing) if housing else {}
            _resolve_combat(
                s, boss,
                atk_mod_global=world_atk_mod,
                def_mod_global=world_def_mod,
                pet_bonuses=pet_bonuses
            )

    defenders_won = (boss["hp"]["current"] <= 0)
    xp_each = max(10, total_xp // len(defenders))
    gil_each = max(10, total_gil // len(defenders))
    
    result_lines = []
    level_ups = []
    
    if defenders_won:
        for s in defenders:
            uid = str(s.get("user_id", ""))
            start = starting_states_by_uid.get(uid, {})
            simulated_hp = s.get("hp", {}).get("current", 0)
            consumed_conditions = set(start.get("conditions", [])) - set(s.get("conditions", []))
            result = await _commit_background_combat_result(
                uid,
                starting_hp=start.get("hp", 0),
                simulated_hp=simulated_hp,
                consumed_conditions=consumed_conditions,
                xp_reward=xp_each if simulated_hp > 0 else 0,
                gil_reward=gil_each if simulated_hp > 0 else 0,
                knockout_xp_reward=xp_each // 2 if simulated_hp <= 0 else 0,
                knockout_gil_reward=gil_each // 2 if simulated_hp <= 0 else 0,
            )
            if not result:
                continue
            character_name = result["character_name"]
            if result["blackout"]:
                result_lines.append(
                    f"💀 **{character_name}** was knocked out, but the team prevailed! "
                    f"(lost {result['blackout']['xp_loss']} XP, {result['blackout']['gil_loss']}g)"
                )
            elif result["knockout_applied"]:
                result_lines.append(
                    f"💀 **{character_name}** was knocked out, but the team prevailed! "
                    f"(+{xp_each // 2} XP, +{gil_each // 2}g)"
                )
            elif simulated_hp <= 0:
                result_lines.append(
                    f"⚔️ **{character_name}** recovered during the defense and remained standing."
                )
            else:
                result_lines.append(
                    f"⚔️ **{character_name}** helped subdue {thief['name']} and secured the vaults! "
                    f"(+{xp_each} XP, +{gil_each}g)"
                )
            if result["leveled"]:
                level_ups.append(f"🎉 **{character_name}** reached **Level {result['new_level']}!**")
    else:
        # The loss applies to active players' current bank balances, not
        # detached load_all() snapshots.
        import time as _time
        from utils.ttrpg.character_manager import active_since
        active_ids = await asyncio.to_thread(active_since, _time.time() - 48 * 3600)
        stolen_details = []
        for uid in sorted(active_ids):
            def apply_bank_loss(sheet):
                balance = sheet.get("bank_balance", 0)
                if balance <= 0:
                    return None
                stolen = max(1, int(balance * 0.05))
                sheet["bank_balance"] = max(0, balance - stolen)
                return sheet.get("character_name", f"User {uid}"), stolen

            bank_loss = await _mutate_player_sheet(uid, apply_bank_loss)
            if bank_loss:
                character_name, stolen = bank_loss
                stolen_details.append(f"🏦 **{character_name}**: -{stolen} Gil")

        for s in defenders:
            uid = str(s.get("user_id", ""))
            start = starting_states_by_uid.get(uid, {})
            simulated_hp = s.get("hp", {}).get("current", 0)
            consumed_conditions = set(start.get("conditions", [])) - set(s.get("conditions", []))
            result = await _commit_background_combat_result(
                uid,
                starting_hp=start.get("hp", 0),
                simulated_hp=simulated_hp,
                consumed_conditions=consumed_conditions,
            )
            if not result:
                continue
            character_name = result["character_name"]
            if result["blackout"]:
                result_lines.append(
                    f"💀 **{character_name}** was knocked out defending the bank "
                    f"(lost {result['blackout']['xp_loss']} XP, {result['blackout']['gil_loss']} Gil)."
                )
            elif simulated_hp <= 0:
                result_lines.append(
                    f"🛡️ **{character_name}** recovered during the defense and remained standing."
                )
            else:
                result_lines.append(
                    f"🛡️ **{character_name}** survived, but {thief['name']} overpowered the defense and escaped with the loot."
                )
        if stolen_details:
            result_lines.append("\\n**Stolen Bank Balances (5% Vault Heist Loss):**\\n" + "\\n".join(stolen_details))

    embed = discord.Embed(
        title="🕳️ Bank Defense Outcome",
        description="\n".join(result_lines),
        color=0x27ae60 if defenders_won else 0xcc4444
    )
    if level_ups:
        embed.add_field(name="\u200b", value="\n".join(level_ups), inline=False)
    await channel.send(embed=embed)
    
    outcome_txt = f"Bank Secured — {thief['name']} subdued" if defenders_won else f"{thief['name']} escaped with vault loot"
    await _log_world_event(f"🛡️ **Bank Defense:** {outcome_txt}.")
    log_action(f"Noon Event: Iron Magpies Bank Heist ({thief['name']} - {'Won' if defenders_won else 'Lost'})")


run_the_coin_hoarder = run_iron_magpies_heist


async def run_boundary_shift(bot_ctx, channel):
    """Noon event: Whisperwood Boundary Shift."""
    import discord
    import time
    from utils.ttrpg.world_state import load_world_state, update_world_state
    from utils.ttrpg.broadcast import log_world_event as _log_world_event, broadcast_world_event

    wstate = {}
    wstate["encounter_mod"] = {"tier_shift": 1}
    wstate["encounter_mod_expiry"] = time.time() + 24 * 3600
    await update_world_state(lambda state: state.update({
        "encounter_mod": wstate["encounter_mod"],
        "encounter_mod_expiry": wstate["encounter_mod_expiry"],
    }))

    await channel.send(embed=discord.Embed(
        title="🍃 Whisperwood Boundary Shift",
        description=(
            "**⚠️ WARNING: FOREST BOUNDARY DETECTED CLOSER**\n\n"
            "*The ancient border stakes are found twelve feet inside the overworld borders this morning. "
            "The forest edges are creeping, breathing, and pushing closer to Oakhaven.*\n\n"
            "Until the next noon event, solo hunts on the Whisperwood Edge encounter higher tier threats."
        ),
        color=0x27ae60
    ))
    await _log_world_event("🍃 **Boundary Shift** — Whisperwood boundary shifted twelve feet; Edge hunts shifted +1 tier until the next noon event.")
    log_action("Noon Event: Boundary Shift")


async def run_sealed_wax_jar(bot_ctx, channel):
    """Noon event: The Sealed Wax Jar."""
    import discord
    import time
    from utils.ttrpg.world_state import load_world_state, update_world_state
    from utils.ttrpg.broadcast import log_world_event as _log_world_event, broadcast_world_event

    wstate = {}
    wstate["special_item_sale"] = {"item": "lucky_charm", "price": 20}
    wstate["special_item_sale_expiry"] = time.time() + 24 * 3600
    await update_world_state(lambda state: state.update({
        "special_item_sale": wstate["special_item_sale"],
        "special_item_sale_expiry": wstate["special_item_sale_expiry"],
    }))

    # Post-save verification — catch persistence failures immediately
    verify = load_world_state()
    sale_data = verify.get("special_item_sale", {})
    sale_expiry = verify.get("special_item_sale_expiry", 0)
    if sale_data.get("item") == "lucky_charm" and sale_expiry > 0:
        log_info(f"[sealed-wax-jar] ✅ World state verified: special_item_sale={sale_data}, expiry={sale_expiry:.0f}")
    else:
        log_warning(f"[sealed-wax-jar] ❌ PERSISTENCE FAILURE: special_item_sale={sale_data}, expiry={sale_expiry}, full_keys={sorted(verify.keys())}")

    await channel.send(embed=discord.Embed(
        title="🫙 The Sealed Wax Jar",
        description=(
            "**📋 NOTICE: SPECIAL MERCHANDISE OFFER**\n\n"
            "*Hemlock climbs up his top shelf and takes down a dark jar sealed in thick grey wax. "
            "He breaks it open, exposing small lucky charms that shine with ancient warding.*\n\n"
            "Hemlock is selling Lucky Charms for only **20 Gil** (discounted from 40) until the next noon event."
        ),
        color=0xd35400
    ))
    await _log_world_event("🫙 **Sealed Jar** — Hemlock opened the sealed wax jar, offering Lucky Charms at 20 Gil until the next noon event.")
    log_action("Noon Event: Sealed Wax Jar")


async def run_elaras_private_ritual(bot_ctx, channel):
    """Noon event: Elara's Private Ritual."""
    import discord
    from utils.ttrpg.character_manager import load_all
    from utils.ttrpg.progression import check_level_up
    from utils.ttrpg.broadcast import log_world_event as _log_world_event

    await channel.send(embed=discord.Embed(
        title="🌙 Elara's Private Ritual",
        description=(
            "*Elder Elara stands before the Shrine flame, murmuring words that carry no echo, "
            "sprinkling a dark powder over the basins. Sensing your presence, she stops, "
            "covers the dish, and turns to you with a cold, level stare.*\n\n"
            "Oakhaven residents witness the quiet ritual and gain minor insight."
        ),
        color=0x9b59b6
    ))

    town_locations = {
        "oakhaven", "stone_hearth", "hemlocks_store",
        "shrine", "watchtower", "oakhaven_bank", "herbalists_hut",
        "housing_district", "tricklebrook_pond"
    }

    candidate_ids = list(dict.fromkeys(
        str(s.get("user_id")) for s in await load_all()
        if s.get("user_id") and s.get("location") in town_locations
    ))
    if not candidate_ids:
        return

    result_lines = []
    level_ups = []
    for uid in candidate_ids:
        def apply(sheet):
            if sheet.get("location") not in town_locations:
                return None
            sheet["xp"] = sheet.get("xp", 0) + 10
            leveled, new_level = check_level_up(sheet)
            return sheet.get("character_name", "An adventurer"), leveled, new_level

        result = await _mutate_player_sheet(uid, apply)
        if not result:
            continue
        character_name, leveled, new_level = result
        result_lines.append(f"🌙 **{character_name}** — *Witnessed the Ritual* (+10 XP)")
        if leveled:
            level_ups.append(f"🎉 **{character_name}** reached **Level {new_level}!**")

    if not result_lines:
        return
    embed = discord.Embed(title="🌙 A Quiet Connection", description="\n".join(result_lines), color=0x9b59b6)
    if level_ups:
        embed.add_field(name="\u200b", value="\n".join(level_ups), inline=False)
    await channel.send(embed=embed)
    await _log_world_event("🌙 **Elara's Ritual** — Elder Elara performed a private ritual at the Shrine, witnessed by town dwellers.")
    log_action("Noon Event: Elara's Private Ritual")

