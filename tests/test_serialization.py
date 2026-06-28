"""Tests for serialization safety (sanitize function)."""

from datetime import datetime, timezone

import pytest

from memlink.serialization import sanitize


class TestSanitize:
    def test_none_passthrough(self):
        assert sanitize(None) is None

    def test_bool_passthrough(self):
        assert sanitize(True) is True
        assert sanitize(False) is False

    def test_int_passthrough(self):
        assert sanitize(42) == 42

    def test_float_passthrough(self):
        assert sanitize(3.14) == 3.14

    def test_str_passthrough(self):
        assert sanitize("hello") == "hello"

    def test_datetime_to_iso(self):
        dt = datetime(2024, 1, 15, 8, 0, 0, tzinfo=timezone.utc)
        result = sanitize(dt)
        assert result == "2024-01-15T08:00:00+00:00"

    def test_nested_dict(self):
        data = {"a": {"b": 1}}
        assert sanitize(data) == {"a": {"b": 1}}

    def test_list(self):
        assert sanitize([1, "a", None]) == [1, "a", None]

    def test_set_to_sorted_list(self):
        result = sanitize({"tags": {3, 1, 2}})
        assert result == {"tags": [1, 2, 3]}

    def test_frozenset_to_sorted_list(self):
        s = frozenset(["z", "a", "m"])
        assert sanitize(s) == ["a", "m", "z"]

    def test_tuple_to_list(self):
        assert sanitize((1, 2)) == [1, 2]

    def test_circular_reference_detected(self):
        data: dict = {"ref": None}
        data["ref"] = data
        with pytest.raises(ValueError, match="Circular reference"):
            sanitize(data)

    def test_nesting_too_deep(self):
        data: dict = {}
        current = data
        for _ in range(150):
            current["nested"] = {}
            current = current["nested"]
        with pytest.raises(ValueError, match="nesting exceeds"):
            sanitize(data)

    def test_unknown_type_to_string(self):
        class Custom:
            def __str__(self) -> str:
                return "CustomObj"

        with pytest.warns(UserWarning, match="Non-serializable type"):
            result = sanitize(Custom())
        assert result == "CustomObj"

    def test_nested_datetime(self):
        data = {"created": datetime(2024, 6, 28, 10, 0, 0, tzinfo=timezone.utc)}
        result = sanitize(data)
        assert result == {"created": "2024-06-28T10:00:00+00:00"}

    def test_mixed_list_with_set(self):
        result = sanitize([3, {1, 2}, "hello"])
        assert result == [3, [1, 2], "hello"]
