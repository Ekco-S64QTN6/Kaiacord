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
REINDEX_TRIGGER = Path(".trigger_reindex")

# Folders a sidecar is allowed to name. Anything else is filed as a document,
# so a malformed or hostile sidecar cannot write outside the corpus.
ALLOWED_FOLDERS = {
    "blogs", "books", "deep_dive_reports", "documents",
    "news", "transcripts", "troubleshooting",
}
DEFAULT_FOLDER = "documents"

_SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")


def safe_stem(name: str) -> str:
    """Filesystem-safe stem. Guards against traversal from sidecar titles."""
    stem = _SAFE_NAME.sub("_", Path(name).stem).strip("._-")
    return (stem or "document")[:120]


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


def process_one(md_path: Path, dry_run: bool = False) -> tuple[bool, str]:
    """Returns (ok, message)."""
    meta = load_sidecar(md_path)
    raw = md_path.read_text(encoding="utf-8", errors="replace")
    body = normalise(strip_existing_frontmatter(raw))

    if len(body.split()) < 50:
        return False, f"too short after cleaning ({len(body.split())} words)"

    title = meta.get("title") or titlecase(md_path.stem.replace("_", " "))
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

    summary = meta.get("summary") or trim_summary(first_paragraph(body))
    keywords = derive_keywords(title, author, body)

    front = build_frontmatter(
        title=title, author=author, category=meta.get("category", "Reference"),
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
    dest = dest_dir / f"{safe_stem(title)}.md"
    n = 2
    while dest.exists():
        dest = dest_dir / f"{safe_stem(title)}_{n}.md"
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
        REINDEX_TRIGGER.touch()

    print(f"Ingress: {ok} filed, {failed} failed"
          + (" (dry run, nothing written)" if args.dry_run else ""))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
