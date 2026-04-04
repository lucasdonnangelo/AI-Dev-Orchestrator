from __future__ import annotations

from multiply import multiply


class TestMultiplyPositiveNumbers:
    def test_two_positive_integers(self) -> None:
        assert multiply(3, 4) == 12

    def test_one_and_any_number(self) -> None:
        assert multiply(1, 99) == 99

    def test_large_positive_integers(self) -> None:
        assert multiply(100, 200) == 20000


class TestMultiplyNegativeNumbers:
    def test_two_negative_integers(self) -> None:
        assert multiply(-3, -4) == 12

    def test_negative_times_positive(self) -> None:
        assert multiply(-5, 6) == -30

    def test_positive_times_negative(self) -> None:
        assert multiply(7, -8) == -56


class TestMultiplyZero:
    def test_zero_times_positive(self) -> None:
        assert multiply(0, 5) == 0

    def test_positive_times_zero(self) -> None:
        assert multiply(5, 0) == 0

    def test_zero_times_zero(self) -> None:
        assert multiply(0, 0) == 0

    def test_zero_times_negative(self) -> None:
        assert multiply(0, -7) == 0


class TestMultiplyFloats:
    def test_two_positive_floats(self) -> None:
        assert multiply(2.5, 4.0) == 10.0

    def test_float_precision(self) -> None:
        result = multiply(0.1, 0.2)
        assert abs(result - 0.02) < 1e-10

    def test_negative_float(self) -> None:
        assert multiply(-1.5, 2.0) == -3.0


class TestMultiplyMixedInputs:
    def test_int_and_float(self) -> None:
        assert multiply(3, 2.5) == 7.5

    def test_float_and_int(self) -> None:
        assert multiply(4.0, 5) == 20.0

    def test_negative_int_and_positive_float(self) -> None:
        assert multiply(-2, 3.5) == -7.0

    def test_positive_int_and_negative_float(self) -> None:
        assert multiply(4, -0.5) == -2.0
