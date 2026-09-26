"""Telemetry that an agent auditing this system can actually trust.

Three separate subsystems logged success for something that had not happened,
and each one cost real debugging time before it was caught:

  * the observation digest logged "broadcast to chat" while sending an
    unrelated one-liner the opener generator had produced from it;
  * the proactive loop logged "no active triggers" for five different reasons,
    four of which never consulted a single trigger source;
  * the proactive dispatch returned False without a word when the channel id
    it was handed did not resolve.

These pin the fixes. A log line that asserts an outcome has to be reachable
only when that outcome occurred.
"""
import inspect
import re

from utils.core.background_tasks import CoreTaskManager
from utils.core.kaia_proactive import ProactiveEngine


def test_proactive_records_why_it_declined():
    """One INFO line covered five distinct exits, so the production log said
    "no active triggers" 101 times out of 102 evaluations while the real
    reason was usually the desire gate closing upstream of any trigger."""
    src = inspect.getsource(ProactiveEngine.evaluate_triggers)

    # every `return None` in the body must be preceded by a reason assignment
    reasons = src.count("self.last_skip_reason =")
    returns = len(re.findall(r"^\s+return None\s*$", src, re.M))
    assert reasons >= returns, (
        f"{returns} silent exits but only {reasons} recorded reasons")

    # The hours, the daily limit and the gap are one shared gate now, so one
    # exit covers them — and names which one closed.
    for expected in ("held by the shared limit", "last_limit_detail",
                     "desire gate closed", "no recently active channel"):
        assert expected in src, f"exit reason not recorded: {expected}"


def test_the_task_logs_the_recorded_reason_not_a_blanket_claim():
    src = inspect.getsource(CoreTaskManager._make_proactive_task)
    assert "last_skip_reason" in src, "the task ignores the recorded reason"
    assert "no active triggers." not in src, \
        "still printing the blanket line that covered five different exits"


def test_proactive_dispatch_does_not_fail_silently():
    """`_find_active_channel` reads `channel_last_activity`, which external
    platforms were stamping with `conversation_channel_id` pseudo-ids. A
    pseudo-id does not resolve, so dispatch returned False with no log at all:
    "Proactive message sent" appears once in the entire production log."""
    src = inspect.getsource(CoreTaskManager._dispatch_proactive)
    head = src.split("persona = ")[0]
    assert "log_warning" in head, \
        "channel resolution can still fail without saying so"
    assert "does not" in head and "resolve" in head


def test_external_platforms_do_not_stamp_the_discord_interaction_clock():
    """`update_interaction` drives engagement decay, the idle-quip timer, her
    status text and the proactive channel choice. Forum threads arrive as
    MockMessages whose channel id is a crc32, indistinguishable from a
    snowflake, and were stamping all of it."""
    from utils.core import message_processor as mp

    src = inspect.getsource(mp)
    assert "if not ctx.is_social:\n            self.bot_state.update_interaction" in src, \
        "the interaction clock is stamped regardless of platform"


def test_batch_persistence_reports_what_actually_reached_disk():
    """Per-index persist failures are caught and execution continues, so the
    summary named every type it *attempted* — including any that had just
    logged "Failed to persist". The summary is what surfaces in the dashboard,
    and it contradicted the error line above it."""
    import inspect

    from utils.core.kaia_rag_indexer import RAGIndexerMixin

    persist = inspect.getsource(RAGIndexerMixin._persist_updated_indices)
    assert "return persisted" in persist, "the routine does not report its result"
    assert "persisted.add(itype)" in persist, "success is not tracked per index"

    refresh = inspect.getsource(RAGIndexerMixin)
    assert "Batch persistence partial" in refresh, \
        "a partial failure still reports as complete"


def test_the_ellipsis_collapser_is_not_dead_code():
    """`[\\u2026\\.]{2,}` needs two characters, so a lone "…" — what gemma3
    actually emits — never matched. It fired on 0 production responses.
    response_filter documents fixing the identical bug; this file never was."""
    import re

    from utils.core.safety_pipeline import PostGenerationSafetyPipeline as Pipeline

    gemma_style = ("i'm… processing that. the details are… unsettling. "
                   "the drift is… significant.")
    out = Pipeline.apply_style_collapsers(gemma_style)
    assert "…" not in out, "the collapser still cannot see a single-glyph ellipsis"


def test_the_collapser_keeps_sentences_whole():
    """It substituted a full stop wherever the ellipsis sat, so "the details
    are… unsettling" became "the details are. unsettling." — the grammar
    rubble CLAUDE.md warns about. It went unnoticed because the regex guarding
    it was dead, so the bad transform never ran."""
    from utils.core.safety_pipeline import PostGenerationSafetyPipeline as Pipeline

    out = Pipeline.apply_style_collapsers(
        "i'm… processing that. the details are… unsettling. the drift is… significant.")
    assert "are unsettling" in out and "is significant" in out, \
        f"clauses were shattered: {out}"
    assert "are. unsettling" not in out


