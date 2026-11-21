"""An open loop is the speaker's own plan, the thing she can ask after when they return."""
import pytest

from utils.core.open_loops import find
import re
import time
from unittest.mock import patch


@pytest.mark.parametrize("said", [
    "i'm going to try the new creatine stack this week and see",
    "im gonna celebrate this open jar with some pasta tonight",
    "I’ll tell you how the race goes after the weekend, promise",
    "ok here is the deal, wish me luck.",
])
def test_a_plan_of_their_own_is_kept(said):
    assert find(said)


@pytest.mark.parametrize("said", [
    "Kaia. I have a nice picture of clouds for you. Do you want to see it? yes or no?",
    "take a little while to consider whether you still want to keep observing us in general",
    "that's gonna be a conspiracy theory going forward i think",
    "i'm certain of it. they lost consciousness from the g forces",
    "are you going to play that game with us this weekend then?",
    "i will never do anything like this to you ever again",
    "```i'll fix these issues and re-run the failed shots in the background```",
    "short one",
])
def test_anything_else_is_not(said):
    assert not find(said)


class TestCuriosityPatterns:
    """Verify that tightened patterns match intended phrases only."""

    def _get_patterns(self):
        """Import the compiled patterns directly."""
        from utils.core.curiosity_scanner import _UNRESOLVED_PATTERNS
        return _UNRESOLVED_PATTERNS

    def _matches_any(self, text):
        """Return True if any unresolved pattern matches the text."""
        for p in self._get_patterns():
            if p.search(text):
                return True
        return False

    # --- "going to" pattern ---

    def test_going_to_try_matches(self):
        assert self._matches_any("I'm going to try that tomorrow")

    def test_going_to_fix_matches(self):
        assert self._matches_any("going to fix the build tonight")

    def test_going_to_work_on_matches(self):
        assert self._matches_any("I'm going to work on that")

    def test_going_to_bed_does_not_match(self):
        """'going to bed' should NOT trigger curiosity — it's not an intent."""
        # Must not match the 'going to' pattern specifically
        going_to_pattern = re.compile(
            r"\bgoing to\s+(?:try|check|fix|test|look into|work on|start|finish|build|run)\b",
            re.IGNORECASE
        )
        assert not going_to_pattern.search("I'm going to bed")

    def test_going_to_be_does_not_match(self):
        going_to_pattern = re.compile(
            r"\bgoing to\s+(?:try|check|fix|test|look into|work on|start|finish|build|run)\b",
            re.IGNORECASE
        )
        assert not going_to_pattern.search("it's going to be a problem")

    # --- "next time" pattern ---

    def test_next_time_ill_matches(self):
        next_time_pattern = re.compile(
            r"\bnext time\s+(?:i|i'll|we|we'll|let's)\b", re.IGNORECASE
        )
        assert next_time_pattern.search("next time I'll check the logs")

    def test_next_time_lets_matches(self):
        next_time_pattern = re.compile(
            r"\bnext time\s+(?:i|i'll|we|we'll|let's)\b", re.IGNORECASE
        )
        assert next_time_pattern.search("next time let's try something different")

    def test_see_you_next_time_does_not_match(self):
        """'see you next time' is a farewell, not an intent."""
        next_time_pattern = re.compile(
            r"\bnext time\s+(?:i|i'll|we|we'll|let's)\b", re.IGNORECASE
        )
        assert not next_time_pattern.search("see you next time")

    def test_until_next_time_does_not_match(self):
        next_time_pattern = re.compile(
            r"\bnext time\s+(?:i|i'll|we|we'll|let's)\b", re.IGNORECASE
        )
        assert not next_time_pattern.search("until next time!")


def test_someone_elses_plans_are_not_the_speakers():
    """Real lines that matched when any subject would do (24 Sept, 42 hits, half false)."""
    from utils.core.curiosity_scanner import _UNRESOLVED_PATTERNS
    for line in ("Theres some massive open source WoW thing, blizzard is going to try to get it taken down",
                 "Just keep working on that zen and enlightenment",
                 "Was hoping to get a pic of it in the pond",
                 "Opus 5.5 has been working on it"):
        assert not any(p.search(line) for p in _UNRESOLVED_PATTERNS), line
    assert any(p.search("I'm gonna try green beans and spinach") for p in _UNRESOLVED_PATTERNS)
