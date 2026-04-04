from __future__ import annotations


def add(a: int | float, b: int | float) -> int | float:
    """Return the sum of two numbers.

    Args:
        a: First operand (int or float).
        b: Second operand (int or float).

    Returns:
        The arithmetic sum a + b.

    Examples:
        >>> add(2, 3)
        5
        >>> add(-1, 1)
        0
        >>> add(1.5, 2.5)
        4.0
    """
    return a + b
