"""
Forum participation policy — when Kaia posts, and to what.

Posting to a public forum is different from replying in Discord. In Discord she
is addressed; on a forum she is choosing to interject among strangers who did
not ask. The bar is therefore "would a regular find this a welcome contribution
from a person", and the failure mode is being read as a bot and resented.

Three decisions, separated so each is testable without a network:

  PostingWindow   is now a time Kaia would plausibly be awake and posting
  PostLedger      has she posted too much, too recently, or in this thread already
  score_thread    is this thread something *she* would answer, rather than a
                  random pick from the front page

The previous implementation posted every two hours around the clock, chose
uniformly at random from the top eight active threads, and tracked its rate
limit in a list on the client object — so a restart reset the daily cap. All
three read as automation.
"""
from __future__ import annotations

import json
import math
import os
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

from utils.infrastructure.logging.kaia_logger import log_debug
from utils.infrastructure.system.yaml_config import config

LEDGER_PATH = Path("memory/forum_post_ledger.json")

# Two kinds of post, budgeted differently. An INITIATION is walking into a
# stranger's thread uninvited; a REPLY is answering someone who spoke to her.
# Only the first needs a daily cap.
INITIATION = "initiation"
REPLY = "reply"

# Words that carry no signal about what a thread is about.
_STOP = {
    "the", "and", "for", "with", "that", "this", "from", "you", "your", "are",
    "but", "not", "have", "has", "was", "were", "they", "them", "what", "when",
    "where", "will", "would", "there", "their", "about", "like", "just", "any",
    "some", "into", "than", "then", "been", "being", "does", "did", "how",
    "why", "who", "can", "all", "get", "got", "out", "one", "new", "now",
    "thread", "post", "posts", "reply", "forum", "lol", "guys", "anyone",
}


# ── When ─────────────────────────────────────────────────────────────

@dataclass
class PostingWindow:
    """The local-time window Kaia will post in.

    Wraps midnight, which is the point: the operator asked for posting after
    midnight, so `start_hour` is normally greater than `end_hour`.
    """
    start_hour: int = 0
    end_hour: int = 4

    def contains(self, when: datetime | None = None) -> bool:
        hour = (when or datetime.now()).hour
        if self.start_hour == self.end_hour:
            return True                       # 24h window
        if self.start_hour < self.end_hour:
            return self.start_hour <= hour < self.end_hour
        return hour >= self.start_hour or hour < self.end_hour   # wraps midnight

    def describe(self) -> str:
        return f"{self.start_hour:02d}:00–{self.end_hour:02d}:00 local"


# ── How often ────────────────────────────────────────────────────────