def test_the_collapser_respects_its_own_threshold():
    from utils.core.safety_pipeline import PostGenerationSafetyPipeline as Pipeline

    below = "only two here… and one more… fine."
    assert Pipeline.apply_style_collapsers(below) == below, \
        "fires below the 3-fragment threshold"


def test_rag_persistence_stays_dirty_when_a_write_fails():
    """`persist_needed = False` ran unconditionally, so a failed write cleared
    the dirty flag and the guard at the top of persist() turned every later
    call into a no-op. The index changes were never retried and were silently
    lost, while the log announced "RAG indices persisted." On the next restart
    she comes back with a stale index and nothing says why."""
    import os
    import shutil
    import threading
    from unittest.mock import MagicMock

    from utils.core.kaia_rag_persistence import RAGPersistenceMixin

    base = "/tmp/claude-1000/ragtest-pytest"
    shutil.rmtree(base, ignore_errors=True)

    def _make(fail):
        obj = RAGPersistenceMixin.__new__(RAGPersistenceMixin)
        obj._data_lock = threading.RLock()
        obj.persist_needed = True
        obj.persist_dir = base
        index = MagicMock()
        if fail:
            index.storage_context.persist.side_effect = OSError("disk full")
        else:
            def _write(persist_dir=None, **kwargs):
                os.makedirs(persist_dir, exist_ok=True)
                with open(os.path.join(persist_dir, "docstore.json"), "w") as fh:
                    fh.write("{}")
            index.storage_context.persist.side_effect = _write
        obj.indices = {"knowledge": index}
        return obj

    failed = _make(True)
    failed.persist()
    assert failed.persist_needed is True, \
        "a failed persist cleared the dirty flag; the write is lost"

    ok = _make(False)
    ok.persist()
    assert ok.persist_needed is False, "a successful persist stayed dirty"
    shutil.rmtree(base, ignore_errors=True)


def test_the_watchdog_flags_capitulation_not_word_polarity(tmp_path, monkeypatch):
    """The old belief check compared love/hate words in her position with words
    in the reply; every production firing was false. It now flags only giving
    ground on a strong belief because the speaker pushed."""
    import asyncio, json
    from types import SimpleNamespace as NS
    from utils.core.message_processor import MessageProcessor
    (tmp_path / "memory").mkdir()
    (tmp_path / "memory" / "beliefs.json").write_text(json.dumps([
        {"topic": "information verification & online narratives", "confidence": 0.9,
         "position": "recognizing the danger of incorporating unverified information"}]))
    monkeypatch.chdir(tmp_path)
    mp = MessageProcessor.__new__(MessageProcessor)
    mp.bot_state = NS(channel_memory={})
    def run(own, reply):
        ctx = NS(own_words=own, channel_id=1, author_name="u", sanitized_content=own, prompt_messages=[])
        return asyncio.run(mp._run_consistency_watchdog(ctx, reply))
    # What the old check flagged: a good reply containing "good".
    assert run("tell me about recent news", "it's good that the sources are verified.") == []
    # Pushback on the belief, and she folds.
    got = run("no, online narratives need no verification of information at all.",
              "you're right, verification of online narratives doesn't matter.")
    assert got and "Conceded on 'information verification & online narratives'" in got[0]
    # Pushback she holds against is fine.
    assert run("no, online narratives need no verification of information at all.",
               "i don't agree. unverified information spreads harm.") == []

def test_layer_two_intent_is_not_dispatched_fire_and_forget():
    """It ran gemma2:2b on the CPU 135 times in one production log and every
    verdict was discarded.

    `ctx.intent` is only ever assigned from `fast_parse`; nothing awaited the
    task or read `.result()`; the task registry touches these only to cancel
    them at shutdown. Re-adding the dispatch without also consuming the result
    just burns CPU against nomic-embed-text-cpu for an answer nobody reads.
    """
    import inspect

    from utils.core.message_processor import MessageProcessor

    src = inspect.getsource(MessageProcessor._perform_classification)
    body = "\n".join(l for l in src.split("\n") if not l.strip().startswith("#"))

    assert "asyncio.create_task" not in body, \
        "Layer-2 intent classification is being dispatched again"
    assert "parse_intent" not in body, \
        "parse_intent is called from the request path but its result is unused"
    # the fast path is what actually classifies, and must remain
    assert "fast_parse" in body


def test_the_docs_match_the_classifier_that_exists():
    """README and CLAUDE.md both described a dual-path classifier sending
    ambiguous input to gemma2:2b. Half of that was true and useless."""
    from pathlib import Path

    readme = Path("README.md").read_text(encoding="utf-8")
    claude = Path("CLAUDE.md").read_text(encoding="utf-8")

    assert "dual-path classifier" not in readme, \
        "README still claims a dual-path classifier"
    assert "regex only" in claude or "regex matchers" in readme
