"""Bounded YouTube transcript HTTP, worker and command admission tests."""

import asyncio
import threading
from types import SimpleNamespace

import pytest
from requests import Session

from tools.maintenance import youtube_to_kb_md as converter
from utils.commands import youtube_handler as handler


@pytest.fixture(autouse=True)
def _clear_transcript_admission(monkeypatch):
    with handler._inflight_lock:
        handler._inflight_video_ids.clear()
        handler._inflight_paths.clear()
    monkeypatch.setattr(handler, "_last_used", {})
    yield
    with handler._inflight_lock:
        handler._inflight_video_ids.clear()
        handler._inflight_paths.clear()


def test_transcript_session_adds_a_finite_default_http_timeout(monkeypatch):
    calls = []

    def fake_request(_self, method, url, **kwargs):
        calls.append((method, url, kwargs.get("timeout")))
        return object()

    monkeypatch.setattr(Session, "request", fake_request)
    client = converter._TranscriptHTTPTimeoutSession()

    client.get("https://youtube.test/list")
    client.get("https://youtube.test/transcript", timeout=3.0)

    assert calls == [
        ("GET", "https://youtube.test/list", converter.TRANSCRIPT_HTTP_TIMEOUT_S),
        ("GET", "https://youtube.test/transcript", 3.0),
    ]


def test_transcript_api_receives_the_bounded_session(monkeypatch):
    import youtube_transcript_api

    captured = {}

    class FakeApi:
        def __init__(self, http_client=None):
            captured["client"] = http_client

        def list(self, _video_id):
            raise RuntimeError("offline unit fixture")

    monkeypatch.setattr(youtube_transcript_api, "YouTubeTranscriptApi", FakeApi)

    with pytest.raises(converter.YouTubeError, match="no transcript available"):
        converter.fetch_transcript("abcdefghijk")

    assert isinstance(captured["client"], converter._TranscriptHTTPTimeoutSession)


def test_global_transcript_reservations_are_bounded_and_deduplicated():
    assert handler._reserve_transcript("video-one") == "reserved"
    assert handler._reserve_transcript("video-one") == "duplicate"
    assert handler._reserve_transcript("video-two") == "reserved"
    assert handler._reserve_transcript("video-three") == "busy"

    handler._release_transcript("video-one")

    assert handler._reserve_transcript("video-three") == "reserved"
    handler._release_transcript("video-two")
    handler._release_transcript("video-three")


def _message(video_id, channel_id):
    sent = []

    async def send(embed=None, **_kwargs):
        sent.append(getattr(embed, "description", "") if embed is not None else "")

    return SimpleNamespace(
        content=f"!youtube https://youtu.be/{video_id}",
        channel=SimpleNamespace(id=channel_id, send=send),
        author=SimpleNamespace(display_name="listener", id=channel_id),
    ), sent


@pytest.mark.parametrize(
    "existing, video_id, expected",
    [
        (("abcdefghijk",), "abcdefghijk", "already being fetched"),
        (("lmnopqrstuv", "wxyzABCDE_1"), "12345678901", "already fetching a couple of transcripts"),
    ],
)
def test_handler_refuses_duplicate_or_over_capacity_jobs(existing, video_id, expected):
    for active_id in existing:
        assert handler._reserve_transcript(active_id) == "reserved"
    msg, sent = _message(video_id, channel_id=9001)

    asyncio.run(handler.handle_youtube_command(None, msg, None))

    assert len(sent) == 1 and expected in sent[0]
    assert not handler._is_transcript_inflight(video_id)


def test_concurrent_same_title_jobs_reserve_distinct_ingress_paths(monkeypatch, tmp_path):
    monkeypatch.setattr(handler, "INGRESS", tmp_path)
    tmp_path.mkdir(exist_ok=True)

    first = handler._reserve_ingress_path("same video title", converter.safe_filename)
    second = handler._reserve_ingress_path("same video title", converter.safe_filename)

    assert first != second
    assert first.name == "Transcript - same video title.md"
    assert second.name == "Transcript - same video title (2).md"
    assert handler._inflight_paths == {first, second}

    handler._release_ingress_path(first)
    handler._release_ingress_path(second)
    assert handler._inflight_paths == set()


def test_handler_releases_its_reservation_when_staging_raises(monkeypatch):
    video_id = "abcdefghijk"
    msg, _sent = _message(video_id, channel_id=9002)

    async def fail_stage(*_args):
        raise RuntimeError("synthetic staging failure")

    monkeypatch.setattr(handler, "_stage_transcript", fail_stage)

    with pytest.raises(RuntimeError, match="synthetic staging failure"):
        asyncio.run(handler.handle_youtube_command(None, msg, None))

    assert not handler._is_transcript_inflight(video_id)


def test_cancelling_an_off_loop_worker_waits_for_the_real_thread():
    started = threading.Event()
    release = threading.Event()
    finished = threading.Event()

    def blocking_work():
        started.set()
        release.wait(3.0)
        finished.set()
        return "complete"

    async def scenario():
        task = asyncio.create_task(handler._run_off_loop(blocking_work))
        assert await asyncio.to_thread(started.wait, 1.0)
        task.cancel()
        await asyncio.sleep(0.03)
        assert not task.done()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert finished.is_set()

    try:
        asyncio.run(scenario())
    finally:
        release.set()
