"""Retry temporary LLM failures (429 / 503) with exponential backoff.

Waits 2, 4, 8, 16, 32 seconds between attempts (doubling each time, capped),
plus up to 1 s of random "jitter" so parallel jobs don't retry in lockstep.
Only RetryableError is retried; anything else (bad key, bad request) fails at
once, because waiting won't fix it.
"""
import random
import time

from src.llm.base import RetryableError

MAX_ATTEMPTS = 6       # 1 try + 5 retries: up to ~62 s of waiting in total
BASE_DELAY = 2.0
MAX_DELAY = 60.0


def backoff_delays(attempts: int = MAX_ATTEMPTS, base: float = BASE_DELAY,
                   cap: float = MAX_DELAY) -> list[float]:
    """The waits between attempts, without jitter: [2, 4, 8, 16, 32] by default."""
    return [min(cap, base * 2 ** i) for i in range(attempts - 1)]


def call_with_backoff(fn, *args, sleep=time.sleep, jitter=random.random,
                      attempts: int = MAX_ATTEMPTS, on_retry=None):
    """Call fn(*args); on RetryableError wait and try again, up to `attempts` times.

    `sleep` and `jitter` are parameters so tests can run instantly.
    `on_retry(attempt, error, delay)` is called before each wait (for logging).
    """
    delays = backoff_delays(attempts)
    for attempt in range(attempts):
        try:
            return fn(*args)
        except RetryableError as err:
            if attempt == attempts - 1:
                raise
            delay = delays[attempt] + jitter()
            if on_retry:
                on_retry(attempt + 1, err, delay)
            sleep(delay)
