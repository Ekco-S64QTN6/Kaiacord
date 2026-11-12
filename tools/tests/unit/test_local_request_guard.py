"""A loopback dashboard answers only requests addressed to its own loopback name (GitHub #366).

Binding to 127.0.0.1 does not stop a web page: a hostname re-pointed at
127.0.0.1 (DNS rebinding) reaches the server with its own Host, and a page
elsewhere can post to it. Each dashboard is driven here over a real socket.
"""
import http.client
import threading
from http.server import ThreadingHTTPServer

import pytest

from utils.core.sanitizer import local_request_ok


def test_only_this_servers_loopback_names_are_accepted():
    assert local_request_ok("127.0.0.1:8080", None, 8080)
    assert local_request_ok("localhost:8080", "http://localhost:8080", 8080)
    assert local_request_ok("[::1]:8080", "http://127.0.0.1:8080", 8080)
    assert not local_request_ok("evil.example:8080", None, 8080)                       # rebinding: no Origin needed
    assert not local_request_ok("evil.example:8080", "http://evil.example:8080", 8080)  # Origin agreeing with Host
    assert not local_request_ok("127.0.0.1:8080", "http://evil.example", 8080)         # a page elsewhere
    assert not local_request_ok("127.0.0.1:8080", "null", 8080)                        # a sandboxed frame
    assert not local_request_ok("127.0.0.1:9999", None, 8080)                          # another port's name
    assert not local_request_ok("127.0.0.1", None, 8080)
    assert not local_request_ok(None, None, 8080) and not local_request_ok("", None, 8080)


def _handlers():
    from utils.admin.server import Handler as admin
    from utils.audio.dj_dashboard import _Handler as booth
    from utils.radio.rx_dashboard import _Handler as rx
    return {"admin": admin, "booth": booth, "rx": rx}


@pytest.fixture(params=["admin", "booth", "rx"])
def dashboard(request):
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _handlers()[request.param])
    srv.daemon_threads = True
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield srv.server_address[1]
    srv.shutdown()
    srv.server_close()


def _ask(port, method, path, host=None, origin=None):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    conn.putrequest(method, path, skip_host=True)
    conn.putheader("Host", host if host is not None else f"127.0.0.1:{port}")
    if origin:
        conn.putheader("Origin", origin)
    conn.putheader("Content-Length", "0")
    conn.endheaders()
    r = conn.getresponse()
    body = r.read()
    conn.close()
    return r.status, body


def test_the_page_is_served_to_its_own_address_and_refused_to_any_other(dashboard):
    port = dashboard
    assert _ask(port, "GET", "/")[0] == 200
    assert _ask(port, "GET", "/", host=f"localhost:{port}")[0] == 200
    status, body = _ask(port, "GET", "/", host=f"evil.example:{port}")
    assert status == 403 and len(body) < 20                       # nothing of the page comes back


@pytest.mark.parametrize("host, origin", [
    ("evil.example:{port}", None),                                # rebinding, no Origin
    ("evil.example:{port}", "http://evil.example:{port}"),        # Origin agreeing with a hostile Host
    ("127.0.0.1:{port}", "http://evil.example"),                  # a page elsewhere posting here
])
def test_a_control_post_from_elsewhere_is_refused(dashboard, host, origin):
    port = dashboard
    for path in ("/skip", "/tune", "/api/run/audit"):
        status, _ = _ask(port, "POST", path, host=host.format(port=port), origin=origin and origin.format(port=port))
        assert status == 403, path
