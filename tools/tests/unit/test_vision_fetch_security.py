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


def test_vision_attachment_selection_caps_images_not_other_files():
    processor = _processor()
    attachments = [
        SimpleNamespace(filename="notes.pdf"),
        SimpleNamespace(filename="first.png"),
        SimpleNamespace(filename="second.jpg"),
        SimpleNamespace(filename="third.gif"),
        SimpleNamespace(filename="fourth.webp"),
        SimpleNamespace(filename="fifth.jpeg"),
        SimpleNamespace(filename="readme.txt"),
    ]

    selected, skipped = processor._select_vision_image_attachments(attachments)

    assert [item.filename for item in selected] == [
        "first.png", "second.jpg", "third.gif", "fourth.webp"
    ]
    assert skipped == 1



def test_public_image_redirect_is_validated_and_processed(monkeypatch):
    processor = _processor()
    redirect = _FakeResponse(status=302, headers={"Location": "/cdn/photo.png"})
    final = _FakeResponse(
        status=200,
        headers={"Content-Type": "image/png; charset=binary"},
        chunks=[b"image-bytes"],
    )
    session = _FakeSession([redirect, final])
    checked = []
    connector = object()
    decoded = []

    def safe(url):
        checked.append(url)
        return True

    def prepare(data, is_gif):
        decoded.append((data, is_gif))
        return "encoded-image"

    monkeypatch.setattr(mp, "is_safe_url", safe)
    monkeypatch.setattr(mp, "public_only_connector", lambda: connector)
    monkeypatch.setattr(mp.aiohttp, "ClientSession", lambda **kwargs: _FakeSessionFactory(session, kwargs))
    monkeypatch.setattr(processor, "_prepare_image_payload", prepare)

    result = asyncio.run(
        processor._fetch_image_as_base64("https://images.example.test/original.png")
    )

    assert result == "encoded-image"
    assert checked == [
        "https://images.example.test/original.png",
        "https://images.example.test/cdn/photo.png",
    ]
    assert [url for url, _kwargs in session.requests] == [
        "https://images.example.test/original.png",
        "https://images.example.test/cdn/photo.png",
    ]
    assert all(kwargs["allow_redirects"] is False for _url, kwargs in session.requests)
    assert session.kwargs["connector"] is connector
    assert decoded == [(b"image-bytes", False)]
    assert redirect.released and final.released


def _jpeg(width, height):
    import io
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (width, height), (120, 60, 30)).save(buf, format="JPEG", quality=90)
    return buf.getvalue()


@pytest.mark.parametrize("size", [(8000, 6000), (1080, 20000)])
def test_a_jpeg_over_the_pixel_budget_is_decoded_small_not_skipped(size):
    """A 48 MP phone photo or a long screenshot is over the budget at full size;
    JPEG draft decoding reads it near the size it is sent at."""
    import base64
    import io
    from PIL import Image

    width, height = size
    assert width * height > MessageProcessor.VISION_MAX_SOURCE_PIXELS
    out = _processor()._prepare_image_payload(_jpeg(width, height), is_gif=False)

    assert out
    sent = Image.open(io.BytesIO(base64.b64decode(out))).size
    assert max(sent) == MessageProcessor.VISION_MAX_EDGE


def test_an_image_that_did_not_load_is_named_in_the_prompt():
    note = MessageProcessor._unseen_images_note
    assert note(1, 1) == ""
    assert note(0, 0) == ""
    assert "The attached image could not be loaded, so you cannot see it." in note(1, 0)
    assert "The 3 attached images could not be loaded, so you cannot see them." in note(3, 0)
    assert "1 of the 2 attached images" in note(2, 1)
