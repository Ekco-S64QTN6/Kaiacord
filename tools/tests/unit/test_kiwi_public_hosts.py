"""KiwiSDR subprocess destinations must be public, pinned IP literals."""
import asyncio
import socket
from dataclasses import replace

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
