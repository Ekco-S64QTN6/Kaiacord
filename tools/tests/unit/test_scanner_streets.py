"""Street names in dispatch transcripts, put right against the local list."""
import json

import pytest

from utils.radio import ledger, scanner, streets

NAMES = ["South Cockrell Hill Road", "North Cockrell Hill Road", "Hill Avenue", "Throckmorton Street",
         "Corsicana Street", "East Lake Highlands Drive", "Noel Road", "Coronado Avenue", "Lear Street",
         "Main Street", "Avon Avenue", "Belt Line Road", "Medford Court"]


@pytest.fixture(autouse=True)
def street_list(tmp_path, monkeypatch):
    p = tmp_path / "streets.json"
    p.write_text(json.dumps(streets.build(NAMES)))
    monkeypatch.setattr(streets, "path", lambda: p)
    monkeypatch.setattr(streets, "_cache", {})
    return p


def test_the_list_keeps_names_and_types_without_directions():
    data = streets.build(NAMES)["names"]
    assert data["cockrell hill"] == ["road"] and data["belt line"] == ["road"]
    assert streets.split_name("Ramp") is None


try:
    import nltk.corpus  # noqa: F401
    _NLTK = True
except ImportError:            # a standalone without the word list corrects phrases only
    _NLTK = False
_single = pytest.mark.skipif(not _NLTK, reason="single-word fixes need nltk's English word list")


@pytest.mark.parametrize("heard,fixed", [
    ("cross of South Cockroach Hill Road and Main Street", "cross of South Cockrell Hill Road and Main Street"),
    pytest.param("1607 Rockmorton Street, 1607 Rockmorton Street",
                 "1607 Throckmorton Street, 1607 Throckmorton Street", marks=_single),
    pytest.param("1515 Corticana Street", "1515 Corsicana Street", marks=_single),
])
def test_a_misheard_street_is_put_right(heard, fixed):
    assert streets.correct(heard)[0] == fixed


@pytest.mark.parametrize("heard", [
    "cross of Main Street and Hill Avenue",          # known streets
    "X-ray, Avenue Street",                          # a type word is never a name
    "cross of First Avenue",                         # an English word is never replaced ("Avon")
    "cross of Condo Avenue",                         # a syllable count off ("Coronado")
    "cross of Levar Street",                         # ("Lear")
    "cross of cockroach hill road",                  # lowercase: Whisper's comma-broken spans
    "cross of Beltline Road",                        # spacing alone needs no fix
])
def test_what_is_not_touched(heard):
    assert streets.correct(heard) == (heard, [])


def test_without_a_list_nothing_changes(street_list):
    street_list.unlink()
    assert streets.correct("South Cockroach Hill Road")[1] == []


def test_only_dispatch_channels_are_corrected():
    assert scanner.fix_streets("South Cockroach Hill Road", 460_575_000) == "South Cockrell Hill Road"
    assert scanner.fix_streets("South Cockroach Hill Road", 146_520_000) == "South Cockroach Hill Road"   # ham


def test_a_logged_transcript_is_corrected_in_place(tmp_path, monkeypatch):
    import importlib.util
    from pathlib import Path
    monkeypatch.setattr(ledger, "telemetry_path", lambda p: str(tmp_path / "ledger.sqlite3"))
    ledger.record(460_575_000, "voice", 20, 3000, 0.1, transcript="cross of South Cockroach Hill Road, map 62")
    root = Path(__file__).resolve().parents[3]
    spec = importlib.util.spec_from_file_location("ledger_repair", root / "tools/maintenance/ledger_repair.py")
    repair = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(repair)
    assert repair.repair_streets(apply=False) == 1 and "Cockroach" in ledger.channel(460_575_000)["last_transcript"]
    assert repair.repair_streets(apply=True) == 1
    assert ledger.channel(460_575_000)["last_transcript"] == "cross of South Cockrell Hill Road, map 62"
    assert repair.repair_streets(apply=True) == 0
