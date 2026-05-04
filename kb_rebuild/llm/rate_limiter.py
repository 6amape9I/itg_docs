from __future__ import annotations

import random
import threading
import time
from dataclasses import dataclass
from typing import Callable

from kb_rebuild.llm.openrouter_client import OpenRouterError


@dataclass
class RateLimitPermit:
    limiter: "AdaptiveRateLimiter"
    released: bool = False

    def release(self) -> None:
        if not self.released:
            self.released = True
            self.limiter.release()

    def __enter__(self) -> "RateLimitPermit":
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.release()


class AdaptiveRateLimiter:
    def __init__(
        self,
        *,
        max_inflight: int = 1,
        min_request_interval_seconds: float = 5.0,
        rate_limit_backoff_seconds: float = 120.0,
        max_rate_limit_backoff_seconds: float = 300.0,
        jitter_seconds: float = 0.0,
        success_streak_to_increase: int = 20,
        time_fn: Callable[[], float] | None = None,
        sleep_fn: Callable[[float], None] | None = None,
    ) -> None:
        if max_inflight <= 0:
            raise ValueError("max_inflight must be > 0")
        if min_request_interval_seconds < 0:
            raise ValueError("min_request_interval_seconds must be >= 0")
        if rate_limit_backoff_seconds < 0:
            raise ValueError("rate_limit_backoff_seconds must be >= 0")
        if max_rate_limit_backoff_seconds < rate_limit_backoff_seconds:
            raise ValueError("max_rate_limit_backoff_seconds must be >= rate_limit_backoff_seconds")
        if jitter_seconds < 0:
            raise ValueError("jitter_seconds must be >= 0")

        self.max_inflight = max_inflight
        self.min_request_interval_seconds = min_request_interval_seconds
        self.rate_limit_backoff_seconds = rate_limit_backoff_seconds
        self.max_rate_limit_backoff_seconds = max_rate_limit_backoff_seconds
        self.jitter_seconds = jitter_seconds
        self.success_streak_to_increase = success_streak_to_increase
        self.time_fn = time_fn or time.monotonic
        self.sleep_fn = sleep_fn or time.sleep

        self._lock = threading.Lock()
        self._inflight = 0
        self._effective_max_inflight = max_inflight
        self._next_request_at = 0.0
        self._cooldown_until = 0.0
        self._stable_success_streak = 0
        self._stats = {
            "cooldown_events_count": 0,
            "cooldown_seconds_total": 0.0,
            "retry_after_values_seconds": [],
            "effective_max_inflight": max_inflight,
        }

    def acquire(self) -> RateLimitPermit:
        while True:
            with self._lock:
                now = self.time_fn()
                allowed_at = max(self._next_request_at, self._cooldown_until)
                if self._inflight < self._effective_max_inflight and now >= allowed_at:
                    self._inflight += 1
                    self._next_request_at = now + self.min_request_interval_seconds
                    return RateLimitPermit(self)
                wait_for = max(allowed_at - now, 0.01)
            self.sleep_fn(wait_for)

    def release(self) -> None:
        with self._lock:
            self._inflight = max(0, self._inflight - 1)

    def notify_success(self) -> None:
        with self._lock:
            self._stable_success_streak += 1
            if (
                self._effective_max_inflight < self.max_inflight
                and self._stable_success_streak >= self.success_streak_to_increase
            ):
                self._effective_max_inflight += 1
                self._stable_success_streak = 0
                self._stats["effective_max_inflight"] = self._effective_max_inflight

    def notify_error(self, error: OpenRouterError, attempt_index: int) -> float:
        if error.status_code != 429:
            return 0.0
        retry_after = error.retry_after_seconds
        backoff = self.rate_limit_backoff_seconds * (2 ** max(0, attempt_index))
        if retry_after is not None:
            self._stats["retry_after_values_seconds"].append(round(retry_after, 3))
        cooldown = max(backoff, retry_after or 0.0)
        cooldown = min(cooldown, self.max_rate_limit_backoff_seconds)
        if self.jitter_seconds:
            cooldown += random.uniform(0.0, self.jitter_seconds)
        with self._lock:
            self._stable_success_streak = 0
            self._effective_max_inflight = 1
            self._stats["effective_max_inflight"] = self._effective_max_inflight
            self._stats["cooldown_events_count"] += 1
            self._stats["cooldown_seconds_total"] = round(
                float(self._stats["cooldown_seconds_total"]) + cooldown,
                3,
            )
            self._cooldown_until = max(self._cooldown_until, self.time_fn() + cooldown)
        return cooldown

    def snapshot(self) -> dict[str, object]:
        with self._lock:
            return {
                "cooldown_events_count": self._stats["cooldown_events_count"],
                "cooldown_seconds_total": round(float(self._stats["cooldown_seconds_total"]), 3),
                "retry_after_values_seconds": list(self._stats["retry_after_values_seconds"]),
                "effective_max_inflight": self._stats["effective_max_inflight"],
            }
