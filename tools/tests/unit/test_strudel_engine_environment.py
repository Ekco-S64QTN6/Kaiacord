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



def test_http_server_uses_os_assigned_port_and_closes_socket_and_thread():
    from utils.audio.strudel_engine import StrudelEngine

    engine = StrudelEngine()
    engine._serve()
    server = engine._srv
    thread = engine._srv_thread
    address = server.server_address

    assert address[0] == "127.0.0.1"
    assert engine.port == address[1]
    assert thread.is_alive()
    assert server.fileno() >= 0

    engine._close_server()

    assert server.fileno() == -1
    assert not thread.is_alive()
    assert engine._srv is None
    assert engine._srv_thread is None
    assert engine.port == 0

    # Cleanup remains safe on repeated calls.
    engine._close_server()
