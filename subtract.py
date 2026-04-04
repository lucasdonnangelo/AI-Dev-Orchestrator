"""subtract.py — Provides a simple arithmetic subtraction utility.

This module exposes a single function, subtract(a, b), that computes
the difference between two numeric values (a - b).  It is intentionally
minimal so it can be imported by any part of the project without side
effects.
"""

from __future__ import annotations


def subtract(a: int | float, b: int | float) -> int | float:
    """Return the arithmetic difference *a* minus *b*.

    Args:
        a: The minuend (number to subtract from).
        b: The subtrahend (number to subtract).

    Returns:
        The value of ``a - b``.  The return type mirrors the input types:
        two ``int`` arguments produce an ``int``; any ``float`` argument
        produces a ``float``.

    Examples:
        >>> subtract(10, 3)
        7
        >>> subtract(-5, -3)
        -2
        >>> subtract(3.5, 1.5)
        2.0
        >>> subtract(5, 1.5)
        3.5
    """
    return a - b
