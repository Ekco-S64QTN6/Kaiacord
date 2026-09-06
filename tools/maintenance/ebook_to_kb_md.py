#!/usr/bin/env python3
"""
ebook_to_kb_md.py — convert EPUB / PDF / TXT / HTML into Kaia knowledge-base Markdown.

Why this exists
---------------
A plain `pandoc -s -i book.epub -o book.md` produces Markdown that is technically valid
but poor RAG input. Observed in knowledge_base before this script:

  * Calibre metadata frontmatter instead of Kaia's schema.
  * 268 pandoc fenced divs (`::: {.titlepage}`), 65 empty anchors (`[]{#Part01.xhtml}`),
    43 inline style spans (`[O]{style="font-size:2em;"}`), raw `<svg>`/`<image>` blocks.
  * 95 image references to files that were never extracted.
  * Chapter titles split character-by-character across styling spans, so the *title* of a
    chapter tokenises as garbage for BM25 and embeds meaninglessly.
  * TXT input reduced to ~4000-character single-line paragraph blobs with no headings,
    which chunk badly: one chunk spans several unrelated ideas.

Two-stage approach:
  1. Tell pandoc not to *emit* the noise (disable native_divs/native_spans/fenced_divs/
     bracketed_spans/header_attributes/raw_html). This is far more reliable than
     regexing structures away afterwards.
  2. Clean what still gets through, restore paragraph structure, detect chapter
     headings, and write Kaia's frontmatter schema.

Usage
-----
    python3 tools/maintenance/ebook_to_kb_md.py INPUT [INPUT ...] [options]

    --outdir DIR      output directory (default: knowledge_base/books)
    --title  TEXT     override detected title
    --author TEXT     override detected author
    --category TEXT   frontmatter category (default: Reference)
    --doctype TEXT    frontmatter document_type (default: inferred)
    --summary TEXT    frontmatter summary (default: first substantial paragraph)
    --keywords A,B    frontmatter keywords (default: derived from title/author)
    --stdout          print to stdout instead of writing a file
    --force           overwrite an existing output file
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import unicodedata
from pathlib import Path

# --- pandoc extensions that generate the noise documented above -------------------
_PANDOC_MD = (
    "markdown"
    "-raw_html"                 # drop <svg>/<div>/<span> passthrough
    "-native_divs"
    "-native_spans"
    "-fenced_divs"              # ::: {.titlepage}
    "-bracketed_spans"          # [text]{style=...}
    "-header_attributes"        # ## Title {#anchor .class}
    "-inline_code_attributes"
    "-link_attributes"
    "-smart"                    # keep straight quotes; simpler to normalise
)

TEXT_EXT = {".txt", ".text", ".md"}
PANDOC_EXT = {".epub", ".html", ".htm", ".xhtml", ".rtf", ".odt", ".docx"}
PDF_EXT = {".pdf"}


# ─────────────────────────────────────────────────────────────────────────────
# Extraction
# ─────────────────────────────────────────────────────────────────────────────
def _require(tool: str, hint: str) -> None:
    if not shutil.which(tool):
        sys.exit(f"error: '{tool}' is required for this input type.\n       {hint}")


def extract_pandoc(path: Path) -> tuple[str, dict]:
    """Convert via pandoc and return (markdown, ebook_metadata).

    Runs standalone (-s) so pandoc emits the ebook's own metadata as a YAML block, which
    is parsed for title/author before clean_markup() strips it. One invocation, not two.
    """
    _require("pandoc", "Install with: sudo pacman -S pandoc")
    proc = subprocess.run(
        ["pandoc", "-s", "-t", _PANDOC_MD, "--wrap=none", "--strip-comments", str(path)],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        sys.exit(f"error: pandoc failed on {path.name}:\n{proc.stderr.strip()}")
    return proc.stdout, parse_yaml_head(proc.stdout)


def parse_yaml_head(text: str) -> dict:
    """Pull title/author out of pandoc's emitted YAML block (no yaml dependency)."""
    m = RE_YAML_BLOCK.match(text)
    if not m:
        return {}
    meta, key = {}, None
    for line in m.group(0).splitlines()[1:-1]:
        if not line.strip():
            continue
        if re.match(r"^[A-Za-z_-]+:", line):
            key, _, val = line.partition(":")
            key = key.strip().lower()
            val = val.strip().strip('"').strip("'")
            if key in ("title", "creator", "author") and val:
                meta.setdefault("author" if key == "creator" else key, val)
        elif line.startswith("- ") and key in ("title", "creator", "author"):
            # First list entry wins (calibre emits multiple identifiers/dates).
            meta.setdefault("author" if key == "creator" else key,
                            line[2:].strip().strip('"').strip("'"))
    return {k: v for k, v in meta.items() if v}


