"""Real-browser gesture tests for the DJ booth cue and beat-loop controls."""
from __future__ import annotations

import io
import time
import types

import numpy as np
import pytest
from playwright.sync_api import sync_playwright

from utils.audio import dj_dashboard as D
from utils.audio import library
from utils.audio import records as R
from utils.audio.beatgrid import Grid


@pytest.fixture
def booth(monkeypatch, tmp_path):
    """Run the actual loopback booth against one deterministic in-memory deck."""
    guild_id = 918273
    grid = Grid(120.0, 0.0, 8.0)
    frame_count = 20 * R.FRAMES_PER_S
    values = (np.arange(frame_count, dtype=np.int16) % 14000) + 1000
    payload = np.repeat(values, R.FRAME_SAMPLES * 2).tobytes()

    def factory(_path, ratio, gain=0.0, offset=0.0, semitones=0):
        start = int(round(offset / ratio * R.FRAMES_PER_S))
        return io.BytesIO(payload[start * R.FRAME_BYTES:])

    record = library.Record(
        path="/virtual/dj-booth-playwright-track.wav",
        artist="Browser Test",
        title="Gesture Track",
        bpm=120,
        key="8A",
        genre="House",
    )
    first = R.Deck(record, 1.0, 300.0, factory)
    first.grid = grid
    deadline = time.monotonic() + 3.0
    while not first.ready(100) and time.monotonic() < deadline:
        time.sleep(0.01)
    assert first.ready(100), "the deterministic deck decoder did not warm"

    voice = types.SimpleNamespace(
        guild=types.SimpleNamespace(id=guild_id),
        channel=types.SimpleNamespace(name="Browser Booth", members=[]),
    )
    session = R.RecordsSession(voice, [], "Playwright")
    source = R.CrossfadeSource(
        first,
        lambda _deck: None,
        stream_factory=factory,
        grid_at=lambda *_args: grid,
    )
    source.rides = False
    source._fine = lambda _deck, _plan: None
    session.source = source
    session._humans = lambda: ["Browser Test"]
    session.names = ["Browser Test — Gesture Track"]

    monkeypatch.setattr(
        D, "_cfg",
        lambda key, default=None: 0 if key == "dj_dashboard_port" else default,
    )
    monkeypatch.setattr(D, "_mood", lambda: {"arousal": 0.5})
    monkeypatch.setattr(D, "_want_wave", lambda track_path: D.track_id(track_path))
    monkeypatch.setattr(D.record_cues, "record_key", lambda item: item.path)
    monkeypatch.setattr(
        D.record_cues,
        "telemetry_path",
        lambda _name: str(tmp_path / "cues.json"),
    )
    D.record_cues.clear_cache()
    monkeypatch.setitem(R._sessions, guild_id, session)

    base = D.serve()
    assert base.startswith("http://127.0.0.1:"), "the DJ booth HTTP server did not start"
    yield session, source, record, base

    server, D._server = D._server, None
    if server is not None:
        server.shutdown()
        server.server_close()
    source.cleanup()
    R._sessions.pop(guild_id, None)
    D.record_cues.clear_cache()


def _wait_for_ui_state(page, selector: str, value: str) -> None:
    page.wait_for_function(
        """({selector, value}) => {
          const element = document.querySelector(selector);
          return !!element && element.textContent.trim() === value;
        }""",
        arg={"selector": selector, "value": value},
        timeout=10000,
    )


def _real_post_click(page, locator, route: str, expected_status: int = 200, **options) -> None:
    with page.expect_response(
        lambda response: response.url.endswith(route)
        and response.request.method == "POST"
    ) as response_info:
        locator.click(**options)
    assert response_info.value.status == expected_status


