from __future__ import annotations

import pytest

from add import add


class TestAddPositiveNumbers:
    """Tests for add() with positive integers."""

    def test_basic_sum(self) -> None:
        assert add(2, 3) == 5

    def test_large_numbers(self) -> None:
        assert add(1000, 2000) == 3000

    def test_single_digit(self) -> None:
        assert add(1, 1) == 2


class TestAddNegativeNumbers:
    """Tests for add() with negative integers."""

    def test_negative_and_positive(self) -> None:
        assert add(-1, 1) == 0

    def test_both_negative(self) -> None:
        assert add(-3, -7) == -10

    def test_negative_result(self) -> None:
        assert add(-10, 4) == -6


class TestAddZero:
    """Tests for add() involving zero."""

    def test_both_zero(self) -> None:
        assert add(0, 0) == 0

    def test_zero_left(self) -> None:
        assert add(0, 5) == 5

    def test_zero_right(self) -> None:
        assert add(5, 0) == 5


class TestAddFloats:
    """Tests for add() with floating-point numbers."""

    def test_basic_float_sum(self) -> None:
        assert add(1.5, 2.5) == 4.0

    def test_float_precision(self) -> None:
        result = add(0.1, 0.2)
        assert pytest.approx(result) == 0.3

    def test_negative_float(self) -> None:
        assert add(-1.5, 1.5) == pytest.approx(0.0)

    def test_mixed_int_float(self) -> None:
        assert add(2, 2.5) == pytest.approx(4.5)