def extract_pdf(path: Path) -> str:
    """Plain (reading-order) extraction.

    `-layout` is deliberately NOT used: on a two-column academic PDF it interleaves the
    sidebar with the body, producing text that reads as nonsense. Plain mode follows the
    document's own reading order.
    """
    _require("pdftotext", "Install poppler: sudo pacman -S poppler")
    proc = subprocess.run(
        ["pdftotext", "-nopgbrk", "-q", str(path), "-"],
        capture_output=True, text=True,
    )
    if proc.returncode != 0 or not proc.stdout.strip():
        sys.exit(f"error: pdftotext produced no text for {path.name} "
                 f"(scanned image PDF? OCR is out of scope).")
    return proc.stdout


def extract_text(path: Path) -> str:
    for enc in ("utf-8", "utf-8-sig", "latin-1"):
        try:
            return path.read_text(encoding=enc)
        except UnicodeDecodeError:
            continue
    return path.read_bytes().decode("utf-8", errors="replace")


# ─────────────────────────────────────────────────────────────────────────────
# Cleaning
# ─────────────────────────────────────────────────────────────────────────────
RE_YAML_BLOCK = re.compile(r"\A---\n.*?\n---\n", re.S)
RE_HTML_FENCE = re.compile(r"^```\{=html\}\n.*?^```\n", re.M | re.S)
RE_INLINE_HTML = re.compile(r"`[^`]*`\{=html\}")
RE_EMPTY_ANCHOR = re.compile(r"\[\]\{#[^}]*\}")
RE_ATTR_SPAN = re.compile(r"\{[.#][^}]*\}|\{style=\"[^\"]*\"\}|\{=html\}")
RE_FENCED_DIV = re.compile(r"^:{3,}.*$", re.M)
RE_IMAGE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
RE_RAW_TAG = re.compile(r"</?(?:svg|image|div|span|img|a|p|br|hr)\b[^>]*/?>", re.I)
RE_ESCAPES = re.compile(r"\\([<>{}\[\]*_#`|~^])")
RE_RULE_RUN = re.compile(r"^[=\-_*]{4,}\\?\s*$", re.M)
RE_MANY_BLANKS = re.compile(r"\n{3,}")
RE_TRAILING_WS = re.compile(r"[ \t]+$", re.M)

# Unicode that adds no meaning but pollutes tokenisation.
_ZAP = {
    "\u00a0": " ", "\u2007": " ", "\u202f": " ", "\u2009": " ", "\u200a": " ",
    "\u200b": "", "\u200c": "", "\u200d": "", "\ufeff": "",
    "\u00ad": "",                     # soft hyphen
    "\u2018": "'", "\u2019": "'", "\u201a": "'", "\u201b": "'",
    "\u201c": '"', "\u201d": '"', "\u201e": '"',
    "\u2013": "-", "\u2014": "-", "\u2212": "-",
    "\u2026": "...",
}


