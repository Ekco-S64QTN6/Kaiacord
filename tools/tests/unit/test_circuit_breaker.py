"""The breaker every social poller and document converter relies on."""
import utils.infrastructure.circuit_breaker as cb


def test_trips_after_the_threshold_and_refuses_calls():
    b = cb.CircuitBreaker("t", failure_threshold=3, recovery_timeout=60)
    for _ in range(2):
        b.record_failure()
    assert b.can_proceed()
    b.record_failure()
    assert b.state is cb.CircuitState.OPEN and not b.can_proceed()


def test_half_open_allows_one_trial_then_closes_or_reopens(monkeypatch):
    now = [1000.0]
    monkeypatch.setattr(cb.time, "time", lambda: now[0])
    b = cb.CircuitBreaker("t", failure_threshold=1, recovery_timeout=60)
    b.record_failure()
    now[0] += 61
    assert b.can_proceed() and b.state is cb.CircuitState.HALF_OPEN
    assert not b.can_proceed(), "a second call went through during the trial"
    b.record_failure()
    assert b.state is cb.CircuitState.OPEN and not b.can_proceed()
    now[0] += 61
    assert b.can_proceed()
    b.record_success()
    assert b.state is cb.CircuitState.CLOSED and b.can_proceed() and b.can_proceed()


def test_an_outcome_is_never_dropped_under_contention():
    """record_* used a non-blocking acquire and silently skipped when the lock
    was held, so a failure could go uncounted."""
    import threading
    b = cb.CircuitBreaker("t", failure_threshold=10_000)
    threads = [threading.Thread(target=lambda: [b.record_failure() for _ in range(500)]) for _ in range(8)]
    for t in threads: t.start()
    for t in threads: t.join()
    assert b.failures == 4000


def test_an_unreported_trial_does_not_hold_the_breaker_shut(monkeypatch):
    now = [1000.0]
    monkeypatch.setattr(cb.time, "time", lambda: now[0])
    b = cb.CircuitBreaker("t", failure_threshold=1, recovery_timeout=60)
    b.record_failure()
    now[0] += 61
    assert b.can_proceed()          # trial handed out, never reported
    now[0] += 61
    assert b.can_proceed(), "the breaker stayed shut on a trial nobody reported"
