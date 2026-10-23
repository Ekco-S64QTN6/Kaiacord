"""The X client cache: a failed session must not be handed to the next caller."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import utils.social.kaia_twitter as kx


def test_a_failed_login_leaves_no_client_behind(monkeypatch, tmp_path):
    """One failed login used to end X posting until a restart: the client
    that never logged in stayed cached and was returned to every caller."""
    monkeypatch.setattr(kx, "is_x_configured", lambda: True)
    monkeypatch.setattr(kx, "_cookies_path", tmp_path / "x_cookies.json")
    monkeypatch.setattr(kx, "_client", None)
    fake = MagicMock()
    fake.login = AsyncMock(side_effect=RuntimeError("bad password"))
    monkeypatch.setattr(kx, "Client", lambda *a: fake)
    assert asyncio.run(kx.get_x_client()) is None
    assert kx._client is None


def test_an_auth_error_drops_the_cached_session(monkeypatch, tmp_path):
    cookies = tmp_path / "x_cookies.json"
    cookies.write_text("{}")
    monkeypatch.setattr(kx, "_cookies_path", cookies)
    dead = SimpleNamespace(create_tweet=AsyncMock(side_effect=RuntimeError("401 Unauthorized")))
    monkeypatch.setattr(kx, "_client", dead)
    monkeypatch.setattr(kx, "get_x_client", AsyncMock(return_value=dead))
    ok, _ = asyncio.run(kx.post_to_x("hello"))
    assert not ok and kx._client is None and not cookies.exists()


def test_browser_cookie_extraction_logs_lock_failures_and_uses_wal_safe_profile_copy(
    monkeypatch, tmp_path
):
    import sqlite3
    import sys
    from pathlib import Path
    from types import SimpleNamespace

    profile_root = tmp_path / ".mozilla" / "firefox"
    profile = profile_root / "custom-profile"
    profile.mkdir(parents=True)
    database = profile / "cookies.sqlite"
    database.write_bytes(b"sqlite-main-db")
    Path(str(database) + "-wal").write_bytes(b"sqlite-wal")
    Path(str(database) + "-shm").write_bytes(b"sqlite-shm")

    warnings = []
    monkeypatch.setattr(kx, "log_warning", lambda msg, *a, **k: warnings.append(str(msg)))
    monkeypatch.setattr(kx, "log_debug", lambda *a, **k: None)
    monkeypatch.setattr(kx, "log_info", lambda *a, **k: None)
    monkeypatch.setattr(kx, "_COOKIE_EXTRACTION_WARNED", set())
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))

    def locked_loader(**kwargs):
        if "cookie_file" not in kwargs:
            raise sqlite3.OperationalError("database is locked")
        copied = Path(kwargs["cookie_file"])
        assert copied.is_file()
        assert Path(str(copied) + "-wal").read_bytes() == b"sqlite-wal"
        # A live -shm file contains process coordination state and must not be copied.
        assert not Path(str(copied) + "-shm").exists()
        if kwargs["domain_name"] == "x.com":
            return [SimpleNamespace(name="auth_token", value="test-session")]
        raise sqlite3.OperationalError("database is locked")

    fake = SimpleNamespace(
        chrome=locked_loader,
        chromium=locked_loader,
        brave=locked_loader,
        firefox=locked_loader,
        librewolf=locked_loader,
    )
    monkeypatch.setitem(sys.modules, "browser_cookie3", fake)

    cookies = kx._extract_browser_cookies()

    assert cookies == {"auth_token": "test-session"}
    assert any("OperationalError" in msg and "database is locked" in msg for msg in warnings)
    assert any(str(database) in msg for msg in warnings)
    # The fallback copy is temporary; the browser's original DB and sidecars remain.
    assert database.read_bytes() == b"sqlite-main-db"
    assert Path(str(database) + "-wal").read_bytes() == b"sqlite-wal"


def test_cookie_profile_discovery_includes_librewolf_brave_and_sandbox_paths(tmp_path):
    from pathlib import Path

    roots = [
        tmp_path / ".librewolf" / "profile" / "cookies.sqlite",
        tmp_path / ".firedragon" / "profile" / "cookies.sqlite",
        tmp_path / ".config" / "BraveSoftware" / "Brave-Browser" / "Default" / "Network" / "Cookies",
        tmp_path / "snap" / "firefox" / "common" / ".mozilla" / "firefox" / "profile" / "cookies.sqlite",
    ]
    for candidate in roots:
        candidate.parent.mkdir(parents=True, exist_ok=True)
        candidate.write_bytes(b"db")

    candidates = kx._browser_cookie_db_candidates(tmp_path)
    found = {db.resolve(): (label, loader) for label, loader, _root, db in candidates}

    assert found[roots[0].resolve()][1] == "librewolf"
    assert found[roots[1].resolve()][1] == "firefox"
    assert found[roots[2].resolve()][1] == "brave"
    assert found[roots[3].resolve()][1] == "firefox"


def test_cookie_extraction_never_pairs_auth_and_csrf_from_different_profiles(
    monkeypatch, tmp_path
):
    import sys
    from types import SimpleNamespace

    warnings = []
    monkeypatch.setattr(kx, "log_warning", lambda msg, *a, **k: warnings.append(str(msg)))
    monkeypatch.setattr(kx, "log_debug", lambda *a, **k: None)
    monkeypatch.setattr(kx, "log_info", lambda *a, **k: None)
    monkeypatch.setattr(kx, "_COOKIE_EXTRACTION_WARNED", set())
    monkeypatch.setattr(kx.Path, "home", classmethod(lambda cls: tmp_path))

    def chrome(**kwargs):
        if kwargs.get("domain_name") == "x.com":
            return [SimpleNamespace(name="auth_token", value="chrome-auth")]
        return []

    def firefox(**kwargs):
        if kwargs.get("domain_name") == "twitter.com":
            return [SimpleNamespace(name="ct0", value="firefox-csrf")]
        return []

    empty = lambda **kwargs: []
    fake = SimpleNamespace(
        chrome=chrome, chromium=empty, brave=empty,
        firefox=firefox, librewolf=empty,
    )
    monkeypatch.setitem(sys.modules, "browser_cookie3", fake)

    cookies = kx._extract_browser_cookies()

    assert cookies == {"auth_token": "chrome-auth"}
    assert "ct0" not in cookies
    assert any("no matching ct0" in warning for warning in warnings)
