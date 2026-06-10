"""Unit tests for workouts router helper functions."""

import pytest

from app.routers.workouts import _parse_workout, _tsb_status


class TestTSBStatus:
    @pytest.mark.parametrize("tsb,expected", [
        (11.0, "Fresh"),
        (1.0, "Neutral"),
        (-5.0, "Tired"),
        (-20.0, "Very Tired"),
        (-30.0, "Exhausted"),
    ])
    def test_categories(self, tsb, expected):
        assert _tsb_status(tsb) == expected


class TestParseWorkout:
    def test_complete_workout(self):
        raw = {
            "workoutId": 99,
            "title": "Threshold Intervals",
            "workoutDay": "2024-03-15T00:00:00",
            "workoutTypeValueId": "Bike",
            "tssPlanned": 90.0,
            "tssActual": 88.5,
            "distancePlanned": 50000,
            "distanceActual": 49800,
            "totalTimePlanned": 5400,
            "totalTime": 5350,
            "description": "4x10 at threshold",
            "coachComments": "Keep cadence high",
            "athleteComments": "Felt good",
        }
        result = _parse_workout(raw)
        assert result["id"] == "99"
        assert result["title"] == "Threshold Intervals"
        assert result["date"] == "2024-03-15"
        assert result["type"] == "bike"
        assert result["tss_planned"] == 90.0
        assert result["tss_actual"] == 88.5
        assert result["completed"] is True
        assert result["description"] == "4x10 at threshold"
        assert result["coach_comments"] == "Keep cadence high"
        assert result["athlete_comments"] == "Felt good"

    def test_planned_only_is_not_completed(self):
        raw = {"workoutId": 1, "tssPlanned": 80.0, "workoutDay": "2024-01-01T00:00:00"}
        result = _parse_workout(raw)
        assert result["completed"] is False

    def test_actual_tss_marks_as_completed(self):
        raw = {"workoutId": 2, "tssActual": 55.0, "workoutDay": "2024-01-01T00:00:00"}
        result = _parse_workout(raw)
        assert result["completed"] is True

    def test_empty_workout_does_not_crash(self):
        result = _parse_workout({})
        assert result["id"] == ""
        assert result["date"] == ""
        assert result["completed"] is False

    def test_type_is_lowercased(self):
        raw = {"workoutId": 1, "workoutTypeValueId": "RUN", "workoutDay": "2024-01-01T00:00:00"}
        result = _parse_workout(raw)
        assert result["type"] == "run"
