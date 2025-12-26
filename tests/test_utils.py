"""Shared test utilities for filtarr tests.

This module contains utilities for properly mocking async functions
to avoid 'coroutine never awaited' warnings in tests.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock


class CreateTaskMock:
    """Mock for asyncio.create_task that properly handles coroutines.

    This mock closes any coroutine passed to it to avoid 'coroutine never awaited'
    warnings, and tracks the returned mock task objects.
    """

    def __init__(self) -> None:
        self.tasks: list[MagicMock] = []
        self.call_count = 0

    def __call__(self, coro: Any) -> MagicMock:
        """Handle a call to create_task, closing the coroutine and returning a mock task."""
        # Close the coroutine to prevent 'never awaited' warnings
        coro.close()
        mock_task = MagicMock()
        mock_task.add_done_callback = MagicMock()
        self.tasks.append(mock_task)
        self.call_count += 1
        return mock_task

    def assert_called_once(self) -> None:
        """Assert that create_task was called exactly once."""
        if self.call_count != 1:
            msg = (
                f"Expected 'create_task' to have been called once. Called {self.call_count} times."
            )
            raise AssertionError(msg)

    @property
    def last_task(self) -> MagicMock:
        """Return the last mock task that was created."""
        if not self.tasks:
            raise AssertionError("No tasks were created")
        return self.tasks[-1]


def create_asyncio_run_mock(return_value: Any) -> MagicMock:
    """Create a mock for asyncio.run that properly handles coroutines.

    This mock closes any coroutine passed to it to avoid 'coroutine never awaited'
    warnings, and returns the provided return value.
    """

    def side_effect(coro: Any) -> Any:
        # Close the coroutine to prevent 'never awaited' warnings
        coro.close()
        return return_value

    return MagicMock(side_effect=side_effect)
