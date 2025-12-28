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
