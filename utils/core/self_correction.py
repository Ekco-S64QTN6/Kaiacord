"""She corrects herself when a source says she was wrong.

The safety pipeline spends everything on not being wrong out loud; nothing
repaired a claim once it was out. This does, under rules that keep it honest:

- Only claims that were grounded in the first place: a reply whose retrieval
  held reference material (books, documents, knowledge) is recorded with its
  source files, one sentence per checkable fact. Replies reach this lowercased,
  so in practice that means a sentence with a number in it.
- The contradiction comes from a document. The model is shown the claim and
  the source passage that best matches it and asked whether the passage
  contradicts it — never "were you wrong?". A verdict counts only when it
  quotes the passage verbatim, the quote carries a number or name the claim
  doesn't, and it doesn't also repeat every number the claim has.
- At most MAX_PER_DAY a day, and never twice on the same claim.
- The correction names what she said and what the source says.

`features.self_correction: true` posts it in the channel where she said it.
Unset or false, it is recorded in memory/self_corrections.jsonl and logged as
"would correct", so the judgement can be read before she speaks on it.
"""
import asyncio
import hashlib
import json
import os
import re
import threading
import time
import uuid
from typing import List, Optional

from utils.core.atomic_write import write_atomic
from utils.infrastructure.logging.kaia_logger import log_debug, log_info, log_warning
from utils.infrastructure.monitoring.telemetry_paths import telemetry_path

CLAIMS = telemetry_path(os.path.join("memory", "grounded_claims.jsonl"))
CORRECTIONS = telemetry_path(os.path.join("memory", "self_corrections.jsonl"))
KEEP_DAYS = 3
MIN_AGE_SECONDS = 1800
MAX_PER_DAY = 1
MAX_CHECKS_PER_RUN = 6
MIN_OVERLAP = 3
_claims_lock = threading.Lock()          # an append must not land between prune's read and rewrite

_FACT = re.compile(r"\b\d[\d,.]*\b|\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+\b")
_WORD = re.compile(r"[a-z]{4,}")
_SENTENCE = re.compile(r"(?<=[.!?])\s+")


def _id(text: str) -> str:
    return hashlib.sha1(text.strip().lower().encode()).hexdigest()[:16]


def fact_sentences(response: str, original: str = "") -> List[str]:
    """Sentences of the reply that state a checkable fact.

    `response` has been lowercased by the filters; `original` casing, when
    available, is what finds proper names.
    """
    text = original or response
    return [s.strip() for s in _SENTENCE.split(text)
            if 20 <= len(s.strip()) <= 300 and _FACT.search(s)][:4]


def record_claim(channel_id, author: str, question: str, response: str, sources: List[str]) -> None:
    """Keep a grounded reply's factual sentences and where they came from."""
    facts = fact_sentences(response)
    sources = sorted({s for s in sources if s and os.path.isfile(s)})
    if not facts or not sources:
        return
    with _claims_lock, open(CLAIMS, "a", encoding="utf-8") as f:
        for fact in facts:
            f.write(json.dumps({"ts": time.time(), "channel_id": channel_id, "author": author,
                                "question": question[:200], "claim": fact, "id": _id(fact),
                                "sources": sources[:6]}) + "\n")


def _read_jsonl(path: str) -> List[dict]:
    rows = []
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                try:
                    rows.append(json.loads(line))
                except ValueError:
                    pass
    except OSError:
        pass
    return rows


def best_passage(claim: str, sources: List[str]) -> Optional[tuple]:
    """(source, paragraph) sharing the most distinctive words with the claim."""
    want = set(_WORD.findall(claim.lower()))
    best, best_score = None, MIN_OVERLAP - 1
    for src in sources:
        try:
            with open(src, encoding="utf-8", errors="replace") as f:
                text = f.read()
        except OSError:
            continue
        for para in re.split(r"\n\s*\n", text):
            para = " ".join(para.split())
            if not 40 <= len(para) <= 2500:
                continue
            score = len(want & set(_WORD.findall(para.lower())))
            if score > best_score:
                best, best_score = (src, para), score
    return best


def accept(claim: str, passage: str, verdict: dict) -> Optional[str]:
    """The quote that shows the contradiction, if the verdict stands up."""
    if not isinstance(verdict, dict) or verdict.get("contradicts") is not True:
        return None
    quote = " ".join(str(verdict.get("quote", "")).split()).strip(' "')
    if len(quote) < 8 or quote.lower() not in passage.lower():
        return None
    # Her replies are lowercased, so compare as lowercase text.
    # A number must match exactly; a name counts as the same if any of its
    # words is in the claim ("the Hugo Award" / "the hugo").
    words = set(re.findall(r"[a-z]+", claim.lower()))
    numbers = {n.rstrip(".,") for n in re.findall(r"\d[\d,.]*", claim)}
    # A quote that repeats every number the claim has is restating it, not
    # contradicting it ("300 megawatts, 1 gigawatt" against "a 1 gigawatt").
    if numbers and numbers <= {n.rstrip(".,") for n in re.findall(r"\d[\d,.]*", quote)}:
        return None
    # About the same thing: the sentence the quote comes from shares a word of
    # the claim's subject. Of five verdicts recorded as contradictions, a
    # sentence about one model's benchmark "contradicted" praise for isolating a PR.
    if not _content_stems(claim) & _content_stems(_sentence_of(quote, passage)):
        return None
    new = [f for f in _FACT.findall(quote)
           if (_replaces_a_number(f, numbers) if f[0].isdigit()
               else not words & set(f.lower().split()))]
    return quote if new else None


def _number(text: str) -> Optional[float]:
    try:
        return float(text.replace(",", "").rstrip("."))
    except ValueError:
        return None


