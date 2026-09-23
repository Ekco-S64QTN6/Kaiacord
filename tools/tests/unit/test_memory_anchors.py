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
