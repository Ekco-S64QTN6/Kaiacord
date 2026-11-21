"""The radio log keeps its recordings when the file cannot be read."""
from utils.radio import log as radio_log


def test_an_unreadable_log_is_kept_aside_not_replaced():
    """Adding one recording to the [] an unreadable log loads as replaced the log
    and orphaned every clip it named."""
    path = radio_log.log_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('[{"id": "e1", "clip": "e1.ogg"', encoding="utf-8")
    try:
        radio_log.add({"id": "e2", "kind": "numbers", "station": "E11", "khz": 5000.0,
                       "started": "2026-11-21T03:00:00+00:00"})
        kept = list(path.parent.glob(path.name + ".unreadable-*"))
        assert len(kept) == 1 and '"e1.ogg"' in kept[0].read_text(encoding="utf-8")
        assert [e["id"] for e in radio_log.entries()] == ["e2"]
    finally:
        path.unlink(missing_ok=True)
        for k in path.parent.glob(path.name + ".unreadable-*"):
            k.unlink()


def test_a_missing_log_is_simply_empty():
    radio_log.log_path().unlink(missing_ok=True)
    assert radio_log.entries(strict=True) == []
    assert not list(radio_log.log_path().parent.glob(radio_log.log_path().name + ".unreadable-*"))
