"""Resource-bounded PDF text extraction shared by every application path.

PDFs are complex, attacker-controlled object graphs. Parsing is confined to one
disposable child process at a time; neither a thread timeout nor a caller-specific
worker can bypass the shared process and memory budget.
"""
from __future__ import annotations

import json
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any, Optional

PDF_MAX_INPUT_BYTES = 50 * 1024 * 1024
PDF_MAX_PAGES = 800
PDF_MAX_TEXT_CHARS = 1_500_000
PDF_WORKER_MEMORY_BYTES = 512 * 1024 * 1024
PDF_WORKER_CPU_SECONDS = 30
PDF_WORKER_TIMEOUT_SECONDS = 40
PDF_WORKER_QUEUE_WAIT_SECONDS = 60
PDF_MAX_CONCURRENT_WORKERS = 1

# All PDF consumers in this interpreter share this slot: linked messages,
# RAG refreshes, dreams and public downloads cannot start independent pools.
_PDF_WORKER_SEMAPHORE = threading.BoundedSemaphore(PDF_MAX_CONCURRENT_WORKERS)

_WORKER_TEMPLATE = r"""
import sys
try:
    import resource
    memory_limit = __MEMORY_BYTES__
    cpu_limit = __CPU_SECONDS__
    resource.setrlimit(resource.RLIMIT_AS, (memory_limit, memory_limit))
    resource.setrlimit(resource.RLIMIT_CPU, (cpu_limit, cpu_limit + 1))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
except Exception:
    sys.exit(3)

# Do not leave parser memory in a core dump. Linux PR_SET_DUMPABLE is best effort;
# RLIMIT_CORE is mandatory and the resource ceilings above fail closed.
try:
    import ctypes
    ctypes.CDLL(None, use_errno=True).prctl(4, 0, 0, 0, 0)
except Exception:
    pass

try:
    import json
    from io import BytesIO
    from pypdf import PdfReader

    raw = sys.stdin.buffer.read(__MAX_INPUT_BYTES__ + 1)
    if len(raw) > __MAX_INPUT_BYTES__ or not raw.startswith(b"%PDF-"):
        sys.exit(2)

    reader = PdfReader(BytesIO(raw), strict=False)
    if reader.is_encrypted:
        sys.exit(2)

    meta = reader.metadata
    pages = reader.pages
    page_count = len(pages)
    page_limit = __MAX_PAGES__
    text_limit = __MAX_TEXT_CHARS__
    collected = []
    total_chars = 0
    truncated = page_count > page_limit

    for page_index in range(min(page_count, page_limit)):
        if total_chars >= text_limit:
            truncated = True
            break
        page_text = (pages[page_index].extract_text() or "").strip()
        if not page_text:
            continue
        remaining = text_limit - total_chars
        if len(page_text) > remaining:
            page_text = page_text[:remaining]
            truncated = True
        if page_text:
            collected.append([page_index + 1, page_text])
            total_chars += len(page_text)

    def short(value):
        # PDF metadata is attacker-controlled. Keep it printable and single-line
        # before callers place titles in Markdown or author/subject in frontmatter.
        flattened = " ".join(str(value or "").split())
        return "".join(char for char in flattened if char.isprintable())[:500]

    result = {
        "title": short(meta.title if meta else ""),
        "author": short(meta.author if meta else ""),
        "subject": short(meta.subject if meta else ""),
        "page_count": page_count,
        "pages": collected,
        "truncated": truncated,
    }
    sys.stdout.buffer.write(json.dumps(result, ensure_ascii=False).encode("utf-8"))
except Exception:
    # Syntax, parser, decompression and resource failures all fail closed.
    sys.exit(4)
"""


def _build_worker_script(
    *,
    max_input_bytes: int,
    max_pages: int,
    max_text_chars: int,
    memory_bytes: int,
    cpu_seconds: int,
) -> str:
    """Build the isolated child program from validated integer limits."""
    limits = {
        "__MAX_INPUT_BYTES__": max_input_bytes,
        "__MAX_PAGES__": max_pages,
        "__MAX_TEXT_CHARS__": max_text_chars,
        "__MEMORY_BYTES__": memory_bytes,
        "__CPU_SECONDS__": cpu_seconds,
    }
    script = _WORKER_TEMPLATE
    for marker, value in limits.items():
        script = script.replace(marker, str(value))
    return script


