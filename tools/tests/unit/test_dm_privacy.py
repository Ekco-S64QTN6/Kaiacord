"""A DM is written to its own log under memory/, never to the shared
user_logs that retrieval serves to public replies."""
import ast
import inspect
import textwrap
from pathlib import Path
from types import SimpleNamespace

from utils.core import dm_log


def test_a_dm_goes_to_its_own_log(tmp_path, monkeypatch):
    monkeypatch.setattr(dm_log, "telemetry_path", lambda p: str(tmp_path / p))
    dm_log.record(519557167779676160, "Starkind", "this is between us", "understood.")
    p = tmp_path / "memory" / "dm_logs" / "519557167779676160.md"
    text = p.read_text()
    assert "Starkind: this is between us" in text and "Kaia: understood." in text
    assert "knowledge_base" not in str(p)


def test_a_dm_log_redacts_credentials_from_user_and_reply_urls(tmp_path, monkeypatch):
    monkeypatch.setattr(dm_log, "telemetry_path", lambda p: str(tmp_path / p))
    said = "read https://alice:pw@files.example.com/a?accessToken=user-secret&format=pdf"
    reply = "https://api.example.com/b?clientSecret=reply-secret&format=pdf#private"
    dm_log.record(42, "tester", said, reply)

    saved = (tmp_path / "memory" / "dm_logs" / "42.md").read_text(encoding="utf-8")
    assert "https://files.example.com/a?format=pdf" in saved
    assert "https://api.example.com/b?format=pdf" in saved
    for secret in ("alice", "pw", "user-secret", "reply-secret", "clientSecret", "#private"):
        assert secret not in saved


def test_the_pipeline_routes_dms_away_from_the_shared_log(log_turn):
    seen = log_turn(True)
    assert seen["private"] and not seen["shared"]
    seen["private"].clear()
    seen = log_turn(False)
    assert seen["shared"] and not seen["private"]


def test_a_reply_full_of_ellipses_is_still_logged(log_turn):
    """The user's own message went unlogged with a reply the style check disliked."""
    seen = log_turn(False, reply="well… it's… complicated… isn't it… yes… — — — — —")
    assert seen["shared"] and seen["shared"][0][2] == "this is between us"


def test_a_dm_never_becomes_one_of_her_notes():
    """Notes are indexed and retrieval serves public replies."""
    src = Path("utils/core/message_processor.py").read_text()
    gate = src[src.index("from utils.core import kaia_notes") - 400: src.index("from utils.core import kaia_notes")]
    assert '"is_dm"' in gate


def test_private_dm_does_not_update_cross_channel_memory():
    """Private turns must not feed stores that are injected into later public turns."""
    from utils.core.message_processor import MessageProcessor

    source = textwrap.dedent(inspect.getsource(MessageProcessor._background_logging_and_memory))
    tree = ast.parse(source)
    parents = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parents[child] = node

    guarded_names = {
        "learn_from_interaction", "update_relationship", "save_event_async",
        "record_claim", "note_argument", "emotional_arc", "observe_exchange",
        "desire_engine", "append_growth_event", "_find_open_loop",
        "write_atomic", "queue_afterthought", "set_open_loop",
    }
    found = set()
    for node in ast.walk(tree):
        name = None
        if isinstance(node, ast.Name):
            name = node.id
        elif isinstance(node, ast.Attribute):
            name = node.attr
        if name not in guarded_names:
            continue
        found.add(name)
        parent = parents.get(node)
        guarded = False
        while parent is not None:
            if isinstance(parent, ast.If) and "not is_private_dm" in ast.unparse(parent.test):
                guarded = True
                break
            parent = parents.get(parent)
        assert guarded, f"{name} can still be reached by a private DM"
    assert guarded_names <= found, f"privacy audit lost coverage for {guarded_names - found}"


def test_private_dm_does_not_change_the_cross_channel_user_state():
    from utils.core.message_processor import MessageProcessor

    source = inspect.getsource(MessageProcessor._retrieve_and_generate)
    assert "if not _is_private_dm(ctx):\n                    self.bot_state.update_user_state" in source


