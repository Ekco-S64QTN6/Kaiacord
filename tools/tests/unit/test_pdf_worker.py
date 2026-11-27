"""Real-process regression coverage for the shared PDF parser boundary."""
import io
import json
import os
import subprocess
import sys
import time
from types import SimpleNamespace
from pathlib import Path

import pytest

from utils.core import pdf_worker as pw


def _small_pdf(text="bounded PDF fixture text"):
    escaped = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    stream = f"BT /F1 12 Tf 72 720 Td ({escaped}) Tj ET".encode("ascii")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
    ]
    data = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for number, body in enumerate(objects, 1):
        offsets.append(len(data))
        data.extend(f"{number} 0 obj\n".encode("ascii"))
        data.extend(body)
        data.extend(b"\nendobj\n")
    xref = len(data)
    data.extend(f"xref\n0 {len(offsets)}\n".encode("ascii"))
    data.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        data.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    data.extend(
        f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\n"
        f"startxref\n{xref}\n%%EOF\n".encode("ascii")
    )
    return bytes(data)


def test_worker_extracts_text_and_page_metadata_in_a_child_process():
    result = pw.extract_pdf_bytes(_small_pdf())

    assert result is not None
    assert result["page_count"] == 1
    assert result["pages"] == [(1, "bounded PDF fixture text")]
    assert result["text"] == "bounded PDF fixture text"
    assert result["truncated"] is False


def test_malformed_and_encrypted_pdfs_fail_closed():
    from pypdf import PdfWriter

    assert pw.extract_pdf_bytes(b"%PDF-1.4\nnot a valid document") is None

    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    writer.encrypt("secret")
    output = io.BytesIO()
    writer.write(output)
    assert pw.extract_pdf_bytes(output.getvalue()) is None


def test_oversized_input_is_rejected_before_starting_the_child(monkeypatch):
    called = []
    monkeypatch.setattr(pw.subprocess, "run", lambda *a, **k: called.append(True))

    result = pw.extract_pdf_bytes(
        b"%PDF-" + b"x" * 17,
        max_input_bytes=16,
    )

    assert result is None
    assert called == []


def test_invalid_worker_limits_are_rejected():
    with pytest.raises(ValueError):
        pw.extract_pdf_bytes(_small_pdf(), memory_bytes=True)
    with pytest.raises(ValueError):
        pw.extract_pdf_bytes(_small_pdf(), max_pages=0)


def test_child_timeout_fails_closed(monkeypatch):
    captured = {}

    def timeout(command, **kwargs):
        captured["command"] = command
        captured.update(kwargs)
        raise subprocess.TimeoutExpired(command, kwargs["timeout"])

    monkeypatch.setattr(pw.subprocess, "run", timeout)
    assert pw.extract_pdf_bytes(_small_pdf(), timeout_seconds=2) is None
    assert captured["command"][:2] == [sys.executable, "-I"]
    assert captured["timeout"] == 2
    assert captured["stdout"] == subprocess.PIPE
    assert captured["stderr"] == subprocess.DEVNULL


def test_worker_program_sets_hard_resource_limits_and_no_core_dumps(monkeypatch):
    captured = {}
    payload = json.dumps({
        "title": "", "author": "", "subject": "", "page_count": 1,
        "pages": [[1, "bounded output"]], "truncated": False,
    }).encode()

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured["input"] = kwargs["input"]
        captured["timeout"] = kwargs["timeout"]
        captured["stdout"] = kwargs["stdout"]
        captured["stderr"] = kwargs["stderr"]
        script = command[-1]
        assert "resource.setrlimit(resource.RLIMIT_AS" in script
        assert "resource.setrlimit(resource.RLIMIT_CPU" in script
        assert "resource.setrlimit(resource.RLIMIT_CORE, (0, 0))" in script
        assert ".prctl(4, 0, 0, 0, 0)" in script
        return SimpleNamespace(returncode=0, stdout=payload)

    monkeypatch.setattr(pw.subprocess, "run", fake_run)
    result = pw.extract_pdf_bytes(_small_pdf())

    assert result["text"] == "bounded output"
    assert captured["command"][:2] == [sys.executable, "-I"]
    assert captured["input"] == _small_pdf()
    assert captured["timeout"] == pw.PDF_WORKER_TIMEOUT_SECONDS


def test_pdf_file_read_is_bounded_before_the_child(tmp_path, monkeypatch):
    path = tmp_path / "oversized.pdf"
    path.write_bytes(b"%PDF-" + b"x" * 32)
    called = []
    monkeypatch.setattr(pw.subprocess, "run", lambda *a, **k: called.append(True))

    assert pw.extract_pdf_file(path, max_input_bytes=16) is None
    assert called == []


@pytest.mark.skipif(sys.platform != "linux", reason="Linux resource limits required")
def test_worker_enforces_its_address_space_limit():
    raw = _small_pdf()
    memory_limit = 256 * 1024 * 1024
    script = pw._build_worker_script(
        max_input_bytes=pw.PDF_MAX_INPUT_BYTES,
        max_pages=20,
        max_text_chars=1000,
        memory_bytes=memory_limit,
        cpu_seconds=10,
    ) + f"""
import mmap
try:
    mmap.mmap(-1, {memory_limit + 32 * 1024 * 1024})
except (OSError, MemoryError):
    sys.exit(42)
sys.exit(43)
"""
    completed = pw._run_pdf_child(raw, script, timeout_seconds=5)
    assert completed is not None
    assert completed.returncode == 42, "child did not hit RLIMIT_AS"


