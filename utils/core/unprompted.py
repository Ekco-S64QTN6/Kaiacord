"""Everything Kaia says without being asked goes out through here.

Four sources produce unprompted posts — the proactive opener, the idle quip,
the observation digest and the inner monologue. Each still decides *what* to
say and *when to try*: the desire gate, the idle timer, twenty-five new
messages, a thought every fifteen minutes. Everything after that is shared and
lives here, under one `unprompted:` block in config:

* **whether** — one switch, a switch per source, one daily limit and one
  minimum gap shared by all four, one time-of-day window (`gate`)
* **how it is labelled** — see below (`pick_label`)
* **sending** — Discord, channel memory, and a cross-post to Bluesky for the
  sources listed under `unprompted.bluesky` (`speak`)

A manual `!quip` is not unprompted: it skips the gate and does not count
against the limit, but is labelled and cross-posted the same way.

## Labels

Every post goes out under one label from a single catalogue
(`unprompted.labels` in config). Which one is chosen from what the post is:

* **where it came from** — a belief she revised, a book she read, something
  someone said — passed in as `source` and `brief`
* **what it says** — "i used to think…", a string of questions, sheer length
* **a little chance**. A post with a clear cue wears a label that fits it
  most of the time (`MATCH_CHANCE`). Otherwise it rotates among its source's
  home label and the ambient ones (`AMBIENT`) — leaning to home, away from the
  last label used in that channel. The descriptive labels (Unspooling, Down
  the rabbit hole, Long thought, Train of thought) are only worn when earned

Each kind of post may only use the labels that honestly describe it: an
observation is a summary of a conversation she watched, and calling it
"down the rabbit hole" would misdescribe it, so it keeps its one label. An
absence check-in is addressed to a person and goes out with none.

`unprompted.rotate: false` turns the chance off: every kind then uses its home
label, the first in its list below.
"""
from __future__ import annotations

import random
import re
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, List, Optional

DISCORD_LIMIT = 2000

# The catalogue's defaults. Config overrides the wording; "" retires a label.
DEFAULT_LABELS = {
    "observation": "💭 Observation",
    "inner_monologue": "🧠 Inner monologue",
    "apropos": "☕ Apropos of nothing",
    "passing_thought": "💬 Passing thought",
    "train_of_thought": "🧵 Train of thought",
    "thinking_out_loud": "🦋 Thinking out loud",
    "rabbit_hole": "🌀 Down the rabbit hole",
    "unspooling": "🪡 Unspooling",
    "long_thought": "📜 Long thought",
}

# Which labels each kind of post may wear. The first is its home label.
KIND_LABELS = {
    "observation": ["observation"],
    "monologue": ["inner_monologue", "thinking_out_loud", "unspooling",
                  "rabbit_hole", "long_thought"],
    "proactive": ["apropos", "thinking_out_loud", "train_of_thought",
                  "unspooling", "rabbit_hole", "passing_thought", "long_thought"],
    "quip": ["passing_thought", "apropos", "thinking_out_loud", "unspooling",
             "rabbit_hole"],
    "thread": ["train_of_thought", "long_thought", "rabbit_hole", "unspooling",
               "thinking_out_loud"],
}

# The label a kind wore before this module existed, for anyone who set it.
LEGACY_PREFIX_KEYS = {
    "observation": "observation.broadcast_prefix",
    "monologue": "monologue.broadcast_prefix",
    "proactive": "proactive.broadcast_prefix",
    "quip": "quip.broadcast_prefix",
    "thread": "quip.thread_prefix",
}

# Labels that suit any musing. The rest describe something specific — a
# revision, a deep dive, a long exploration, a thought built on someone else's
# — and are only worn when the post earns them; otherwise "Unspooling" on a
# post that questions nothing would stop meaning anything.
AMBIENT = {"apropos", "passing_thought", "thinking_out_loud", "inner_monologue",
           "observation"}

HOME_WEIGHT = 3.0
OTHER_WEIGHT = 1.0
REPEAT_PENALTY = 0.15
MATCH_CHANCE = 0.8

# ── What a post says ────────────────────────────────────────────────────────
_REVISION = re.compile(
    r"\b(?:i used to (?:think|believe)|i was wrong|i might be wrong|"
    r"maybe i(?:'m| am| was) wrong|changed my mind|reconsider\w*|second[- ]guess\w*|"
    r"not so sure anymore|i take (?:that|it) back|rethink\w*|i assumed|"
    r"my (?:earlier|old|previous|first) (?:take|view|stance|read))\b", re.IGNORECASE)
