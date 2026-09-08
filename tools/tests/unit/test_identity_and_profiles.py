"""Who is who, across Discord and the forum.

Three ways Kaia lost track of a person:

  * Her own forum account was profiled as a stranger. `forum_Kaia_322197/
    user_profile.md` read "a forum user... haven't formed a strong opinion yet
    — need to see more of their posts."
  * A forum handle that does not match a Discord name is a different person as
    far as the code is concerned. `magnetaress` on P99 is Starkind in Discord;
    nothing in the data says so.
  * A Discord directory is named `<display name>_<id>`, and display names
    change. One person had three directories and a rename started a fresh
    history each time.
"""
import json
import pathlib
from pathlib import Path

import pytest


@pytest.fixture
def reg(tmp_path, monkeypatch):
    from utils.social.kaia_identities import IdentityRegistry
    r = IdentityRegistry()
    monkeypatch.setattr(type(r), "REGISTRY_PATH", tmp_path / "registry.json")
    r.data = {"discord_to_forum": {}, "forum_to_discord": {}, "mappings": {},
              "self_forum_ids": [], "display_names": {}}
    return r


# ── Self ─────────────────────────────────────────────────────────────

def test_her_own_forum_account_is_recognised(reg):
    reg.mark_self(322197)
    assert reg.is_self(322197) and reg.is_self("322197")
    assert not reg.is_self(251675)
    assert not reg.is_self(None) and not reg.is_self("not-a-number")


def test_the_live_registry_knows_which_account_is_hers():
    from utils.social.kaia_identities import registry
    assert registry.is_self(322197), "forum_Kaia_322197 must be marked as self"


def test_the_self_marker_file_says_so_plainly():
    p = Path("knowledge_base/user_logs/forum_Kaia_322197/user_profile.md")
    if not p.exists():
        pytest.skip("no forum corpus")
    text = p.read_text(encoding="utf-8")
    assert "is_self: true" in text
    assert "own forum account" in text.lower()
    # The stranger-profile phrasing must be gone.
    assert "haven't formed a strong opinion" not in text
    assert "a forum user with the rank" not in text


def test_profiling_refuses_to_run_on_herself():
    import inspect
    from utils.social.kaia_forum import ForumClient
    src = inspect.getsource(ForumClient.generate_personality_profile)
    assert "registry.is_self(user_id)" in src
    assert src.index("is_self(user_id)") < src.index("client.chat"), \
        "the self-check must come before the model call"


# ── Linking ──────────────────────────────────────────────────────────

def test_a_forum_handle_resolves_to_the_person(reg):
    reg.set_display_name("519557167779676160", "Starkind")
    reg.link_discord_to_forum("519557167779676160", 210090)
    assert reg.describe_forum_user(210090) == "Starkind"
    assert reg.describe_forum_user(999999) is None


def test_one_person_can_hold_several_forum_accounts(reg):
    reg.set_display_name("519557167779676160", "Starkind")
    for fid in (210090, 228819):
        reg.link_discord_to_forum("519557167779676160", fid)
    assert sorted(reg.get_forum_ids("519557167779676160")) == [210090, 228819]


def test_the_operator_supplied_links_are_recorded():
    """Names that give nothing away have to be recorded, not inferred."""
    from utils.social.kaia_identities import registry
    for forum_id, name in ((251675, "Ekco"), (33136, "Jimjam"),
                           (22006, "Cecily"), (210090, "Starkind")):
        assert registry.describe_forum_user(forum_id) == name, forum_id


def test_the_registry_is_keyed_by_id_not_directory_name():
    """One entry was keyed "Ekco_177011971818782721" and another by a synthetic
    label, so lookups depended on which had been written first."""
    from utils.social.kaia_identities import registry
    for key in registry.data["discord_to_forum"]:
        assert "_" not in key or key.startswith("Identity_"), f"directory-shaped key: {key}"


