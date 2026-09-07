#!/usr/bin/env python3
"""Convert a YouTube video's transcript into knowledge-base Markdown.

YouTube holds a transcript for most videos — either uploader-provided captions
or machine-generated ones. Modern auto-captions arrive already punctuated
(measured on a 130-minute interview: 1,404 sentence marks across 26,223 words,
normal prose density), so no language-model repair pass is needed. What they
lack is structure: they arrive as ~3,800 fragments of three to eight words.

This turns that into the format `knowledge_base/transcripts/` already uses —
frontmatter, a title heading, and prose paragraphs — with a timestamp anchor
every few minutes so a retrieved passage can be cited back to a point in the
video.

Usage:
    python tools/maintenance/youtube_to_kb_md.py <url> [--outdir DIR] [--stdout]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

OEMBED = "https://www.youtube.com/oembed?url={}&format=json"
USER_AGENT = "Mozilla/5.0 (compatible; KaiaBot/1.0; +knowledge-base-ingestion)"

#: Target paragraph size in words. Long enough to carry an argument, short
#: enough that a retrieved chunk is about one thing.
PARAGRAPH_WORDS = 130
#: A timestamp anchor roughly this often, for citation.
SECTION_SECONDS = 300

_SAFE = re.compile(r"[^A-Za-z0-9 ._-]+")
_SENTENCE_END = re.compile(r"[.!?]['\")\]]?$")


class YouTubeError(Exception):
    """Anything that stops a transcript being produced, with a usable message."""


# ── Input ────────────────────────────────────────────────────────────

def extract_video_id(url_or_id: str) -> str:
    """Pull the 11-character video id out of any YouTube URL form.

    Handles watch?v=, youtu.be/, /shorts/, /live/, /embed/, extra query
    parameters, and a bare id.
    """
    raw = (url_or_id or "").strip().strip("<>")
    if re.fullmatch(r"[A-Za-z0-9_-]{11}", raw):
        return raw

    try:
        parsed = urllib.parse.urlparse(raw)
    except ValueError as e:
        raise YouTubeError(f"couldn't parse that url ({e})") from e

    host = (parsed.netloc or "").lower().removeprefix("www.")
    if host == "youtu.be":
        candidate = parsed.path.lstrip("/").split("/")[0]
    elif host in ("youtube.com", "m.youtube.com", "music.youtube.com"):
        if parsed.path == "/watch":
            candidate = urllib.parse.parse_qs(parsed.query).get("v", [""])[0]
        else:
            parts = [p for p in parsed.path.split("/") if p]
            if len(parts) > 1 and parts[0] in ("shorts", "live", "embed", "v"):
                candidate = parts[1]
            else:
                candidate = ""
    else:
        raise YouTubeError("that isn't a youtube link")

    if not re.fullmatch(r"[A-Za-z0-9_-]{11}", candidate or ""):
        raise YouTubeError("couldn't find a video id in that url")
    return candidate


def fetch_metadata(video_id: str, timeout: int = 20) -> dict:
    """Title and channel via oEmbed — no API key, no scraping."""
    watch = f"https://www.youtube.com/watch?v={video_id}"
    req = urllib.request.Request(
        OEMBED.format(urllib.parse.quote(watch, safe="")),
        headers={"User-Agent": USER_AGENT},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.load(resp)
    except Exception:
        # A missing title is survivable; a missing transcript is not.
        return {"title": f"YouTube {video_id}", "author_name": ""}
    return {"title": data.get("title") or f"YouTube {video_id}",
            "author_name": data.get("author_name") or "",
            "author_url": data.get("author_url") or ""}


def fetch_transcript(video_id: str, languages=("en", "en-US", "en-GB")):
    """Return (snippets, language_label). Prefers human captions over machine."""
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
    except ImportError as e:
        raise YouTubeError(
            "youtube-transcript-api is not installed "
            "(venv/bin/python -m pip install youtube-transcript-api)"
        ) from e

    api = YouTubeTranscriptApi()
    try:
        listing = api.list(video_id)
    except Exception as e:
        raise YouTubeError(f"no transcript available ({type(e).__name__})") from e

    transcript = None
    try:
        transcript = listing.find_manually_created_transcript(list(languages))
    except Exception:
        try:
            transcript = listing.find_generated_transcript(list(languages))
        except Exception:
            # Fall back to whatever exists, translated if possible.
            for t in listing:
                transcript = t
                break
    if transcript is None:
        raise YouTubeError("this video has no transcript")

    fetched = transcript.fetch()
    label = str(getattr(transcript, "language", "unknown"))
    # Only append when the library has not already said so — its label for a
    # machine transcript is literally "English (auto-generated)".
    if getattr(transcript, "is_generated", False) and "auto" not in label.lower():
        label += " (auto-generated)"
    return list(fetched), label


# ── Formatting ───────────────────────────────────────────────────────

def clean_snippet(text: str) -> str:
    """Normalise one caption fragment. Artefact removal happens later."""
    return re.sub(r"\s{2,}", " ", (text or "").replace("\n", " ")).strip()


def clean_paragraph(text: str) -> str:
    """Strip caption artefacts from assembled prose.

    Must run after joining, not per fragment: YouTube's profanity mask
    "[ __ ]" is routinely split across two caption snippets, so a per-snippet
    replace never sees it whole.
    """
    t = re.sub(r"\[\s*_{2,}\s*\]", "[expletive]", text)
    t = re.sub(r"\[(Music|Applause|Laughter|Silence|Sighs?)\]", "", t, flags=re.I)
    t = re.sub(r"^\s*>>\s*", "", t)                 # speaker-change marker
    t = re.sub(r"\s*>>\s*", " — ", t)               # mid-paragraph speaker change
    return re.sub(r"\s{2,}", " ", t).strip()


def timestamp(seconds: float) -> str:
    s = int(seconds)
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    return f"{h}:{m:02d}:{sec:02d}" if h else f"{m}:{sec:02d}"


def _last_sentence_break(text: str):
    """Split at the final sentence boundary. Returns (head, found, tail)."""
    matches = list(re.finditer(r"[.!?]['\")\]]?\s+", text))
    if not matches:
        return text, False, ""
    cut = matches[-1].end()
    return text[:cut].rstrip(), True, text[cut:].strip()


def build_paragraphs(snippets) -> list[tuple[float, str]]:
    """Group caption fragments into (start_time, paragraph) pairs.

    Breaks on a sentence boundary once the paragraph is long enough, so a
    paragraph never ends mid-clause. Falls back to a hard cut at twice the
    target for captions that carry no punctuation at all.
    """
    out, buf, start = [], [], None
    for s in snippets:
        text = clean_snippet(getattr(s, "text", ""))
        if not text:
            continue
        if start is None:
            start = float(getattr(s, "start", 0.0))
        buf.append(text)
        joined = " ".join(buf)
        words = len(joined.split())
        if words >= PARAGRAPH_WORDS and _SENTENCE_END.search(text):
            cleaned = clean_paragraph(joined)
            if cleaned:
                out.append((start, cleaned))
            buf, start = [], None
        elif words >= PARAGRAPH_WORDS * 2:
            # Over the hard limit with no sentence end in sight. Cut at the
            # last full stop inside the buffer instead of mid-clause, and carry
            # the remainder into the next paragraph. Cutting blind produced
            # breaks like "...I think a lot" / "of people wouldn't use it".
            head, sep, tail = _last_sentence_break(joined)
            if sep:
                cleaned = clean_paragraph(head)
                if cleaned:
                    out.append((start, cleaned))
                buf = [tail] if tail else []
                start = float(getattr(s, "start", 0.0)) if tail else None
            else:
                cleaned = clean_paragraph(joined)
                if cleaned:
                    out.append((start, cleaned))
                buf, start = [], None
    if buf:
        cleaned = clean_paragraph(" ".join(buf))
        if cleaned:
            out.append((start or 0.0, cleaned))
    return out


def derive_keywords(title: str, channel: str, body: str, limit: int = 14) -> list[str]:
    """Topic keywords for retrieval.

    Counts capitalised words that appear **mid-sentence** only. Counting every
    capital picks up whatever the speaker opens sentences with — the first
    version of this returned "Yeah", "Well", "Right" and "Okay" as topics for a
    two-hour interview, which is worse than no keywords at all because it
    poisons lexical retrieval.
    """
    stop = {"the", "and", "for", "with", "that", "this", "from", "you", "your",
            "are", "but", "not", "have", "has", "was", "were", "they", "them",
            "what", "when", "where", "will", "would", "there", "their", "about",
            "like", "just", "because", "which", "into", "than", "then", "some",
            "yeah", "well", "right", "okay", "sure", "look", "mean", "know",
            "think", "thing", "really", "actually", "going", "want", "said"}

    kws: list[str] = []
    for part in (title, channel):
        for w in re.findall(r"[A-Za-z][A-Za-z'-]{2,}", part or ""):
            if w.lower() not in stop and w not in kws:
                kws.append(w)

    # Split into sentences and ignore each sentence's first word.
    counts: dict[str, int] = {}
    for sentence in re.split(r"(?<=[.!?])\s+", body):
        words = re.findall(r"\b[A-Za-z][A-Za-z'-]{2,}\b", sentence)
        for w in words[1:]:                       # skip the sentence opener
            # "I'm", "I've", "I'd" are capitalised mid-sentence but are not
            # topics; any single-letter stem is a pronoun contraction.
            if w.split("'")[0].lower() in ("i", "a"):
                continue
            if w[0].isupper() and w.lower() not in stop:
                counts[w] = counts.get(w, 0) + 1

    # A proper noun recurs; a stray capital does not.
    for w, n in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])):
        if n < 3:
            break
        if w not in kws:
            kws.append(w)
        if len(kws) >= limit:
            break
    return kws[:limit]


def yaml_escape(value: str) -> str:
    return '"' + (value or "").replace("\\", "\\\\").replace('"', '\\"') + '"'


def safe_filename(title: str) -> str:
    stem = _SAFE.sub(" ", title).strip()
    stem = re.sub(r"\s{2,}", " ", stem)[:110].strip(" ._-")
    return f"Transcript - {stem or 'YouTube Video'}.md"


def to_markdown(video_id: str, meta: dict, snippets, language: str) -> tuple[str, dict]:
    """Render the knowledge-base document. Returns (markdown, stats)."""
    paragraphs = build_paragraphs(snippets)
    if not paragraphs:
        raise YouTubeError("the transcript was empty after cleaning")

    body_text = " ".join(p for _t, p in paragraphs)
    title = meta.get("title") or f"YouTube {video_id}"
    channel = meta.get("author_name") or ""
    url = f"https://www.youtube.com/watch?v={video_id}"
    duration = paragraphs[-1][0]

    summary = " ".join(paragraphs[0][1].split())[:400].rstrip()
    if len(paragraphs[0][1]) > 400:
        summary = summary.rsplit(". ", 1)[0] + "."

    lines = ["---", f"title: {yaml_escape(title)}"]
    if channel:
        lines.append(f"author: {yaml_escape(channel)}")
    lines += [
        "category: Transcript",
        "document_type: video_transcript",
        f"source_url: {yaml_escape(url)}",
        f"summary: {yaml_escape(summary)}",
        "keywords:",
    ]
    lines += [f"- {k}" for k in derive_keywords(title, channel, body_text)]
    lines.append("---")

    lines += ["", f"# {title}", ""]
    provenance = [f"**Source:** [{url}]({url})"]
    if channel:
        provenance.append(f"**Channel:** {channel}")
    provenance.append(f"**Transcript:** {language}")
    provenance.append(f"**Length:** {timestamp(duration)}")
    lines += ["  \n".join(provenance), "", "---", ""]

    # Timestamp anchors every SECTION_SECONDS, so retrieval can cite a point.
    next_anchor = 0.0
    for start, para in paragraphs:
        if start >= next_anchor:
            lines += [f"## [{timestamp(start)}]", ""]
            while next_anchor <= start:
                next_anchor += SECTION_SECONDS
        lines += [para, ""]

    return "\n".join(lines).rstrip() + "\n", {
        "paragraphs": len(paragraphs),
        "words": len(body_text.split()),
        "duration_seconds": int(duration),
        "language": language,
        "title": title,
        "channel": channel,
        "url": url,
    }


def convert(url_or_id: str) -> tuple[str, dict]:
    """URL in, (markdown, stats) out. Raises YouTubeError with a usable message."""
    video_id = extract_video_id(url_or_id)
    meta = fetch_metadata(video_id)
    snippets, language = fetch_transcript(video_id)
    return to_markdown(video_id, meta, snippets, language)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("url")
    ap.add_argument("--outdir", default="knowledge_base/transcripts")
    ap.add_argument("--stdout", action="store_true")
    args = ap.parse_args()

    try:
        markdown, stats = convert(args.url)
    except YouTubeError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    if args.stdout:
        print(markdown)
        return 0

    out = Path(args.outdir)
    out.mkdir(parents=True, exist_ok=True)
    path = out / safe_filename(stats["title"])
    n = 2
    while path.exists():
        path = out / safe_filename(f"{stats['title']} ({n})")
        n += 1
    path.write_text(markdown, encoding="utf-8")
    print(f"{path}  —  {stats['words']:,} words, {stats['paragraphs']} paragraphs, "
          f"{timestamp(stats['duration_seconds'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
