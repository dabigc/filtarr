"""Tests for state management functionality."""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

from filtarr.state import (
    STATE_VERSION,
    BatchProgress,
    CheckRecord,
    StateFile,
    StateManager,
)


class TestBatchProgress:
    """Tests for BatchProgress dataclass."""

    def test_processed_count(self) -> None:
        """Should return count of processed IDs."""
        progress = BatchProgress(
            batch_id="test-batch",
            item_type="movie",
            total_items=10,
            processed_ids={1, 2, 3},
        )
        assert progress.processed_count == 3

    def test_remaining_count(self) -> None:
        """Should return remaining items count."""
        progress = BatchProgress(
            batch_id="test-batch",
            item_type="movie",
            total_items=10,
            processed_ids={1, 2, 3},
        )
        assert progress.remaining_count == 7

    def test_mark_processed(self) -> None:
        """Should add ID to processed set."""
        progress = BatchProgress(
            batch_id="test-batch",
            item_type="movie",
            total_items=10,
        )
        progress.mark_processed(5)
        assert 5 in progress.processed_ids
        assert progress.processed_count == 1

    def test_is_processed(self) -> None:
        """Should check if ID is in processed set."""
        progress = BatchProgress(
            batch_id="test-batch",
            item_type="movie",
            total_items=10,
            processed_ids={1, 2, 3},
        )
        assert progress.is_processed(1) is True
        assert progress.is_processed(5) is False

    def test_to_dict(self) -> None:
        """Should serialize to dictionary."""
        started_at = datetime(2024, 1, 15, 12, 0, 0, tzinfo=UTC)
        progress = BatchProgress(
            batch_id="test-batch",
            item_type="movie",
            total_items=10,
            processed_ids={1, 2, 3},
            started_at=started_at,
        )
        result = progress.to_dict()

        assert result["batch_id"] == "test-batch"
        assert result["item_type"] == "movie"
        assert result["total_items"] == 10
        assert set(result["processed_ids"]) == {1, 2, 3}
        assert result["started_at"] == "2024-01-15T12:00:00+00:00"

    def test_from_dict_valid(self) -> None:
        """Should deserialize from valid dictionary."""
        data = {
            "batch_id": "test-batch",
            "item_type": "series",
            "total_items": 20,
            "processed_ids": [5, 10, 15],
            "started_at": "2024-01-15T12:00:00+00:00",
        }
        progress = BatchProgress.from_dict(data)

        assert progress.batch_id == "test-batch"
        assert progress.item_type == "series"
        assert progress.total_items == 20
        assert progress.processed_ids == {5, 10, 15}

    def test_from_dict_missing_fields(self) -> None:
        """Should handle missing fields with defaults."""
        data = {}
        progress = BatchProgress.from_dict(data)

        assert progress.batch_id == ""
        assert progress.item_type == "mixed"
        assert progress.total_items == 0
        assert progress.processed_ids == set()

    def test_from_dict_invalid_item_type(self) -> None:
        """Should default to 'mixed' for invalid item_type."""
        data = {"item_type": "invalid"}
        progress = BatchProgress.from_dict(data)
        assert progress.item_type == "mixed"

    def test_from_dict_invalid_processed_ids(self) -> None:
        """Should handle non-list processed_ids."""
        data = {"processed_ids": "not a list"}
        progress = BatchProgress.from_dict(data)
        assert progress.processed_ids == set()

    def test_from_dict_invalid_total_items(self) -> None:
        """Should handle non-numeric total_items."""
        data = {"total_items": "not a number"}
        progress = BatchProgress.from_dict(data)
        assert progress.total_items == 0

    def test_from_dict_empty_started_at(self) -> None:
        """Should use current time for empty started_at."""
        data = {"started_at": ""}
        before = datetime.now(UTC)
        progress = BatchProgress.from_dict(data)
        after = datetime.now(UTC)

        assert before <= progress.started_at <= after