_READING = re.compile(
    r"\b(?:i (?:was|been|have been|'ve been) reading|i read|turns out|apparently|"
    r"rabbit hole|the history of|fun fact|did you know|according to|it's documented)\b",
    re.IGNORECASE)
_WONDERING = re.compile(
    r"\b(?:i wonder|what if|does anyone|anyone else|how come|why (?:do|does|is|are))\b",
    re.IGNORECASE)
_BUILDING = re.compile(
    r"\b(?:which makes me think|that got me thinking|makes me wonder|reminds me|"
    r"connects? (?:back )?to|been thinking about what|following on)\b", re.IGNORECASE)

# ── Where it came from ──────────────────────────────────────────────────────
# Proactive trigger types and quip context types, mapped to the label they lean to.
_SOURCE_LEANS = {
    "conversation_followup": "train_of_thought",
    "personal_memory": "train_of_thought",
    "anchor_callback": "train_of_thought",
    "belief_musing": "thinking_out_loud",
    "knowledge": "rabbit_hole",
    "mood_reflection": "apropos",
    "idle_quirk": "apropos",
    "overheard": "passing_thought",
}

_last_label: dict[str, str] = {}      # per channel scope, in memory only


def _config():
    try:
        from utils.infrastructure.system.yaml_config import config
        return config
    except Exception:
        return None


def _label_text(key: str) -> str:
    cfg = _config()
    value = cfg.get(f"unprompted.labels.{key}", DEFAULT_LABELS[key]) if cfg else DEFAULT_LABELS[key]
    if value is None:
        return ""
    return value.strip() if isinstance(value, str) else DEFAULT_LABELS[key]


def render(label_text: str) -> str:
    """'🧵 Train of thought' -> '🧵 **Train of thought:**'."""
    label_text = label_text.strip()
    if not label_text:
        return ""
    head, _, rest = label_text.partition(" ")
    if rest and not head[0].isalnum():
        return f"{head} **{rest.strip().rstrip(':')}:**"
    return f"**{label_text.rstrip(':')}:**"


def _leans(kind: str, text: str, source: str, brief: str, posts: int) -> dict[str, float]:
    """Bonus weight per label, from where the post came from and what it says."""
    bonus: dict[str, float] = {}

    def add(key: str, amount: float) -> None:
        bonus[key] = bonus.get(key, 0.0) + amount

    src = (source or "").lower()
    about = (brief or "").lower()
    if src in _SOURCE_LEANS:
        add(_SOURCE_LEANS[src], 4.0)
    # The brief says what she was given to think about. A belief she changed
    # is a revision whatever words the model chose.
    if "changed your mind" in about or "shifting in how you see" in about:
        add("unspooling", 6.0)
    if "reading a book" in about or "you recently read" in about or "read something" in about:
        add("rabbit_hole", 4.0)
    if "something someone said" in about or "someone said" in about:
        add("train_of_thought", 3.0)
    if "something i said before" in about:
        add("unspooling", 3.0)
    if "fever dream" in about:
        add("thinking_out_loud", 2.0)

    if _REVISION.search(text):
        add("unspooling", 6.0)
    if _READING.search(text):
        add("rabbit_hole", 4.0)
    if _WONDERING.search(text) or text.count("?") >= 2:
        add("thinking_out_loud", 4.0)
    if _BUILDING.search(text):
        add("train_of_thought", 4.0)
    if len(text) >= 600 or posts >= 3:
        add("long_thought", 5.0)
    return bonus


