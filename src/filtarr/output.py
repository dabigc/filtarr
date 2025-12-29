"""Output formatting utilities for CLI commands."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime


@dataclass
class OutputFormatter:
    """Formats output lines with optional timestamps.

    Attributes:
        timestamps: Whether to prefix lines with timestamps.
    """

    timestamps: bool = True

    # Collected warnings and errors for summary
    warnings: list[str] = field(default_factory=list)
    errors: list[tuple[str, str]] = field(default_factory=list)

    def format_line(self, message: str) -> str:
        """Format a message line with optional timestamp.

        Args:
            message: The message to format.

        Returns:
            Formatted message, optionally prefixed with timestamp.
        """
        if self.timestamps:
            ts = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
            return f"[{ts}] {message}"
        return message

    def format_warning(self, message: str) -> str:
        """Format a warning message.

        Args:
            message: The warning message.

        Returns:
            Formatted warning.
        """
        return f"Warning: {message}"

    def format_error(self, item_name: str, error: str) -> str:
        """Format an error message.

        Args:
            item_name: Name of the item that errored.
            error: The error message.

        Returns:
            Formatted error.
        """
        return f"Error: {item_name} - {error}"

    def add_warning(self, message: str) -> None:
        """Add a warning to be shown in summary."""
        self.warnings.append(message)

    def add_error(self, item_name: str, error: str) -> None:
        """Add an error to be shown in summary."""
        self.errors.append((item_name, error))

    def format_summary(self) -> list[str]:
        """Format collected warnings and errors as summary lines.

        Returns:
            List of summary lines.
        """
        lines: list[str] = []

        if self.warnings:
            # Group similar warnings
            warning_counts: dict[str, int] = {}
            for w in self.warnings:
                warning_counts[w] = warning_counts.get(w, 0) + 1

            lines.append("")
            lines.append(f"Warnings ({len(self.warnings)}):")
            for warning, count in warning_counts.items():
                if count > 1:
                    lines.append(f"  - {warning} (x{count})")
                else:
                    lines.append(f"  - {warning}")

        if self.errors:
            lines.append("")
            lines.append(f"Errors ({len(self.errors)}):")
            for item_name, error in self.errors:
                lines.append(f"  - {item_name}: {error}")

        return lines
