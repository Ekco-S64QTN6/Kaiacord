"""SSRF address checks must reject every non-global address range."""
import pytest

from utils.core.sanitizer import _is_public_ip


@pytest.mark.parametrize("address", [
    "0.0.0.0",
    "10.0.0.1",
    "127.0.0.1",
    "169.254.169.254",
    "100.64.0.1",       # RFC 6598 shared address space / CGNAT
    "100.127.255.254",
    "192.0.2.10",       # documentation range
    "198.18.0.1",       # benchmarking range
    "198.51.100.7",     # documentation range
    "203.0.113.10",     # documentation range
    "224.0.0.1",        # multicast
    "240.0.0.1",        # reserved
    "::",
    "::1",
    "fc00::1",
    "fe80::1",
    "2001:db8::1",      # documentation range
])
def test_non_global_addresses_are_not_public(address):
    assert not _is_public_ip(address), address


@pytest.mark.parametrize("address", [
    "1.1.1.1",
    "8.8.8.8",
    "2606:4700:4700::1111",
])
def test_globally_routable_addresses_remain_public(address):
    assert _is_public_ip(address), address


def test_ipv6_zone_identifier_does_not_bypass_address_classification():
    assert not _is_public_ip("fe80::1%eth0")