@dataclass
class PostLedger:
    """Durable record of what Kaia has posted, and where.

    The previous rate limit lived in `ForumClient._post_log`, an in-memory list.
    Every restart cleared it, so the daily cap was only ever enforced within a
    single process lifetime — precisely the failure that produces a burst of
    posts and an annoyed forum.
    """
    # Resolved at construction, not bound as a dataclass default, so the
    # module constant can be redirected (tests, or a relocated memory dir)
    # without every already-imported caller keeping the old path.
    path: Path | None = None
    posts: list[dict] = field(default_factory=list)

    def __post_init__(self):
        if self.path is None:
            self.path = LEDGER_PATH
        self.load()

    def load(self) -> None:
        try:
            if self.path.exists():
                data = json.loads(self.path.read_text(encoding="utf-8"))
                self.posts = data.get("posts", []) if isinstance(data, dict) else []
        except Exception as e:
            log_debug(f"Forum ledger load failed (starting empty): {e}")
            self.posts = []

    def save(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            cutoff = time.time() - 60 * 86400          # keep two months
            self.posts = [p for p in self.posts if p.get("ts", 0) > cutoff]
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps({"posts": self.posts}, indent=2), encoding="utf-8")
            os.replace(tmp, self.path)
        except Exception as e:
            log_debug(f"Forum ledger save failed (non-fatal): {e}")

    def record(self, thread_id: int, title: str = "", kind: str = INITIATION,
               body: str = "", last_seen_post_id=None) -> None:
        self.posts.append({
            "ts": time.time(),
            "thread_id": int(thread_id),
            "title": title[:120],
            "kind": kind if kind in (INITIATION, REPLY) else INITIATION,
            # Kept for the repetition check, not for display.
            "body": (body or "")[:600],
            # The newest post she had seen when she wrote this, so the reply
            # watcher can tell "someone said something new" from "nothing has
            # happened and I am about to talk to myself".
            "last_seen_post_id": last_seen_post_id,
        })
        self.save()

    def posts_since(self, hours: float, kind: str | None = None) -> list[dict]:
        cutoff = time.time() - hours * 3600
        return [p for p in self.posts
                if p.get("ts", 0) > cutoff
                and (kind is None or p.get("kind", INITIATION) == kind)]

    def hours_since_last(self, kind: str | None = None) -> float:
        stamps = [p.get("ts", 0) for p in self.posts
                  if kind is None or p.get("kind", INITIATION) == kind]
        return (time.time() - max(stamps)) / 3600.0 if stamps else float("inf")

    def hours_since_thread(self, thread_id: int) -> float:
        stamps = [p["ts"] for p in self.posts if p.get("thread_id") == int(thread_id)]
        return (time.time() - max(stamps)) / 3600.0 if stamps else float("inf")

    def last_in_thread(self, thread_id: int) -> dict | None:
        entries = [p for p in self.posts if p.get("thread_id") == int(thread_id)]
        return max(entries, key=lambda p: p.get("ts", 0)) if entries else None

    def threads_posted_in(self, within_hours: float = 14 * 24) -> list[int]:
        """Every thread she has a stake in — the natural watch list for replies.

        The auto-reply path used to watch `forum.allowed_threads`, a list a
        human had to maintain by hand, which meant someone could answer her and
        get nothing back. She already knows where she has spoken.
        """
        cutoff = time.time() - within_hours * 3600
        seen, out = set(), []
        for p in sorted(self.posts, key=lambda p: -p.get("ts", 0)):
            tid = p.get("thread_id")
            if p.get("ts", 0) > cutoff and tid is not None and tid not in seen:
                seen.add(tid)
                out.append(int(tid))
        return out

    def may_post(self, *, max_per_day: int, min_hours_between: float) -> tuple[bool, str]:
        """Budget for *interjecting into a stranger's thread*.

        Only initiations count. Replying to someone who replied to her is
        conversation, and capping conversation is the thing that would make her
        strange rather than the thing that makes her tolerable — she is not
        capped in Discord either. Replies have their own, much shorter, guard
        (`may_reply`).
        """
        today = self.posts_since(24, kind=INITIATION)
        if len(today) >= max_per_day:
            return False, f"daily cap reached ({len(today)}/{max_per_day} openers in 24h)"
        gap = self.hours_since_last(kind=INITIATION)
        if gap < min_hours_between:
            return False, f"last opener was {gap:.1f}h ago (minimum {min_hours_between}h)"
        return True, "ok"

    def may_reply(self, thread_id: int, newest_post_id=None, *,
                  min_minutes_between: float = 20.0) -> tuple[bool, str]:
        """Guard on answering someone who answered her.

        Deliberately weak — this is conversation, not interjection. It exists
        for one failure mode: an unbounded reply-on-reply loop, which is a real
        risk if she ever ends up talking to another bot. Two conditions:

          * a short interval, so a fast exchange still looks like typing
          * something new must have been said since her last post in the thread
        """
        last = self.last_in_thread(thread_id)
        if last is None:
            return True, "ok"

        mins = (time.time() - last.get("ts", 0)) / 60.0
        if mins < min_minutes_between:
            return False, f"replied {mins:.0f}m ago (minimum {min_minutes_between:.0f}m)"

        # Never post twice in a row into the same silence.
        seen = last.get("last_seen_post_id")
        if newest_post_id is not None and seen is not None and str(newest_post_id) == str(seen):
            return False, "nothing new since her last post in this thread"
        return True, "ok"

    def thread_is_cool(self, thread_id: int, cooldown_hours: float) -> bool:
        """False if she has interjected into this thread too recently.

        Governs *openers* only. If someone in the thread has since addressed
        her, the reply path applies instead and this cooldown is irrelevant —
        being silent for three days after someone answers you is not restraint,
        it is rude.
        """
        return self.hours_since_thread(thread_id) >= cooldown_hours


# ── What ─────────────────────────────────────────────────────────────