def test_real_clicks_store_overwrite_recall_clear_cues_and_control_beat_loops(booth):
    _session, source, record, base = booth
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1600, "height": 1100})
        page.add_init_script("localStorage.setItem('kaia.fx', '0')")
        try:
            response = page.goto(base, wait_until="domcontentloaded", timeout=15000)
            assert response is not None and response.ok
            _wait_for_ui_state(page, "#deck1 [data-f=state]", "ON AIR")

            memory = page.locator('#deck1 [data-cue-kind="memory"]')
            _real_post_click(page, memory, "/cuebank")
            page.wait_for_function(
                "() => document.querySelector('#deck1 [data-cue-kind=memory]').classList.contains('filled')",
                timeout=5000,
            )
            first_memory = D.record_cues.load(record)["memory"]
            assert first_memory == pytest.approx(source.current.at() * source.current.ratio)

            for _ in range(40):
                source.read()
            _real_post_click(page, memory, "/cuebank", modifiers=["Shift"])
            overwritten_memory = D.record_cues.load(record)["memory"]
            assert overwritten_memory > first_memory + 0.5

            _real_post_click(page, memory, "/cuebank", button="right")
            page.wait_for_function(
                "() => !document.querySelector('#deck1 [data-cue-kind=memory]').classList.contains('filled')",
                timeout=5000,
            )
            assert D.record_cues.load(record)["memory"] is None

            hot = page.locator('#deck1 [data-cue-kind="hot"][data-cue-index="0"]')
            _real_post_click(page, hot, "/cuebank")
            page.wait_for_function(
                """() => document.querySelector('#deck1 [data-cue-kind="hot"][data-cue-index="0"]').classList.contains('filled')""",
                timeout=5000,
            )
            first_hot = D.record_cues.load(record)["hot"][0]
            for _ in range(35):
                source.read()
            _real_post_click(page, hot, "/cuebank", modifiers=["Shift"])
            overwritten_hot = D.record_cues.load(record)["hot"][0]
            assert overwritten_hot > first_hot + 0.5

            for _ in range(30):
                source.read()
            old_deck = source.current
            _real_post_click(page, hot, "/cuebank")
            assert source.current is not old_deck
            assert source.current.at() * source.current.ratio == pytest.approx(
                overwritten_hot, abs=0.04
            )
            _real_post_click(page, hot, "/cuebank", button="right")
            page.wait_for_function(
                """() => !document.querySelector('#deck1 [data-cue-kind="hot"][data-cue-index="0"]').classList.contains('filled')""",
                timeout=5000,
            )
            assert D.record_cues.load(record)["hot"][0] is None

            one_beat = page.locator('#deck1 [data-loop-beats="1"]')
            _real_post_click(page, one_beat, "/loop", expected_status=204)
            _wait_for_ui_state(page, "#deck1 [data-loop-status]", "ARM 1")
            loop_deck = source.current
            loop = loop_deck._loop
            assert loop is not None and loop.beats == 1

            while loop_deck.played < loop.start_played:
                source.read()
            _wait_for_ui_state(page, "#deck1 [data-loop-status]", "LOOP 1")
            exit_button = page.locator("#deck1 [data-loop-exit]")
            assert exit_button.is_enabled()
            _real_post_click(page, exit_button, "/loop", expected_status=204)
            assert source._pending_loop_exit is not None
            for _ in range(len(loop.frames) + 3):
                if source.current is not loop_deck:
                    break
                source.read()
            assert source.current is not loop_deck
            assert source.current._loop is None
            assert source.current.at(0) * source.current.ratio == pytest.approx(
                loop.end_own, abs=0.04
            )
            _wait_for_ui_state(page, "#deck1 [data-loop-status]", "OFF")
        finally:
            page.close()
            browser.close()


def test_real_browser_controls_the_tempo_synced_master_echo(booth):
    _session, source, _record, base = booth
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1600, "height": 1100})
        page.add_init_script("localStorage.setItem('kaia.fx', '0')")
        try:
            response = page.goto(base, wait_until="domcontentloaded", timeout=15000)
            assert response is not None and response.ok
            _wait_for_ui_state(page, "#deck1 [data-f=state]", "ON AIR")

            echo = page.locator("#echoToggle")
            assert echo.text_content().strip() == "ECHO OFF"

            # Set up the next throw while it is idle. Polling renderer state
            # must not overwrite the operator's next-throw settings.
            page.locator("#echoBeats").select_option("2")
            feedback = page.locator("#echoFeedback")
            feedback.focus()
            feedback.press("ArrowRight")
            page.wait_for_timeout(250)
            assert page.locator("#echoBeats").input_value() == "2"
            assert feedback.input_value() == "0.4"

            with page.expect_response(
                lambda result: result.url.endswith("/fx/echo")
                and result.request.method == "POST"
            ) as enabled_response:
                echo.click()
            assert enabled_response.value.status == 204
            assert source.effects.active
            assert source.effects.snapshot()["beats"] == 2.0
            assert source.effects.snapshot()["feedback"] == pytest.approx(0.4)
            _wait_for_ui_state(page, "#echoToggle", "ECHO ON")
            for _ in range(26):
                source.read()
            assert source.effects.snapshot()["enabled"] is True
            assert np.max(np.abs(source.effects._buffer)) > 0

            with page.expect_response(
                lambda result: result.url.endswith("/fx/echo")
                and result.request.method == "POST"
            ) as stopped_response:
                echo.click()
            assert stopped_response.value.status == 204
            assert source.effects.tail_active
            _wait_for_ui_state(page, "#echoToggle", "ECHO TAIL")

            with page.expect_response(
                lambda result: result.url.endswith("/reset")
                and result.request.method == "POST"
            ) as reset_response:
                page.locator("#auto").click()
            assert reset_response.value.status == 204
            assert not source.effects.active and not source.effects.tail_active
        finally:
            page.close()
            browser.close()