def _positive_int(value: int, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return value


def _run_pdf_child(
    raw_bytes: bytes,
    worker_script: str,
    *,
    timeout_seconds: int,
    queue_wait_seconds: float = PDF_WORKER_QUEUE_WAIT_SECONDS,
    semaphore_held: bool = False,
):
    """Run one worker under the shared semaphore; subprocess.run kills and reaps on timeout."""
    if not isinstance(raw_bytes, bytes) or not raw_bytes.startswith(b"%PDF-"):
        return None
    acquired_here = False
    if not semaphore_held:
        if not _PDF_WORKER_SEMAPHORE.acquire(timeout=max(0.0, queue_wait_seconds)):
            return None
        acquired_here = True
    try:
        try:
            return subprocess.run(
                [sys.executable, "-I", "-c", worker_script],
                input=raw_bytes,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                timeout=timeout_seconds,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return None
    finally:
        if acquired_here:
            _PDF_WORKER_SEMAPHORE.release()


def extract_pdf_bytes(
    raw_bytes: bytes,
    *,
    max_input_bytes: int = PDF_MAX_INPUT_BYTES,
    max_pages: int = PDF_MAX_PAGES,
    max_text_chars: int = PDF_MAX_TEXT_CHARS,
    memory_bytes: int = PDF_WORKER_MEMORY_BYTES,
    cpu_seconds: int = PDF_WORKER_CPU_SECONDS,
    timeout_seconds: int = PDF_WORKER_TIMEOUT_SECONDS,
    queue_wait_seconds: float = PDF_WORKER_QUEUE_WAIT_SECONDS,
    _semaphore_held: bool = False,
) -> Optional[dict[str, Any]]:
    """Return bounded page text and metadata, or None for invalid/unsafe PDFs."""
    limits = {
        "max_input_bytes": _positive_int(max_input_bytes, "max_input_bytes"),
        "max_pages": _positive_int(max_pages, "max_pages"),
        "max_text_chars": _positive_int(max_text_chars, "max_text_chars"),
        "memory_bytes": _positive_int(memory_bytes, "memory_bytes"),
        "cpu_seconds": _positive_int(cpu_seconds, "cpu_seconds"),
        "timeout_seconds": _positive_int(timeout_seconds, "timeout_seconds"),
    }
    if not isinstance(raw_bytes, bytes) or len(raw_bytes) > limits["max_input_bytes"]:
        return None
    if not raw_bytes.startswith(b"%PDF-"):
        return None

    script = _build_worker_script(
        max_input_bytes=limits["max_input_bytes"],
        max_pages=limits["max_pages"],
        max_text_chars=limits["max_text_chars"],
        memory_bytes=limits["memory_bytes"],
        cpu_seconds=limits["cpu_seconds"],
    )
    completed = _run_pdf_child(
        raw_bytes,
        script,
        timeout_seconds=limits["timeout_seconds"],
        queue_wait_seconds=queue_wait_seconds,
        semaphore_held=_semaphore_held,
    )
    if completed is None or completed.returncode != 0:
        return None
    try:
        result = json.loads(completed.stdout.decode("utf-8", errors="strict"))
    except (UnicodeDecodeError, ValueError):
        return None
    if not isinstance(result, dict) or not isinstance(result.get("pages"), list):
        return None

    pages = []
    for item in result["pages"]:
        if (not isinstance(item, list) or len(item) != 2
                or isinstance(item[0], bool) or not isinstance(item[0], int)
                or not isinstance(item[1], str)):
            return None
        pages.append((item[0], item[1]))

    result["pages"] = pages
    result["text"] = "\n\n".join(text for _number, text in pages)
    result["truncated"] = bool(result.get("truncated"))
    result["page_count"] = max(0, int(result.get("page_count", 0)))
    return result


def extract_pdf_file(
    path: str | Path,
    *,
    max_input_bytes: int = PDF_MAX_INPUT_BYTES,
    max_pages: int = PDF_MAX_PAGES,
    max_text_chars: int = PDF_MAX_TEXT_CHARS,
    memory_bytes: int = PDF_WORKER_MEMORY_BYTES,
    cpu_seconds: int = PDF_WORKER_CPU_SECONDS,
    timeout_seconds: int = PDF_WORKER_TIMEOUT_SECONDS,
    queue_wait_seconds: float = PDF_WORKER_QUEUE_WAIT_SECONDS,
) -> Optional[dict[str, Any]]:
    """Read and parse one PDF while holding the shared slot.

    Acquire before reading: otherwise a dream batch could buffer many 50 MiB
    files while all its threads waited for the single parser process.
    """
    limit = _positive_int(max_input_bytes, "max_input_bytes")
    if not _PDF_WORKER_SEMAPHORE.acquire(timeout=max(0.0, queue_wait_seconds)):
        return None
    try:
        try:
            with Path(path).open("rb") as source:
                raw_bytes = source.read(limit + 1)
        except OSError:
            return None
        if len(raw_bytes) > limit:
            return None
        return extract_pdf_bytes(
            raw_bytes,
            max_input_bytes=limit,
            max_pages=max_pages,
            max_text_chars=max_text_chars,
            memory_bytes=memory_bytes,
            cpu_seconds=cpu_seconds,
            timeout_seconds=timeout_seconds,
            _semaphore_held=True,
        )
    finally:
        _PDF_WORKER_SEMAPHORE.release()