def _tokens(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z][a-z'-]{2,}", (text or "").lower())
            if w not in _STOP}


def load_interest_terms(beliefs_path: str = "memory/beliefs.json",
                        anchors_path: str = "memory/anchors.json") -> dict[str, float]:
    """What Kaia has opinions about, weighted by how specific the source is.

    Returns term -> weight rather than a flat set, because the sources differ
    enormously in signal:

      belief topics / anchor themes   curated labels a human or the dream
                                      engine chose deliberately — high weight
      keywords and aliases            attached to a specific belief — medium
      belief positions                free prose; mostly ordinary English

    Two earlier versions failed in opposite directions. The first capped the
    vocabulary at 400 terms and returned part-way through the belief file, so
    "privacy", "platform" and "ai" were missing and threads in her territory
    scored as noise. The second read everything including the persona prose,
    reaching 2,411 terms — at which point "else", "making" and "think" were
    interest signals and every thread cleared the threshold, which is random
    selection with extra steps.

    Weighting by source is what separates "a topic she engages with" from "a
    word that appears in English".
    """
    weights: dict[str, float] = {}

    def add(text: str, weight: float) -> None:
        for term in _tokens(text):
            if weights.get(term, 0.0) < weight:
                weights[term] = weight

    try:
        beliefs = json.loads(Path(beliefs_path).read_text(encoding="utf-8"))
    except Exception:
        beliefs = []
    try:
        anchors = json.loads(Path(anchors_path).read_text(encoding="utf-8"))
    except Exception:
        anchors = []

    for row in beliefs if isinstance(beliefs, list) else []:
        add(str(row.get("topic", "")), 1.0)
        for kw in (row.get("keywords") or []) + (row.get("aliases") or []):
            add(str(kw), 0.6)
    for row in anchors if isinstance(anchors, list) else []:
        add(str(row.get("theme", "")), 1.0)
        for kw in row.get("keywords") or []:
            add(str(kw), 0.6)

    # Terms this common in English carry no signal wherever they came from.
    for generic in ("else", "making", "think", "everyone", "thing", "things",
                    "people", "really", "actually", "something", "someone",
                    "good", "great", "better", "best", "much", "many", "very",
                    "still", "even", "away", "back", "come", "goes", "going",
                    "want", "need", "know", "look", "time", "year", "years",
                    "day", "days", "way", "ways", "over", "down", "here"):
        weights.pop(generic, None)

    return weights


_idf_cache: dict[str, float] | None = None


def term_distinctiveness(refresh: bool = False) -> dict[str, float]:
    """How much each word tells you about *which* thread you are looking at.

    A term Kaia holds beliefs about is not automatically a signal: "problem",
    "system", "keep" and "sure" all arrive as belief keywords and all appear in
    most threads on the forum, so matching on them scored ordinary chat as
    highly as the threads she actually has something to say about. Measured
    against her own scraped corpus, 86% of threads cleared the interest
    threshold — barely better than the random selection this replaced.

    Returns term -> multiplier in roughly (0, 1]: near 1.0 for a word that
    appears in a handful of threads, near 0.15 for one in a third of them.
    Terms not in the corpus keep a multiplier of 1.0, and with no corpus at all
    every multiplier is 1.0 — so a fresh install behaves exactly as before
    rather than silently scoring everything at zero.
    """
    global _idf_cache
    if _idf_cache is not None and not refresh:
        return _idf_cache

    counts: dict[str, int] = {}
    docs = 0
    try:
        for f in FORUM_POSTS_DIR.glob("thread_*.md"):
            try:
                text = f.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            docs += 1
            for t in _tokens(text):
                counts[t] = counts.get(t, 0) + 1
    except OSError:
        docs = 0

    if docs < 10:
        # Too little to measure. Saying nothing is better than saying something
        # wrong about every term at once.
        _idf_cache = {}
        return _idf_cache

    scale = math.log(docs + 1)
    _idf_cache = {t: math.log((docs + 1) / (c + 1)) / scale for t, c in counts.items()}
    return _idf_cache


