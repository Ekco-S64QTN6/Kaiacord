import time
import asyncio
from enum import Enum
from typing import Callable, Any, Optional
from utils.infrastructure.logging.kaia_logger import log_warning, log_error

class CircuitState(Enum):
    CLOSED = "CLOSED"    # Normal operation
    OPEN = "OPEN"        # Failed, blocking requests
    HALF_OPEN = "HALF_OPEN" # Testing if service recovered

class CircuitBreaker:
    """
    Prevents cascading failures by blocking calls to a failing service.
    """
    def __init__(self, 
                 name: str, 
                 failure_threshold: int = 5, 
                 recovery_timeout: float = 60.0):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        
        self.state = CircuitState.CLOSED
        self.failures = 0
        self.last_failure_time: Optional[float] = None
        self._lock = asyncio.Lock()

    async def call(self, func: Callable, *args, **kwargs) -> Any:
        async with self._lock:
            if self.state == CircuitState.OPEN:
                if time.time() - self.last_failure_time > self.recovery_timeout:
                    log_warning(f"[CIRCUIT BREAKER] {self.name} entering HALF_OPEN state.")
                    self.state = CircuitState.HALF_OPEN
                else:
                    raise RuntimeWarning(f"Circuit breaker {self.name} is OPEN.")

        try:
            result = await func(*args, **kwargs)
            
            async with self._lock:
                if self.state == CircuitState.HALF_OPEN:
                    log_warning(f"[CIRCUIT BREAKER] {self.name} RECOVERED. Closing circuit.")
                    self.state = CircuitState.CLOSED
                    self.failures = 0
            return result
            
        except Exception as e:
            async with self._lock:
                self.failures += 1
                self.last_failure_time = time.time()
                
                if self.failures >= self.failure_threshold:
                    if self.state != CircuitState.OPEN:
                        log_error(f"[CIRCUIT BREAKER] {self.name} TRIPPED! Opening circuit for {self.recovery_timeout}s.")
                        self.state = CircuitState.OPEN
                
                raise e