def test_private_dm_predicate_is_explicit():
    from utils.core.message_processor import _is_private_dm

    assert _is_private_dm(SimpleNamespace(is_dm=True)) is True
    assert _is_private_dm(SimpleNamespace(is_dm=False)) is False
    assert _is_private_dm(SimpleNamespace()) is False


def test_dm_interaction_does_not_become_the_proactive_target(tmp_path):
    from utils.infrastructure.system.bot_state import BotState

    state = BotState(state_file=str(tmp_path / "bot_state.json"))
    state.update_interaction(None)
    assert state.last_interaction_time > 0
    assert state.channel_last_activity == {}
    assert state.last_active_channel_id is None
    state.close()


def test_server_wide_private_monologue_does_not_enter_direct_reply_prompts():
    """Cross-channel thoughts are unscoped; they must not steer direct replies."""
    from utils.core.message_processor import MessageProcessor

    source = textwrap.dedent(inspect.getsource(MessageProcessor._retrieve_and_generate))
    tree = ast.parse(source)
    assert not any(
        isinstance(node, ast.Attribute) and node.attr == "get_injection"
        for node in ast.walk(tree)
    ), "direct replies must not inject the private monologue buffer"
    assert "self.ctx.monologue" not in source
    assert "monologue.get_injection()" not in Path("utils/core/message_processor.py").read_text(
        encoding="utf-8"
    )




def test_a_guard_does_not_quote_a_dm_reply_into_the_log(monkeypatch):
    from utils.core import private_turn
    from utils.core import response_filter as rf
    lines = []
    monkeypatch.setattr(rf, "log_warning", lines.append)
    token = private_turn.enter(True)
    try:
        rf.BotSpeakFilter.strip_apologies("you're right, the divorce papers came through on tuesday.")
    finally:
        private_turn.leave(token)
    assert lines and all("divorce" not in l and private_turn.WITHHELD in l for l in lines)
    lines.clear()
    rf.BotSpeakFilter.strip_apologies("you're right, the cron job was the culprit.")
    assert lines and "cron job" in lines[0]

def test_private_inline_vision_diagnostics_withhold_attachment_url_filename_and_error():
    from utils.core import private_turn
    from utils.core.message_processor import (
        _vision_attachment_fetch_log,
        _vision_attachment_failure_log,
    )

    url = (
        "https://cdn.discordapp.com/attachments/123456/789012/"
        "private-medical-document.png?ex=secret&is=token&hm=signed"
    )
    filename = "private-medical-document.png"
    error = OSError("private storage location unavailable")
    token = private_turn.enter(True)
    try:
        fetch_log = _vision_attachment_fetch_log(url)
        failure_log = _vision_attachment_failure_log(filename, error)
    finally:
        private_turn.leave(token)

    assert private_turn.WITHHELD in fetch_log
    assert private_turn.WITHHELD in failure_log
    for secret in ("123456", "789012", filename, "secret", "token", "signed", "private storage"):
        assert secret not in fetch_log
        assert secret not in failure_log


def test_public_inline_vision_diagnostics_keep_context_but_redact_url_credentials():
    from utils.core.message_processor import (
        _vision_attachment_fetch_log,
        _vision_attachment_failure_log,
    )

    url = "https://cdn.discordapp.com/attachments/123456/789012/photo.png?accessToken=fetch-secret&format=png"
    filename = "photo.png"
    error = OSError(
        "connection reset for "
        "https://cdn.discordapp.com/attachments/123456/789012/photo.png?"
        "clientSecret=error-secret&format=png"
    )

    fetch_log = _vision_attachment_fetch_log(url)
    assert "https://cdn.discordapp.com/attachments/123456/789012/photo.png?format=png" in fetch_log
    assert "accessToken" not in fetch_log and "fetch-secret" not in fetch_log

    failure_log = _vision_attachment_failure_log(filename, error)
    assert filename in failure_log
    assert "connection reset" in failure_log
    assert "clientSecret" not in failure_log and "error-secret" not in failure_log
    assert "format=png" in failure_log

