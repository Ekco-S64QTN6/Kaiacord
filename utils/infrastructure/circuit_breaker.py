"""
Circuit Breaker
================

Shared circuit breaker for any external service calls (API endpoints, file
converters, etc.).  Lives in utils/infrastructure so that both core and social
modules can import it without creating a dependency inversion.
"""

import time
from utils.infrastructure.logging.kaia_logger import log_info, log_warning


class CircuitBreaker:
    """Simple circuit breaker with exponential-style failure tracking.

    Usage::

        breaker = CircuitBreaker("my_service", failure_threshold=3, reset_timeout=300)

        if breaker.can_proceed():
            try:
                result = call_external_service()
                breaker.record_success()
            except Exception:
                breaker.record_failure()
    """

    def __init__(self, name: str, failure_threshold: int = 3, reset_timeout: int = 300):
        self.name = name
        self.failures = 0
        self.threshold = failure_threshold
        self.reset_timeout = reset_timeout  # seconds before auto-reset
        self.last_failure_time = 0.0
        self.is_open = False

    def can_proceed(self) -> bool:
        """Return True if calls should be allowed through."""
        if not self.is_open:
            return True
        # Auto-reset after timeout window
        if time.time() - self.last_failure_time >= self.reset_timeout:
            self.is_open = False
            self.failures = 0
            log_info(f"Circuit breaker '{self.name}' reset after timeout")
            return True
        return False

    def record_success(self) -> None:
        """Record a successful call — resets failure counter."""
        self.failures = 0
        self.is_open = False

    def record_failure(self) -> None:
        """Record a failed call — opens the breaker after threshold."""
        self.failures += 1
        self.last_failure_time = time.time()
        if self.failures >= self.threshold:
            self.is_open = True
            log_warning(f"Circuit breaker '{self.name}' OPEN after {self.failures} failures")
