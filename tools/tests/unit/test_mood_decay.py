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


def test_engagement_decays_once_per_idle_span(tmp_path):
    """update_kaia_state runs twice in one turn before the interaction clock is
    stamped; the second call must not apply the same idle span again."""
    import time
    from utils.infrastructure.system.bot_state import BotState

    state = BotState(state_file=str(tmp_path / "bot_state.json"))
    state.save = lambda: None
    state.kaia_engagement = 0.8
    state.last_interaction_time = time.time() - 10 * 3600

    state.update_kaia_state()
    first = state.kaia_engagement
    state.update_kaia_state(coherence_sample=0.5)

    assert abs(first - 0.8 * 0.5 ** (10 / 24)) < 1e-3
    assert state.kaia_engagement == first


def test_a_plain_read_of_the_mood_sees_it_decayed(monkeypatch, tmp_path):
    """The art intent, the proactive opener, presence and !scores read the
    properties directly; on a quiet day they saw arousal as of hours ago."""
    clock = [1_000_000.0]
    arc = _arc(monkeypatch, tmp_path, clock)
    clock[0] += 6 * 3600
    assert arc.arousal < 1.0 and arc.social_energy > 0.0
    first = arc.arousal
    assert arc.arousal == first      # reading again changes nothing


def test_mood_shapes_generation_within_its_bounds():
    """Bounded, and a drained Kaia is asked to be terser, not worse."""
    from utils.core.kaia_mood import mood_length_note, mood_temperature_delta
    assert mood_temperature_delta(0.5) == 0.0
    assert mood_temperature_delta(1.0) == 0.05 and mood_temperature_delta(0.0) == -0.05
    assert mood_temperature_delta(7) == 0.05
    assert mood_length_note(0.8) == "" and "say less" in mood_length_note(0.1)


def test_a_busy_day_tires_her_without_emptying_her(monkeypatch, tmp_path):
    """She sat at zero social energy for 52 of a busy day's 118 turns and took
    16 hours of quiet to refill. Sixty turns across a day — bursts of six, a
    minute apart — should tire her, not empty her; and from empty, a quiet
    evening should bring her most of the way back."""
    import datetime
    clock = [datetime.datetime(2026, 10, 1, 9, 0).timestamp()]
    arc = _arc(monkeypatch, tmp_path, clock)
    arc._mood.social_energy = 0.8
    arc._mood.arousal = 0.4
    low = []
    for _ in range(10):
        for _ in range(6):
            arc.update(0.5, 80)
            low.append(arc._mood.social_energy)
            clock[0] += 60
        clock[0] += 75 * 60
    assert min(low) > 0.3
    assert arc._mood.arousal < 0.99               # toward 1.0, not onto it

    arc._mood.social_energy = 0.0
    arc._mood.last_updated = clock[0]
    clock[0] += 5 * 3600
    arc.get_prompt_injection()
    assert arc._mood.social_energy > 0.5