def normalise_unicode(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    for bad, good in _ZAP.items():
        text = text.replace(bad, good)
    # Any remaining control chars except tab/newline.
    return "".join(c for c in text if c in "\t\n" or unicodedata.category(c) != "Cc")


def clean_markup(text: str) -> str:
    text = RE_YAML_BLOCK.sub("", text)
    text = RE_HTML_FENCE.sub("", text)
    text = RE_INLINE_HTML.sub("", text)
    text = RE_EMPTY_ANCHOR.sub("", text)
    text = RE_FENCED_DIV.sub("", text)
    text = RE_IMAGE.sub("", text)
    text = RE_RAW_TAG.sub("", text)
    text = RE_ATTR_SPAN.sub("", text)
    text = RE_ESCAPES.sub(r"\1", text)
    text = RE_RULE_RUN.sub("", text)
    text = RE_TRAILING_WS.sub("", text)
    return text


# Recurring page furniture in PDF extractions: running headers/footers, page numbers,
# and journal/URL strips that pdftotext interleaves into the body text.
# Case-INSENSITIVE furniture: URLs, page markers, journal strips.
RE_FURNITURE_CI = re.compile(
    r"^[ \t]*(?:"
    r"\|"                                         # bare column separator
    r"|page[ \t]+\d{1,4}"
    r"|(?:www\.|https?://)[^\s]*(?:[ \t]+[^\s]+)?"   # "WWW. usenix.org"
    r"|;login:.*"
    r"|\d{1,4}"                                   # standalone page number
    r")[ \t]*[.|]?[ \t]*$",
    re.M | re.I)

# Case-SENSITIVE furniture: all-caps running headers and month-year strips.
# This one must NOT be case-insensitive: with re.I, "[A-Z\s]{4,40}" matches any short
# lowercase line and silently deletes real prose (it ate a line of the author bio).
RE_FURNITURE_CS = re.compile(
    r"^[ \t]*(?:"
    r"[A-Z][A-Za-z]*[ \t]+\d{4}"                  # "JANUARY 2014"
    r"|[A-Z][A-Z\s.&'-]{3,39}"                    # ALL-CAPS running header
    r")[ \t]*$",
    re.M)


def strip_page_furniture(text: str) -> str:
    """Remove running headers, footers and page numbers from PDF text.

    pdftotext emits these inline with the prose, e.g. a paragraph interrupted by
    '| JANUARY 2014 | WWW. usenix.org | PAGE 8'. Left in, they become their own RAG
    chunks and pollute the surrounding one.
    """
    text = RE_FURNITURE_CI.sub("", text)
    return RE_FURNITURE_CS.sub("", text)


RE_DROPCAP = re.compile(r"^([A-Z])\n{1,2}([a-z]{2,})", re.M)


def rejoin_dropcaps(text: str) -> str:
    """Reattach a decorative drop cap to its word.

    A large initial letter is a separate text run in the PDF, so pdftotext yields
    "S\n\nometimes, when I check my work email" - the first word of a section is split
    and neither fragment matches a search for "Sometimes".
    """
    return RE_DROPCAP.sub(r"\1\2", text)


def dehyphenate(text: str) -> str:
    """Rejoin words split across a hard line break ('inter-\\nnational')."""
    return re.sub(r"(\w)-\n(\w)", r"\1\2", text)


def reflow(text: str) -> str:
    """Rebuild paragraphs from hard-wrapped lines (PDF/TXT input).

    A blank line separates paragraphs; single newlines inside a paragraph are joins.
    Lines that look like headings or list items are preserved as their own block.
    """
    out_paras = []
    for block in re.split(r"\n\s*\n", text):
        lines = [ln.strip() for ln in block.split("\n") if ln.strip()]
        if not lines:
            continue
        if any(re.match(r"^(#{1,6} |[-*+] |\d+[.)] |> )", ln) for ln in lines):
            out_paras.append("\n".join(lines))
        else:
            out_paras.append(" ".join(lines))
    return "\n\n".join(out_paras)


# A chapter heading in PLAIN TEXT (not already a Markdown heading).
# [ \t]* rather than \s*: \s matches newlines, which made an earlier version swallow the
# *following* heading line and emit "## CHAPTER 1 - ## Ignition".
RE_ROMAN_HEAD = re.compile(
    r"^[ \t]*((?:[IVXLC]{1,7})\.)[ \t]+([A-Z][^\n]{2,80}?)[ \t]*$", re.M)
RE_CHAPTER_WORD = re.compile(
    r"^[ \t]*((?:CHAPTER|Chapter|PART|Part|BOOK|Book)[ \t]+[\dIVXLC]{1,7})[.:]?[ \t]*([^\n]{0,80})$",
    re.M)
RE_ANY_HEADING = re.compile(r"^(#{1,6})[ \t]+(.*)$", re.M)


def demote_headings(text: str) -> str:
    """Shift every existing heading down one level, capped at h6.

    The converter adds its own `# <Title>` as the document root. Ebook chapter headings
    arrive from pandoc as h1, which would sit at the same level as the title and make the
    document look like many separate documents to a heading-aware chunker.
    """
    return RE_ANY_HEADING.sub(
        lambda m: f"{'#' * min(len(m.group(1)) + 1, 6)} {m.group(2).strip()}", text)


def merge_chapter_labels(text: str) -> str:
    """Join a bare 'CHAPTER n' line to the heading that follows it.

    EPUBs frequently emit the label and the chapter title as separate blocks:
        CHAPTER 1
        ## Ignition
    which yields a heading of just the title and a stray text line. Merged into
    '## Chapter 1 - Ignition' the heading carries both, so retrieval on either the number
    or the name finds the section.
    """
    pattern = re.compile(
        r"^[ \t]*((?:CHAPTER|Chapter)[ \t]+[\dIVXLC]{1,7})[.:]?[ \t]*\n+"
        r"[ \t]*#{1,6}[ \t]+([^\n]{1,90})$",
        re.M)
    return pattern.sub(lambda m: f"## {m.group(1).title()} - {m.group(2).strip()}", text)


def promote_headings(text: str) -> str:
    """Turn standalone chapter lines into '## ' headings.

    Chunkers split on headings; a book with none becomes a wall of undifferentiated
    chunks. Only short standalone lines are promoted, never prose, and never a line that
    is already a heading.
    """
    def _roman(m):
        return f"\n## {m.group(1)} {m.group(2).strip()}\n"

    def _word(m):
        tail = m.group(2).strip().lstrip("#").strip()
        return f"\n## {m.group(1).title()}{(' - ' + tail) if tail else ''}\n"

    text = RE_CHAPTER_WORD.sub(_word, text)
    text = RE_ROMAN_HEAD.sub(_roman, text)
    return text


# An ALL-CAPS section title run inline at the start of a paragraph, immediately followed
# by the body text on the same line, e.g.
#   "ON NIHILISM Nihilism no longer wears the dark, Wagnerian ... colors"
# Plain-text sources typeset section titles this way, so without this split the title is
# buried mid-paragraph: the document has no headings at all and every chunk looks alike.
# Words that stay lowercase inside a title, so "THE PRECESSION OF SIMULACRA" becomes
# "The Precession of Simulacra" rather than "The Precession Of Simulacra".
_TITLE_SMALL = {"a", "an", "the", "of", "in", "on", "at", "to", "for", "and", "or",
                "nor", "but", "as", "by", "from", "into", "with", "over"}

_CAPS_WORD = re.compile(r"^[A-Z][A-Z0-9'\u2019:,.\-&]*$")


def titlecase(text: str) -> str:
    out = []
    for i, w in enumerate(text.split()):
        lw = w.lower()
        # A small word stays lowercase, unless it opens a clause after ':' or '-'
        # ("History: A Retro Scenario", not "History: a Retro Scenario").
        after_break = i and out and out[-1].endswith((":", "-", "\u2014"))
        if i and not after_break and lw.strip(":,.") in _TITLE_SMALL:
            out.append(lw)
        elif "'" in w or "\u2019" in w:
            sep = "'" if "'" in w else "\u2019"
            head, _, tail = w.partition(sep)
            out.append(head.capitalize() + sep + tail.lower())
        else:
            out.append(w.capitalize())
    return " ".join(out)


def split_inline_caps_headings(text: str) -> str:
    """Promote a leading ALL-CAPS section title into its own '## ' heading.

    Plain-text and PDF sources typeset section titles in capitals, either inline with the
    first sentence ("ON NIHILISM Nihilism no longer wears...") or on their own line. Left
    as-is the document has no headings at all, so every chunk looks alike to a retriever
    and the section name never anchors a match.

    Token-based rather than one large regex: the regex version silently missed two-letter
    leading words ("ON NIHILISM") and own-line titles.
    """
    out = []
    for para in text.split("\n\n"):
        stripped = para.lstrip()
        if stripped.startswith("#") or not stripped:
            out.append(para)
            continue

        # Take the leading run of all-caps tokens (allowing a newline break after it).
        head_line, _, rest_of_para = stripped.partition("\n")
        tokens = head_line.split()
        n = 0
        while n < len(tokens) and _CAPS_WORD.match(tokens[n]):
            n += 1

        title = " ".join(tokens[:n]).strip(" :,-.")
        # Guards: enough substance to be a title, not a whole shouted paragraph.
        if n == 0 or len(title) < 5 or n > 10:
            out.append(para)
            continue

        remainder = " ".join(tokens[n:]).strip()
        if rest_of_para.strip():
            remainder = (remainder + " " + rest_of_para.strip()).strip()
        # A title must be followed by actual prose, and must not BE the paragraph.
        if len(remainder) < 40 or not re.match(r"[A-Z\"'(]", remainder):
            out.append(para)
            continue

        out.append(f"## {titlecase(title)}\n\n{remainder}")
    return "\n\n".join(out)


def split_runon_paragraphs(text: str, max_chars: int = 1500) -> str:
    """Break very long single-paragraph blobs on sentence boundaries.

    TXT sources arrive as ~4000-character paragraphs. A 1024-token chunker will cut
    those mid-sentence at arbitrary points; splitting on sentence ends first means each
    chunk starts and finishes on a real boundary.
    """
    out = []
    for para in text.split("\n\n"):
        if len(para) <= max_chars or para.lstrip().startswith("#"):
            out.append(para)
            continue
        sentences = re.split(r"(?<=[.!?\"'])\s+", para)
        buf, cur = [], ""
        for s in sentences:
            if cur and len(cur) + len(s) + 1 > max_chars:
                buf.append(cur.strip())
                cur = s
            else:
                cur = f"{cur} {s}".strip()
        if cur:
            buf.append(cur.strip())
        out.extend(buf)
    return "\n\n".join(out)


# ─────────────────────────────────────────────────────────────────────────────
# Metadata
# ─────────────────────────────────────────────────────────────────────────────
_NOISE_TOKENS = re.compile(
    r"(?i)\b(?:_?oceanofpdf(?:\.com)?|z-?lib(?:\.org)?|libgen|epub|mobi|azw3?|pdf|"
    r"retail|ebook|calibre|v?\d+(?:\.\d+)*)\b")


def title_from_filename(path: Path) -> tuple[str, str]:
    """Derive (title, author) from a messy download filename.

    Handles the shapes actually seen: '_OceanofPDF.com_Out_of_Control_-_Kevin_Kelly',
    'postsingular_rudy_rucker_2021', 'Simulacra-and-Simulation'.
    """
    stem = path.stem
    stem = _NOISE_TOKENS.sub(" ", stem)
    stem = re.sub(r"[_]+", " ", stem)
    stem = re.sub(r"\s*-\s*", " - ", stem)
    stem = re.sub(r"\b(19|20)\d{2}\b", " ", stem)     # stray year
    stem = re.sub(r"\s{2,}", " ", stem).strip(" -.")

    author = ""
    if " - " in stem:
        left, right = [s.strip() for s in stem.rsplit(" - ", 1)]
        # The author half is short and has no lowercase connective words.
        if right and len(right.split()) <= 4:
            stem, author = left, right
    title = " ".join(w if w.isupper() else w.capitalize() for w in stem.split())
    author = " ".join(w.capitalize() for w in author.split())
    return title.strip(), author.strip()


def infer_doctype(path: Path, category: str) -> str:
    if path.suffix.lower() in PDF_EXT:
        return "Article"
    return "Novel" if category.lower() in {"fiction", "sci-fi", "cyberpunk"} else "Book"


# Front-matter boilerplate that is never a useful summary of the work.
RE_BOILERPLATE = re.compile(
    r"(?i)\b(copyright|all rights reserved|isbn|first edition|published by|"
    r"printed in|tor books|library of congress|cataloging|www\.|http|"
    r"cover (?:art|painting|design)|typeset|permission of the publisher|"
    r"this is a work of fiction|table of contents|acknowledg)")


def first_paragraph(text: str, min_len: int = 120, max_len: int = 400) -> str:
    """First substantial prose paragraph, skipping publisher boilerplate.

    Without the boilerplate filter the summary came out as the copyright notice or a
    bare URL, which is worse than useless as an embedding for the whole book.
    """
    for para in text.split("\n\n"):
        p = para.strip()
        if p.startswith("#") or len(p) < min_len:
            continue
        if RE_BOILERPLATE.search(p):
            continue
        # Mostly-uppercase blocks are title pages, not prose.
        letters = [c for c in p if c.isalpha()]
        if letters and sum(c.isupper() for c in letters) / len(letters) > 0.5:
            continue
        p = re.sub(r"\s+", " ", p)
        return (p[:max_len].rsplit(" ", 1)[0] + "...") if len(p) > max_len else p
    return ""


def yaml_escape(s: str) -> str:
    s = s.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{s}"'


def build_frontmatter(title, author, category, doctype, summary, keywords) -> str:
    lines = ["---"]
    full_title = f"{title} by {author}" if author else title
    lines.append(f"title: {yaml_escape(full_title)}")
    if author:
        lines.append(f"author: {yaml_escape(author)}")
    lines.append(f"category: {yaml_escape(category)}")
    lines.append(f"document_type: {yaml_escape(doctype)}")
    lines.append(f"summary: {yaml_escape(summary)}" if summary else 'summary: ""')
    lines.append("keywords:")
    for k in keywords:
        lines.append(f"- {k}")
    lines.append("---")
    return "\n".join(lines)


def derive_keywords(title: str, author: str, text: str, limit: int = 10) -> list[str]:
    kws: list[str] = []
    for part in (title, author):
        for w in part.split():
            w = w.strip(".,:;'\"")
            if len(w) > 2 and w.lower() not in {"the", "and", "of", "by", "a", "an"}:
                if w not in kws:
                    kws.append(w)
    if title and title not in kws:
        kws.insert(0, title)
    if author and author not in kws:
        kws.append(author)
    return kws[:limit]


# ─────────────────────────────────────────────────────────────────────────────
# Pipeline
# ─────────────────────────────────────────────────────────────────────────────
def convert(path: Path, args) -> tuple[str, str]:
    ext = path.suffix.lower()
    meta: dict = {}
    if ext in PANDOC_EXT:
        raw, meta = extract_pandoc(path)
        needs_reflow = False
    elif ext in PDF_EXT:
        raw, needs_reflow = extract_pdf(path), True
    elif ext in TEXT_EXT:
        raw, needs_reflow = extract_text(path), True
    else:
        sys.exit(f"error: unsupported input type '{ext}' ({path.name})")

    text = normalise_unicode(raw)
    text = clean_markup(text)
    if needs_reflow:
        if ext in PDF_EXT:
            text = strip_page_furniture(text)
            text = rejoin_dropcaps(text)
        text = dehyphenate(text)
        text = reflow(text)
    text = demote_headings(text)
    text = merge_chapter_labels(text)
    text = promote_headings(text)
    if needs_reflow:
        # Plain-text/PDF sources typeset section titles inline in caps.
        text = split_inline_caps_headings(text)
    text = split_runon_paragraphs(text)
    text = RE_MANY_BLANKS.sub("\n\n", text).strip()

    f_title, f_author = title_from_filename(path)
    title = args.title or meta.get("title") or f_title
    author = args.author or meta.get("author") or f_author
    category = args.category
    doctype = args.doctype or infer_doctype(path, category)
    summary = args.summary or first_paragraph(text)
    keywords = ([k.strip() for k in args.keywords.split(",") if k.strip()]
                if args.keywords else derive_keywords(title, author, text))

    heading = f"# {title} by {author}" if author else f"# {title}"
    body = f"{build_frontmatter(title, author, category, doctype, summary, keywords)}\n\n{heading}\n\n{text}\n"

    # knowledge_base naming conventions:
    #   books/     "Book - <Title> by <Author>.md"
    #   documents/ "<Topic> - <Title>.md"
    prefix = args.prefix if args.prefix is not None else "Book"
    stem = f"{title} by {author}" if (author and prefix == "Book") else title
    name = f"{prefix} - {stem}.md" if prefix else f"{stem}.md"
    name = re.sub(r'[\\/:*?"<>|]', "-", name)
    return name, body


def main() -> None:
    ap = argparse.ArgumentParser(description="Convert EPUB/PDF/TXT/HTML to Kaia KB Markdown.")
    ap.add_argument("inputs", nargs="+", type=Path)
    ap.add_argument("--outdir", type=Path, default=Path("knowledge_base/books"))
    ap.add_argument("--title"); ap.add_argument("--author")
    ap.add_argument("--category", default="Reference")
    ap.add_argument("--doctype"); ap.add_argument("--summary"); ap.add_argument("--keywords")
    ap.add_argument("--prefix", default=None,
                    help="filename prefix: 'Book' for knowledge_base/books (default), "
                         "a topic like 'AI'/'Essay' for knowledge_base/documents, "
                         "or '' for no prefix")
    ap.add_argument("--stdout", action="store_true")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    for path in args.inputs:
        if not path.is_file():
            print(f"skip: not a file: {path}", file=sys.stderr)
            continue
        name, body = convert(path, args)
        if args.stdout:
            print(body)
            continue
        args.outdir.mkdir(parents=True, exist_ok=True)
        dest = args.outdir / name
        if dest.exists() and not args.force:
            print(f"skip: {dest} exists (use --force)", file=sys.stderr)
            continue
        dest.write_text(body, encoding="utf-8")
        print(f"wrote {dest}  ({len(body):,} chars)")


if __name__ == "__main__":
    main()