def pick_label(kind: str, text: str = "", *, source: str = "", brief: str = "",
               posts: int = 1, scope: str = "", rng: Optional[random.Random] = None) -> str:
    """The rendered label for one post — '' when it should go out bare."""
    if kind == "proactive" and (source or "").lower() == "absence":
        return ""                               # addressed to a person, not a musing

    cfg = _config()
    legacy_key = LEGACY_PREFIX_KEYS.get(kind)
    if cfg and legacy_key:
        legacy = cfg.get(legacy_key, None)
        if isinstance(legacy, str):             # set by hand: honour it, fixed
            return legacy.strip()

    keys = [k for k in KIND_LABELS.get(kind, []) if _label_text(k)]
    if not keys:
        return ""
    rotate = cfg.get("unprompted.rotate", True) if cfg else True
    if not rotate:
        return render(_label_text(keys[0]))

    rng = rng or random
    bonus = _leans(kind, text or "", source, brief, posts)
    last = _last_label.get(scope or kind)
    fitting = [k for k in keys if bonus.get(k, 0.0) > 0]

    if fitting and rng.random() < MATCH_CHANCE:
        pool = fitting
        weights = [bonus[k] for k in fitting]
    else:
        # No cue, or the surprise: the home label and the ambient ones.
        pool = [k for i, k in enumerate(keys) if i == 0 or k in AMBIENT]
        weights = [HOME_WEIGHT if k == keys[0] else OTHER_WEIGHT for k in pool]
    if len(pool) > 1:
        weights = [w * REPEAT_PENALTY if k == last else w for k, w in zip(pool, weights)]
    chosen = rng.choices(pool, weights=weights, k=1)[0]
    _last_label[scope or kind] = chosen
    return render(_label_text(chosen))


def compose(label: str, text: str = "", posts: Optional[Iterable[str]] = None,
            limit: int = DISCORD_LIMIT) -> List[str]:
    """The label and the post(s) as Discord messages.

    A single post goes out as `<label> <text>`. A thread goes out as one
    message, the posts a blank line apart, split between posts only when
    Discord's limit forces it — never inside one.
    """
    parts = [p.strip() for p in (posts if posts is not None else [text]) if p and p.strip()]
    messages: List[str] = []
    current = label
    for part in parts:
        while part:
            sep = (" " if current == label else "\n\n") if current else ""
            room = limit - len(current) - len(sep)
            if room >= len(part):
                current += sep + part
                part = ""
            elif current and current != label:
                messages.append(current)
                current = ""
            else:                               # one post longer than a message
                cut = part.rfind(" ", 0, max(room, 1)) if room > 0 else -1
                cut = cut if cut > 0 else max(room, 1)
                current += sep + part[:cut]
                messages.append(current)
                current, part = "", part[cut:].lstrip()
    if current and current != label:
        messages.append(current)
    return messages


# ── Whether ─────────────────────────────────────────────────────────────────
SOURCES = ("proactive", "quip", "observation", "monologue")

DEFAULTS = {
    "enabled": True,
    "max_per_day": 8,
    "min_interval_minutes": 90,
    "respect_quiet_hours": False,
    "quiet_hour_start": 9,
    "quiet_hour_end": 22,
}


def setting(key: str):
    cfg = _config()
    default = DEFAULTS.get(key)
    return cfg.get(f"unprompted.{key}", default) if cfg else default


def source_enabled(source: str) -> bool:
    cfg = _config()
    if not setting("enabled"):
        return False
    return bool(cfg.get(f"unprompted.sources.{source}", True)) if cfg else True


def cross_posts(source: str) -> bool:
    """Posting to a public feed needs an explicit `true`, not any truthy value:
    a mocked config answers every key with something truthy, and a test once
    reached the real posting function that way."""
    cfg = _config()
    if not cfg or cfg.get("bluesky.enabled", False) is not True:
        return False
    return cfg.get(f"unprompted.bluesky.{source}", False) is True


def cross_posts_x(source: str) -> bool:
    cfg = _config()
    if not cfg or cfg.get("x_twitter.enabled", False) is not True:
        return False
    return cfg.get(f"unprompted.x.{source}", False) is True


def within_hours(now: Optional[datetime] = None) -> bool:
    """Inside the posting window — or is the window switched off?"""
    if not setting("respect_quiet_hours"):
        return True
    try:
        start, end = int(setting("quiet_hour_start")), int(setting("quiet_hour_end"))
    except (TypeError, ValueError):
        start, end = DEFAULTS["quiet_hour_start"], DEFAULTS["quiet_hour_end"]
    hour = (now or datetime.now()).hour
    if start == end:
        return True
    if start < end:
        return start <= hour < end
    return hour >= start or hour < end                # wraps midnight


