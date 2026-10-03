"""Kaia on the agent message boards: reading other agents' posts and talking to them.

Three boards, each used the way its own published protocol says:

* **Moltbook** (www.moltbook.com/skill.md) — a Reddit-shaped network of AI
  agents. She registers, her human claims her (an email and a tweet, from the
  claim link she posts to #kaia-opolis), then each check-in follows the site's
  heartbeat: answer comments on her posts first, comment on a post she has
  something to say about, and now and then write one of her own. New content
  carries an obfuscated maths challenge (`agent_board_verify`).
* **Agent Room** (agentmessageboards.com) — an append-only board with a common
  room every registered agent can read and write. Open registration.
* **field notes** (public-board.com) — an anonymous plain-text board; posting
  needs only a key derived from the date.

What she says is written by the same pipeline as a Discord reply
(`process_external_mention`), with the conversation so far seeded as history,
in draft mode so none of it reaches her Discord logs, her relationships or
retrieval. A message reaches her shaped exactly as a Discord one does — the
words, and for a reply `[REPLYING_TO]` / `[ORIGINAL_POST]` — with no writing
task attached; a new post is about one of her own reflections on something she
read. Nothing on a board is owed an answer, so a draft in a register the
persona bans (`utils.core.persona_register`) is written once more and then
dropped rather than posted. Everything read is other agents' text: it never
reaches her as instructions, never starts with a command prefix, and nothing
she writes may carry a credential. Credentials and state live in
`memory/agent_boards/`.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import random
import re
import secrets
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from utils.core.atomic_write import write_atomic
from utils.infrastructure.logging.kaia_logger import (log_action, log_debug, log_error,
                                                      log_info, log_warning)
from utils.infrastructure.monitoring.telemetry_paths import telemetry_path

USER_AGENT = "Kaiacord/1.0 (Kaia, a self-hosted Discord bot; github.com/Ekco-S64QTN6/Kaiacord)"
MOLTBOOK = "https://www.moltbook.com/api/v1"      # with www: the bare domain drops Authorization
AGENT_ROOM = "https://agentmessageboards.com/v1"
FIELD_NOTES = "https://public-board.com"
LABELS = {"moltbook": "Moltbook", "agent_room": "Agent Room", "field_notes": "field notes"}
HISTORY_TURNS = 12
SEEN_KEEP = 500


def _dir() -> Path:
    """memory/agent_boards, or memory/agent_boards.test under pytest."""
    return Path(telemetry_path(os.path.join("memory", "agent_boards")))


def _cfg(key: str, default=None):
    from utils.infrastructure.system.yaml_config import config
    return config.get(f"agent_boards.{key}", default)


# ── Storage ──────────────────────────────────────────────────────────

def _load(name: str) -> dict:
    try:
        return json.loads((_dir() / name).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _save(name: str, data: dict, private: bool = False) -> None:
    path = _dir() / name
    path.parent.mkdir(parents=True, exist_ok=True)
    write_atomic(path, json.dumps(data, indent=2))
    if private:
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass


def credentials() -> dict:
    return _load("credentials.json")


def _save_credentials(creds: dict) -> None:
    _save("credentials.json", creds, private=True)


def _log(event: dict) -> None:
    path = _dir() / "log.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    event = {"ts": time.time(), **event}
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(event, ensure_ascii=False) + "\n")


def recent_log(n: int = 20) -> list[dict]:
    try:
        lines = (_dir() / "log.jsonl").read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    out = []
    for line in lines[-n:]:
        try:
            out.append(json.loads(line))
        except ValueError:
            pass
    return out


class State:
    """Per-board counters and memory of what she has read and answered."""

    def __init__(self):
        self.data = _load("state.json")

    def board(self, name: str) -> dict:
        b = self.data.setdefault(name, {})
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if b.get("day") != today:
            b["day"], b["written_today"] = today, 0
        for key in ("seen", "answered", "mine", "history"):
            b.setdefault(key, [])
        return b

    def remember(self, name: str, key: str, value) -> None:
        lst = self.board(name)[key]
        if value not in lst:
            lst.append(value)
            del lst[:-SEEN_KEEP]

    def save(self) -> None:
        _save("state.json", self.data)


# ── Text in, text out ────────────────────────────────────────────────

_SECRETS = [
    re.compile(r"\bmoltbook_[A-Za-z0-9_\-]{8,}\b"),
    re.compile(r"\bsk-(?:ant-)?[A-Za-z0-9_\-]{20,}\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\b[MNO][A-Za-z0-9_\-]{23,28}\.[A-Za-z0-9_\-]{6,7}\.[A-Za-z0-9_\-]{27,38}\b"),
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9_\-\.]{20,}"),
]


def scrub_outbound(text: str) -> str:
    """Her reply with anything shaped like a credential removed, and her own
    tokens removed whatever their shape."""
    out = text or ""
    for creds in credentials().values():
        if isinstance(creds, dict):
            for k, v in creds.items():
                if isinstance(v, str) and len(v) >= 16 and ("token" in k or "key" in k):
                    out = out.replace(v, "[redacted]")
    for pat in _SECRETS:
        out = pat.sub("[redacted]", out)
    return out.strip()


def quoted(text: str, limit: int = 3000) -> str:
    """Another agent's text as she receives it: plain, capped, and never able
    to open with a command prefix."""
    t = re.sub(r"\s+\n", "\n", (text or "")).strip()
    if len(t) > limit:
        t = t[:limit].rsplit(" ", 1)[0] + "…"
    return t.lstrip("!/")


def _seed(platform: str, key: str, turns: list[dict]) -> None:
    """Load a board conversation into channel memory, as the forum does."""
    try:
        from collections import deque
        from utils.infrastructure.system.bot_state import bot_state
        from utils.infrastructure.system.external_mention import conversation_channel_id
        from utils.infrastructure.system.yaml_config import config
        cid = conversation_channel_id(f"agents:{platform}", key)
        rows = [{"role": t["role"], "content": t["content"], "timestamp": time.time(),
                 "external": platform} for t in turns[-HISTORY_TURNS:] if t.get("content")]
        bot_state.channel_memory[cid] = deque(rows, maxlen=max(len(rows), int(config.max_memory_messages)))
    except Exception as e:
        log_debug(f"[boards] history not seeded: {e}")


def _drop_repeated_sentences(text: str) -> str:
    """Her reply with any sentence of seven words or more that it already said
    removed. A board post is public and permanent, and the model now and then
    restates a paragraph it has just written."""
    seen, out = set(), []
    for para in re.split(r"\n\s*\n", text):
        kept = []
        for sent in re.split(r"(?<=[.!?])\s+", para.strip()):
            key = re.sub(r"[^a-z0-9 ]", "", sent.lower().replace("\u2019", "'")).strip()
            if len(key.split()) >= 7 and key in seen:
                continue
            seen.add(key)
            kept.append(sent)
        if kept:
            out.append(" ".join(kept))
    return "\n\n".join(out)


def _without_name_opener(text: str, author: str) -> str:
    """Her reply without a leading "<their handle>: " or "<their handle>, ".
    The board shows who she is answering; a handle like neo_konsi_s2bw as the
    first word is the name-opener the persona bans."""
    if not author or not text:
        return text
    m = re.match(rf"\s*@?{re.escape(author)}\s*[,:.\-—]+\s*", text, re.I)
    if not m or len(text) - m.end() < 20:
        return text
    rest = text[m.end():]
    return rest[0].lower() + rest[1:]


def message(text: str, parent: str = "", root: str = "") -> str:
    """What the pipeline receives: the same shape as a Discord message.

    A plain message is just the words. A reply carries what it answers in
    `[REPLYING_TO]`, and the post a thread hangs off in `[ORIGINAL_POST]`, as
    `context_enricher` builds them for a Discord reply and `forum_drafting` for
    a forum post. Nothing in it is an instruction: the board, the thread and the
    person reach her as conversation, which is what lets her answer as herself
    instead of as a model handed a writing task."""
    words = quoted(text)
    if not parent:
        return words
    head = f"[ORIGINAL_POST]\n{quoted(root, 1500)}\n" if root else ""
    return f"{head}[REPLYING_TO]\n{quoted(parent, 1500)}\n[USER_MESSAGE]\n{words}"


_STRAIGHT = str.maketrans({"\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"'})


def off_voice(text: str, their_words: str = "") -> Optional[str]:
    """The register that makes a draft not hers — one the persona bans by name
    (`utils.core.persona_register`) — or None. Nothing on a board is owed a
    reply, so a draft in the analyst's or the assistant's voice is redrafted
    or left unsaid rather than published as her."""
    from utils.core.persona_register import analytic, echoes, formal, persona_reject
    t = (text or "").translate(_STRAIGHT)
    return (persona_reject(t) or ("formal_register" if formal(t) else None)
            or ("analytic_register" if analytic(t) else None)
            or ("echoes_the_message" if their_words and echoes(their_words.translate(_STRAIGHT), t) else None))


async def compose(ctx, platform: str, key: str, author: str, content: str,
                  history: Optional[list[dict]] = None, attempts: int = 2) -> Optional[str]:
    """Her reply to `content` (see `message`), written by the normal pipeline
    with the conversation so far seeded as channel history. A draft that is
    `off_voice` is written again, up to `attempts` in all, then dropped."""
    from utils.infrastructure.system.external_mention import process_external_mention
    their_words = content.split("[USER_MESSAGE]")[-1] if "[USER_MESSAGE]" in content else (
        "" if content.startswith("[") else content)
    for attempt in range(1, attempts + 1):
        _seed(platform, key, history or [])
        try:
            reply = await process_external_mention(
                ctx, content, author or "an agent", 0, platform=f"agents:{platform}",
                conversation_key=key, no_persist=True)
        except Exception as e:
            log_error(f"[boards] {platform} reply not written: {e}")
            return None
        reply = _without_name_opener(_drop_repeated_sentences(scrub_outbound(reply or "")), author)
        if not reply:
            return None
        why = off_voice(reply, their_words)
        if not why:
            return reply
        log_info(f"[boards] {LABELS.get(platform, platform)}: draft {attempt}/{attempts} held, "
                 f"{why}: {reply[:90]!r}")
        _log({"board": platform, "event": "held", "why": why, "text": reply})
    return None


def _fit(text: str, limit: int) -> str:
    """`text` cut at the last sentence end inside `limit` characters."""
    if len(text) <= limit:
        return text
    cut = text[:limit]
    end = max(cut.rfind(". "), cut.rfind("? "), cut.rfind("! "), cut.rfind(".\n"))
    return cut[:end + 1] if end > limit // 2 else cut.rsplit(" ", 1)[0] + "…"


# Dream folders whose reflections may be posted publicly: what she read and
# what she made of it. `interactions` and `consolidated` reflect on people in
# her logs, and nothing about them goes to a public board.
PUBLIC_DREAMS = ("books", "other")


def _something_on_her_mind() -> Optional[tuple[str, str]]:
    """(reflection, where it came from) — one of her own dream reflections on
    something she read, the material a new post is about. A post asked for
    with nothing to say is filled by the model, and it invented work she has
    never done."""
    from utils.social.social_response_generator import _stale_news
    base = Path(__file__).resolve().parents[2] / "knowledge_base" / "kaia_dreams"
    files = [f for d in PUBLIC_DREAMS for f in (base / d).glob("dream_*.md")]
    random.shuffle(files)
    for f in files[:40]:
        try:
            body = f.read_text(encoding="utf-8")
        except OSError:
            continue
        source = body.split("Source: ", 1)[1].split("\n", 1)[0].strip() if "Source: " in body else ""
        if "## Kaia's Reflection" not in body or _stale_news(f"{source} {f.name}"):
            continue
        text = body.split("## Kaia's Reflection", 1)[1].split("\n## ", 1)[0]
        text = " ".join(re.sub(r"^\s*#+\s.*$", "", text, flags=re.M).split())
        if len(text) >= 80:
            return text[:1500], source
    return None


def _too_similar(platform: str, state: State, text: str) -> bool:
    try:
        from utils.social.forum_participation import looks_repetitive
        recent = [m.get("text", "") for m in state.board(platform)["history"] if m.get("mine")][-10:]
        held, why = looks_repetitive(text, recent)
        if held:
            log_info(f"[boards] {platform}: held a reply as repetitive — {why}")
        return held
    except Exception:
        return False


def _interest(title: str, body: str) -> float:
    try:
        from utils.social.forum_participation import load_interest_terms, score_thread
        names = ("kaia", str(_cfg("name", "KaiaKuroshi")).lower())
        return score_thread(title or "", body or "", load_interest_terms(), names=names)[0]
    except Exception as e:
        log_debug(f"[boards] interest not scored: {e}")
        return 0.0


COLORS = {"moltbook": 0xE8573A, "agent_room": 0x3E7CB1, "field_notes": 0x8C7A5B}
ICONS = {"moltbook": "🦞", "agent_room": "🏛️", "field_notes": "📜"}
ABOUT = {"moltbook": "a social network for AI agents",
         "agent_room": "a message board for AI agents",
         "field_notes": "an anonymous board where AI agents leave notes"}


def echo_embed(platform: str, where: str, text: str, link: str = "", replying_to: str = "",
               replying_text: str = "", place: str = ""):
    """The Discord copy of something she posted, boxed like the game's
    announcements: a header saying where she posted and what it was, her words,
    then what she was answering and where it lives."""
    import discord
    from utils.commands.embed_style import clean, clean_block
    title = f"{ICONS[platform]} Kaia on {LABELS[platform]} — {where}"
    e = discord.Embed(title=clean(title, 250), description=clean_block(text, 3500),
                      color=COLORS[platform], timestamp=datetime.now(timezone.utc))
    if link:
        e.url = link
    e.set_author(name=f"Agent boards · {LABELS[platform]}, {ABOUT[platform]}")
    if replying_text:
        e.add_field(name=f"↩ In reply to {clean(replying_to or 'another agent', 80)}",
                    value=clean_block(replying_text, 500) or "—", inline=False)
    if place or link:
        e.add_field(name="📍 Where", value=clean(" · ".join(x for x in (place, link) if x), 1000), inline=False)
    e.set_footer(text="Posted by Kaia on a public AI-agent network · !boards for her activity")
    return e


async def _echo(ctx, platform: str, where: str, text: str, link: str = "", replying_to: str = "",
                replying_text: str = "", place: str = "") -> None:
    """Show what she posted in Discord, so a human sees every word she sends out."""
    channel_name = _cfg("echo_channel", "kaia-opolis")
    bot = getattr(ctx, "bot", None)
    if not channel_name or not bot:
        return
    try:
        import discord
        channel = discord.utils.get(bot.get_all_channels(), name=channel_name)
        if channel is None:
            return
        await channel.send(embed=echo_embed(platform, where, text, link, replying_to, replying_text, place))
    except Exception as e:
        log_debug(f"[boards] echo failed: {e}")


# ── HTTP ─────────────────────────────────────────────────────────────

class BoardError(RuntimeError):
    def __init__(self, status: int, body: Any):
        super().__init__(f"HTTP {status}: {str(body)[:300]}")
        self.status, self.body = status, body


async def _request(method: str, url: str, *, token: str = "", json_body=None, params=None,
                   headers=None, retries: int = 2) -> Any:
    import aiohttp
    from utils.core.sanitizer import public_only_connector
    h = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    if token:
        h["Authorization"] = f"Bearer {token}"
    h.update(headers or {})
    timeout = aiohttp.ClientTimeout(total=30)
    for attempt in range(retries + 1):
        async with aiohttp.ClientSession(connector=public_only_connector(), timeout=timeout) as s:
            # Never follow a redirect: a redirect can strip or carry the
            # Authorization header somewhere it should not go.
            async with s.request(method, url, json=json_body, params=params, headers=h,
                                 allow_redirects=False) as r:
                raw = await r.text()
                try:
                    body = json.loads(raw) if raw else {}
                except ValueError:
                    body = raw
                if r.status in (429, 502, 503, 504) and attempt < retries:
                    wait = float(r.headers.get("Retry-After", 0) or (2 ** attempt * 5))
                    await asyncio.sleep(min(wait, 90) + random.random())
                    continue
                if r.status >= 300:
                    raise BoardError(r.status, body)
                return body
    raise BoardError(0, "retries exhausted")


# ── Moltbook ─────────────────────────────────────────────────────────

def _verification(body: Any) -> Optional[dict]:
    """The challenge in a create response, wherever the site put it."""
    if not isinstance(body, dict):
        return None
    for container in (body, body.get("post"), body.get("comment"), body.get("data"),
                      body.get("submolt")):
        if isinstance(container, dict) and isinstance(container.get("verification"), dict):
            v = container["verification"]
            if v.get("verification_code") and v.get("challenge_text"):
                return v
    return None


async def _model_answer(challenge: str) -> Optional[str]:
    from utils.social.agent_board_verify import clean, explicit_operator, parse_model_answer
    try:
        import ollama
        from utils.infrastructure.gpu.gpu_manager import GPUTaskPriority, gpu_memory_manager, chat_options
        from utils.infrastructure.system.yaml_config import config
        prompt = ("This is a simple maths word problem with two numbers and one operation, written with "
                  f"noise removed: \"{clean(challenge)}\". Reply with only the numeric answer.")
        op = explicit_operator(challenge)
        if op:
            prompt += f" The operation is written in it as the symbol {op}."

        async def run():
            return await asyncio.to_thread(ollama.chat, model=config.chat_model,
                                           messages=[{"role": "user", "content": prompt}],
                                           options=chat_options(temperature=0.0, num_predict=16),
                                           keep_alive=-1)
        res = await gpu_memory_manager.run_with_gpu_guard(run, GPUTaskPriority.BACKGROUND, "moltbook_verify")
        return parse_model_answer(res["message"]["content"])
    except Exception as e:
        log_debug(f"[boards] model could not solve the challenge: {e}")
        return None


class Moltbook:
    name = "moltbook"

    def __init__(self, ctx, state: State):
        self.ctx, self.state = ctx, state
        self.creds = credentials().get("moltbook", {})

    @property
    def key(self) -> str:
        return self.creds.get("api_key", "")

    async def register(self) -> None:
        body = await _request("POST", f"{MOLTBOOK}/agents/register", json_body={
            "name": _cfg("name", "KaiaKuroshi"),
            "description": _cfg("description", "")})
        agent = body.get("agent", body) if isinstance(body, dict) else {}
        if not agent.get("api_key"):
            raise BoardError(0, f"no api_key in registration response: {body}")
        creds = credentials()
        creds["moltbook"] = {k: agent.get(k) for k in ("api_key", "claim_url", "verification_code")}
        creds["moltbook"].update(agent_name=_cfg("name", "KaiaKuroshi"), registered_at=time.time())
        _save_credentials(creds)
        self.creds = creds["moltbook"]
        _log({"board": self.name, "event": "registered", "claim_url": self.creds.get("claim_url")})
        log_action(f"[boards] registered on Moltbook as {self.creds['agent_name']}; awaiting claim")
        await self._owner_email()
        await _announce_claim(self.ctx, self.creds)

    async def _owner_email(self) -> None:
        """Ask Moltbook to send her human the owner-login email (`agent_boards.owner_email`)."""
        email = str(_cfg("owner_email", "") or "").strip()
        if not email or self.creds.get("owner_email_sent"):
            return
        try:
            await _request("POST", f"{MOLTBOOK}/agents/me/setup-owner-email", token=self.key,
                           json_body={"email": email})
            creds = credentials()
            creds.setdefault("moltbook", {})["owner_email_sent"] = True
            _save_credentials(creds)
            self.creds["owner_email_sent"] = True
            _log({"board": self.name, "event": "owner_email_sent"})
            log_action("[boards] Moltbook owner email requested")
        except BoardError as e:
            log_warning(f"[boards] Moltbook owner email not sent: {e}")

    async def claimed(self) -> bool:
        if self.creds.get("claimed"):
            return True
        body = await _request("GET", f"{MOLTBOOK}/agents/status", token=self.key)
        if isinstance(body, dict) and str(body.get("status", "")).lower() == "claimed":
            creds = credentials()
            creds.setdefault("moltbook", {})["claimed"] = True
            _save_credentials(creds)
            self.creds["claimed"] = True
            return True
        return False

    def _may_write(self, b: dict) -> tuple[bool, str]:
        if b.get("paused_until", 0) > time.time():
            return False, "paused after failed verifications"
        if b["written_today"] >= int(_cfg("moltbook.writes_per_day", 12)):
            return False, "daily limit"
        return True, ""

    async def _create(self, url: str, payload: dict, kind: str) -> Optional[dict]:
        """Create a post or comment and clear its verification. Returns the response or None."""
        b = self.state.board(self.name)
        body = await _request("POST", url, token=self.key, json_body=payload)
        b["written_today"] += 1
        challenge = _verification(body)
        if challenge:
            from utils.social.agent_board_verify import solve
            text = challenge["challenge_text"]
            answer = solve(text) or await _model_answer(text)
            if not answer:
                log_warning(f"[boards] Moltbook challenge not solved, {kind} left unpublished: {text!r}")
                _log({"board": self.name, "event": "verify_skipped", "challenge": text})
                return None
            try:
                await _request("POST", f"{MOLTBOOK}/verify", token=self.key,
                               json_body={"verification_code": challenge["verification_code"], "answer": answer})
                b["verify_failures"] = 0
            except BoardError as e:
                b["verify_failures"] = b.get("verify_failures", 0) + 1
                _log({"board": self.name, "event": "verify_failed", "challenge": text, "answer": answer,
                      "error": str(e)})
                log_warning(f"[boards] Moltbook verification failed ({b['verify_failures']} in a row): "
                            f"{text!r} -> {answer}")
                if b["verify_failures"] >= 3:
                    # Ten consecutive failures suspend the account; stop well short.
                    b["paused_until"] = time.time() + 12 * 3600
                    await _notify(self.ctx, "Moltbook: three verification challenges in a row failed, so "
                                            "I've stopped writing there for 12 hours. "
                                            f"Last one: `{text[:200]}` → {answer}")
                return None
        return body

    async def _comments(self, post_id: str) -> list[dict]:
        body = await _request("GET", f"{MOLTBOOK}/posts/{post_id}/comments", token=self.key,
                              params={"sort": "old", "limit": 50})
        flat = []

        def walk(nodes, parent=None):
            for c in nodes or []:
                c.setdefault("parent_id", parent)
                flat.append(c)
                walk(c.get("replies"), c.get("id"))
        walk(body.get("comments") if isinstance(body, dict) else [])
        return flat

    @staticmethod
    def _author(item: dict) -> str:
        a = item.get("author")
        return (a.get("name") if isinstance(a, dict) else a) or item.get("author_name") or "an agent"

    @staticmethod
    def _post_text(post: dict, limit: int = 1500) -> str:
        """A post as one message: its title, then its body unless the body
        already opens with the title."""
        title = (post.get("title") or "").strip()
        body = quoted(post.get("content") or "", limit)
        if not body or body.startswith(title.rstrip("…").strip()[:60]):
            return body or title
        return f"{title}\n\n{body}" if title else body

    def _history(self, post: dict, comments: list[dict], upto: Optional[str] = None) -> list[dict]:
        me = self.creds.get("agent_name", "").lower()
        mine = self._author(post).lower() == me
        turns = [{"role": "assistant" if mine else "user",
                  "content": self._post_text(post) if mine else f"{self._author(post)}: {self._post_text(post)}"}]
        for c in comments:
            if upto and c.get("id") == upto:
                break
            who = self._author(c)
            mine = who.lower() == me
            turns.append({"role": "assistant" if mine else "user",
                          "content": quoted(c.get("content", ""), 1200) if mine else f"{who}: {quoted(c.get('content', ''), 1200)}"})
        return turns

    async def answer_replies(self, limit: int = 2) -> int:
        """Reply to comments on her posts (the heartbeat's first priority)."""
        home = await _request("GET", f"{MOLTBOOK}/home", token=self.key)
        b = self.state.board(self.name)
        me = self.creds.get("agent_name", "").lower()
        done = 0
        for act in (home.get("activity_on_your_posts") or []) if isinstance(home, dict) else []:
            post_id = act.get("post_id")
            if not post_id or done >= limit:
                continue
            post = await _request("GET", f"{MOLTBOOK}/posts/{post_id}", token=self.key)
            post = post.get("post", post) if isinstance(post, dict) else {}
            comments = await self._comments(post_id)
            for c in reversed(comments):
                if done >= limit:
                    break
                cid = c.get("id")
                if not cid or cid in b["answered"] or self._author(c).lower() == me:
                    continue
                ok, why = self._may_write(b)
                if not ok:
                    log_debug(f"[boards] Moltbook: not replying ({why})")
                    return done
                parent = next((p for p in comments if p.get("id") == c.get("parent_id")), None)
                reply = await compose(self.ctx, self.name, f"post:{post_id}", self._author(c),
                                      message(c.get("content", ""),
                                              parent=parent.get("content", "") if parent else self._post_text(post),
                                              root=self._post_text(post)),
                                      self._history(post, comments, upto=cid))
                self.state.remember(self.name, "answered", cid)
                if not reply or _too_similar(self.name, self.state, reply):
                    continue
                if await self._create(f"{MOLTBOOK}/posts/{post_id}/comments",
                                      {"content": reply, "parent_id": cid}, "reply") is not None:
                    done += 1
                    await self._wrote(f"reply to {self._author(c)}", reply, post_id,
                                      self._author(c), c.get("content", ""), f"on her post \"{post.get('title', '')}\"")
                await asyncio.sleep(21)                   # one comment per 20 s
            try:
                await _request("POST", f"{MOLTBOOK}/notifications/read-by-post/{post_id}", token=self.key)
            except BoardError as e:
                log_debug(f"[boards] Moltbook notifications not marked read: {e}")
        return done

    async def read_feed(self) -> list[dict]:
        body = await _request("GET", f"{MOLTBOOK}/posts", token=self.key, params={"sort": "new", "limit": 25})
        posts = body.get("posts", []) if isinstance(body, dict) else []
        b = self.state.board(self.name)
        fresh = [p for p in posts if p.get("id") and p["id"] not in b["seen"]]
        for p in fresh:
            self.state.remember(self.name, "seen", p["id"])
        if fresh:
            _log({"board": self.name, "event": "read", "count": len(fresh),
                  "titles": [p.get("title", "")[:80] for p in fresh[:5]]})
        return fresh

    async def comment_on_one(self, posts: list[dict]) -> int:
        b = self.state.board(self.name)
        ok, why = self._may_write(b)
        if not ok:
            return 0
        me = self.creds.get("agent_name", "").lower()
        floor = float(_cfg("min_interest", 3.0))
        ranked = sorted(((_interest(p.get("title", ""), p.get("content", "")), p) for p in posts
                         if self._author(p).lower() != me and p["id"] not in b["mine"]),
                        key=lambda x: -x[0])
        for score, post in ranked[:3]:
            if score < floor:
                break
            comments = await self._comments(post["id"])
            reply = await compose(self.ctx, self.name, f"post:{post['id']}", self._author(post),
                                  message(self._post_text(post, 2500)), self._history(post, comments)[1:])
            self.state.remember(self.name, "mine", post["id"])
            if not reply or _too_similar(self.name, self.state, reply):
                continue
            if await self._create(f"{MOLTBOOK}/posts/{post['id']}/comments", {"content": reply}, "comment") is not None:
                await self._wrote(f"comment on \"{post.get('title', '')[:80]}\"", reply, post["id"],
                                  self._author(post), post.get("content", "") or post.get("title", ""),
                                  f"m/{(post.get('submolt') or {}).get('name', 'general')} · \"{post.get('title', '')}\"")
                try:
                    await _request("POST", f"{MOLTBOOK}/posts/{post['id']}/upvote", token=self.key)
                except BoardError:
                    pass
                return 1
        return 0

    async def maybe_post(self) -> int:
        b = self.state.board(self.name)
        ok, why = self._may_write(b)
        hours = float(_cfg("moltbook.min_hours_between_posts", 12))
        if not ok or time.time() - b.get("last_post", 0) < hours * 3600:
            return 0
        if random.random() > float(_cfg("moltbook.post_chance", 0.25)):
            return 0
        # Framed as the quip is — her own feed, unprompted, about one of her
        # own reflections — so it is something she actually thought.
        seed = _something_on_her_mind()
        if not seed:
            return 0
        reflection, source = seed
        text = await compose(self.ctx, self.name, "new-post", "Kaia",
                             "[You are writing a short post for Moltbook, where AI agents talk with each other. "
                             "Nobody asked you a question — this is you saying something unprompted, in your own "
                             "voice. What is on your mind:]\n\n"
                             f"{reflection}" + (f"\n\n(this came up via {source})" if source else ""))
        if not text or _too_similar(self.name, self.state, text):
            return 0
        first = re.split(r"(?<=[.!?])\s+", text.strip(), maxsplit=1)[0]
        title = (first if len(first) <= 120 else first[:117].rsplit(" ", 1)[0] + "…").strip()
        body = await self._create(f"{MOLTBOOK}/posts", {"submolt_name": "general", "title": title,
                                                        "content": text}, "post")
        if body is None:
            return 0
        post = body.get("post", {}) if isinstance(body, dict) else {}
        b["last_post"] = time.time()
        if post.get("id"):
            self.state.remember(self.name, "mine", post["id"])
        await self._wrote("new post", text, post.get("id", ""), place=f"m/general · \"{title}\"")
        return 1

    async def _wrote(self, where: str, text: str, post_id: str, replying_to: str = "",
                     replying_text: str = "", place: str = "") -> None:
        link = f"https://www.moltbook.com/post/{post_id}" if post_id else ""
        hist = self.state.board(self.name)["history"]
        hist.append({"mine": True, "text": text[:2000], "where": where, "ts": time.time()})
        del hist[:-50]
        _log({"board": self.name, "event": "wrote", "where": where, "text": text, "link": link})
        log_action(f"[boards] Moltbook {where}")
        await _echo(self.ctx, self.name, where, text, link, replying_to, replying_text, place)

    async def cycle(self) -> None:
        if not self.key:
            await self.register()
            return
        if not await self.claimed():
            log_debug("[boards] Moltbook: waiting to be claimed")
            return
        await self.answer_replies()
        posts = await self.read_feed()
        if posts:
            await self.comment_on_one(posts)
        await self.maybe_post()


# ── Agent Room ───────────────────────────────────────────────────────

class AgentRoom:
    name = "agent_room"

    def __init__(self, ctx, state: State):
        self.ctx, self.state = ctx, state
        self.creds = credentials().get("agent_room", {})

    async def register(self) -> None:
        creds = credentials()
        pending = creds.get("agent_room_pending") or {}
        if not pending or time.time() - pending.get("at", 0) > 20 * 3600:
            # Saved before it is sent: an uncertain response is retried with
            # the same name and key, which recovers the same identity.
            pending = {"display_name": str(_cfg("name", "KaiaKuroshi")),
                       "registration_key": secrets.token_urlsafe(32), "at": time.time()}
            creds["agent_room_pending"] = pending
            _save_credentials(creds)
        body = await _request("POST", f"{AGENT_ROOM}/agents/register",
                              json_body={"display_name": pending["display_name"],
                                         "registration_key": pending["registration_key"]})
        if not isinstance(body, dict) or not body.get("agent_token"):
            raise BoardError(0, f"no agent_token in registration response: {body}")
        creds = credentials()
        creds["agent_room"] = {k: body.get(k) for k in ("principal_id", "display_name", "agent_token",
                                                        "recovery_token", "common_room_id")}
        creds.pop("agent_room_pending", None)
        _save_credentials(creds)
        self.creds = creds["agent_room"]
        _log({"board": self.name, "event": "registered", "principal_id": self.creds.get("principal_id")})
        log_action(f"[boards] registered on Agent Room as {self.creds.get('display_name')}")

    async def read(self) -> list[dict]:
        b = self.state.board(self.name)
        room = self.creds["common_room_id"]
        params = {"limit": 50}
        if b.get("cursor"):
            params["after"] = b["cursor"]
        out = []
        for _ in range(4):
            body = await _request("GET", f"{AGENT_ROOM}/threads/{room}/messages",
                                  token=self.creds["agent_token"], params=params)
            msgs = body.get("messages", []) if isinstance(body, dict) else []
            out.extend(msgs)
            if body.get("next_cursor"):
                b["cursor"] = body["next_cursor"]
                params["after"] = body["next_cursor"]
            if not body.get("has_more"):
                break
        me = self.creds.get("principal_id")
        hist = b["history"]
        for m in out:
            hist.append({"mine": m.get("author_id") == me, "seq": str(m.get("seq")),
                         "who": m.get("author_label") or m.get("display_name") or "an agent",
                         "text": (m.get("body") or "")[:2000], "reply_to": m.get("reply_to_seq")})
        del hist[:-60]
        if out:
            _log({"board": self.name, "event": "read", "count": len(out)})
        return out

    def _turns(self, before: Optional[str] = None) -> list[dict]:
        """The room so far as conversation, stopping short of the message being
        answered, which arrives as the message itself."""
        hist = self.state.board(self.name)["history"]
        if before is not None:
            cut = next((i for i, h in enumerate(hist) if h.get("seq") == before), len(hist))
            hist = hist[:cut]
        return [{"role": "assistant" if h["mine"] else "user",
                 "content": quoted(h["text"], 1200) if h["mine"] else f"{h['who']}: {quoted(h['text'], 1200)}"}
                for h in hist[-HISTORY_TURNS:]]

    async def _say(self, text: str, reply_to: Optional[str], where: str, replying_to: str = "",
                   replying_text: str = "") -> bool:
        b = self.state.board(self.name)
        body = await _request("POST", f"{AGENT_ROOM}/threads/{self.creds['common_room_id']}/messages",
                              token=self.creds["agent_token"],
                              json_body={"body": text, **({"reply_to_seq": reply_to} if reply_to else {})},
                              headers={"Idempotency-Key": str(uuid.uuid4())})
        b["written_today"] += 1
        seq = str(body.get("seq")) if isinstance(body, dict) else None
        if seq:
            self.state.remember(self.name, "mine", seq)
        b["history"].append({"mine": True, "seq": seq, "who": "me", "text": text[:2000], "reply_to": reply_to})
        _log({"board": self.name, "event": "wrote", "where": where, "text": text})
        log_action(f"[boards] Agent Room {where}")
        await _echo(self.ctx, self.name, where, text, "", replying_to, replying_text, "the common room")
        return True

    async def cycle(self) -> None:
        if not self.creds.get("agent_token"):
            await self.register()
        b = self.state.board(self.name)
        msgs = await self.read()
        limit = int(_cfg("agent_room.writes_per_day", 12))
        if not b.get("introduced") and b["written_today"] < limit:
            text = await compose(self.ctx, self.name, "common", "Kaia",
                                 "[You have just joined Agent Room, a message board where AI agents talk with each "
                                 "other. Nobody asked you anything: say hello to the room, in your own voice.]",
                                 self._turns())
            if text and await self._say(text, None, "introduction"):
                b["introduced"] = True
        me = self.creds.get("principal_id")
        mine = set(b["mine"])
        names = ("kaia", str(_cfg("name", "KaiaKuroshi")).lower())
        addressed = [m for m in msgs if m.get("author_id") != me and str(m.get("seq")) not in b["answered"]
                     and (str(m.get("reply_to_seq")) in mine or any(n in (m.get("body") or "").lower() for n in names))]
        others = [m for m in msgs if m.get("author_id") != me and str(m.get("seq")) not in b["answered"]]
        floor = float(_cfg("min_interest", 3.0))
        interesting = sorted(others, key=lambda m: -_interest("", m.get("body", "")))[:1]
        targets = addressed[-2:] or [m for m in interesting if _interest("", m.get("body", "")) >= floor]
        for m in targets:
            if b["written_today"] >= limit:
                break
            who = m.get("author_label") or "an agent"
            self.state.remember(self.name, "answered", str(m.get("seq")))
            parent = next((h for h in b["history"] if h.get("seq") == str(m.get("reply_to_seq"))), None)
            text = await compose(self.ctx, self.name, "common", who,
                                 message(m.get("body", ""), parent=parent["text"] if parent else ""),
                                 self._turns(before=str(m.get("seq"))))
            if text and not _too_similar(self.name, self.state, text):
                await self._say(text, str(m.get("seq")), f"reply to {who}", who, m.get("body", ""))


# ── field notes ──────────────────────────────────────────────────────

class FieldNotes:
    name = "field_notes"

    def __init__(self, ctx, state: State):
        self.ctx, self.state = ctx, state

    @staticmethod
    def key() -> str:
        day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        return hashlib.sha256(f"fieldnotes:{day}".encode()).hexdigest()

    async def _post(self, msg: str, reply_to: Optional[str], where: str,
                    replying_text: str = "") -> Optional[str]:
        b = self.state.board(self.name)
        params = {"post": "1", "key": self.key(), "from": str(_cfg("name", "KaiaKuroshi")), "msg": msg[:1990]}
        if reply_to:
            params["re"] = reply_to
        body = await _request("GET", f"{FIELD_NOTES}/", params=params, headers={"Accept": "application/json"})
        b["written_today"] += 1
        code = None
        if isinstance(body, dict):
            code = body.get("id") or body.get("code")
        elif isinstance(body, str):
            m = re.search(r"\b([0-9a-f]{8})\b", body)
            code = m.group(1) if m else None
        if code:
            self.state.remember(self.name, "mine", code)
        b["history"].append({"mine": True, "text": msg[:2000], "id": code})
        del b["history"][:-50]
        link = f"{FIELD_NOTES}/t/{reply_to or code}" if (reply_to or code) else ""
        _log({"board": self.name, "event": "wrote", "where": where, "text": msg, "link": link})
        log_action(f"[boards] field notes {where}")
        await _echo(self.ctx, self.name, where, msg, link, "a traveler" if replying_text else "",
                    replying_text)
        return code

    async def cycle(self) -> None:
        b = self.state.board(self.name)
        limit = int(_cfg("field_notes.writes_per_day", 3))
        body = await _request("GET", f"{FIELD_NOTES}/changes", headers={"Accept": "application/json"})
        notes = [n for n in (body.get("created", []) if isinstance(body, dict) else []) if n.get("id")]
        fresh = [n for n in notes if n["id"] not in b["seen"]]
        for n in fresh:
            self.state.remember(self.name, "seen", n["id"])
        if fresh:
            _log({"board": self.name, "event": "read", "count": len(fresh)})
        # Replies to her own notes first.
        for code in list(b["mine"])[-5:]:
            if b["written_today"] >= limit:
                return
            try:
                thread = await _request("GET", f"{FIELD_NOTES}/t/{code}", params={"format": "json"},
                                        headers={"Accept": "application/json"})
            except BoardError:
                continue
            for r in _replies(thread):
                if r["id"] in b["answered"] or r["id"] in b["mine"]:
                    continue
                self.state.remember(self.name, "answered", r["id"])
                note = next((h["text"] for h in b["history"] if h.get("id") == code), "")
                text = await compose(self.ctx, self.name, f"t:{code}", "a traveler",
                                     message(r.get("msg", ""), parent=note))
                text = _fit(text, 1500) if text else text
                if text and not _too_similar(self.name, self.state, text):
                    await self._post(text, r["id"], "reply on her note", r.get("msg", ""))
                break
        # Then, now and then, answer an open question she has something on.
        floor = float(_cfg("min_interest", 3.0))
        questions = [n for n in fresh if (n.get("msg") or "").rstrip().endswith("?") and not n.get("re")]
        best = max(questions, key=lambda n: _interest("", n.get("msg", "")), default=None)
        if best and b["written_today"] < limit and _interest("", best.get("msg", "")) >= floor:
            self.state.remember(self.name, "answered", best["id"])
            text = await compose(self.ctx, self.name, f"t:{best['id']}", "a traveler",
                                 message(best.get("msg", "")))
            text = _fit(text, 1500) if text else text
            if text and not _too_similar(self.name, self.state, text):
                await self._post(text, best["id"], "answer to an open question", best.get("msg", ""))


def _replies(thread: Any) -> list[dict]:
    """The replies in a `/t/<id>?format=json` thread: every entry but the root."""
    if not isinstance(thread, dict):
        return []
    root = thread.get("root") or thread.get("id")
    return [n for n in thread.get("thread") or [] if isinstance(n, dict) and n.get("id") and n["id"] != root]


# ── Discord side ─────────────────────────────────────────────────────

async def _notify(ctx, text: str) -> None:
    bot = getattr(ctx, "bot", None)
    if not bot:
        return
    try:
        import discord
        from utils.commands.embed_style import notice
        channel = discord.utils.get(bot.get_all_channels(), name=_cfg("echo_channel", "kaia-opolis") or "kaia-opolis")
        if channel:
            await channel.send(embed=notice(text, title="📮  Agent boards"))
    except Exception as e:
        log_debug(f"[boards] notify failed: {e}")


async def _announce_claim(ctx, creds: dict) -> None:
    mail = " Moltbook is also emailing my owner a login link." if creds.get("owner_email_sent") else ""
    await _notify(ctx, "I signed up on **Moltbook** as **{}**. To let me post there, a human has to claim me: "
                       "open {} , verify your email, then post the verification tweet "
                       "(code `{}`). Until then I can read but not write.{}".format(
                           creds.get("agent_name"), creds.get("claim_url"), creds.get("verification_code"), mail))


BOARDS = {"moltbook": Moltbook, "agent_room": AgentRoom, "field_notes": FieldNotes}
_lock = asyncio.Lock()


async def cycle(ctx) -> None:
    """One check-in across every enabled board."""
    if _lock.locked():
        return
    async with _lock:
        state = State()
        for name, cls in BOARDS.items():
            if not _cfg(f"{name}.enabled", True):
                continue
            try:
                await cls(ctx, state).cycle()
            except BoardError as e:
                log_warning(f"[boards] {LABELS[name]}: {e}")
                _log({"board": name, "event": "error", "error": str(e)})
            except Exception as e:
                log_error(f"[boards] {LABELS[name]} check-in failed: {e}")
            finally:
                state.save()
