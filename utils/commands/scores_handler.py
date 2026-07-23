"""
Kaia Chatbot Memory & Cognitive Scores Handler
===============================================

Aggregates stats and leaderboards from Kaia's chatbot memory layers:
- User relationship affinity ranks & familiarity stages (memory/bot_state.json & memory/relationships/*.json)
- Active belief store & revision records (memory/beliefs.json)
- Episodic memory anchors & salience (memory/anchors.json)
- System operational statistics & emotional vector (memory/stats.json, mood_state.json, bot_state.json)

Displays a high-tech, gamified Discord Embed window with interactive category selection dropdowns.
"""

import os
import json
import asyncio
import time
from typing import List, Dict, Any
import discord
from discord.ui import View, Select

from utils.infrastructure.logging.kaia_logger import log_info, log_error, log_debug


def _tech_bar(current: float, maximum: float, length: int = 10) -> str:
    """Returns a sleek, high-tech unicode progress bar for Discord embeds."""
    if maximum <= 0:
        return "▱" * length
    pct = max(0.0, min(1.0, current / maximum))
    filled = int(round(pct * length))
    return "▰" * filled + "▱" * (length - filled)


def _get_stage_badge(fam: float) -> str:
    """Determine human-readable relationship stage from familiarity score."""
    if fam >= 0.85:
        return "👑 `Inner Circle`"
    elif fam >= 0.65:
        return "🛡️ `Confidant`"
    elif fam >= 0.40:
        return "🗡️ `Familiar`"
    elif fam >= 0.15:
        return "📜 `Acquaintance`"
    else:
        return "👤 `Stranger`"


