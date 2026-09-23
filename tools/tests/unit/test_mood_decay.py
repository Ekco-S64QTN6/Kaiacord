"""Mood decay is a function of elapsed time, not of how often mood is read."""
import utils.core.kaia_mood as kaia_mood


def _arc(monkeypatch, tmp_path, clock):
    monkeypatch.setattr(kaia_mood, "STATE_PATH", str(tmp_path / "mood_state.json"))
    monkeypatch.setattr(kaia_mood, "HISTORY_PATH", str(tmp_path / "mood_history.jsonl"))
    monkeypatch.setattr(kaia_mood.time, "time", lambda: clock[0])
    arc = kaia_mood.EmotionalArc()
    arc._mood.arousal = 1.0
    arc._mood.social_energy = 0.0
    arc._mood.last_updated = clock[0]
    return arc


def test_reading_the_mood_does_not_decay_it_again(monkeypatch, tmp_path):
    """Every reader used to re-apply the whole interval since the last
    interaction, so six reads over three hours decayed arousal as if eighteen
    hours had passed."""
    clock = [1_000_000.0]
    often = _arc(monkeypatch, tmp_path, clock)
    for _ in range(6):
        clock[0] += 1800
        often.get_prompt_injection()

    clock[0] = 1_000_000.0
    once = _arc(monkeypatch, tmp_path, clock)
    clock[0] += 3 * 3600
    once.get_prompt_injection()

    assert abs(often._mood.arousal - once._mood.arousal) < 1e-9
    expected = kaia_mood.BASELINE_AROUSAL + (1.0 - kaia_mood.BASELINE_AROUSAL) * 0.5 ** (
        3 * 3600 / kaia_mood.DECAY_HALF_LIFE)
    assert abs(once._mood.arousal - expected) < 1e-9
