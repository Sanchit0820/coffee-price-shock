"""A minimal rate limiter: guarantees a minimum gap between calls per key.

Used by the scraper (key = website host) and the LLM layer (key = provider).
"""
import time


class RateLimiter:
    def __init__(self, min_interval: float):
        self.min_interval = min_interval
        # key -> time.monotonic() of the last call. monotonic() is used instead of
        # time.time() because it never jumps backwards if the system clock changes.
        self._last_call: dict[str, float] = {}

    def wait(self, key: str, min_interval: float | None = None) -> None:
        """Sleep just long enough that calls for `key` are spaced out.

        `min_interval` overrides the default for this call (e.g. a site's
        robots.txt Crawl-delay is longer than our default).
        """
        interval = self.min_interval if min_interval is None else min_interval
        last = self._last_call.get(key)
        if last is not None:
            remaining = interval - (time.monotonic() - last)
            if remaining > 0:
                time.sleep(remaining)
        self._last_call[key] = time.monotonic()
