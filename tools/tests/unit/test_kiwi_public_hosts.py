"""KiwiSDR subprocess destinations must be public, pinned IP literals."""
import asyncio
import socket

import pytest

from utils.radio import kiwi
from utils.radio.fetch import FeedError


@pytest.mark.parametrize("host", [
    "127.0.0.1",
    "10.0.0.7",
    "172.16.0.1",
    "192.168.1.1",
    "169.254.169.254",
    "100.64.0.1",
    "224.0.0.1",
    "0.0.0.0",
    "::1",
    "fc00::1",
    "fe80::1",
])
def test_non_public_ip_literals_are_rejected(host):
    with pytest.raises(FeedError, match="not public"):
        kiwi._resolve_public_host(host)


def test_public_ip_literal_is_pinned_without_dns(monkeypatch):
    def forbidden(*_args, **_kwargs):
        raise AssertionError("IP literal must not trigger DNS")

    monkeypatch.setattr(kiwi.socket, "getaddrinfo", forbidden)
    assert kiwi._resolve_public_host("8.8.8.8") == "8.8.8.8"


def test_hostname_with_only_public_dns_answers_is_pinned(monkeypatch):
    monkeypatch.setattr(kiwi.socket, "getaddrinfo", lambda *_a, **_k: [
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 0)),
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("1.1.1.1", 0)),
    ])
    assert kiwi._resolve_public_host("receiver.example") == "1.1.1.1"


def test_hostname_with_any_private_dns_answer_is_rejected(monkeypatch):
    monkeypatch.setattr(kiwi.socket, "getaddrinfo", lambda *_a, **_k: [
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 0)),
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 0)),
    ])
    with pytest.raises(FeedError, match="not public"):
        kiwi._resolve_public_host("rebound.example")


def test_resolve_receiver_returns_a_pinned_copy_without_mutating_directory_entry(monkeypatch):
    receiver = kiwi.Receiver(
        host="receiver.example", port=8073, name="rx", location="",
        lat=0, lon=0, users=0, users_max=4, snr=30,
        low_hz=0, high_hz=30_000_000,
    )
    monkeypatch.setattr(kiwi, "_resolve_public_host", lambda _host: "8.8.4.4")

    pinned = asyncio.run(kiwi.resolve_receiver(receiver))

    assert receiver.connect_host == ""
    assert pinned.host == "receiver.example"
    assert pinned.connect_host == "8.8.4.4"
    assert kiwi._recorder_cmd(pinned, 8992, "usb")[4:6] == ["-s", "8.8.4.4"]


def test_recorder_refuses_an_unpinned_receiver():
    receiver = kiwi.Receiver(
        host="receiver.example", port=8073, name="rx", location="",
        lat=0, lon=0, users=0, users_max=4, snr=30,
        low_hz=0, high_hz=30_000_000,
    )
    with pytest.raises(FeedError, match="has not been resolved"):
        kiwi._recorder_cmd(receiver, 8992, "usb")


def test_recorder_refuses_a_private_pinned_address():
    receiver = kiwi.Receiver(
        host="receiver.example", port=8073, name="rx", location="",
        lat=0, lon=0, users=0, users_max=4, snr=30,
        low_hz=0, high_hz=30_000_000,
        connect_host="169.254.169.254",
    )
    with pytest.raises(FeedError, match="not public"):
        kiwi._recorder_cmd(receiver, 8992, "usb")


@pytest.mark.parametrize("url", [
    "http://user:pass@receiver.example",
    "http://receiver.example/path",
    "http://receiver.example/?redirect=1",
    "http://receiver.example#fragment",
    "http://receiver.example:",
    "http://receiver.example:99999",
    "file:///etc/passwd",
])
def test_receiver_url_parser_rejects_ambiguous_or_unsafe_urls(url):
    with pytest.raises(ValueError):
        kiwi._host_port(url)


def test_receiver_url_parser_keeps_normal_proxy_ports():
    assert kiwi._host_port("http://proxy.example:8174") == ("proxy.example", 8174)
    assert kiwi._host_port("http://proxy.example/") == ("proxy.example", 8073)


@pytest.mark.parametrize("url", [
    "http://127.0.0.1:8073",
    "http://10.0.0.8:8073",
    "http://169.254.169.254:8073",
    "http://[::1]:8073",
    "http://[fe80::1]:8073",
])
def test_directory_parser_rejects_private_receiver_ip_literals(url):
    with pytest.raises(ValueError, match="not public"):
        kiwi._host_port(url)