class TestCheckRecord:
    """Tests for CheckRecord dataclass."""

    def test_to_dict(self) -> None:
        """Should serialize to dictionary."""
        last_checked = datetime(2024, 1, 15, 12, 0, 0, tzinfo=UTC)
        record = CheckRecord(
            last_checked=last_checked,
            result="available",
            tag_applied="4k-available",
        )
        result = record.to_dict()

        assert result["last_checked"] == "2024-01-15T12:00:00+00:00"
        assert result["result"] == "available"
        assert result["tag_applied"] == "4k-available"

    def test_from_dict_valid(self) -> None:
        """Should deserialize from valid dictionary."""
        data = {
            "last_checked": "2024-01-15T12:00:00+00:00",
            "result": "available",
            "tag_applied": "4k-available",
        }
        record = CheckRecord.from_dict(data)

        assert record.result == "available"
        assert record.tag_applied == "4k-available"

    def test_from_dict_missing_fields(self) -> None:
        """Should handle missing fields with defaults."""
        data = {}
        record = CheckRecord.from_dict(data)

        assert record.result == "unavailable"
        assert record.tag_applied is None

    def test_from_dict_invalid_result(self) -> None:
        """Should default to 'unavailable' for invalid result."""
        data = {"result": "invalid"}
        record = CheckRecord.from_dict(data)
        assert record.result == "unavailable"

    def test_from_dict_empty_last_checked(self) -> None:
        """Should use current time for empty last_checked."""
        data = {"last_checked": ""}
        before = datetime.now(UTC)
        record = CheckRecord.from_dict(data)
        after = datetime.now(UTC)

        assert before <= record.last_checked <= after

    def test_from_dict_non_string_tag_applied(self) -> None:
        """Should handle non-string tag_applied values."""
        data = {"tag_applied": 123}  # Not a string
        record = CheckRecord.from_dict(data)
        assert record.tag_applied is None


class TestStateFile:
    """Tests for StateFile dataclass."""

    def test_make_key(self) -> None:
        """Should create consistent keys for item types."""
        state = StateFile()
        assert state._make_key("movie", 123) == "movie:123"
        assert state._make_key("series", 456) == "series:456"

    def test_record_and_get_check(self) -> None:
        """Should record and retrieve check records."""
        state = StateFile()

        state.record_check(
            item_type="movie",
            item_id=123,
            has_4k=True,
            tag_applied="4k-available",
        )

        record = state.get_check("movie", 123)
        assert record is not None
        assert record.result == "available"
        assert record.tag_applied == "4k-available"

    def test_get_check_not_found(self) -> None:
        """Should return None for missing records."""
        state = StateFile()
        record = state.get_check("movie", 999)
        assert record is None

    def test_get_stale_unavailable_items(self) -> None:
        """Should return items that need rechecking."""
        state = StateFile()
        now = datetime.now(UTC)

        # Old unavailable (should be returned)
        state.checks["movie:1"] = CheckRecord(
            last_checked=now - timedelta(days=10),
            result="unavailable",
            tag_applied=None,
        )
        # Recent unavailable (should not be returned)
        state.checks["movie:2"] = CheckRecord(
            last_checked=now - timedelta(days=1),
            result="unavailable",
            tag_applied=None,
        )
        # Available (should not be returned)
        state.checks["movie:3"] = CheckRecord(
            last_checked=now - timedelta(days=10),
            result="available",
            tag_applied="4k-available",
        )

        stale = state.get_stale_unavailable_items(recheck_days=7)

        assert len(stale) == 1
        assert stale[0] == ("movie", 1)

    def test_to_dict(self) -> None:
        """Should serialize to dictionary."""
        state = StateFile()
        state.record_check("movie", 123, "available", "4k-available")

        result = state.to_dict()

        assert result["version"] == STATE_VERSION
        assert "checks" in result
        assert "movie:123" in result["checks"]

    def test_from_dict_valid(self) -> None:
        """Should deserialize from valid dictionary."""
        data = {
            "version": STATE_VERSION,
            "checks": {
                "movie:123": {
                    "last_checked": datetime.now(UTC).isoformat(),
                    "result": "available",
                    "tag_applied": "4k-available",
                }
            },
        }
        state = StateFile.from_dict(data)

        record = state.get_check("movie", 123)
        assert record is not None
        assert record.result == "available"

    def test_from_dict_preserves_version(self) -> None:
        """Should preserve version from data."""
        data = {
            "version": 999,
            "checks": {"movie:123": {"result": "available"}},
        }
        state = StateFile.from_dict(data)

        # Version is preserved but data is still loaded
        assert state.version == 999
        record = state.get_check("movie", 123)
        assert record is not None

    def test_from_dict_invalid_checks(self) -> None:
        """Should handle non-dict checks field."""
        data = {
            "version": STATE_VERSION,
            "checks": "not a dict",
        }
        state = StateFile.from_dict(data)
        assert state.get_check("movie", 123) is None