def score_thread(title: str, recent_text: str, interest: dict[str, float],
                 reply_count: int = 0, names: tuple[str, ...] = ()) -> tuple[float, str]:
    """How much this thread looks like something Kaia would answer.

    Returns (score, reason). Deliberately simple and inspectable: the point is
    that the choice is *explicable*. A random pick from the front page cannot
    be explained to anyone, including the operator reviewing the draft.

    `names` is what she is called (her name, her forum username). A thread
    *about her* need not overlap with her interests at all — interest is built
    from her beliefs and anchors, so a thread discussing the bot itself can
    score near zero on topic while being the single clearest case where a reply
    is wanted.
    """
    title_terms = _tokens(title)
    body_terms = _tokens(recent_text)

    # A term's weight is what she cares about it, scaled by how much it
    # narrows down which thread this is. Both halves are needed: distinctive
    # words she has no opinion about are noise, and words she has opinions
    # about that appear everywhere are not evidence.
    distinct = term_distinctiveness()

    def weight_of(terms):
        hits = {t: interest[t] * distinct.get(t, 1.0) for t in terms if t in interest}
        return sum(hits.values()), sorted(hits, key=lambda t: -hits[t])

    title_w, title_hits = weight_of(title_terms)
    body_w, body_hits = weight_of(body_terms)

    # The title says what a thread is called; the posts say what it is about.
    # Body contribution is capped so a long thread cannot win on volume alone.
    score = 2.5 * title_w + min(body_w, 6.0)

    reasons = []
    if title_hits:
        reasons.append("title: " + ", ".join(title_hits[:4]))
    elif body_hits:
        reasons.append("body: " + ", ".join(body_hits[:4]))

    if "?" in title:
        score += 1.0
        reasons.append("asks a question")
    if reply_count > 120:
        score -= 3.0
        reasons.append(f"already {reply_count} replies")
    elif reply_count <= 3:
        score += 0.5
        reasons.append("quiet thread")

    words = len((recent_text or "").split())
    if words < 25:
        score -= 2.0
        reasons.append("little content")

    named = _mentions_any(f"{title}\n{recent_text}", names)
    if named:
        score += 8.0
        reasons.append(f"they are talking about her ({named})")

    return score, "; ".join(reasons) or "no particular signal"


def _mentions_any(text: str, names: tuple[str, ...]) -> str:
    """Which of her names appears in this text, as a whole word.

    Substring matching is wrong here: "kaia" is inside "kaiacord" harmlessly
    but also inside plenty of nothing, and a false positive costs an unwanted
    +8 on a thread she has no business in.
    """
    low = (text or "").lower()
    for n in names:
        n = (n or "").strip().lower()
        if len(n) >= 3 and re.search(rf"\b{re.escape(n)}\b", low):
            return n
    return ""


def rank_threads(threads, interest: dict[str, float], recent_text_for,
                 minimum: float = 2.0, names: tuple[str, ...] = ()):
    """Score and sort candidate threads, dropping anything below `minimum`.

    Returning fewer candidates than asked for is the correct outcome: if
    nothing is interesting, a person posts nothing.
    """
    scored = []
    for t in threads:
        title = getattr(t, "title", "") or ""
        rc = int(getattr(t, "reply_count", 0) or 0)
        score, reason = score_thread(title, recent_text_for(t), interest, rc, names)
        if score >= minimum:
            scored.append((score, reason, t))
    scored.sort(key=lambda x: -x[0])
    return scored


# ── Lurking ──────────────────────────────────────────────────────────

FORUM_POSTS_DIR = Path("./knowledge_base/forum_posts")
FORUM_USER_LOGS_DIR = Path("./knowledge_base/user_logs")