def _replaces_a_number(figure: str, numbers: set) -> bool:
    """A figure in the quote contradicts the claim only in place of one the claim
    gave, of the same size: 1984 for 1986, Opus 4.6 for 4.8. A figure the claim
    never stated is detail ("borrowed Ṁ5,000" against "claude opus 4.6 borrowing")."""
    if figure.rstrip(".,") in numbers:
        return False
    value = _number(figure)
    for n in numbers:
        other = _number(n)
        if value and other and 0.1 <= value / other <= 10:
            return True
    return False


def _sentence_of(quote: str, passage: str) -> str:
    """The passage sentence the quote was copied from (the quote if not found)."""
    low = quote.lower()
    for sentence in re.split(r"(?<=[.!?])\s+", passage or ""):
        if low in " ".join(sentence.split()).lower():
            return sentence
    return quote
_STOPWORDS = frozenset("that this with from have were they their there what which about would could "
                       "should into just like been being also than then them these those your over "
                       "only some such very more most much".split())


def _content_stems(text: str) -> set:
    """Words of four letters or more, a plural or -ing folded, stopwords out."""
    out = set()
    for w in re.findall(r"[a-z]{4,}", (text or "").lower()):
        if w in _STOPWORDS:
            continue
        for suffix in ("ing", "ed", "es", "s"):
            if w.endswith(suffix) and len(w) - len(suffix) >= 4:
                w = w[: -len(suffix)]
                break
        out.add(w)
    return out


def _prompt(claim: str, passage: str) -> str:
    return (
        "A statement and a passage from its source follow.\n\n"
        f'STATEMENT: "{claim}"\n\nPASSAGE: "{passage}"\n\n'
        "Does the passage directly contradict the statement — a different number, date, "
        "name or fact about the same thing? Different emphasis, missing detail or a passage "
        "about something else is NOT a contradiction.\n"
        'Reply with JSON only: {"contradicts": true|false, '
        '"quote": "the exact words from the passage that contradict it, copied verbatim"}'
    )


def correction_text(entry: dict) -> str:
    title = os.path.splitext(os.path.basename(entry["source"]))[0].replace("_", " ")
    who = f" to {entry['author']}" if entry.get("author") else ""
    return (f"correction on something i said{who} earlier. i said: \"{entry['claim']}\" "
            f"{title} says: \"{entry['quote']}\". i had that wrong.")


async def check(ctx, now: Optional[float] = None) -> int:
    """Check recent grounded claims against their sources. Returns corrections made."""
    from utils.infrastructure.gpu.gpu_manager import GPUTaskPriority, chat_options, gpu_memory_manager
    now = now or time.time()
    def _prune():
        with _claims_lock:
            kept = [c for c in _read_jsonl(CLAIMS) if now - c.get("ts", 0) <= KEEP_DAYS * 86400]
            write_atomic(CLAIMS, "".join(json.dumps(c) + "\n" for c in kept))
            return kept
    claims = await asyncio.to_thread(_prune)
    done = await asyncio.to_thread(_read_jsonl, CORRECTIONS)
    seen = {d["id"] for d in done}
    today = time.strftime("%Y-%m-%d", time.localtime(now))
    made_today = sum(1 for d in done if d.get("date") == today and d.get("verdict") == "contradicted")
    if made_today >= MAX_PER_DAY:
        return 0
    post = ctx.config.get("features.self_correction", False) is True
    model = ctx.config.chat_model
    checked = made = 0
    for c in claims:
        if c["id"] in seen or now - c["ts"] < MIN_AGE_SECONDS or checked >= MAX_CHECKS_PER_RUN:
            continue
        seen.add(c["id"])
        found = await asyncio.to_thread(best_passage, c["claim"], c["sources"])
        entry = {"id": c["id"], "date": today, "ts": now, "claim": c["claim"],
                 "channel_id": c["channel_id"], "author": c.get("author", "")}
        if not found:
            entry["verdict"] = "no_passage"
        else:
            checked += 1
            source, passage = found
            try:
                resp = await gpu_memory_manager.run_with_gpu_guard(
                    model_name=model, priority=GPUTaskPriority.BACKGROUND,
                    coro=asyncio.wait_for(ctx.ollama_client.chat(
                        model=model, messages=[{"role": "user", "content": _prompt(c["claim"], passage)}],
                        options=chat_options(temperature=0.0, num_predict=160), format="json",
                        keep_alive=-1), timeout=120),
                    task_id=f"selfcheck_{uuid.uuid4().hex[:8]}")
                quote = accept(c["claim"], passage, json.loads(resp["message"]["content"]))
            except Exception as e:
                log_debug(f"Self-check of a claim failed: {type(e).__name__}: {e}")
                continue
            entry.update(source=source, verdict="contradicted" if quote else "consistent",
                         quote=quote or "")
        with open(CORRECTIONS, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
        if entry["verdict"] != "contradicted":
            continue
        text = correction_text(entry)
        if not post:
            log_info(f"[SELF_CORRECTION] would correct (features.self_correction is off): {text[:160]}")
        else:
            try:
                channel = ctx.bot.get_channel(int(c["channel_id"]))
                if channel is None:
                    log_warning("Self-correction not posted: its channel is gone.")
                    continue
                from utils.core import unprompted
                from utils.infrastructure.system.messaging import send_kaia_response
                delivered = False
                for message in unprompted.compose(unprompted.pick_label("correction"), text):
                    delivered = await send_kaia_response(channel, message) or delivered
                if not delivered:
                    log_warning("Self-correction not posted: Discord refused the message.")
                    continue
                log_info(f"[SELF_CORRECTION] posted: {text[:160]}")
            except Exception as e:
                log_warning(f"Self-correction not posted: {type(e).__name__}: {e}")
                continue
        made += 1
        if made_today + made >= MAX_PER_DAY:
            break
    return made