class TestStateManager:
    """Tests for StateManager file I/O and operations."""

    def test_init_accepts_path(self, tmp_path: Path) -> None:
        """Should initialize with path."""
        state_path = tmp_path / "state.json"
        manager = StateManager(state_path)
        assert manager.path == state_path

    def test_save_and_load(self, tmp_path: Path) -> None:
        """Should save and load state correctly."""
        state_path = tmp_path / "state.json"
        manager = StateManager(state_path)

        manager.record_check("movie", 123, True, "4k-available")
        manager.save()

        # Load fresh manager
        manager2 = StateManager(state_path)
        record = manager2.get_check("movie", 123)

        assert record is not None
        assert record.result == "available"
        assert record.tag_applied == "4k-available"

    def test_load_missing_file(self, tmp_path: Path) -> None:
        """Should handle missing state file."""
        state_path = tmp_path / "nonexistent.json"
        manager = StateManager(state_path)

        # Should not raise, should start with empty state
        assert manager.get_check("movie", 123) is None

    def test_load_corrupted_json(self, tmp_path: Path) -> None:
        """Should handle corrupted JSON file."""
        state_path = tmp_path / "state.json"
        state_path.write_text("{ invalid json }")

        manager = StateManager(state_path)

        # Should not raise, should start with empty state
        assert manager.get_check("movie", 123) is None

    def test_load_non_dict_json_raises(self, tmp_path: Path) -> None:
        """Non-dict JSON content raises AttributeError."""
        state_path = tmp_path / "state.json"
        state_path.write_text('"just a string"')

        manager = StateManager(state_path)
        # Non-dict JSON causes an error during load
        with pytest.raises(AttributeError):
            manager.get_check("movie", 123)

    def test_record_check_has_4k_true(self, tmp_path: Path) -> None:
        """Should record 'available' for has_4k=True."""
        state_path = tmp_path / "state.json"
        manager = StateManager(state_path)

        manager.record_check("movie", 123, True, "4k-available")
        record = manager.get_check("movie", 123)

        assert record is not None
        assert record.result == "available"

    def test_record_check_has_4k_false(self, tmp_path: Path) -> None:
        """Should record 'unavailable' for has_4k=False."""
        state_path = tmp_path / "state.json"
        manager = StateManager(state_path)

        manager.record_check("movie", 123, False, "4k-unavailable")
        record = manager.get_check("movie", 123)

        assert record is not None
        assert record.result == "unavailable"

    def test_get_stale_unavailable_items(self, tmp_path: Path) -> None:
        """Should return stale unavailable items from state."""
        state_path = tmp_path / "state.json"
        manager = StateManager(state_path)

        # Record a check that will be stale by setting timestamp manually
        state = manager.load()
        state.checks["movie:1"] = CheckRecord(
            last_checked=datetime.now(UTC) - timedelta(days=10),
            result="unavailable",
            tag_applied=None,
        )
        manager.save()

        stale = manager.get_stale_unavailable_items(recheck_days=7)
        assert ("movie", 1) in stale

    def test_start_batch(self, tmp_path: Path) -> None:
        """Should create new batch progress."""
        state_path = tmp_path / "state.json"
        manager = StateManager(state_path)

        progress = manager.start_batch("test-batch-id", "movie", 100)

        assert progress.batch_id == "test-batch-id"
        assert progress.item_type == "movie"
        assert progress.total_items == 100
        assert progress.processed_count == 0

    def test_get_batch_progress(self, tmp_path: Path) -> None:
        """Should retrieve batch progress."""
        state_path = tmp_path / "state.json"
        manager = StateManager(state_path)

        manager.start_batch("test-batch", "series", 50)
        progress = manager.get_batch_progress()

        assert progress is not None
        assert progress.item_type == "series"
        assert progress.total_items == 50

    def test_get_batch_progress_none(self, tmp_path: Path) -> None:
        """Should return None when no batch in progress."""
        state_path = tmp_path / "state.json"
        manager = StateManager(state_path)

        progress = manager.get_batch_progress()
        assert progress is None

    def test_update_batch_progress(self, tmp_path: Path) -> None:
        """Should update batch progress with processed ID."""
        state_path = tmp_path / "state.json"
        manager = StateManager(state_path)

        manager.start_batch("test-batch", "movie", 100)
        manager.update_batch_progress(42)

        progress = manager.get_batch_progress()
        assert progress is not None
        assert 42 in progress.processed_ids

    def test_clear_batch_progress(self, tmp_path: Path) -> None:
        """Should clear batch progress."""
        state_path = tmp_path / "state.json"
        manager = StateManager(state_path)

        manager.start_batch("test-batch", "movie", 100)
        manager.clear_batch_progress()

        progress = manager.get_batch_progress()
        assert progress is None

    def test_batch_progress_persists(self, tmp_path: Path) -> None:
        """Should persist batch progress across saves/loads."""
        state_path = tmp_path / "state.json"
        manager = StateManager(state_path)

        manager.start_batch("test-batch", "movie", 100)
        manager.update_batch_progress(1)
        manager.update_batch_progress(2)
        manager.save()

        # Load fresh manager
        manager2 = StateManager(state_path)
        progress = manager2.get_batch_progress()

        assert progress is not None
        assert progress.processed_ids == {1, 2}

    def test_save_atomic(self, tmp_path: Path) -> None:
        """Should save atomically (via tmp file rename)."""
        state_path = tmp_path / "state.json"
        manager = StateManager(state_path)

        manager.record_check("movie", 123, True, "4k-available")
        manager.save()

        # Verify file exists and is valid JSON
        content = json.loads(state_path.read_text())
        assert "checks" in content

    def test_save_error_handling(self, tmp_path: Path) -> None:
        """Should handle save errors gracefully."""
        state_path = tmp_path / "state.json"
        manager = StateManager(state_path)

        # Make path unwritable
        with patch.object(Path, "write_text", side_effect=PermissionError("denied")):
            # Should not raise
            manager.save()


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_empty_state_file(self, tmp_path: Path) -> None:
        """Should handle empty state file."""
        state_path = tmp_path / "state.json"
        state_path.write_text("")

        manager = StateManager(state_path)
        assert manager.get_check("movie", 123) is None

    def test_null_json_content_raises(self, tmp_path: Path) -> None:
        """Null JSON content raises AttributeError."""
        state_path = tmp_path / "state.json"
        state_path.write_text("null")

        manager = StateManager(state_path)
        with pytest.raises(AttributeError):
            manager.get_check("movie", 123)

    def test_array_json_content_raises(self, tmp_path: Path) -> None:
        """Array JSON content raises AttributeError."""
        state_path = tmp_path / "state.json"
        state_path.write_text("[]")

        manager = StateManager(state_path)
        with pytest.raises(AttributeError):
            manager.get_check("movie", 123)

    def test_batch_progress_with_float_ids(self) -> None:
        """Should handle float IDs in batch progress deserialization."""
        data = {
            "batch_id": "test",
            "item_type": "movie",
            "total_items": 10.5,  # Float instead of int
            "processed_ids": [1.0, 2.0, 3.0],  # Floats instead of ints
        }
        progress = BatchProgress.from_dict(data)

        assert progress.total_items == 10
        assert progress.processed_ids == {1, 2, 3}

    def test_check_record_various_result_values(self) -> None:
        """Should handle various result values."""
        # Valid values
        for result in ["available", "unavailable"]:
            data = {"result": result}
            record = CheckRecord.from_dict(data)
            assert record.result == result

        # Invalid values default to unavailable
        for result in ["", "unknown", None, 123, True]:
            data = {"result": result}
            record = CheckRecord.from_dict(data)
            assert record.result == "unavailable"

    def test_state_file_many_records(self, tmp_path: Path) -> None:
        """Should handle many records efficiently."""
        state_path = tmp_path / "state.json"
        manager = StateManager(state_path)

        # Add many records
        for i in range(1000):
            manager.record_check("movie", i, i % 2 == 0, None)

        manager.save()

        # Reload and verify
        manager2 = StateManager(state_path)
        for i in range(1000):
            record = manager2.get_check("movie", i)
            assert record is not None
            expected = "available" if i % 2 == 0 else "unavailable"
            assert record.result == expected

    def test_batch_progress_item_types(self) -> None:
        """Should handle all valid item types."""
        for item_type in ["movie", "series", "mixed"]:
            progress = BatchProgress(
                batch_id="test",
                item_type=item_type,  # type: ignore[arg-type]
                total_items=10,
            )
            assert progress.item_type == item_type

    def test_concurrent_batch_updates(self, tmp_path: Path) -> None:
        """Should handle rapid batch updates."""
        state_path = tmp_path / "state.json"
        manager = StateManager(state_path)

        manager.start_batch("test-batch", "movie", 1000)

        # Rapid updates
        for i in range(100):
            manager.update_batch_progress(i)

        progress = manager.get_batch_progress()
        assert progress is not None
        assert progress.processed_count == 100

    def test_stale_items_boundary_conditions(self, tmp_path: Path) -> None:
        """Should handle boundary conditions for stale item detection."""
        state_path = tmp_path / "state.json"
        manager = StateManager(state_path)
        now = datetime.now(UTC)

        state = manager.load()
        # Exactly at boundary (7 days)
        state.checks["movie:1"] = CheckRecord(
            last_checked=now - timedelta(days=7),
            result="unavailable",
            tag_applied=None,
        )
        # Just under boundary
        state.checks["movie:2"] = CheckRecord(
            last_checked=now - timedelta(days=6, hours=23),
            result="unavailable",
            tag_applied=None,
        )
        # Just over boundary
        state.checks["movie:3"] = CheckRecord(
            last_checked=now - timedelta(days=7, minutes=1),
            result="unavailable",
            tag_applied=None,
        )
        manager.save()

        stale = manager.get_stale_unavailable_items(recheck_days=7)

        # Items 1 and 3 should be stale (>= 7 days)
        stale_ids = [item_id for _, item_id in stale]
        assert 1 in stale_ids
        assert 3 in stale_ids
        assert 2 not in stale_ids


