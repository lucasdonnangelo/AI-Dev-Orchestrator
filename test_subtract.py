"""test_subtract.py — Unit tests for the subtract() function.

Run with:
    pytest test_subtract.py -v
"""

from __future__ import annotations

import pytest

from subtract import subtract


# ---------------------------------------------------------------------------
# Positive integers
# ---------------------------------------------------------------------------

class TestPositiveIntegers:
    def test_basic_subtraction(self) -> None:
        assert subtract(10, 3) == 7

    def test_result_is_zero(self) -> None:
        assert subtract(5, 5) == 0

    def test_large_values(self) -> None:
        assert subtract(1_000_000, 999_999) == 1


# ---------------------------------------------------------------------------
# Negative numbers
# ---------------------------------------------------------------------------

class TestNegativeNumbers:
    def test_both_negative(self) -> None:
        assert subtract(-5, -3) == -2

    def test_negative_minus_positive(self) -> None:
        assert subtract(-4, 6) == -10

    def test_positive_minus_negative(self) -> None:
        # Subtracting a negative is addition
        assert subtract(4, -6) == 10

    def test_negative_result(self) -> None:
        assert subtract(3, 8) == -5


# ---------------------------------------------------------------------------
# Zero subtraction
# ---------------------------------------------------------------------------

class TestZeroSubtraction:
    def test_zero_as_subtrahend(self) -> None:
        """subtract(a, 0) should return a unchanged."""
        assert subtract(5, 0) == 5

    def test_zero_as_minuend(self) -> None:
        """subtract(0, b) should return -b."""
        assert subtract(0, 5) == -5

    def test_both_zero(self) -> None:
        assert subtract(0, 0) == 0


# ---------------------------------------------------------------------------
# Float values
# ---------------------------------------------------------------------------

class TestFloatValues:
    def test_basic_float_subtraction(self) -> None:
        assert subtract(3.5, 1.5) == pytest.approx(2.0)

    def test_float_result_negative(self) -> None:
        assert subtract(1.5, 3.5) == pytest.approx(-2.0)

    def test_float_close_to_zero(self) -> None:
        assert subtract(0.1, 0.1) == pytest.approx(0.0)

    def test_large_float(self) -> None:
        assert subtract(1e9, 0.5e9) == pytest.approx(0.5e9)


# ---------------------------------------------------------------------------
# Mixed int / float inputs
# ---------------------------------------------------------------------------

class TestMixedInputs:
    def test_int_minus_float(self) -> None:
        assert subtract(5, 1.5) == pytest.approx(3.5)

    def test_float_minus_int(self) -> None:
        assert subtract(4.5, 2) == pytest.approx(2.5)

    def test_int_minus_negative_float(self) -> None:
        assert subtract(3, -0.5) == pytest.approx(3.5)


# ---------------------------------------------------------------------------
# Parametrized edge-case sweep
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("a, b, expected", [
    (10,   3,    7),      # acceptance criterion
    (-5,  -3,   -2),     # acceptance criterion
    (3,    10,  -7),     # acceptance criterion
    (1.5,  0.5,  1.0),  # acceptance criterion
    (5,    0,    5),
    (0,    5,   -5),
    (3.5,  1.5,  2.0),
    (5,    1.5,  3.5),
    (0,    0,    0),
    (-1,   1,   -2),
    (1,   -1,    2),
])
def test_parametrized_cases(a: int | float, b: int | float, expected: int | float) -> None:
    assert subtract(a, b) == pytest.approx(expected)
