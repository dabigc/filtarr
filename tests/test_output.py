"""Tests for output formatting utilities."""

from filtarr.output import OutputFormatter


def test_output_formatter_with_timestamps() -> None:
    """OutputFormatter should add timestamps when enabled."""
    formatter = OutputFormatter(timestamps=True)
    output = formatter.format_line("Test message")
    # Should have timestamp prefix like [2025-12-28 20:00:00]
    assert output.startswith("[")
    assert "] Test message" in output


def test_output_formatter_without_timestamps() -> None:
    """OutputFormatter should not add timestamps when disabled."""
    formatter = OutputFormatter(timestamps=False)
    output = formatter.format_line("Test message")
    assert output == "Test message"
    assert not output.startswith("[")


def test_output_formatter_warning() -> None:
    """OutputFormatter should format warnings."""
    formatter = OutputFormatter(timestamps=False)
    output = formatter.format_warning("Slow request (27s)")
    assert output == "Warning: Slow request (27s)"


def test_output_formatter_error() -> None:
    """OutputFormatter should format errors."""
    formatter = OutputFormatter(timestamps=False)
    output = formatter.format_error("The Matrix (123)", "404 Not Found")
    assert output == "Error: The Matrix (123) - 404 Not Found"


def test_output_formatter_add_warning() -> None:
    """OutputFormatter should accumulate warnings."""
    formatter = OutputFormatter(timestamps=False)
    formatter.add_warning("Slow request")
    formatter.add_warning("Another warning")
    assert len(formatter.warnings) == 2
    assert "Slow request" in formatter.warnings
    assert "Another warning" in formatter.warnings


def test_output_formatter_add_error() -> None:
    """OutputFormatter should accumulate errors."""
    formatter = OutputFormatter(timestamps=False)
    formatter.add_error("Movie 1", "Not found")
    formatter.add_error("Movie 2", "Timeout")
    assert len(formatter.errors) == 2
    assert ("Movie 1", "Not found") in formatter.errors
    assert ("Movie 2", "Timeout") in formatter.errors


def test_output_formatter_summary_empty() -> None:
    """OutputFormatter should return empty list when no warnings or errors."""
    formatter = OutputFormatter(timestamps=False)
    summary = formatter.format_summary()
    assert summary == []


def test_output_formatter_summary_with_warnings() -> None:
    """OutputFormatter should format warnings in summary."""
    formatter = OutputFormatter(timestamps=False)
    formatter.add_warning("Slow request")
    formatter.add_warning("Connection timeout")
    summary = formatter.format_summary()
    assert "Warnings (2):" in summary
    assert "  - Slow request" in summary
    assert "  - Connection timeout" in summary


def test_output_formatter_summary_groups_duplicate_warnings() -> None:
    """OutputFormatter should group identical warnings in summary."""
    formatter = OutputFormatter(timestamps=False)
    formatter.add_warning("Slow request")
    formatter.add_warning("Slow request")
    formatter.add_warning("Slow request")
    summary = formatter.format_summary()
    assert "Warnings (3):" in summary
    # Find the line with "Slow request" and verify it has (x3)
    warning_lines = [line for line in summary if "Slow request" in line]
    assert len(warning_lines) == 1
    assert "(x3)" in warning_lines[0]


def test_output_formatter_summary_with_errors() -> None:
    """OutputFormatter should format errors in summary."""
    formatter = OutputFormatter(timestamps=False)
    formatter.add_error("The Matrix (123)", "404 Not Found")
    formatter.add_error("Inception (456)", "Connection timeout")
    summary = formatter.format_summary()
    assert "Errors (2):" in summary
    assert "  - The Matrix (123): 404 Not Found" in summary
    assert "  - Inception (456): Connection timeout" in summary


def test_output_formatter_summary_with_warnings_and_errors() -> None:
    """OutputFormatter should format both warnings and errors in summary."""
    formatter = OutputFormatter(timestamps=False)
    formatter.add_warning("Slow request")
    formatter.add_error("Movie 1", "Not found")
    summary = formatter.format_summary()
    assert "Warnings (1):" in summary
    assert "Errors (1):" in summary
