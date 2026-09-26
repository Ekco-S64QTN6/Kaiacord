"""Memory anchors: matching, the injected line, and concurrent writers."""
import json
import threading

import pytest

import utils.core.memory_anchors as ma


@pytest.fixture
def store(tmp_path, monkeypatch):
    path = tmp_path / "anchors.json"
    monkeypatch.setattr(ma, "ANCHORS_PATH", str(path))
    return path


def test_punctuation_does_not_hide_a_match(store):
    ma.save_anchor(None, "loneliness_and_validation",
                   "craving validation, and the loneliness of being unseen.", weight=0.9)
    hits = ma.find_matching_anchors("is validation just a cure for loneliness?")
    assert [a["theme"] for a in hits] == ["loneliness_and_validation"]


def test_one_shared_word_is_not_a_match(store):
    ma.save_anchor(None, "intellectual humility", "I don't know everything.", weight=0.9)
    assert ma.find_matching_anchors("Tattoos don't get u into heaven?") == []


def test_filler_words_that_miss_the_theme_are_not_a_match(store):
    ma.save_anchor(None, "responsibility & burden",
                   "being a little real about duty", weight=0.9)
    assert ma.find_matching_anchors("it's a little bit like being in a dream") == []


def test_an_anchor_with_no_person_does_not_name_none(store):
    line = ma.format_anchor_injection({"theme": "privacy_erosion",
                                       "anchor_text": "devices as data collection",
                                       "user_name": None})
    assert "None" not in line
    assert "privacy erosion" in line


def test_dream_salience_is_clamped(store):
    ma.save_anchor(None, "nostalgia", "old servers humming", salience=16.8)
    [saved] = json.loads(store.read_text())
    assert saved["salience"] == 1.0


def test_concurrent_saves_keep_every_anchor(store):
    def save(i):
        ma.save_anchor(None, f"theme {i}", f"anchor text number {i}")

    threads = [threading.Thread(target=save, args=(i,)) for i in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(json.loads(store.read_text())) == 20


def test_the_cap_evicts_the_weakest_not_the_oldest(tmp_path, monkeypatch):
    import json, time
    monkeypatch.setattr(ma, "ANCHORS_PATH", str(tmp_path / "anchors.json"))
    monkeypatch.setattr(ma, "MAX_ANCHORS", 2)
    old = time.time() - 40 * 86400
    (tmp_path / "anchors.json").write_text(json.dumps([
        {"theme": "boats", "anchor_text": "an old boat she keeps coming back to", "weight": 0.9,
         "salience": 1.0, "created_at": old, "access_count": 6},
        {"theme": "toast", "anchor_text": "a passing remark about toast", "weight": 0.2,
         "salience": 0.1, "created_at": time.time() - 86400}]))
    ma.save_anchor(None, "rain", "rain on a tin roof at night", weight=0.7)
    assert sorted(a["theme"] for a in json.loads((tmp_path / "anchors.json").read_text())) == ["boats", "rain"]


def test_an_updated_anchor_is_dated_by_its_update():
    import time
    anchor = {"theme": "boats", "anchor_text": "x", "created_at": time.time() - 90 * 86400,
              "updated_at": time.time() - 3600}
    assert "earlier today" in ma.format_anchor_injection(anchor)


def test_eviction_spares_the_new_and_keeps_what_she_recalls():
    """Evicting the weakest turned the store over every two weeks, so nothing
    lived long enough to fade."""
    import time
    from utils.core import memory_anchors as ma
    now = time.time()
    old = now - 60 * 86400
    anchors = ([{"anchor_text": f"recalled {i}", "created_at": old, "access_count": 5, "effective_weight": 0.3}
                for i in range(40)]
               + [{"anchor_text": f"never {i}", "created_at": old, "access_count": 0, "effective_weight": 0.9}
                  for i in range(40)]
               + [{"anchor_text": f"new {i}", "created_at": now, "access_count": 0, "effective_weight": 0.2}
                  for i in range(30)])
    kept = ma._evict(anchors, now)
    assert len(kept) == ma.MAX_ANCHORS
    texts = {a["anchor_text"] for a in kept}
    assert all(f"recalled {i}" in texts for i in range(40))
    assert all(f"new {i}" in texts for i in range(30))


def test_a_faded_anchor_is_offered_as_a_fragment():
    import time
    from utils.core.memory_anchors import format_anchor_injection
    faded = {"theme": "boats", "anchor_text": "we talked about the old wooden boat on the lake at dawn",
             "user_name": "Ekco", "created_at": time.time() - 200 * 86400, "effective_weight": 0.3}
    line = format_anchor_injection(faded)
    assert line.startswith("[faded memory:") and "don't fill in the rest" in line
    assert "at dawn" not in line
    fresh = dict(faded, effective_weight=0.8)
    assert format_anchor_injection(fresh).startswith("[memory anchor:")
