"""Resource-bounded PDF text extraction shared by every application path.

PDFs are complex, attacker-controlled object graphs. Parsing is confined to one
disposable child process at a time; neither a thread timeout nor a caller-specific
worker can bypass the shared process and memory budget.
"""
from __future__ import annotations

import asyncio
import contextvars
import json
import subprocess
import sys
import threading
import time
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
_PDF_CANCELLATION: contextvars.ContextVar[Optional[threading.Event]] = contextvars.ContextVar(
    "pdf_worker_cancellation", default=None
)
_PDF_SEMAPHORE_POLL_SECONDS = 0.05


def _cancellation_event() -> Optional[threading.Event]:
    """Return the cancellation token copied into this worker thread, if any."""
    return _PDF_CANCELLATION.get()


def _is_cancelled() -> bool:
    event = _cancellation_event()
    return bool(event is not None and event.is_set())


def cancellation_requested() -> bool:
    """Whether the current PDF operation's async owner has been cancelled."""
    return _is_cancelled()


async def run_cancellable_in_thread(func, /, *args, **kwargs):
    """Run a synchronous PDF caller while retaining ownership through cancellation.

    asyncio.to_thread() cancellation only cancels its awaiter. The worker thread
    continues, so PDF entry points use this wrapper: on cancellation it signals
    the copied threading.Event and drains the thread after the semaphore wait or
    parser child has stopped. The synchronous call remains usable outside asyncio.
    """
    cancel_event = threading.Event()
    token = _PDF_CANCELLATION.set(cancel_event)
    try:
        worker = asyncio.create_task(asyncio.to_thread(func, *args, **kwargs))
    finally:
        _PDF_CANCELLATION.reset(token)

    try:
        return await asyncio.shield(worker)
    except asyncio.CancelledError:
        cancel_event.set()
        # Keep owning the executor thread until its parser child is killed and
        # reaped, or its semaphore wait notices cancellation. A second cancel
        # request must not detach that cleanup either.
        while not worker.done():
            try:
                await asyncio.shield(worker)
            except asyncio.CancelledError:
                continue
            except Exception:
                break
        try:
            worker.result()
        except Exception:
            pass
        raise


def _acquire_worker_slot(queue_wait_seconds: float) -> bool:
    """Acquire the shared parser slot while remaining responsive to cancellation."""
    try:
        wait = max(0.0, float(queue_wait_seconds))
    except (TypeError, ValueError, OverflowError):
        wait = 0.0
    deadline = time.monotonic() + wait
    event = _cancellation_event()
    while True:
        if event is not None and event.is_set():
            return False
        remaining = deadline - time.monotonic()
        acquired = _PDF_WORKER_SEMAPHORE.acquire(
            timeout=min(_PDF_SEMAPHORE_POLL_SECONDS, max(0.0, remaining))
        )
        if acquired:
            if event is not None and event.is_set():
                _PDF_WORKER_SEMAPHORE.release()
                return False
            return True
        if remaining <= 0:
            return False


def _kill_and_reap(process: subprocess.Popen) -> None:
    """Terminate a parser child and collect its pipes/exit status before returning."""
    try:
        if process.poll() is None:
            process.kill()
    except OSError:
        pass
    try:
        process.communicate(timeout=5.0)
    except subprocess.TimeoutExpired:
        # SIGKILL should make this exceptional; issue it again and do not abandon
        # the Popen object while its child is still waitable.
        try:
            process.kill()
        except OSError:
            pass
        process.communicate()

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
    """Run one disposable parser, with caller cancellation and kill/reap ownership."""
    if not isinstance(raw_bytes, bytes) or not raw_bytes.startswith(b"%PDF-"):
        return None
    event = _cancellation_event()
    if event is not None and event.is_set():
        return None

    acquired_here = False
    if not semaphore_held:
        if not _acquire_worker_slot(queue_wait_seconds):
            return None
        acquired_here = True

    arguments = [sys.executable, "-I", "-c", worker_script]
    process = None
    try:
        if event is not None and event.is_set():
            return None
        try:
            process = subprocess.Popen(
                arguments,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
            )
        except OSError:
            return None

        deadline = time.monotonic() + max(0.001, float(timeout_seconds))
        input_bytes: Optional[bytes] = raw_bytes
        while True:
            if event is not None and event.is_set():
                _kill_and_reap(process)
                return None

            remaining = deadline - time.monotonic()
            if remaining <= 0:
                _kill_and_reap(process)
                return None
            try:
                stdout, _stderr = process.communicate(
                    input=input_bytes,
                    timeout=min(_PDF_SEMAPHORE_POLL_SECONDS, remaining),
                )
                if event is not None and event.is_set():
                    return None
                return subprocess.CompletedProcess(arguments, process.returncode, stdout, None)
            except subprocess.TimeoutExpired:
                # communicate() retains the original input after TimeoutExpired;
                # subsequent calls must omit it while polling for cancellation.
                input_bytes = None
            except OSError:
                _kill_and_reap(process)
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
    if _is_cancelled():
        return None
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
    if _is_cancelled() or not _acquire_worker_slot(queue_wait_seconds):
        return None
    try:
        if _is_cancelled():
            return None
        try:
            with Path(path).open("rb") as source:
                raw_bytes = source.read(limit + 1)
        except OSError:
            return None
        if _is_cancelled() or len(raw_bytes) > limit:
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
