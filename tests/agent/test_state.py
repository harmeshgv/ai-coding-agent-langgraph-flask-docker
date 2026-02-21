"""Tests for agent state enums and utilities."""

from app.agent.state import TaskType


class TestTaskTypeFromString:
    """Tests for TaskType.from_string."""

    def test_from_string_coding(self):
        assert TaskType.from_string("coding") == TaskType.CODING

    def test_from_string_bugfixing(self):
        assert TaskType.from_string("bugfixing") == TaskType.BUGFIXING

    def test_from_string_analyzing(self):
        assert TaskType.from_string("analyzing") == TaskType.ANALYZING

    def test_from_string_unknown(self):
        assert TaskType.from_string("unknown") == TaskType.UNKNOWN

    def test_from_string_normalizes_whitespace_and_case(self):
        assert TaskType.from_string("  CODING  ") == TaskType.CODING

    def test_from_string_uppercase(self):
        assert TaskType.from_string("BUGFIXING") == TaskType.BUGFIXING

    def test_from_string_mixed_case(self):
        assert TaskType.from_string("Analyzing") == TaskType.ANALYZING

    def test_from_string_unrecognized_returns_unknown(self):
        assert TaskType.from_string("refactoring") == TaskType.UNKNOWN

    def test_from_string_empty_returns_unknown(self):
        assert TaskType.from_string("") == TaskType.UNKNOWN

    def test_from_string_whitespace_only_returns_unknown(self):
        assert TaskType.from_string("   ") == TaskType.UNKNOWN