class TestIsRecentlyChecked:
    """Tests for StateManager.is_recently_checked method."""

    def test_returns_false_when_item_not_in_state(self, tmp_path: Path) -> None:
        """Should return False when item has never been checked."""
        state_path = tmp_path / "state.json"
        manager = StateManager(state_path)

        result = manager.is_recently_checked("movie", 999, ttl_hours=24)

        assert result is False

    def test_returns_false_when_check_is_older_than_ttl(self, tmp_path: Path) -> None:
        """Should return False when check is older than TTL period."""
        state_path = tmp_path / "state.json"
        manager = StateManager(state_path)

        # Record a check from 48 hours ago
        state = manager.load()
        state.checks["movie:123"] = CheckRecord(
            last_checked=datetime.now(UTC) - timedelta(hours=48),
            result="available",
            tag_applied="4k-available",
        )
        manager.save()

        result = manager.is_recently_checked("movie", 123, ttl_hours=24)

        assert result is False

    def test_returns_true_when_check_is_within_ttl(self, tmp_path: Path) -> None:
        """Should return True when check is within TTL period."""
        state_path = tmp_path / "state.json"
        manager = StateManager(state_path)

        # Record a check from 1 hour ago
        state = manager.load()
        state.checks["movie:123"] = CheckRecord(
            last_checked=datetime.now(UTC) - timedelta(hours=1),
            result="available",
            tag_applied="4k-available",
        )
        manager.save()

        result = manager.is_recently_checked("movie", 123, ttl_hours=24)

        assert result is True

    def test_returns_false_when_ttl_is_zero(self, tmp_path: Path) -> None:
        """Should return False when TTL is 0 (disabled)."""
        state_path = tmp_path / "state.json"
        manager = StateManager(state_path)

        # Record a recent check
        manager.record_check("movie", 123, True, "4k-available")

        result = manager.is_recently_checked("movie", 123, ttl_hours=0)

        assert result is False

    def test_handles_timezone_naive_datetime(self, tmp_path: Path) -> None:
        """Should handle timezone-naive datetimes for backwards compatibility."""
        state_path = tmp_path / "state.json"
        manager = StateManager(state_path)

        # Record a check with timezone-naive datetime (simulating old state files)
        state = manager.load()
        state.checks["movie:123"] = CheckRecord(
            last_checked=datetime.now().replace(tzinfo=None) - timedelta(hours=1),
            result="available",
            tag_applied="4k-available",
        )
        manager.save()

        result = manager.is_recently_checked("movie", 123, ttl_hours=24)

        assert result is True