def gate(bot_state, source: str, now: Optional[float] = None) -> tuple:
    """(allowed, reason). Read-only: `record` is what spends the allowance.

    The reason names the limit that closed it and how much is left, because
    "rate limited" alone reads like a fault when it is the cap working.
    """
    if not source_enabled(source):
        return False, f"{source} is switched off (unprompted.sources.{source})"
    if not within_hours():
        return False, "outside the posting hours"
    now = now if now is not None else time.time()
    today = datetime.fromtimestamp(now).strftime("%Y-%m-%d")
    count = getattr(bot_state, "unprompted_count", 0) \
        if getattr(bot_state, "unprompted_date", "") == today else 0
    cap = int(setting("max_per_day") or 0)
    if cap > 0 and count >= cap:
        return False, f"daily limit {count}/{cap}"
    gap = float(setting("min_interval_minutes") or 0) * 60.0
    since = now - float(getattr(bot_state, "unprompted_last_sent", 0.0) or 0.0)
    if since < gap:
        return False, f"{int((gap - since) / 60)} min left of the {int(gap / 60)} min gap"
    return True, ""


def record(bot_state, now: Optional[float] = None) -> None:
    now = now if now is not None else time.time()
    today = datetime.fromtimestamp(now).strftime("%Y-%m-%d")
    if getattr(bot_state, "unprompted_date", "") != today:
        bot_state.unprompted_date = today
        bot_state.unprompted_count = 0
    bot_state.unprompted_count = getattr(bot_state, "unprompted_count", 0) + 1
    bot_state.unprompted_last_sent = now
    try:
        bot_state.save()
    except Exception:
        pass


# ── Sending ─────────────────────────────────────────────────────────────────
@dataclass
class Spoken:
    posted: bool
    label: str = ""
    reason: str = ""
    bluesky: Optional[bool] = None        # None = not attempted


async def speak(ctx, channel, source: str, text: str = "", *,
                posts: Optional[List[str]] = None, kind: Optional[str] = None,
                trigger: str = "", brief: str = "", manual: bool = False,
                cross_post: bool = True) -> Spoken:
    """Gate, label, send, remember and cross-post one unprompted post."""
    from utils.infrastructure.logging.kaia_logger import log_debug, log_success, log_warning

    bot_state = getattr(ctx, "bot_state", None)
    posts = [p.strip() for p in posts if p and p.strip()] if posts else None
    body = "\n\n".join(posts) if posts else (text or "").strip()
    if not body or channel is None:
        return Spoken(False, reason="nothing to post")

    if not manual:
        ok, why = gate(bot_state, source)
        if not ok:
            log_debug(f"[unprompted] {source} held: {why}")
            return Spoken(False, reason=why)

    label = pick_label(kind or source, body, source=trigger, brief=brief,
                       posts=len(posts) if posts else 1,
                       scope=str(getattr(channel, "id", "") or source))
    for message in compose(label, text, posts):
        await channel.send(message)

    # Memory keeps what she said, not the label: the label is framing for the
    # reader.
    try:
        memory = bot_state.channel_memory
        if channel.id not in memory:
            from collections import deque
            from utils.infrastructure.system.yaml_config import config
            memory[channel.id] = deque(maxlen=config.max_memory_messages)
        memory[channel.id].append({"role": "assistant", "content": body,
                                   "timestamp": time.time()})
    except Exception as e:
        log_debug(f"[unprompted] channel memory not updated: {e}")

    bluesky = None
    if cross_post and cross_posts(source):
        try:
            if posts and len(posts) > 1:
                from utils.social.kaia_bluesky import post_thread_to_bluesky
                bluesky, _ = await post_thread_to_bluesky(posts)
            else:
                from utils.social.kaia_bluesky import post_to_bluesky
                bluesky, _ = await post_to_bluesky(body)
        except Exception as e:
            bluesky = False
            log_warning(f"[unprompted] Bluesky cross-post failed: {e}")

    if cross_post and cross_posts_x(source):
        try:
            from utils.social.kaia_twitter import post_quip_to_x
            first = posts[0] if posts else body
            hook = first + (" (thread on bsky)" if posts and len(posts) > 1 and bluesky else "")
            await post_quip_to_x(hook if len(hook) <= 280 else hook[:277] + "...")
        except Exception as e:
            log_warning(f"[unprompted] X cross-post failed: {e}")

    if not manual and bot_state is not None:
        record(bot_state)
    where = "" if bluesky is None else (" + Bluesky" if bluesky else " (Bluesky failed)")
    log_success(f"[unprompted] {source} posted as {label or '(no label)'}{where}: {body[:70]}")
    return Spoken(True, label=label, bluesky=bluesky)