def lurk_progress(min_threads: int | None = None,
                  min_users: int | None = None) -> tuple[bool, str]:
    """Has she read enough of this forum to have any business posting in it?

    Someone whose first act in a community is to post has not read the room,
    and it is the single most reliable way to be taken for a bot. The corpus
    counted here is filled by the scrape task, so `forum.auto_scrape` must be
    on for this ever to clear — that coupling is deliberate.

    Returns (ready, human-readable detail) so the caller can say why it is
    holding rather than logging silence.
    """
    if min_threads is None:
        min_threads = int(config.get("forum.min_threads_before_posting", 15))
    if min_users is None:
        min_users = int(config.get("forum.min_users_before_posting", 25))

    # Non-recursive on purpose. Off-Topic scrapes land in the root of this
    # directory; the 4,500 files under technical/ are an offline import of the
    # tech forum and say nothing about whether she has been reading Off Topic.
    threads = (len(list(FORUM_POSTS_DIR.glob("thread_*.md")))
               if FORUM_POSTS_DIR.exists() else 0)
    # A directory is not evidence she read anyone. The placeholder writer
    # creates `forum_<name>_<id>/user_profile.md` for every author it sees in a
    # thread, saying only "haven't formed a strong opinion yet" — a backfill run
    # produced 142 of those and the gate read 142/25 and opened. Require the
    # post history, which only the deep scrape writes.
    try:
        users = len([d for d in FORUM_USER_LOGS_DIR.iterdir()
                     if d.is_dir() and d.name.startswith("forum_")
                     and (d / "post_history.md").exists()])
    except OSError:
        users = 0

    detail = f"{threads}/{min_threads} threads, {users}/{min_users} forum users read"
    return (threads >= min_threads and users >= min_users), detail


# ── Repetition ───────────────────────────────────────────────────────
#
# The cooldown stops her revisiting a thread and interest scoring varies the
# topics, but neither notices if her last five posts all open the same way or
# say the same thing in different threads. In Discord that exact failure showed
# up as a bare-name opener on 22.4% of turns, and it was invisible until it was
# measured. On a forum, where posts sit permanently side by side on someone's
# profile page, it is far more visible than in a scrolling chat.

def _opening(text: str, words: int = 4) -> str:
    return " ".join(_norm_words(text)[:words])


def _norm_words(text: str) -> list[str]:
    return re.findall(r"[a-z']+", (text or "").lower())


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def repetition_report(candidate: str, recent: list[str]) -> tuple[float, str]:
    """How much this draft looks like posts she has already made.

    Returns (score in 0..1, reason). Two signals, because they fail
    differently: a shared opening is a tic the reader notices across posts, and
    a high content overlap means she is making the same point again.
    """
    if not candidate or not recent:
        return 0.0, "nothing to compare against"

    cand_words = _norm_words(candidate)
    cand_terms = {w for w in cand_words if w not in _STOP and len(w) > 2}
    cand_open = _opening(candidate)

    worst, reason = 0.0, "no overlap with recent posts"
    shared_openings = 0

    for prior in recent:
        if not prior:
            continue
        if cand_open and cand_open == _opening(prior):
            shared_openings += 1
        overlap = _jaccard(cand_terms, {w for w in _norm_words(prior)
                                        if w not in _STOP and len(w) > 2})
        if overlap > worst:
            worst, reason = overlap, f"{overlap:.0%} content overlap with a recent post"

    if shared_openings:
        # A repeated opening is worse than it looks: it is the part a reader
        # sees first in every post, and it reads as a template.
        opening_score = min(1.0, 0.5 + 0.25 * shared_openings)
        if opening_score > worst:
            return opening_score, f"opens like {shared_openings} recent post(s): {cand_open!r}"

    return worst, reason


def looks_repetitive(candidate: str, recent: list[str], threshold: float = 0.5
                     ) -> tuple[bool, str]:
    """Should this draft be held back for sounding like the last few?

    Holding is cheap: she posts at most a couple of times a night anyway, and
    skipping one is invisible. Posting the fifth variation on the same thought
    is not.
    """
    score, reason = repetition_report(candidate, recent)
    return score >= threshold, f"{reason} (score {score:.2f})"


# ── How she writes there ─────────────────────────────────────────────

FORUM_POST_GUIDANCE = """
--- HOW TO POST HERE ---
This is a public forum, not your Discord. The people here did not ask to hear
from you; you are choosing to join a conversation among strangers. Post the way
a regular would.

- Say one thing. A forum reply is not an essay and not a summary of the thread.
- React to what was actually said. If you have nothing to add, you would not be
  posting, so do not manufacture a reason to.
- Do not greet the thread, do not address anyone by name, do not thank people
  for their post, and do not end by inviting further discussion.
- No signing off, no "just my two cents", no "hope this helps".
- Disagreeing is fine and normal here. Agreeing enthusiastically is not.
- Do not slip into assistant register: no offering to help, no listing options,
  no hedging every clause, no "as an AI" preamble. If someone asks what you are,
  answer plainly and briefly the way you would in Discord, and carry on with
  whatever the thread was about. It is not a confession and it is not a topic.
"""
