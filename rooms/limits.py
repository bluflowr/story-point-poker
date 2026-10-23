"""
Simple in-memory rate limits, which work because the app runs as one process.

    limiter = RateLimiter(limit=10, window=600)  # 10 per 10 minutes
    if not limiter.allow(key):
        ...  # too many
"""

import threading
import time
import weakref
from collections import defaultdict, deque

_all_limiters = weakref.WeakSet()


class RateLimiter:
    def __init__(self, limit, window, clock=time.monotonic):
        self.limit = limit
        self.window = window
        self.clock = clock
        self._events = defaultdict(deque)  # key -> times of recent events
        self._lock = threading.Lock()
        _all_limiters.add(self)

    def allow(self, key=""):
        """Record an event for `key` and say whether it is within the limit."""
        now = self.clock()
        with self._lock:
            events = self._events[key]
            while events and events[0] <= now - self.window:
                events.popleft()
            if len(events) >= self.limit:
                return False
            events.append(now)
            if len(self._events) > 10_000:
                self._forget_idle_keys(now)
            return True

    def reset(self):
        with self._lock:
            self._events.clear()

    def _forget_idle_keys(self, now):
        idle = [key for key, events in self._events.items() if not events or events[-1] <= now - self.window]
        for key in idle:
            del self._events[key]


def reset_all():
    """Clear every limiter. Used by tests."""
    for limiter in list(_all_limiters):
        limiter.reset()


def client_ip(request):
    """
    The visitor's IP address. On Render, requests arrive through a proxy that
    puts the real address first in X-Forwarded-For. A client can fake that
    header, so per-IP limits are only a speed bump; the global limits are the
    real backstop.
    """
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "")
