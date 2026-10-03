"""The memory audit tells a leak from a heap that won't shrink."""
import json
import tracemalloc

from utils.infrastructure.monitoring import mem_probe


def test_a_sample_records_rss_and_the_trim(tmp_path, monkeypatch):
    out = tmp_path / "mem.jsonl"
    monkeypatch.setattr("utils.infrastructure.monitoring.telemetry_paths.telemetry_path", lambda p: str(out))
    row = mem_probe.sample()
    assert row["rss_mb"] > 0 and row["trimmed_mb"] >= 0 and row["rss_after_trim_mb"] <= row["rss_mb"]
    assert json.loads(out.read_text().splitlines()[-1])["rss_mb"] == row["rss_mb"]
    assert mem_probe.describe(row).startswith("Memory Audit: RSS")


def test_tracing_names_the_line_that_grew(tmp_path, monkeypatch):
    monkeypatch.setattr("utils.infrastructure.monitoring.telemetry_paths.telemetry_path", lambda p: str(tmp_path / "m.jsonl"))
    monkeypatch.setattr(mem_probe, "_baseline", None)
    was = tracemalloc.is_tracing()
    tracemalloc.start(3)
    try:
        mem_probe.sample()                                       # the baseline
        hoard = [bytearray(1024) for _ in range(20000)]          # ~20 MB kept alive
        row = mem_probe.sample()
        assert row["traced_mb"] >= 15
        assert any("test_mem_probe.py" in s["site"] and s["mb"] >= 15 for s in row["sites"])
        assert "grew most: " in mem_probe.describe(row)
        busy = mem_probe.sample(busy=lambda: True)
        assert busy["sites"] == "skipped: voice playing"        # no snapshot while music plays
        del hoard
    finally:
        if not was:
            tracemalloc.stop()


def test_tracing_stays_off_unless_asked():
    if not tracemalloc.is_tracing():
        assert mem_probe.start_trace(enabled=False) is False