def _receiver():
    return kiwi.Receiver(
        host="receiver.example", port=8073, name="rx", location="",
        lat=0, lon=0, users=0, users_max=4, snr=30,
        low_hz=0, high_hz=30_000_000,
    )


def test_record_subprocess_receives_the_pinned_ip_not_the_directory_hostname(
    tmp_path, monkeypatch
):
    import wave
    import numpy as np

    receiver = _receiver()
    captured = {}

    async def fake_exec(*cmd, **_kwargs):
        captured["cmd"] = list(cmd)
        output = tmp_path / "capture.wav"
        with wave.open(str(output), "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(kiwi.SAMPLE_RATE)
            wav.writeframes(np.full(kiwi.SAMPLE_RATE * 4, 100, dtype=np.int16).tobytes())

        class Proc:
            returncode = 0
            pid = 1
            stderr = None
        return Proc()

    async def no_stderr(_proc, _deadline):
        return "", ""

    monkeypatch.setattr(kiwi, "available", lambda: True)
    monkeypatch.setattr(kiwi, "_resolve_public_host", lambda _host: "8.8.8.8")
    monkeypatch.setattr(kiwi.asyncio, "create_subprocess_exec", fake_exec)
    monkeypatch.setattr(kiwi, "_watch_stderr", no_stderr)
    monkeypatch.setattr(kiwi, "note_ok", lambda *_args: None)

    result = asyncio.run(kiwi.record(
        receiver, 8992, "usb", 5, tmp_path, label="hfgcs"
    ))

    assert result == [tmp_path / "capture.wav"]
    assert captured["cmd"][captured["cmd"].index("-s") + 1] == "8.8.8.8"
    assert "receiver.example" not in captured["cmd"]


def test_smeter_subprocess_receives_the_pinned_ip(monkeypatch):
    captured = {}

    class Proc:
        returncode = 0

        async def communicate(self):
            return b"12-Nov-2026 03:00:00 UTC RSSI: -91.5\n", b""

    async def fake_exec(*cmd, **_kwargs):
        captured["cmd"] = list(cmd)
        return Proc()

    monkeypatch.setattr(kiwi, "available", lambda: True)
    monkeypatch.setattr(kiwi, "_resolve_public_host", lambda _host: "1.1.1.1")
    monkeypatch.setattr(kiwi.asyncio, "create_subprocess_exec", fake_exec)
    monkeypatch.setattr(kiwi, "note_ok", lambda *_args: None)

    readings = asyncio.run(kiwi.smeter(_receiver(), 4625, "usb", 1))

    assert len(readings) == 1 and readings[0][1] == -91.5
    assert captured["cmd"][captured["cmd"].index("-s") + 1] == "1.1.1.1"
    assert "receiver.example" not in captured["cmd"]


def test_open_stream_refuses_unpinned_receiver_and_uses_pinned_ip(monkeypatch):
    import subprocess

    captured = []
    monkeypatch.setattr(kiwi, "available", lambda: True)
    monkeypatch.setattr(subprocess, "Popen", lambda cmd, **_kwargs: captured.append(list(cmd)) or object())

    with pytest.raises(FeedError, match="has not been resolved"):
        kiwi.open_stream(_receiver(), 8992, "usb")
    assert captured == []

    pinned = _receiver()
    pinned.connect_host = "8.8.4.4"
    kiwi.open_stream(pinned, 8992, "usb")

    assert captured[0][captured[0].index("-s") + 1] == "8.8.4.4"
    assert "receiver.example" not in captured[0]


def test_parse_directory_excludes_private_ip_literal_rows():
    import json

    rows = [
        {
            "status": "active", "offline": "no", "name": "loopback",
            "sdr_hw": "KiwiSDR", "bands": "0-30000000",
            "users": "0", "users_max": "4", "ext_api": "2",
            "gps": "(38.9, -94.8)", "snr": "30,30",
            "url": "http://127.0.0.1:8073",
        },
        {
            "status": "active", "offline": "no", "name": "public",
            "sdr_hw": "KiwiSDR", "bands": "0-30000000",
            "users": "0", "users_max": "4", "ext_api": "2",
            "gps": "(38.9, -94.8)", "snr": "30,30",
            "url": "http://8.8.8.8:8073",
        },
    ]

    parsed = kiwi.parse_directory("var kiwisdr = " + json.dumps(rows) + ";")

    assert [receiver.name for receiver in parsed] == ["public"]
