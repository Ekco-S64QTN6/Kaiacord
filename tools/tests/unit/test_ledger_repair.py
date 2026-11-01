"""The ledger repair: kept carrier clips re-judged, split rows folded together."""
import importlib.util
from pathlib import Path

import pytest

from utils.radio import ledger, scanner

ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture
def repair(tmp_path, monkeypatch):
    monkeypatch.setattr(ledger, "telemetry_path", lambda p: str(tmp_path / "ledger.sqlite3"))
    monkeypatch.setattr(scanner, "_clips_dir", lambda: tmp_path)
    spec = importlib.util.spec_from_file_location("ledger_repair", ROOT / "tools/maintenance/ledger_repair.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_a_carrier_clip_with_words_becomes_voice_and_one_without_is_dropped(repair, tmp_path, monkeypatch):
    for name in ("talk.ogg", "hopper.ogg"):
        (tmp_path / name).write_bytes(b"x")
    (tmp_path / "hopper.png").write_bytes(b"x")
    ledger.record(460_575_000, "carrier", 20, 3000, 0.1, clip="talk.ogg", when=1000.0)
    ledger.record(927_068_750, "carrier", 9, 3000, 0.1, clip="hopper.ogg", when=1001.0)
    ledger.record(927_068_750, "carrier", 9, 3000, 0.1, clip="gone.ogg", when=1002.0)
    monkeypatch.setattr(repair, "_audio", lambda p: p.name)
    monkeypatch.setattr(repair, "_words", lambda a, f: "engine 11, cross of main and elm, map 45" if a == "talk.ogg" else "")
    monkeypatch.setattr(scanner, "morse_id", lambda a: False)

    assert repair.repair_clips(apply=False) == {"voice": 1, "short": 0, "morse": 0, "dropped": 1, "missing": 1}
    assert (tmp_path / "hopper.ogg").exists() and ledger.channel(460_575_000)["voice"] == 0   # a dry run writes nothing

    repair.repair_clips(apply=True)
    ch = ledger.channel(460_575_000)
    assert ch["voice"] == 1 and "engine 11" in ch["last_transcript"]
    assert not (tmp_path / "hopper.ogg").exists() and not (tmp_path / "hopper.png").exists()
    kinds = {e["clip"] or e["freq_hz"]: e["kind"] for e in ledger.events_since(0)}
    assert kinds["talk.ogg"] == "voice" and kinds[927_068_750] == "carrier" and "gone.ogg" not in kinds


def test_rows_one_transmitter_was_split_across_are_folded_into_the_busier(repair):
    for _ in range(3):
        ledger.record(460_575_000, "voice", 30, 3000, 0.1, transcript="rescue 5")
    ledger.record(460_581_250, "voice", 30, 3000, 0.1, transcript="rescue 6")
    ledger.record(464_337_500, "carrier", 5, 3000, 0.1)
    ledger.record(464_343_750, "carrier", 5, 3000, 0.1)                # no voice: only merged when asked
    assert repair.split_pairs([]) == [(460_581_250, 460_575_000)]
    assert repair.repair_splits([(464_343_750, 464_337_500)], apply=True) == 2
    assert ledger.channel(460_581_250) is None and ledger.channel(464_343_750) is None
    assert ledger.channel(460_575_000)["voice"] == 4 and ledger.channel(464_337_500)["hits"] == 2


def test_a_voiceless_shadow_is_folded_only_beside_a_much_busier_row(repair):
    def hits(f, n):
        for _ in range(n):
            ledger.record(f, "carrier", 5, 3000, 0.1)
    hits(464_337_500, 30); hits(464_343_750, 4)              # a shadow: folded
    hits(463_750_000, 12); hits(463_756_250, 15); hits(463_762_500, 11)   # a chain: maybe two channels, left
    hits(450_812_500, 1); hits(450_818_750, 4)                # too few to tell
    assert repair.split_pairs([], carriers=True) == [(464_343_750, 464_337_500)]
    assert repair.split_pairs([]) == []                       # without --carriers, voice pairs only


def test_apply_is_refused_while_the_scanner_is_watching(repair, monkeypatch, capsys):
    monkeypatch.setattr(scanner, "within_hours", lambda now=None: True)
    assert repair.main(["--merge", "--apply"]) == 2
    assert "refused" in capsys.readouterr().err
