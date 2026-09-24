"""Stop calling a service that keeps failing, and try it again later.

CLOSED lets every call through. `failure_threshold` failures in a row OPEN it,
which refuses calls for `recovery_timeout` seconds. Then it goes HALF_OPEN and
lets one trial call through: success closes it, failure opens it again.
Callers ask `can_proceed()` and report with `record_success()` /
`record_failure()`.
"""
import threading
import time
from enum import Enum
from typing import Optional

from utils.infrastructure.logging.kaia_logger import log_error, log_info, log_warning


class CircuitState(Enum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


class CircuitBreaker:
    def __init__(self, name: str, failure_threshold: int = 5, recovery_timeout: float = 60.0):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.state = CircuitState.CLOSED
        self.failures = 0
        self.last_failure_time: Optional[float] = None
        self._trial_at: Optional[float] = None
        # Held only for a few assignments, so blocking is safe from the loop.
        self._lock = threading.Lock()

    def can_proceed(self) -> bool:
        with self._lock:
            if self.state == CircuitState.CLOSED:
                return True
            if self.state == CircuitState.OPEN:
                if time.time() - (self.last_failure_time or 0) < self.recovery_timeout:
                    return False
                log_warning(f"[CIRCUIT BREAKER] {self.name} entering HALF_OPEN state.")
                self.state = CircuitState.HALF_OPEN
                self._trial_at = None
            # One trial at a time. A caller that never reports back must not
            # hold the breaker shut, so an unanswered trial expires.
            now = time.time()
            if self._trial_at is not None and now - self._trial_at < self.recovery_timeout:
                return False
            self._trial_at = now
            return True

    def record_success(self) -> None:
        with self._lock:
            if self.state != CircuitState.CLOSED:
                log_info(f"[CIRCUIT BREAKER] {self.name} RECOVERED. Closing circuit.")
            self.state = CircuitState.CLOSED
            self.failures = 0
            self.last_failure_time = None
            self._trial_at = None

    def record_failure(self) -> None:
        with self._lock:
            self.failures += 1
            self.last_failure_time = time.time()
            self._trial_at = None
            if self.state == CircuitState.HALF_OPEN or self.failures >= self.failure_threshold:
                if self.state != CircuitState.OPEN:
                    log_error(f"[CIRCUIT BREAKER] {self.name} TRIPPED! Opening circuit for {self.recovery_timeout:g}s.")
                self.state = CircuitState.OPEN
