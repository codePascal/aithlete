"""Unit tests for dashboard router helper functions."""

import pytest

from app.routers.dashboard import (
    _hevy_duration,
    _hevy_workout_to_summary,
    _tp_workout_to_summary,
    _tsb_status,
)


class TestTSBStatus:
    @pytest.mark.parametrize("tsb,expected", [
        (30.0, "Very Fresh"),
        (25.1, "Very Fresh"),
        (25.0, "Fresh"),
        (10.1, "Fresh"),
        (10.0, "Neutral"),
        (0.1, "Neutral"),
        (0.0, "Tired"),
        (-9.9, "Tired"),
        (-10.0, "Very Tired"),
        (-24.9, "Very Tired"),
        (-25.0, "Exhausted"),
        (-50.0, "Exhausted"),
    ])
    def test_tsb_boundaries(self, tsb, expected):
        assert _tsb_status(tsb) == expected


class TestTPWorkoutToSummary:
    def test_basic_workout(self):
        raw = {
            "workoutId": 42,
            "title": "Long Run",
            "workoutDay": "2024-03-15T00:00:00",
            "workoutTypeValueId": "Run",
            "tssPlanned": 120.0,
            "tssActual": 115.5,
            "totalTime": 3600,
        }
        result = _tp_workout_to_summary(raw)
        assert result["source"] == "trainingpeaks"
        assert result["id"] == "42"
        assert result["title"] == "Long Run"
        assert result["date"] == "2024-03-15"
        assert result["type"] == "run"
        assert result["tss_planned"] == 120.0
        assert result["tss_actual"] == 115.5
        assert result["duration_minutes"] == 60.0
        assert result["completed"] is True

    def test_planned_only_workout(self):
        raw = {"workoutId": 1, "tssPlanned": 80.0, "workoutDay": "2024-03-15T00:00:00"}
        result = _tp_workout_to_summary(raw)
        assert result["completed"] is False
        assert result["tss_actual"] is None

    def test_missing_title_falls_back_to_type(self):
        raw = {"workoutId": 1, "workoutTypeValueId": "Bike", "workoutDay": "2024-03-15T00:00:00"}
        result = _tp_workout_to_summary(raw)
        assert result["title"] == "Bike"

    def test_empty_workout_does_not_crash(self):
        result = _tp_workout_to_summary({})
        assert result["source"] == "trainingpeaks"
        assert result["id"] == ""
        assert result["duration_minutes"] == 0.0


class TestHevyWorkoutToSummary:
    def test_basic_workout(self):
        raw = {
            "id": "abc123",
            "title": "Push Day",
            "start_time": "2024-03-15T09:00:00Z",
            "end_time": "2024-03-15T10:05:00Z",
            "exercises": [{"name": "Bench Press"}, {"name": "OHP"}],
        }
        result = _hevy_workout_to_summary(raw)
        assert result["source"] == "hevy"
        assert result["id"] == "abc123"
        assert result["title"] == "Push Day"
        assert result["date"] == "2024-03-15"
        assert result["type"] == "strength"
        assert result["completed"] is True
        assert result["exercise_count"] == 2
        assert result["tss_planned"] is None
        assert result["tss_actual"] is None


class TestHevyDuration:
    def test_standard_duration(self):
        w = {
            "start_time": "2024-03-15T09:00:00Z",
            "end_time": "2024-03-15T10:05:00Z",
        }
        assert _hevy_duration(w) == 65.0

    def test_missing_times_returns_zero(self):
        assert _hevy_duration({}) == 0.0

    def test_malformed_times_returns_zero(self):
        assert _hevy_duration({"start_time": "bad", "end_time": "also bad"}) == 0.0

    def test_sub_minute_duration(self):
        w = {
            "start_time": "2024-03-15T09:00:00Z",
            "end_time": "2024-03-15T09:00:30Z",
        }
        assert _hevy_duration(w) == pytest.approx(0.5, abs=0.01)
