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

    for expected in ("outside active hours", "rate limited",
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
