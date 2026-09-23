#!/usr/bin/env python3
"""Normalise documents staged in knowledge_base/_ingress/ and file them.

`!download` writes raw markdown into `_ingress/` rather than straight into the
corpus. That folder is excluded from RAG indexing, so anything a user submits
sits inert until it has been cleaned and given metadata — which is what makes
it safe to leave `!download` open to everyone.

This script does the second half:

  1. read each staged `*.md` plus its `.meta.json` sidecar
  2. run the same normalisation the ebook converter uses (unicode, markup,
     de-hyphenation, reflow)
  3. derive a title, summary and keywords, and write Kaia's frontmatter schema
  4. move the result into the knowledge-base folder its sidecar chose
  5. request one reindex for the whole batch

A file that fails is left in `_ingress/` with a `.error` sidecar rather than
being dropped, so nothing vanishes silently.

Usage:
    python tools/maintenance/process_ingress.py            # process everything
    python tools/maintenance/process_ingress.py --dry-run  # report only
    python tools/maintenance/process_ingress.py --quiet    # for the hourly task
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from utils.core.atomic_write import write_atomic  # noqa: E402

from tools.maintenance.ebook_to_kb_md import (  # noqa: E402
    build_frontmatter,
    clean_markup,
    dehyphenate,
    derive_keywords,
    first_paragraph,
    normalise_unicode,
    reflow,
    titlecase,
)

KB = Path("knowledge_base")
INGRESS = KB / "_ingress"

# Folders a sidecar is allowed to name. Anything else is filed as a document,
# so a malformed or hostile sidecar cannot write outside the corpus.
ALLOWED_FOLDERS = {
    "books", "documents", "news", "transcripts", "troubleshooting", "wiki",
}
DEFAULT_FOLDER = "documents"

_SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")


def safe_stem(name: str) -> str:
    """Filesystem-safe stem. Guards against traversal from sidecar titles."""
    stem = _SAFE_NAME.sub("_", Path(name).stem).strip("._-")
    return (stem or "document")[:120]


# Spaces are kept: the documents/ convention is "AI - Claude Opus 4.6 System
# Card Report.md", not underscores. Path separators, traversal and the handful
# of characters that upset shells or Windows are still removed.
_SAFE_DISPLAY_NAME = re.compile(r"[^A-Za-z0-9 ._&()',-]+")


def safe_display_stem(name: str) -> str:
    """Filesystem-safe stem that reads like a title rather than a slug."""
    stem = _SAFE_DISPLAY_NAME.sub(" ", Path(name).name)
    stem = re.sub(r"\s{2,}", " ", stem).strip(" ._-")
    return (stem or "document")[:120]


# The topics already in use in knowledge_base/documents/. Filenames there follow
# "<Topic> - <Title>.md" (CLAUDE.md §10) and the topic doubles as the
# frontmatter `category`. Offering the model the existing list keeps the
# taxonomy from fragmenting into synonyms.
KNOWN_TOPICS = [
    "AI", "AI Ethics", "AI Safety", "Architecture", "Cybersecurity", "Design",
    "Engineering", "Geopolitics", "Ghost in the Shell", "Hardware",
    "Investigation", "Kaia", "Linguistics", "Literature", "Lore", "Philosophy",
    "Project 1999", "Sci-Fi", "Security", "TTRPG",
]

_TITLE_PROMPT = (
    "You are cataloguing a document for a personal knowledge base.\n\n"
    "Return ONLY a JSON object:\n"
    '{{"topic": "...", "title": "...", "summary": "...", "keywords": ["..."]}}\n\n'
    "topic: one of these if any fits, otherwise a new one of 1-3 words:\n"
    "{topics}\n\n"
    "If the document is about Kaia herself — this Discord bot, her code, her\n"
    "memory, her behaviour — the topic is \"Kaia\", not \"AI\".\n\n"
    "title: a concise noun-phrase title for the document, 3-9 words, Title Case,\n"
    "no trailing punctuation, no author name, no date. Describe what the\n"
    "document IS, not its opening sentence.\n\n"
    "summary: one or two complete sentences saying what the document argues or\n"
    "covers. Must start at a sentence boundary — never mid-clause.\n\n"
    "keywords: 5-10 distinct topical terms. Not the title, not single common\n"
    "words lifted from the opening line.\n\n"
    "DOCUMENT:\n{sample}\n"
)


def derive_topic_and_title(body: str, fallback_title: str, client=None,
                           model: str = None) -> tuple:
    """Ask the model for a topic, a real title, a summary and keywords.

    Returns (topic, title, summary, keywords).

    The previous behaviour was `title = meta["title"] or titlecase(stem)` with
    `category` hardcoded to "Reference". For anything without a scraped title —
    a pasted block of text, say — the stem was derived from the opening words,
    so a document arrived titled "Kaia another system worked on your code today,
    and you should know what changed before you notice it", with that same
    sentence repeated as the summary and as every keyword.

    Falls back to the old behaviour if the model is unavailable or answers
    badly; a poor title is better than a failed ingest.
    """
    sample = " ".join((body or "").split())[:1500]
    if not sample:
        return "Reference", fallback_title, "", []
    try:
        from ollama import Client
        from utils.infrastructure.system.yaml_config import config
        model = model or config.chat_model
        client = client or Client()
        prompt = _TITLE_PROMPT.format(
            topics=", ".join(KNOWN_TOPICS), sample=sample)
        resp = client.chat(model=model,
                           messages=[{"role": "user", "content": prompt}],
                           options={"temperature": 0.2, "num_predict": 120})
        text = resp["message"]["content"].strip()
        if "```" in text:
            text = text.split("```")[1].lstrip("json").strip()
        data = json.loads(text[text.find("{"):text.rfind("}") + 1])
        topic = str(data.get("topic", "")).strip().strip('"')
        title = str(data.get("title", "")).strip().strip('"').rstrip(".")
        summary = str(data.get("summary", "")).strip().strip('"')
        kws = [str(k).strip() for k in (data.get("keywords") or []) if str(k).strip()]
        if topic and title and 2 <= len(title.split()) <= 14:
            return topic, title, summary, kws[:10]
    except Exception:
        pass
    return "Reference", fallback_title, "", []


SUMMARY_MAX_CHARS = 300


def trim_summary(text: str) -> str:
    """Cap the frontmatter summary at a sentence boundary.

    `first_paragraph` returns the whole paragraph, which for a reflowed web
    article can be several thousand characters — the summary field is read as
    a preview, not as content.
    """
    text = " ".join((text or "").split())
    if len(text) <= SUMMARY_MAX_CHARS:
        return text
    cut = text[:SUMMARY_MAX_CHARS]
    stop = max(cut.rfind(". "), cut.rfind("! "), cut.rfind("? "))
    return (cut[:stop + 1] if stop > SUMMARY_MAX_CHARS // 2 else cut.rstrip()) + "…"


def drop_leading_title(body: str, title: str) -> str:
    """Remove a duplicate title from the first line or two of the body."""
    norm = lambda t: re.sub(r"[^a-z0-9]+", "", (t or "").lower())
    target = norm(title)
    if not target:
        return body
    lines = body.split("\n")
    while lines and (not lines[0].strip() or norm(lines[0].lstrip("# ")) == target):
        lines.pop(0)
    return "\n".join(lines).lstrip("\n")


# Extensions the ebook converter can read. A file dropped into _ingress/ by
# hand is usually one of these rather than markdown.
CONVERTIBLE = {".pdf", ".txt", ".html", ".htm", ".epub", ".docx", ".rtf"}


def convert_staged_file(path: Path, dry_run: bool) -> tuple:
    """Turn a non-markdown staged file into the `.md` the pipeline expects.

    `main()` globbed `*.md` only, so a PDF moved into _ingress/ by hand was
    never picked up: no conversion, no error, no log line, and _ingress/ is
    excluded from indexing, so it was invisible to her as well. It simply sat
    there. Everything needed to handle it already existed in
    `ebook_to_kb_md.py`; nothing called it from here.

    Any sidecar is carried across, so a hand-placed file can still name its
    folder and title if one was written for it.
    """
    ext = path.suffix.lower()
    if ext not in CONVERTIBLE:
        return False, f"unsupported extension {ext or '(none)'}"

    try:
        sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
        from tools.maintenance.ebook_to_kb_md import (
            extract_pdf, extract_text, extract_pandoc, clean_markup, normalise_unicode,
        )
        if ext == ".pdf":
            raw = extract_pdf(path)
        elif ext in (".txt", ".rtf"):
            raw = extract_text(path)
        else:
            raw, _ = extract_pandoc(path)
        raw = clean_markup(normalise_unicode(raw))
    except SystemExit as e:
        # extract_pdf calls sys.exit on a scanned image PDF; one bad file must
        # not take down the whole ingest run.
        return False, f"conversion failed: {e}"
    except Exception as e:                          # noqa: BLE001
        return False, f"conversion failed: {type(e).__name__}: {e}"

    if len(raw.split()) < 50:
        return False, f"converted to only {len(raw.split())} words"

    # A newline inside a filename is not hypothetical: a title copied from a
    # wrapped heading arrived as "Strategic Resilience ...\n\nTechnical
    # Capacities.pdf".
    stem = safe_display_stem(" ".join(path.stem.split()))
    md_path = path.with_name(stem + ".md")
    if dry_run:
        return True, f"would convert -> {md_path.name} ({len(raw.split())} words)"

    write_atomic(md_path, raw)
    side = path.with_suffix(".meta.json")
    if side.exists() and not md_path.with_suffix(".meta.json").exists():
        side.rename(md_path.with_suffix(".meta.json"))
    path.unlink()
    return True, f"converted -> {md_path.name}"


def load_sidecar(md_path: Path) -> dict:
    side = md_path.with_suffix(".meta.json")
    if not side.exists():
        return {}
    try:
        data = json.loads(side.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def strip_existing_frontmatter(text: str) -> str:
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            return text[end + 4:].lstrip("\n")
    return text


def normalise(text: str) -> str:
    """The cleanup chain, in the order the ebook converter applies it."""
    text = normalise_unicode(text)
    text = clean_markup(text)
    text = dehyphenate(text)
    text = reflow(text)
    return text.strip()


def _file_preformatted(md_path: Path, raw: str, meta: dict, dry_run: bool) -> tuple[bool, str]:
    """Move an already-formatted document into place without touching its text.

    Used by !youtube, whose converter emits the finished document. The only
    change made here is appending the submitter, which the converter cannot
    know.
    """
    folder = meta.get("folder") or DEFAULT_FOLDER
    if folder not in ALLOWED_FOLDERS:
        folder = DEFAULT_FOLDER

    title = meta.get("title") or md_path.stem
    dest_dir = KB / folder
    dest = dest_dir / md_path.name
    n = 2
    while dest.exists():
        dest = dest_dir / f"{md_path.stem} ({n}){md_path.suffix}"
        n += 1

    submitter = meta.get("submitted_by") or "unknown"
    document = raw.rstrip() + f"\n\n---\n\n*Submitted by {submitter} via `!youtube`*\n"

    if dry_run:
        return True, f"would file as {dest.relative_to(KB)} (preformatted, {len(raw.split())} words)"

    dest_dir.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".tmp")
    tmp.write_text(document, encoding="utf-8")
    tmp.replace(dest)

    md_path.unlink()
    side = md_path.with_suffix(".meta.json")
    if side.exists():
        side.unlink()
    return True, f"filed as {dest.relative_to(KB)} (preformatted, {len(raw.split())} words)"


def process_one(md_path: Path, dry_run: bool = False) -> tuple[bool, str]:
    """Returns (ok, message)."""
    meta = load_sidecar(md_path)
    raw = md_path.read_text(encoding="utf-8", errors="replace")

    # A preformatted document already carries knowledge-base frontmatter,
    # headings and (for transcripts) timestamp anchors. Running the normaliser
    # over it would reflow the paragraphs and destroy that structure, so it is
    # filed as-is.
    if meta.get("preformatted"):
        return _file_preformatted(md_path, raw, meta, dry_run)

    body = normalise(strip_existing_frontmatter(raw))

    if len(body.split()) < 50:
        return False, f"too short after cleaning ({len(body.split())} words)"

    title = meta.get("title") or titlecase(md_path.stem.replace("_", " "))
    # A sidecar title from a scraped page is trustworthy; a stem derived from
    # the opening words is not. Ask the model for a topic and a real title, and
    # let it correct a sentence-shaped title too.
    topic, better_title, better_summary, better_keywords = derive_topic_and_title(body, title)
    if better_title and better_title != title:
        title = better_title
    author = meta.get("author") or ""
    source = meta.get("source_url") or ""
    submitter = meta.get("submitted_by") or "unknown"

    folder = meta.get("folder") or DEFAULT_FOLDER
    if folder not in ALLOWED_FOLDERS:
        folder = DEFAULT_FOLDER

    # Drop a repeated title line at the top of the body: HTML-to-markdown
    # conversion nearly always leaves the <h1> as the first paragraph, and the
    # document already gets a heading below.
    body = drop_leading_title(body, title)

    # A model-written summary and keyword set beat the extracted fallback,
    # which produced summaries starting mid-clause ("on resilience to loss of
    # control correctly focuses on…") and keyword lists that were the title
    # followed by its individual words.
    # The page's own description (`page_summary`) and keywords come next: they
    # were written by the publisher, which beats anything cut from the body.
    summary = (meta.get("summary") or better_summary
               or trim_summary(meta.get("page_summary") or "")
               or trim_summary(first_paragraph(body)))
    page_keywords = [str(k).strip() for k in (meta.get("keywords") or []) if str(k).strip()]
    keywords = better_keywords or page_keywords or derive_keywords(title, author, body)

    front = build_frontmatter(
        title=title, author=author, category=meta.get("category") or topic,
        doctype=meta.get("document_type", "Article"),
        summary=summary, keywords=keywords,
    )
    # Provenance belongs in the document: retrieval surfaces this text, and a
    # reader (including Kaia) should be able to see where it came from.
    provenance = [f"*Submitted by {submitter} via `!download`*"]
    if source:
        provenance.append(f"*Source: {source}*")
    provenance.append(f"*Ingested: {time.strftime('%Y-%m-%d')}*")

    document = f"{front}\n\n# {title}\n\n" + "\n".join(provenance) + f"\n\n{body}\n"

    dest_dir = KB / folder
    # "<Topic> - <Title>.md", the convention the older documents follow.
    stem = f"{topic} - {title}" if topic and topic != "Reference" else title
    dest = dest_dir / f"{safe_display_stem(stem)}.md"
    n = 2
    while dest.exists():
        dest = dest_dir / f"{safe_display_stem(stem)} ({n}).md"
        n += 1

    if dry_run:
        return True, f"would file as {dest.relative_to(KB)} ({len(body.split())} words)"

    dest_dir.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".tmp")
    tmp.write_text(document, encoding="utf-8")
    tmp.replace(dest)

    md_path.unlink()
    side = md_path.with_suffix(".meta.json")
    if side.exists():
        side.unlink()
    return True, f"filed as {dest.relative_to(KB)} ({len(body.split())} words)"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true", help="report without writing")
    ap.add_argument("--quiet", action="store_true", help="only report totals")
    args = ap.parse_args()

    if not INGRESS.exists():
        if not args.quiet:
            print(f"No ingress directory at {INGRESS}")
        return 0

    # Convert anything that is not already markdown first, so a hand-placed
    # PDF joins the normal path instead of being silently skipped.
    for other in sorted(INGRESS.iterdir()):
        if (not other.is_file() or other.suffix.lower() in (".md", ".json", ".error")
                or other.name == "README.md"):
            continue
        done, note = convert_staged_file(other, args.dry_run)
        if not args.quiet:
            print(f"  {'conv' if done else 'skip'}  {other.name}: {note}")
        if not done and not args.dry_run:
            other.with_suffix(other.suffix + ".error").write_text(note, encoding="utf-8")

    staged = sorted(p for p in INGRESS.glob("*.md") if p.name != "README.md")
    if not staged:
        if not args.quiet:
            print("Ingress is empty.")
        return 0

    ok = failed = 0
    for md in staged:
        try:
            success, message = process_one(md, args.dry_run)
        except Exception as e:                      # noqa: BLE001
            success, message = False, f"{type(e).__name__}: {e}"
        if success:
            ok += 1
            if not args.quiet:
                print(f"  ok    {md.name}: {message}")
        else:
            failed += 1
            if not args.dry_run:
                md.with_suffix(".error").write_text(message, encoding="utf-8")
            print(f"  FAIL  {md.name}: {message}", file=sys.stderr)

    if ok and not args.dry_run:
        # One reindex for the batch, not one per document.
        from utils.core.rag_utils import request_reindex
        request_reindex()

    print(f"Ingress: {ok} filed, {failed} failed"
          + (" (dry run, nothing written)" if args.dry_run else ""))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