def test_a_linked_profile_says_who_it_is():
    p = Path("knowledge_base/user_logs/forum_magnetaress_210090/user_profile.md")
    if not p.exists():
        pytest.skip("profile not generated")
    text = p.read_text(encoding="utf-8")
    assert 'known_as: "Starkind"' in text
    assert "this is Starkind from Discord" in text


# ── One person, one directory ────────────────────────────────────────

def test_a_rename_does_not_start_a_new_history(tmp_path):
    """`galadriel`, `Jimjam` and `Jimjam_the_applauded` were the same id."""
    from utils.core.kaia_rag_persistence import RAGPersistenceMixin as P
    from utils.infrastructure.monitoring.telemetry_paths import corpus_dir

    # corpus_dir redirects writes under pytest, so the fixture has to build the
    # tree where the code will actually look.
    base = pathlib.Path(corpus_dir(str(tmp_path))) / "user_logs"
    (base / "OldName_12345").mkdir(parents=True)
    (base / "OldName_12345" / "interactions_20260101.md").write_text("hi", encoding="utf-8")

    p = P.__new__(P)
    p.knowledge_base_dir = str(tmp_path)
    assert p._existing_dir_for_id("12345") == "OldName_12345"
    assert p._existing_dir_for_id("99999") is None


def test_the_fullest_directory_wins(tmp_path):
    from utils.core.kaia_rag_persistence import RAGPersistenceMixin as P
    from utils.infrastructure.monitoring.telemetry_paths import corpus_dir
    base = pathlib.Path(corpus_dir(str(tmp_path))) / "user_logs"
    for name, n in (("Thin_1", 1), ("Fat_1", 5)):
        (base / name).mkdir(parents=True)
        for i in range(n):
            (base / name / f"f{i}.md").write_text("x", encoding="utf-8")
    p = P.__new__(P)
    p.knowledge_base_dir = str(tmp_path)
    assert p._existing_dir_for_id("1") == "Fat_1"


def test_no_discord_id_has_two_directories():
    logs = Path("knowledge_base/user_logs")
    if not logs.exists():
        pytest.skip("no corpus")
    seen = {}
    for d in logs.iterdir():
        if not d.is_dir() or d.name.startswith("forum_") or "_" not in d.name:
            continue
        uid = d.name.rsplit("_", 1)[-1]
        if not uid.isdigit():
            continue
        seen.setdefault(uid, []).append(d.name)
    split = {k: v for k, v in seen.items() if len(v) > 1}
    assert not split, f"one person across several directories: {split}"


# ── The profile prompt ───────────────────────────────────────────────

def test_the_profiler_does_not_ask_for_a_surveillance_dossier():
    """The prompt asked for a "Digital Dossier" with "AI analyst flair" — the
    register the persona bans and the filters strip. These profiles are
    injected back into her context, so the register leaks into her voice."""
    import ast, inspect, textwrap
    from utils.social.kaia_forum import ForumClient

    # String literals only — an earlier version of this test failed on the
    # comment explaining the removal.
    tree = ast.parse(textwrap.dedent(
        inspect.getsource(ForumClient.generate_personality_profile)))
    literals = " ".join(n.value for n in ast.walk(tree)
                        if isinstance(n, ast.Constant) and isinstance(n.value, str))
    for banned in ("Digital Dossier", "AI analyst"):
        assert banned not in literals, f"prompt still asks for: {banned}"
    assert "lowercase" in literals and "do not flatter" in literals.lower()


def test_profile_output_goes_through_the_filters():
    import inspect
    from utils.social.kaia_forum import ForumClient
    src = inspect.getsource(ForumClient.generate_personality_profile)
    assert "filter_response" in src and "harden" in src


def test_a_thin_history_does_not_get_a_confident_profile():
    import inspect
    from utils.social.kaia_forum import ForumClient
    src = inspect.getsource(ForumClient.generate_personality_profile)
    assert "substantive < 3" in src, "no guard against profiling from a couple of posts"
