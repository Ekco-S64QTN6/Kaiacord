"""The boundary check must not flag her own plumbing as unknown lore.

`extract_entities` targets "hallucinated SYSTEM entities like fake usernames,
file paths, or IDs" — its own docstring — but the pattern is
`[A-Za-z]+[0-9_.-]+...`, which matches any hyphenated English word. Everything
below was flagged in production, at info/warning level, which per CLAUDE.md §9
surfaces it in the dashboard.
"""
import pytest

from utils.core.knowledge_boundary import KnowledgeBoundary


@pytest.fixture(scope="module")
def boundary():
    return KnowledgeBoundary("./knowledge_base")


@pytest.mark.parametrize("token", [
    # her own scaffolding, wrapped around content before the model sees it
    "LINKED_WEB_CONTENT", "CORE_DIRECTIVE",
    # her own name, and a known user
    "@Kaia",
    # ordinary hyphenated English
    "one-liner", "dial-up", "real-time", "post-structuralist", "decision-driven",
    # typos and stutters from actual chat
    "bu-uy-ing", "ca-ame", "Ye-eah", "pre-existin",
    # real files and domains the user pointed at, not inventions
    "README.md", "requirements.txt", "pyproject.toml", "MANIFEST.in",
    "pastebin.com", "github.com", "science.nasa.gov",
])
def test_noise_is_not_flagged_as_an_unknown_entity(boundary, token):
    assert boundary._is_noise(token), f"{token!r} would be reported as unknown lore"


@pytest.mark.parametrize("token", [
    "User_123",   # the docstring's own example
    "Project9",   # ditto
    "vB9f82j5",   # a real URL slug from the log
    "b293571",
    "GOES-19",
])
def test_genuine_synthetic_identifiers_still_flag(boundary, token):
    """The check has to keep doing its job."""
    assert not boundary._is_noise(token), f"{token!r} should still be reported"


def test_a_realistic_message_produces_no_noise(boundary):
    msg = ("Kaia, https://pastebin.com/raw/AQtZyHfN — a real-time one-liner "
           "about the README.md in github.com/Ekco-S64QTN6")
    flagged = boundary.check_known_entities(msg, ["prior turn"])["unknown_in_context"]
    for junk in ("one-liner", "real-time", "README.md", "pastebin.com", "github.com"):
        assert junk not in flagged, f"{junk!r} still flagged: {flagged}"
