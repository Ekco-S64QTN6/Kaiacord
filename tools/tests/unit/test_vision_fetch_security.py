"""Security and resource-bound regressions for inline vision image fetches."""

import asyncio
from types import SimpleNamespace

import pytest

from utils.core import message_processor as mp
from utils.core.message_processor import MessageProcessor


class _FakeContent:
    def __init__(self, chunks):
        self.chunks = chunks

    async def iter_chunked(self, _size):
        for chunk in self.chunks:
            yield chunk


class _FakeResponse:
    def __init__(self, status=200, headers=None, chunks=()):
        self.status = status
        self.headers = headers or {}
        self.content = _FakeContent(chunks)
        self.released = False
        self.entered = False

    def release(self):
        self.released = True

    async def __aenter__(self):
        self.entered = True
        return self

    async def __aexit__(self, *_exc):
        self.released = True


class _FakeSession:
    def __init__(self, responses, **kwargs):
        self.responses = list(responses)
        self.kwargs = kwargs
        self.requests = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_exc):
        return None

    async def get(self, url, **kwargs):
        self.requests.append((url, kwargs))
        return self.responses.pop(0)


class _FakeSessionFactory:
    def __init__(self, session, kwargs):
        self.session = session
        self.kwargs = kwargs

    async def __aenter__(self):
        self.session.kwargs = self.kwargs
        return self.session

    async def __aexit__(self, *_exc):
        return None


def _processor():
    processor = MessageProcessor.__new__(MessageProcessor)
    processor.config = SimpleNamespace(url_fetch_timeout=2)
    return processor


def test_private_image_url_is_rejected_before_opening_a_session(monkeypatch):
    processor = _processor()
    called = []
    monkeypatch.setattr(mp, "is_safe_url", lambda _url: False)
    monkeypatch.setattr(mp.aiohttp, "ClientSession", lambda **_kwargs: called.append(True))

    assert asyncio.run(processor._fetch_image_as_base64("http://127.0.0.1/private.png")) == ""
    assert called == []


def test_image_redirect_to_private_address_is_rejected(monkeypatch):
    processor = _processor()
    redirect = _FakeResponse(
        status=302,
        headers={"Location": "http://169.254.169.254/latest/meta-data"},
    )
    session = _FakeSession([redirect])
    checked = []
    connector = object()

    def safe(url):
        checked.append(url)
        return "169.254.169.254" not in url

    monkeypatch.setattr(mp, "is_safe_url", safe)
    monkeypatch.setattr(mp, "public_only_connector", lambda: connector)
    monkeypatch.setattr(mp.aiohttp, "ClientSession", lambda **kwargs: _FakeSessionFactory(session, kwargs))

    assert asyncio.run(processor._fetch_image_as_base64("https://images.example.test/p.png")) == ""
    assert checked == [
        "https://images.example.test/p.png",
        "http://169.254.169.254/latest/meta-data",
    ]
    assert [url for url, _kwargs in session.requests] == ["https://images.example.test/p.png"]
    assert session.requests[0][1]["allow_redirects"] is False
    assert redirect.released
    assert session.kwargs["connector"] is connector


def test_oversized_image_body_is_rejected_before_image_decode(monkeypatch):
    processor = _processor()
    processor.VISION_MAX_DOWNLOAD_BYTES = 16
    response = _FakeResponse(
        headers={"Content-Type": "image/png"},
        chunks=[b"x" * 17],
    )
    session = _FakeSession([response])
    monkeypatch.setattr(mp, "is_safe_url", lambda _url: True)
    monkeypatch.setattr(mp, "public_only_connector", lambda: object())
    monkeypatch.setattr(mp.aiohttp, "ClientSession", lambda **kwargs: _FakeSessionFactory(session, kwargs))
    decoded = []

    def record_decode(*_args):
        decoded.append(True)
        return "decoded"

    monkeypatch.setattr(processor, "_prepare_image_payload", record_decode)

    assert asyncio.run(processor._fetch_image_as_base64("https://images.example.test/p.png")) == ""
    assert decoded == []
    assert response.released


def test_extreme_source_dimensions_are_rejected_before_rgb_conversion(monkeypatch):
    from PIL import Image

    processor = _processor()

    converted = []

    class _Image:
        width = 5000
        height = 5000

        def __enter__(self):
            return self

        def __exit__(self, *_exc):
            return None

        def convert(self, *_args):
            converted.append(True)
            raise RuntimeError("RGB conversion should not be reached")

    monkeypatch.setattr(Image, "open", lambda *_args, **_kwargs: _Image())
    assert processor._prepare_image_payload(b"image-bytes", is_gif=False) == ""
    assert converted == []


def test_vision_attachment_processing_is_capped_at_four_images():
    import inspect

    source = inspect.getsource(MessageProcessor._generate_response_stage)
    assert "attachments_to_process[:self.VISION_MAX_IMAGES]" in source
    assert "VISION_MAX_IMAGES = 4" in inspect.getsource(MessageProcessor)
