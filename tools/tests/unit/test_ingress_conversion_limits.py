"""A file staged in _ingress by hand is converted under ceilings: its size
before any converter starts, and the converter child's CPU, memory and output."""
import shutil
import sys

import pytest

from tools.maintenance import ebook_to_kb_md as E
from tools.maintenance import process_ingress as P


def test_an_oversized_staged_file_is_refused_before_a_converter_starts(tmp_path, monkeypatch):
    big = tmp_path / "huge.pdf"
    with big.open("wb") as f:
        f.truncate(P.RAW_MAX_BYTES + 1)
    monkeypatch.setattr(E, "extract_pdf", lambda _p: pytest.fail("the converter ran"))
    ok, why = P.convert_staged_file(big, dry_run=True)
    assert not ok and "too large" in why
    assert big.exists()


def test_the_converter_child_runs_under_cpu_and_address_space_ceilings():
    code, out, _ = E._run_bounded(
        [sys.executable, "-c", "import resource as r; "
         "print(r.getrlimit(r.RLIMIT_CPU)[0], r.getrlimit(r.RLIMIT_AS)[0], r.getrlimit(r.RLIMIT_CORE)[0])"],
        address_space=E.PDFTOTEXT_ADDRESS_SPACE)
    assert code == 0
    assert out.split() == [str(E.CONVERT_CPU_S), str(E.PDFTOTEXT_ADDRESS_SPACE), "0"]


def test_output_past_the_ceiling_kills_the_converter(monkeypatch):
    monkeypatch.setattr(E, "MAX_OUTPUT_BYTES", 1000)
    code, out, err = E._run_bounded(
        [sys.executable, "-c", "import sys\nwhile True: sys.stdout.write('x' * 4096)"])
    assert code == -1 and out == "" and "output passed" in err


@pytest.mark.skipif(not shutil.which("pandoc"), reason="pandoc is not installed")
def test_pandoc_still_converts_under_its_heap_limit(tmp_path):
    page = tmp_path / "page.html"
    page.write_text("<html><head><title>T</title></head><body><h1>Heading</h1><p>Some words.</p></body></html>")
    text, _meta = E.extract_pandoc(page)
    assert "Heading" in text and "Some words." in text