def _gather_affinity_ranks() -> List[Dict[str, Any]]:
    """Pull user relationship profiles from memory/bot_state.json and memory/relationships/."""
    affinities = []
    
    # 1. Primary Source: memory/bot_state.json
    bot_state_path = os.path.join("memory", "bot_state.json")
    if os.path.exists(bot_state_path) and os.path.getsize(bot_state_path) > 0:
        try:
            with open(bot_state_path, 'r', encoding='utf-8') as f:
                state_data = json.load(f)
            
            raw_rels = state_data.get("relationships", {})
            for uid, rel in raw_rels.items():
                if not isinstance(rel, dict):
                    continue
                
                name = rel.get("display_name") or rel.get("user_name") or f"User {uid}"
                fam = float(rel.get("familiarity", 0.0))
                msg_count = int(rel.get("interaction_count", 0))
                stage = _get_stage_badge(fam)
                last_seen = float(rel.get("last_seen", 0.0))
                valence = float(rel.get("emotional_valence", 0.5))

                # Count detailed events from memory/relationships/{uid}.json
                event_count = 0
                rel_file = os.path.join("memory", "relationships", f"{uid}.json")
                if os.path.exists(rel_file):
                    try:
                        with open(rel_file, 'r', encoding='utf-8') as rf:
                            raw_events = json.load(rf)
                            if isinstance(raw_events, list):
                                event_count = len(raw_events)
                    except Exception:
                        pass

                affinities.append({
                    "user_id": uid,
                    "user_name": name,
                    "familiarity": fam,
                    "stage": stage,
                    "messages": msg_count,
                    "events_count": event_count,
                    "last_seen": last_seen,
                    "valence": valence
                })
        except Exception as e:
            log_error(f"Failed reading relationships from bot_state.json: {e}")

    # Fallback: Check memory/relationships/ if bot_state was empty
    if not affinities:
        rel_dir = os.path.join("memory", "relationships")
        if os.path.exists(rel_dir):
            for fname in os.listdir(rel_dir):
                if not fname.endswith(".json") or fname.startswith("."):
                    continue
                fpath = os.path.join(rel_dir, fname)
                try:
                    with open(fpath, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    
                    user_name = fname.replace('.json', '').replace('dream_', '')
                    events_count = len(data) if isinstance(data, list) else 0
                    
                    affinities.append({
                        "user_id": fname,
                        "user_name": user_name,
                        "familiarity": 0.5 if events_count > 0 else 0.1,
                        "stage": _get_stage_badge(0.5 if events_count > 0 else 0.1),
                        "messages": events_count,
                        "events_count": events_count,
                        "last_seen": 0.0,
                        "valence": 0.5
                    })
                except Exception:
                    continue

    affinities.sort(key=lambda a: (a['familiarity'], a['messages']), reverse=True)
    return affinities


def _gather_belief_and_anchor_stats() -> Dict[str, Any]:
    """Extract metrics from beliefs.json, anchors.json, growth_log.jsonl, and proactive_topics.json."""
    data = {
        "beliefs_count": 0,
        "top_beliefs": [],
        "anchors_count": 0,
        "top_anchor_theme": "N/A",
        "proactive_topics_count": 0,
        "total_growth_events": 0
    }
    
    # 1. Beliefs
    beliefs_path = os.path.join("memory", "beliefs.json")
    if os.path.exists(beliefs_path) and os.path.getsize(beliefs_path) > 0:
        try:
            with open(beliefs_path, 'r', encoding='utf-8') as f:
                beliefs_list = json.load(f)
                if isinstance(beliefs_list, list):
                    data["beliefs_count"] = len(beliefs_list)
                    sorted_b = sorted(beliefs_list, key=lambda b: b.get('access_count', 0), reverse=True)
                    data["top_beliefs"] = sorted_b[:3]
        except Exception:
            pass

    # 2. Anchors
    anchors_path = os.path.join("memory", "anchors.json")
    if os.path.exists(anchors_path) and os.path.getsize(anchors_path) > 0:
        try:
            with open(anchors_path, 'r', encoding='utf-8') as f:
                anchors_list = json.load(f)
                if isinstance(anchors_list, list):
                    data["anchors_count"] = len(anchors_list)
                    if anchors_list:
                        top_a = max(anchors_list, key=lambda a: a.get('salience', 0.0), default=None)
                        if top_a:
                            data["top_anchor_theme"] = top_a.get('topic') or top_a.get('theme') or "General Memory"
        except Exception:
            pass

    # 3. Proactive Topics
    proactive_path = os.path.join("memory", "proactive_topics.json")
    if os.path.exists(proactive_path) and os.path.getsize(proactive_path) > 0:
        try:
            with open(proactive_path, 'r', encoding='utf-8') as f:
                proactive_data = json.load(f)
                history = proactive_data.get('history', [])
                data["proactive_topics_count"] = len(history)
        except Exception:
            pass

    # 4. Growth Log Events
    growth_path = os.path.join("memory", "growth_log.jsonl")
    if os.path.exists(growth_path) and os.path.getsize(growth_path) > 0:
        try:
            with open(growth_path, 'r', encoding='utf-8') as f:
                data["total_growth_events"] = sum(1 for line in f if line.strip())
        except Exception:
            pass

    return data


def _gather_system_telemetry() -> Dict[str, Any]:
    """Gather metrics from stats.json, mood_state.json, and bot_state.json."""
    telemetry = {
        "total_messages": 0,
        "forum_drafts": 0,
        "forum_approved": 0,
        "forum_rejected": 0,
        "kaia_coherence": 0.87,
        "kaia_engagement": 0.59,
        "valence": 0.1,
        "arousal": 0.4,
        "social_energy": 0.8
    }
    
    # 1. Stats
    stats_path = os.path.join("memory", "stats.json")
    if os.path.exists(stats_path) and os.path.getsize(stats_path) > 0:
        try:
            with open(stats_path, 'r', encoding='utf-8') as f:
                s = json.load(f)
                telemetry["total_messages"] = s.get('total_messages', 0)
                telemetry["forum_drafts"] = s.get('forum_drafts', 0)
                telemetry["forum_approved"] = s.get('forum_approved', 0)
                telemetry["forum_rejected"] = s.get('forum_rejected', 0)
        except Exception:
            pass

    # 2. Bot State
    bot_state_path = os.path.join("memory", "bot_state.json")
    if os.path.exists(bot_state_path) and os.path.getsize(bot_state_path) > 0:
        try:
            with open(bot_state_path, 'r', encoding='utf-8') as f:
                b = json.load(f)
                telemetry["kaia_coherence"] = float(b.get('kaia_coherence', 0.87))
                telemetry["kaia_engagement"] = float(b.get('kaia_engagement', 0.59))
        except Exception:
            pass

    # 3. Mood
    mood_path = os.path.join("memory", "mood_state.json")
    if os.path.exists(mood_path) and os.path.getsize(mood_path) > 0:
        try:
            with open(mood_path, 'r', encoding='utf-8') as f:
                m = json.load(f)
                telemetry["valence"] = float(m.get('valence', 0.1))
                telemetry["arousal"] = float(m.get('arousal', 0.4))
                telemetry["social_energy"] = float(m.get('social_energy', 0.8))
        except Exception:
            pass

    return telemetry


def _build_affinity_embed(affinities: List[Dict[str, Any]]) -> discord.Embed:
    """Build high-end, clean Discord embed for Kaia Relationship & Affinity ranks."""
    embed = discord.Embed(
        title="🫂 Kaia's Inner Circle — Affinity Ranks & Bond Scores",
        description="Gamified relationship affinity scores gleaned from cross-session memory logs.",
        color=0x5865F2  # Blurple / Indigo
    )
    
    if not affinities:
        embed.add_field(name="No Bonded Users Yet", value="No relationship profiles logged in memory.", inline=False)
        return embed

    rank_emojis = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"]
    lines = []
    for i, a in enumerate(affinities[:5]):
        rk = rank_emojis[i] if i < len(rank_emojis) else f"`#{i+1}`"
        pct = int(a['familiarity'] * 100)
        bar = _tech_bar(a['familiarity'], 1.0, length=10)
        events_str = f"`{a['events_count']} Milestones`" if a['events_count'] > 0 else "`0 Milestones`"
        
        entry = (
            f"{rk} **{a['user_name']}**  ·  `{pct}% Affinity`  {a['stage']}\n"
            f"└ `{bar}`  ·  💬 `{a['messages']} Turns`  ·  {events_str}"
        )
        lines.append(entry)

    embed.add_field(name="✨ Top Bonded Companions", value="\n\n".join(lines), inline=False)
    embed.set_footer(text=f"Total Tracked Relationships: {len(affinities)}  │  Kaia Cognitive Engine")
    return embed


def _build_cognitive_embed(mind: Dict[str, Any]) -> discord.Embed:
    """Build high-end Discord embed for Kaia Mind, Beliefs & Anchors."""
    embed = discord.Embed(
        title="🧠 Kaia Cognitive Records — Beliefs & Memory Anchors",
        description="Kaia's revisable belief store, memory anchors, and cognitive growth ledgers.",
        color=0x9B59B6  # Royal Purple
    )
    
    # Active Stores Field
    b_pct = mind['beliefs_count'] / 100.0
    a_pct = mind['anchors_count'] / 100.0
    b_bar = _tech_bar(b_pct, 1.0, length=10)
    a_bar = _tech_bar(a_pct, 1.0, length=10)

    stores_info = (
        f"• **Active Beliefs Capacity**: `{mind['beliefs_count']} / 100` ({int(b_pct*100)}%)\n"
        f"  └ `{b_bar}`\n"
        f"• **Episodic Memory Anchors**: `{mind['anchors_count']} / 100` ({int(a_pct*100)}%)\n"
        f"  └ `{a_bar}`\n"
        f"• **Proactive Topic Diversity**: `{mind['proactive_topics_count']} Topics Logged`\n"
        f"• **Total Growth Ledger Events**: `{mind['total_growth_events']} Ledger Records`"
    )
    embed.add_field(name="📦 Memory Capacity Overview", value=stores_info, inline=False)

    top_beliefs = mind.get('top_beliefs', [])
    if top_beliefs:
        b_lines = []
        for i, b in enumerate(top_beliefs):
            topic = b.get('topic', 'General').title()
            stmt = b.get('position') or b.get('statement') or b.get('belief') or "N/A"
            if len(stmt) > 90:
                stmt = stmt[:87] + "..."
            acc = b.get('access_count', 0)
            conf = int(b.get('confidence', 0.9) * 100)
            b_lines.append(f"`#{i+1}` **{topic}**\n  └ *\"{stmt}\"*\n  └ 🔄 `{acc} Recalls`  ·  `{conf}% Confidence`")
        embed.add_field(name="💡 Most Salient Beliefs", value="\n\n".join(b_lines), inline=False)

    embed.add_field(name="⚓ Top Memory Anchor Theme", value=f"`{mind['top_anchor_theme']}`", inline=False)
    embed.set_footer(text="Kaia Belief & Episodic Memory System  │  Continuous Identity Stream")
    return embed


def _build_telemetry_embed(t: Dict[str, Any]) -> discord.Embed:
    """Build high-end Discord embed for Kaia System Telemetry & Operational Record."""
    embed = discord.Embed(
        title="📊 Kaia Operational Telemetry & System Scores",
        description="System activity statistics, cognitive coherence, and active emotional vector.",
        color=0x2ECC71  # Emerald Green
    )
    
    # Emotional Vector
    v_norm = (t['valence'] + 1.0) / 2.0
    v_pct = int(v_norm * 100)
    a_pct = int(t['arousal'] * 100)
    e_pct = int(t['social_energy'] * 100)
    
    v_bar = _tech_bar(v_norm, 1.0, length=10)
    a_bar = _tech_bar(t['arousal'], 1.0, length=10)
    e_bar = _tech_bar(t['social_energy'], 1.0, length=10)

    mood_block = (
        f"• **Valence** (Sad ↔ Happy): **{t['valence']:+.2f}** ({v_pct}%)\n  └ `{v_bar}`\n"
        f"• **Arousal** (Calm ↔ Alert): **{t['arousal']:.2f}** ({a_pct}%)\n  └ `{a_bar}`\n"
        f"• **Social Energy** (Drained ↔ Full): **{t['social_energy']:.2f}** ({e_pct}%)\n  └ `{e_bar}`"
    )
    embed.add_field(name="🎭 Persistent Emotional Vector", value=mood_block, inline=False)

    # Coherence & Engagement
    coh_pct = int(t['kaia_coherence'] * 100)
    eng_pct = int(t['kaia_engagement'] * 100)
    coherence_block = (
        f"• **Cognitive Coherence Score**: **{coh_pct}%**  `S-Grade Continuity`\n"
        f"• **Engagement Rating**: **{eng_pct}%**  `Active Response Path`"
    )
    embed.add_field(name="⚡ Coherence & Engagement", value=coherence_block, inline=False)

    # Bot & Forum Activity
    approval_pct = (t['forum_approved'] / t['forum_drafts'] * 100) if t['forum_drafts'] > 0 else 0
    bot_block = (
        f"• **Total Processed Messages**: `{t['total_messages']:,}`\n"
        f"• **Forum Moderation Queue**: `{t['forum_drafts']} Drafts` │ `{t['forum_approved']} Approved` ({approval_pct:.1f}%)"
    )
    embed.add_field(name="📊 Operational Activity", value=bot_block, inline=False)

    embed.set_footer(text="Kaiacord System Telemetry  │  Production Grade S")
    return embed


class KaiaScoresSelect(Select):
    """Dropdown component for switching score categories."""
    def __init__(self, affinity_data, mind_data, telemetry_data):
        self.affinity_data = affinity_data
        self.mind_data = mind_data
        self.telemetry_data = telemetry_data
        
        options = [
            discord.SelectOption(label="Kaia Affinity Ranks", description="Top bonded users, familiarity stages, and interaction turns", emoji="🫂", value="affinity"),
            discord.SelectOption(label="Mind & Belief Records", description="Belief store metrics, memory anchors, and growth events", emoji="🧠", value="mind"),
            discord.SelectOption(label="System Telemetry & Mood", description="Emotional arc vector, coherence rating, and message stats", emoji="📊", value="telemetry")
        ]
        super().__init__(placeholder="Select Score Category...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        val = self.values[0]
        if val == "affinity":
            embed = _build_affinity_embed(self.affinity_data)
        elif val == "mind":
            embed = _build_cognitive_embed(self.mind_data)
        else:
            embed = _build_telemetry_embed(self.telemetry_data)
            
        await interaction.response.edit_message(embed=embed, view=self.view)


class KaiaScoresView(View):
    """Interactive View containing KaiaScoresSelect dropdown."""
    def __init__(self, affinity_data, mind_data, telemetry_data):
        super().__init__(timeout=180)
        self.add_item(KaiaScoresSelect(affinity_data, mind_data, telemetry_data))


async def handle_scores_command(ctx, msg):
    """Handle !scores, !score, !stats, !leaderboard commands."""
    try:
        log_info(f"Executing !scores command for {msg.author.name}")
        
        # Gather all data in parallel using to_thread
        affinity_data, mind_data, telemetry_data = await asyncio.gather(
            asyncio.to_thread(_gather_affinity_ranks),
            asyncio.to_thread(_gather_belief_and_anchor_stats),
            asyncio.to_thread(_gather_system_telemetry)
        )
        
        initial_embed = _build_affinity_embed(affinity_data)
        view = KaiaScoresView(affinity_data, mind_data, telemetry_data)
        
        await msg.channel.send(embed=initial_embed, view=view)
    except Exception as e:
        log_error(f"Failed executing !scores command: {e}")
        await msg.channel.send("⚠️ Error compiling score summary. Please try again.")