class TestGetCachedResult:
    """Tests for StateManager.get_cached_result method."""

    def test_returns_none_when_item_not_in_state(self, tmp_path: Path) -> None:
        """Should return None when item has never been checked."""
        state_path = tmp_path / "state.json"
        manager = StateManager(state_path)

        result = manager.get_cached_result("movie", 999, ttl_hours=24)

        assert result is None

    def test_returns_none_when_check_is_older_than_ttl(self, tmp_path: Path) -> None:
        """Should return None when check is older than TTL period."""
        state_path = tmp_path / "state.json"
        manager = StateManager(state_path)

        # Record a check from 48 hours ago
        state = manager.load()
        state.checks["movie:123"] = CheckRecord(
            last_checked=datetime.now(UTC) - timedelta(hours=48),
            result="available",
            tag_applied="4k-available",
        )
        manager.save()

        result = manager.get_cached_result("movie", 123, ttl_hours=24)

        assert result is None

    def test_returns_check_record_when_within_ttl(self, tmp_path: Path) -> None:
        """Should return CheckRecord when check is within TTL period."""
        state_path = tmp_path / "state.json"
        manager = StateManager(state_path)

        # Record a check from 1 hour ago
        state = manager.load()
        state.checks["movie:123"] = CheckRecord(
            last_checked=datetime.now(UTC) - timedelta(hours=1),
            result="available",
            tag_applied="4k-available",
        )
        manager.save()

        result = manager.get_cached_result("movie", 123, ttl_hours=24)

        assert result is not None
        assert result.result == "available"
        assert result.tag_applied == "4k-available"

    def test_returns_none_when_ttl_is_zero(self, tmp_path: Path) -> None:
        """Should return None when TTL is 0 (disabled)."""
        state_path = tmp_path / "state.json"
        manager = StateManager(state_path)

        # Record a recent check
        manager.record_check("movie", 123, True, "4k-available")

        result = manager.get_cached_result("movie", 123, ttl_hours=0)

        assert result is None


class TestEnsureInitialized:
    """Tests for StateManager.ensure_initialized method."""

    def test_creates_state_file_if_not_exists(self, tmp_path: Path) -> None:
        """Should create state file if it doesn't exist."""
        state_path = tmp_path / "subdir" / "state.json"
        manager = StateManager(state_path)

        assert not state_path.exists()

        manager.ensure_initialized()

        assert state_path.exists()
        # Verify file contains valid JSON
        content = json.loads(state_path.read_text())
        assert "version" in content
        assert content["version"] == STATE_VERSION

    def test_works_when_state_file_already_exists(self, tmp_path: Path) -> None:
        """Should work correctly when state file already exists."""
        state_path = tmp_path / "state.json"
        manager = StateManager(state_path)

        # Create existing state with some data
        manager.record_check("movie", 123, True, "4k-available")
        manager.save()

        # Clear cached state
        manager2 = StateManager(state_path)

        # Should not raise and should preserve existing data
        manager2.ensure_initialized()

        assert state_path.exists()
        record = manager2.get_check("movie", 123)
        assert record is not None
        assert record.result == "available"
