from __future__ import annotations

import time
from typing import Any, Callable


class CircuitOpenError(RuntimeError):
    pass


class CircuitBreaker:
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"

    def __init__(self, failure_threshold: int = 3, recovery_timeout: int = 60) -> None:
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.state = self.CLOSED
        self.failure_count = 0
        self.opened_at: float | None = None

    def call(self, func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        if self.state == self.OPEN:
            if self.opened_at is not None and time.time() - self.opened_at >= self.recovery_timeout:
                self.state = self.HALF_OPEN
            else:
                raise CircuitOpenError("circuit breaker is open")

        try:
            result = func(*args, **kwargs)
        except Exception:
            self.failure_count += 1
            if self.failure_count >= self.failure_threshold:
                self.state = self.OPEN
                self.opened_at = time.time()
            raise

        self.failure_count = 0
        self.state = self.CLOSED
        self.opened_at = None
        return result
