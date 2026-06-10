"""Unit tests for strength router helper functions."""

import pytest

from app.routers.strength import _epley_1rm, _parse_set


class TestEpley1RM:
    def test_single_rep_returns_weight(self):
        assert _epley_1rm(100.0, 1) == 100.0

    def test_five_reps(self):
        # 100 * (1 + 5/30) = 100 * 1.1667 = 116.7
        result = _epley_1rm(100.0, 5)
        assert result == pytest.approx(116.7, abs=0.1)

    def test_ten_reps(self):
        # 80 * (1 + 10/30) = 80 * 1.333 = 106.7
        result = _epley_1rm(80.0, 10)
        assert result == pytest.approx(106.7, abs=0.1)

    def test_zero_weight(self):
        assert _epley_1rm(0.0, 5) == 0.0

    def test_result_is_rounded_to_one_decimal(self):
        result = _epley_1rm(102.5, 3)
        assert result == round(result, 1)


class TestParseSet:
    def test_valid_set_with_weight_kg(self):
        s = {"weight_kg": 100.0, "reps": 5, "type": "normal"}
        result = _parse_set(s)
        assert result is not None
        assert result["weight_kg"] == 100.0
        assert result["reps"] == 5
        assert result["type"] == "normal"

    def test_valid_set_with_weight_fallback(self):
        # Hevy sometimes uses "weight" instead of "weight_kg"
        s = {"weight": 80.0, "reps": 8}
        result = _parse_set(s)
        assert result is not None
        assert result["weight_kg"] == 80.0

    def test_missing_weight_returns_none(self):
        assert _parse_set({"reps": 5}) is None

    def test_missing_reps_returns_none(self):
        assert _parse_set({"weight_kg": 100.0}) is None

    def test_both_missing_returns_none(self):
        assert _parse_set({}) is None

    def test_string_values_are_cast(self):
        s = {"weight_kg": "100.0", "reps": "5"}
        result = _parse_set(s)
        assert result is not None
        assert result["weight_kg"] == 100.0
        assert result["reps"] == 5

    def test_invalid_string_returns_none(self):
        assert _parse_set({"weight_kg": "heavy", "reps": 5}) is None

    def test_default_type_is_normal(self):
        s = {"weight_kg": 50.0, "reps": 3}
        result = _parse_set(s)
        assert result is not None
        assert result["type"] == "normal"

    def test_rpe_is_preserved(self):
        s = {"weight_kg": 90.0, "reps": 3, "rpe": 8.5}
        result = _parse_set(s)
        assert result is not None
        assert result["rpe"] == 8.5

    def test_weight_is_rounded(self):
        s = {"weight_kg": 100.123456, "reps": 5}
        result = _parse_set(s)
        assert result is not None
        assert result["weight_kg"] == 100.12
