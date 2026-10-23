"""Strudel-specific audio routing must not mutate the bot's environment."""

from utils.audio import strudel_engine


def test_chromium_receives_private_pulse_sink_environment(monkeypatch):
    monkeypatch.delenv("PULSE_SINK", raising=False)
    env = strudel_engine._browser_environment()

    assert env["PULSE_SINK"] == strudel_engine.SINK_NAME
    assert "PULSE_SINK" not in __import__("os").environ


def test_browser_environment_preserves_other_variables_without_mutating_input():
    original = {"PATH": "/test/bin", "OTHER_FLAG": "keep"}
    env = strudel_engine._browser_environment(original)

    assert env == {
        "PATH": "/test/bin",
        "OTHER_FLAG": "keep",
        "PULSE_SINK": strudel_engine.SINK_NAME,
    }
    assert original == {"PATH": "/test/bin", "OTHER_FLAG": "keep"}