@pytest.mark.skipif(sys.platform != "linux", reason="Linux resource limits required")
def test_worker_cpu_limit_terminates_a_cpu_bound_child(tmp_path):
    raw = _small_pdf()
    marker = tmp_path / "cpu-loop-started"
    script = pw._build_worker_script(
        max_input_bytes=pw.PDF_MAX_INPUT_BYTES,
        max_pages=20,
        max_text_chars=1000,
        memory_bytes=pw.PDF_WORKER_MEMORY_BYTES,
        cpu_seconds=1,
    ) + (
        "\nfrom pathlib import Path\n"
        f"Path({str(marker)!r}).write_text('started')\n"
        "while True:\n    pass\n"
    )

    started = time.monotonic()
    completed = pw._run_pdf_child(raw, script, timeout_seconds=5)
    elapsed = time.monotonic() - started

    assert marker.exists()
    assert completed is not None and completed.returncode != 0
    assert elapsed < 5


@pytest.mark.skipif(sys.platform != "linux", reason="Linux process handling required")
def test_worker_wall_timeout_kills_and_reaps_the_child(tmp_path, monkeypatch):
    raw = _small_pdf()
    pid_file = tmp_path / "pdf-worker.pid"
    script = pw._build_worker_script(
        max_input_bytes=pw.PDF_MAX_INPUT_BYTES,
        max_pages=20,
        max_text_chars=1000,
        memory_bytes=pw.PDF_WORKER_MEMORY_BYTES,
        cpu_seconds=30,
    ) + (
        "\nimport os\nfrom pathlib import Path\n"
        f"Path({str(pid_file)!r}).write_text(str(os.getpid()))\n"
        "import time\ntime.sleep(10)\n"
    )

    started = time.monotonic()
    completed = pw._run_pdf_child(raw, script, timeout_seconds=1)
    assert completed is None
    assert time.monotonic() - started < 3
    assert pid_file.exists(), "worker did not reach its deliberate sleep"
    child_pid = int(pid_file.read_text(encoding="utf-8"))
    with pytest.raises(ProcessLookupError):
        os.kill(child_pid, 0)


def test_public_download_pdf_conversion_uses_the_same_process_budget(monkeypatch):
    from utils.commands import download_handler as downloads

    calls = []
    extracted = {
        "title": "Downloaded report",
        "author": "Example author",
        "subject": "Example subject",
        "page_count": 1,
        "pages": [(1, "This is enough extracted text to validate the conversion route.")],
        "text": "This is enough extracted text to validate the conversion route.",
        "truncated": False,
    }

    def fake_extract(raw_bytes, **kwargs):
        calls.append((raw_bytes, kwargs))
        return extracted

    monkeypatch.setattr(pw, "extract_pdf_bytes", fake_extract)
    title, markdown, metadata = downloads._convert_pdf(
        _small_pdf(), "https://example.test/reports/document.pdf"
    )

    assert title == "Downloaded report"
    assert "## Page 1" in markdown
    assert "validate the conversion route" in markdown
    assert metadata == {"author": "Example author", "summary": "Example subject"}
    assert len(calls) == 1
    assert calls[0][1]["max_input_bytes"] == downloads.MAX_DOWNLOAD_BYTES
    assert calls[0][1]["memory_bytes"] == downloads.PDF_CHILD_MEMORY_BYTES
    assert calls[0][1]["cpu_seconds"] == downloads.PDF_CHILD_CPU_SECONDS
    assert calls[0][1]["timeout_seconds"] == downloads.PDF_CHILD_TIMEOUT_SECONDS

def test_untrusted_pdf_metadata_is_printable_and_single_line():
    from pypdf import PdfWriter

    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    writer.add_metadata({
        "/Title": "Trusted title\n# injected heading\u202e",
        "/Author": "Author\nwith another line",
        "/Subject": "Subject\r\nwith a second line",
    })
    output = io.BytesIO()
    writer.write(output)

    result = pw.extract_pdf_bytes(output.getvalue())

    assert result is not None
    assert result["title"] == "Trusted title # injected heading"
    assert result["author"] == "Author with another line"
    assert result["subject"] == "Subject with a second line"
    assert all("\n" not in result[key] and "\r" not in result[key]
               for key in ("title", "author", "subject"))


def test_pdf_file_waits_for_shared_slot_before_reading(tmp_path, monkeypatch):
    path = tmp_path / "queued.pdf"
    path.write_bytes(_small_pdf())
    opened = []
    real_open = Path.open

    def observed_open(self, *args, **kwargs):
        opened.append(self)
        return real_open(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", observed_open)
    assert pw._PDF_WORKER_SEMAPHORE.acquire(blocking=False)
    try:
        assert pw.extract_pdf_file(path, queue_wait_seconds=0.02) is None
        assert opened == []
    finally:
        pw._PDF_WORKER_SEMAPHORE.release()
