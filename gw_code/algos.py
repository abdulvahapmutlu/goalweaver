"""
Algorithms.
"""

from functools import cache

BASE_CASE_CUTOFF = 2  # avoid magic value


def fib(n: int) -> int:
    """Return the n-th Fibonacci number (0-indexed) using memoization.

    >>> fib(0)
    0
    >>> fib(1)
    1
    >>> fib(10)
    55
    """
    if n < 0:
        raise ValueError("n must be non-negative")

    @cache
    def _f(k: int) -> int:
        if k < BASE_CASE_CUTOFF:
            return k
        return _f(k - 1) + _f(k - 2)

    return _f(n)


__all__ = ["fib"]
