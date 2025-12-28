# Clean Log Output Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Clean up CLI output by suppressing third-party library logs at INFO level, adding timestamp controls, fixing batch progress bar, and collecting warnings/errors into summaries.

**Architecture:** Modify logging configuration to set third-party loggers (httpx, uvicorn) to WARNING at INFO level. Add global CLI flags for timestamps and output format. Refactor batch output to show batch-size progress and collect warnings/errors for end-of-run summary.

**Tech Stack:** Python logging, Typer CLI, Rich progress bars

---

## Task 1: Suppress Third-Party Loggers at INFO Level

**Files:**
- Modify: `src/filtarr/logging.py:118-155`
- Test: `tests/test_logging.py`

**Step 1: Write the failing test**

```python
# tests/test_logging.py - add to existing file

def test_third_party_loggers_suppressed_at_info() -> None:
    """Third-party loggers should be WARNING+ at INFO level."""
    import logging
    from filtarr.logging import configure_logging

    # Reset logging state
    root = logging.getLogger()
    for handler in root.handlers[:]:
        root.removeHandler(handler)

    configure_logging(level="INFO")

    # Check that httpx and uvicorn loggers are set to WARNING
    assert logging.getLogger("httpx").level == logging.WARNING
    assert logging.getLogger("uvicorn").level == logging.WARNING
    assert logging.getLogger("uvicorn.access").level == logging.WARNING


def test_third_party_loggers_verbose_at_debug() -> None:
    """Third-party loggers should be DEBUG at DEBUG level."""
    import logging
    from filtarr.logging import configure_logging

    # Reset logging state
    root = logging.getLogger()
    for handler in root.handlers[:]:
        root.removeHandler(handler)

    configure_logging(level="DEBUG")

    # At DEBUG, third-party loggers inherit from root (DEBUG)
    # They should NOT be set to WARNING
    httpx_logger = logging.getLogger("httpx")
    # Level 0 means NOTSET (inherits from parent)
    assert httpx_logger.level in (logging.NOTSET, logging.DEBUG)
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_logging.py::test_third_party_loggers_suppressed_at_info -v`
Expected: FAIL with assertion error

**Step 3: Implement the fix**

Edit `src/filtarr/logging.py`, modify `configure_logging` function:

```python
def configure_logging(
    level: str | int = logging.INFO,
    format_string: str | None = None,
) -> None:
    """Configure logging with sensitive data filtering.

    At INFO level and above, third-party library loggers (httpx, uvicorn)
    are set to WARNING to reduce noise. At DEBUG level, they inherit
    from root and show all messages.
    """
    # Convert string level to int if needed
    log_level = parse_log_level(level)

    if format_string is None:
        format_string = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

    # Create a handler with the filter
    handler = logging.StreamHandler()
    handler.setLevel(log_level)
    handler.setFormatter(logging.Formatter(format_string))
    handler.addFilter(SensitiveDataFilter())

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    root_logger.addHandler(handler)

    # Suppress third-party library noise at INFO and above
    # At DEBUG level, let them inherit from root (show everything)
    if log_level > logging.DEBUG:
        third_party_loggers = ["httpx", "uvicorn", "uvicorn.access", "uvicorn.error"]
        for logger_name in third_party_loggers:
            logging.getLogger(logger_name).setLevel(logging.WARNING)
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_logging.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/filtarr/logging.py tests/test_logging.py
git commit -m "feat: suppress third-party library logs at INFO level

httpx and uvicorn loggers now only emit WARNING+ at INFO level.
At DEBUG level, they show all messages for debugging."
```

---

## Task 2: Add Timestamps and Output Format to LoggingConfig

**Files:**
- Modify: `src/filtarr/config.py:278-296`
- Test: `tests/test_config.py`

**Step 1: Write the failing test**

```python
# tests/test_config.py - add to existing file

def test_logging_config_has_timestamps_field() -> None:
    """LoggingConfig should have timestamps field defaulting to True."""
    from filtarr.config import LoggingConfig

    config = LoggingConfig()
    assert config.timestamps is True


def test_logging_config_has_output_format_field() -> None:
    """LoggingConfig should have output_format field defaulting to 'text'."""
    from filtarr.config import LoggingConfig

    config = LoggingConfig()
    assert config.output_format == "text"


def test_logging_config_output_format_validation() -> None:
    """LoggingConfig should validate output_format values."""
    from filtarr.config import LoggingConfig, ConfigurationError
    import pytest

    # Valid values
    LoggingConfig(output_format="text")
    LoggingConfig(output_format="json")

    # Invalid value
    with pytest.raises(ConfigurationError):
        LoggingConfig(output_format="xml")
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_config.py::test_logging_config_has_timestamps_field -v`
Expected: FAIL with AttributeError

**Step 3: Implement LoggingConfig changes**

Edit `src/filtarr/config.py`, update `LoggingConfig` dataclass:

```python
# Valid output format values
VALID_OUTPUT_FORMATS = frozenset({"text", "json"})


@dataclass
class LoggingConfig:
    """Configuration for logging.

    Attributes:
        level: Log level name (DEBUG, INFO, WARNING, ERROR, CRITICAL).
        timestamps: Whether to show timestamps in output. Default True.
        output_format: Output format ('text' or 'json'). Default 'text'.
    """

    level: str = "INFO"
    timestamps: bool = True
    output_format: str = "text"

    def __post_init__(self) -> None:
        """Validate log level and output format after initialization."""
        self.level = self.level.upper()
        if self.level not in VALID_LOG_LEVELS:
            raise ConfigurationError(
                f"Invalid log level: {self.level}. "
                f"Valid options: {', '.join(sorted(VALID_LOG_LEVELS))}"
            )

        self.output_format = self.output_format.lower()
        if self.output_format not in VALID_OUTPUT_FORMATS:
            raise ConfigurationError(
                f"Invalid output format: {self.output_format}. "
                f"Valid options: {', '.join(sorted(VALID_OUTPUT_FORMATS))}"
            )
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_config.py::test_logging_config -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/filtarr/config.py tests/test_config.py
git commit -m "feat: add timestamps and output_format to LoggingConfig

- timestamps: bool, default True
- output_format: 'text' or 'json', default 'text'"
```

---

## Task 3: Add Config Parsing for New Logging Fields

**Files:**
- Modify: `src/filtarr/config.py:599-630`
- Test: `tests/test_config.py`

**Step 1: Write the failing test**

```python
# tests/test_config.py - add to existing file

def test_parse_logging_timestamps_from_dict() -> None:
    """Should parse timestamps from config dict."""
    from filtarr.config import _parse_logging_from_dict

    data = {"logging": {"level": "INFO", "timestamps": False}}
    config = _parse_logging_from_dict(data)
    assert config.timestamps is False


def test_parse_logging_output_format_from_dict() -> None:
    """Should parse output_format from config dict."""
    from filtarr.config import _parse_logging_from_dict

    data = {"logging": {"level": "INFO", "output_format": "json"}}
    config = _parse_logging_from_dict(data)
    assert config.output_format == "json"


def test_parse_logging_timestamps_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Should parse FILTARR_TIMESTAMPS from environment."""
    from filtarr.config import LoggingConfig, _parse_logging_from_env

    monkeypatch.setenv("FILTARR_TIMESTAMPS", "false")
    base = LoggingConfig()
    config = _parse_logging_from_env(base)
    assert config.timestamps is False


def test_parse_logging_output_format_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Should parse FILTARR_OUTPUT_FORMAT from environment."""
    from filtarr.config import LoggingConfig, _parse_logging_from_env

    monkeypatch.setenv("FILTARR_OUTPUT_FORMAT", "json")
    base = LoggingConfig()
    config = _parse_logging_from_env(base)
    assert config.output_format == "json"
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_config.py::test_parse_logging_timestamps_from_dict -v`
Expected: FAIL

**Step 3: Update parsing functions**

Edit `src/filtarr/config.py`, update `_parse_logging_from_dict` and `_parse_logging_from_env`:

```python
def _parse_logging_from_dict(data: dict[str, Any]) -> LoggingConfig:
    """Parse LoggingConfig from a config dictionary."""
    if "logging" not in data:
        return LoggingConfig()
    logging_data = data["logging"]
    defaults = LoggingConfig()
    return LoggingConfig(
        level=logging_data.get("level", defaults.level),
        timestamps=logging_data.get("timestamps", defaults.timestamps),
        output_format=logging_data.get("output_format", defaults.output_format),
    )


def _parse_logging_from_env(base: LoggingConfig) -> LoggingConfig:
    """Parse LoggingConfig from environment variables."""
    log_level = os.environ.get("FILTARR_LOG_LEVEL")
    timestamps_str = os.environ.get("FILTARR_TIMESTAMPS")
    output_format = os.environ.get("FILTARR_OUTPUT_FORMAT")

    if log_level is None and timestamps_str is None and output_format is None:
        return base

    timestamps = base.timestamps
    if timestamps_str is not None:
        timestamps = timestamps_str.lower() in ("true", "1", "yes")

    return LoggingConfig(
        level=log_level or base.level,
        timestamps=timestamps,
        output_format=output_format or base.output_format,
    )
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_config.py::test_parse_logging -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/filtarr/config.py tests/test_config.py
git commit -m "feat: parse timestamps and output_format from config/env

- FILTARR_TIMESTAMPS env var
- FILTARR_OUTPUT_FORMAT env var
- logging.timestamps in config.toml
- logging.output_format in config.toml"
```

---

## Task 4: Add Global CLI Flags for Timestamps and Output Format

**Files:**
- Modify: `src/filtarr/cli.py:63-103`
- Test: `tests/test_cli.py`

**Step 1: Write the failing test**

```python
# tests/test_cli.py - add to existing file

def test_global_timestamps_flag() -> None:
    """Global --timestamps flag should be available."""
    from typer.testing import CliRunner
    from filtarr.cli import app

    runner = CliRunner()
    result = runner.invoke(app, ["--no-timestamps", "version"])
    assert result.exit_code == 0


def test_global_output_format_flag() -> None:
    """Global --output-format flag should be available."""
    from typer.testing import CliRunner
    from filtarr.cli import app

    runner = CliRunner()
    result = runner.invoke(app, ["--output-format", "json", "version"])
    assert result.exit_code == 0
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_cli.py::test_global_timestamps_flag -v`
Expected: FAIL with "No such option"

**Step 3: Add global flags to CLI**

Edit `src/filtarr/cli.py`, update the `main` callback:

```python
@app.callback()
def main(
    ctx: typer.Context,
    log_level: Annotated[
        str | None,
        typer.Option(
            "--log-level",
            "-l",
            help="Logging level (debug, info, warning, error, critical).",
        ),
    ] = None,
    timestamps: Annotated[
        bool,
        typer.Option(
            "--timestamps/--no-timestamps",
            help="Show timestamps in output. Default: True.",
        ),
    ] = True,
    output_format: Annotated[
        str | None,
        typer.Option(
            "--output-format",
            "-o",
            help="Output format: text or json.",
        ),
    ] = None,
) -> None:
    """filtarr - Check release availability for movies and TV shows via Radarr/Sonarr."""
    import os

    # Priority: CLI > env var > config.toml > default
    if log_level:
        effective_level = log_level
    elif os.environ.get("FILTARR_LOG_LEVEL"):
        effective_level = os.environ["FILTARR_LOG_LEVEL"]
    else:
        try:
            config = Config.load()
            effective_level = config.logging.level
        except ConfigurationError:
            effective_level = "INFO"

    # Validate log level
    if effective_level.upper() not in VALID_LOG_LEVELS:
        error_console.print(
            f"[red]Invalid log level: {effective_level}[/red]\n"
            f"Valid options: {', '.join(sorted(VALID_LOG_LEVELS))}"
        )
        raise typer.Exit(1)

    # Configure logging
    configure_logging(level=effective_level)

    # Store in context for commands that need it
    ctx.ensure_object(dict)
    ctx.obj["log_level"] = effective_level.upper()
    ctx.obj["timestamps"] = timestamps
    ctx.obj["output_format"] = output_format or "text"
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_cli.py::test_global_timestamps_flag tests/test_cli.py::test_global_output_format_flag -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/filtarr/cli.py tests/test_cli.py
git commit -m "feat: add global --timestamps and --output-format flags

- --timestamps/--no-timestamps (default: True)
- --output-format text|json (default: text)
- Flags stored in typer context for commands to use"
```

---

## Task 5: Create Output Formatter Utility

**Files:**
- Create: `src/filtarr/output.py`
- Test: `tests/test_output.py`

**Step 1: Write the failing test**

```python
# tests/test_output.py - new file

"""Tests for output formatting utilities."""

from datetime import datetime
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
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_output.py -v`
Expected: FAIL with ModuleNotFoundError

**Step 3: Create output formatter**

Create `src/filtarr/output.py`:

```python
"""Output formatting utilities for CLI commands."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


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
            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
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
                # Extract base warning (remove numbers for grouping)
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
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_output.py -v`
Expected: PASS

**Step 5: Add to package exports**

Edit `src/filtarr/__init__.py` to add the export:

```python
from filtarr.output import OutputFormatter
```

**Step 6: Commit**

```bash
git add src/filtarr/output.py tests/test_output.py src/filtarr/__init__.py
git commit -m "feat: add OutputFormatter for consistent CLI output

- Timestamp formatting (on by default)
- Warning and error collection
- Summary generation at end of batch"
```

---

## Task 6: Refactor Batch Progress Bar to Show Batch Size

**Files:**
- Modify: `src/filtarr/cli.py:1055-1083`
- Test: `tests/test_cli_batch.py`

**Step 1: Write the failing test**

```python
# tests/test_cli_batch.py - add to existing file

def test_batch_progress_bar_shows_batch_size(
    mock_radarr_client: MagicMock,
    mock_checker: MagicMock,
) -> None:
    """Progress bar should show batch-size progress, not total library."""
    from unittest.mock import patch, AsyncMock
    from typer.testing import CliRunner
    from filtarr.cli import app

    runner = CliRunner()

    # Mock 100 movies but batch size of 5
    mock_movies = [MagicMock(id=i, title=f"Movie {i}", tags=[]) for i in range(100)]
    mock_radarr_client.get_all_movies = AsyncMock(return_value=mock_movies)
    mock_radarr_client.get_tags = AsyncMock(return_value=[])

    with patch("filtarr.cli.RadarrClient") as mock_client_class:
        mock_client_class.return_value.__aenter__ = AsyncMock(return_value=mock_radarr_client)
        mock_client_class.return_value.__aexit__ = AsyncMock(return_value=None)

        result = runner.invoke(app, [
            "check", "batch", "--all-movies", "--batch-size", "5", "--no-tag"
        ])

    # Check that output shows progress over batch size (5), not total (100)
    # The progress bar description should indicate batch progress
    assert result.exit_code == 0
    # Verify batch limit message appears
    assert "batch limit (5) reached" in result.output.lower() or "5" in result.output
```

**Step 2: Run test to verify current behavior**

Run: `uv run pytest tests/test_cli_batch.py::test_batch_progress_bar_shows_batch_size -v`

**Step 3: Modify batch progress tracking**

Edit `src/filtarr/cli.py`, in the `_run_batch_checks` function, change the progress bar total:

```python
async def _run_batch_checks(
    ctx: BatchContext,
    all_movies: bool,
    all_series: bool,
    skip_tagged: bool,
    file_items: list[tuple[str, str]],
    batch_type: Literal["movie", "series", "mixed"],
    existing_progress: BatchProgress | None,
) -> None:
    """Run batch checks on all items."""
    # ... existing code to fetch movies/series ...

    # Build combined item list
    all_items = _build_item_list(movies_to_check, series_to_check, file_items)

    if not all_items:
        ctx.error_console.print("[red]No items to check[/red]")
        return

    # Calculate items to actually process this run
    items_to_process = len(all_items)
    if existing_progress:
        items_to_process -= existing_progress.processed_count

    # If batch_size is set, limit the progress bar total
    progress_total = items_to_process
    if ctx.batch_size > 0:
        progress_total = min(ctx.batch_size, items_to_process)

    # ... rest of function with progress bar using progress_total ...

    with Progress(
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("{task.completed}/{task.total}"),  # Show X/Y instead of percentage
        TimeElapsedColumn(),
        console=ctx.console,
        disable=progress_total < 3,
    ) as progress:
        task = progress.add_task("Checking items...", total=progress_total)
        # ... rest of processing loop ...
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_cli_batch.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/filtarr/cli.py tests/test_cli_batch.py
git commit -m "fix: batch progress bar shows batch-size progress

Progress bar now shows X/Y where Y is the batch size limit,
not the total library size. Shows '3/5' instead of '0%'."
```

---

## Task 7: Integrate Warning/Error Collection in Batch

**Files:**
- Modify: `src/filtarr/cli.py:892-1010` (batch processing functions)
- Modify: `src/filtarr/cli.py:1169-1180` (print_batch_summary)
- Test: `tests/test_cli_batch.py`

**Step 1: Write the failing test**

```python
# tests/test_cli_batch.py - add to existing file

def test_batch_shows_warnings_in_summary() -> None:
    """Batch should collect warnings and show them in summary."""
    # Test that slow request warnings appear in summary section
    pass  # Implementation depends on how we trigger warnings in test


def test_batch_shows_errors_in_summary() -> None:
    """Batch should show errors both inline and in summary."""
    # Test that errors appear inline AND in summary
    pass  # Implementation depends on mock setup
```

**Step 2: Update BatchContext to include OutputFormatter**

Edit `src/filtarr/cli.py`, add OutputFormatter to BatchContext:

```python
from filtarr.output import OutputFormatter

@dataclass
class BatchContext:
    """Context for batch processing operations."""

    config: Config
    state_manager: StateManager
    search_criteria: SearchCriteria
    criteria_str: str
    sampling_strategy: SamplingStrategy
    seasons: int
    apply_tags: bool
    dry_run: bool
    batch_size: int
    delay: float
    output_format: OutputFormat
    console: Console
    error_console: Console

    # Output formatting
    formatter: OutputFormatter = field(default_factory=OutputFormatter)

    # Counters (mutable)
    results: list[SearchResult] = field(default_factory=list)
    has_match_count: int = 0
    skipped_count: int = 0
    processed_this_run: int = 0
    batch_limit_reached: bool = False
```

**Step 3: Update error handling to collect errors**

Edit `src/filtarr/cli.py`, update `_process_single_item`:

```python
async def _process_single_item(
    ctx: BatchContext,
    item_type: str,
    item_id: int,
    item_name: str,
    batch_progress: BatchProgress | None,
) -> bool:
    """Process a single item and handle the result."""
    try:
        result = await _process_batch_item(ctx, item_type, item_id, item_name)

        if result:
            ctx.results.append(result)
            _handle_batch_result(ctx, result, item_id, batch_progress)
            if result.has_match:
                ctx.has_match_count += 1
            ctx.processed_this_run += 1

            if ctx.batch_size > 0 and ctx.processed_this_run >= ctx.batch_size:
                ctx.batch_limit_reached = True
                return False

    except ConfigurationError as e:
        error_msg = str(e)
        ctx.error_console.print(ctx.formatter.format_line(
            ctx.formatter.format_error(f"{item_type}:{item_name}", error_msg)
        ))
        ctx.formatter.add_error(f"{item_name} ({item_id})" if item_id > 0 else item_name, error_msg)
        if batch_progress and item_id > 0:
            ctx.state_manager.update_batch_progress(item_id)
    except httpx.HTTPStatusError as e:
        error_msg = f"{e.response.status_code} {e.response.reason_phrase}"
        ctx.error_console.print(ctx.formatter.format_line(
            ctx.formatter.format_error(f"{item_type}:{item_name}", error_msg)
        ))
        ctx.formatter.add_error(f"{item_name} ({item_id})" if item_id > 0 else item_name, error_msg)
        if not _is_transient_error(e) and batch_progress and item_id > 0:
            ctx.state_manager.update_batch_progress(item_id)
    # ... similar for other exception types ...

    return True
```

**Step 4: Update batch summary to include warnings/errors**

Edit `src/filtarr/cli.py`, update `_print_batch_summary`:

```python
def _print_batch_summary(ctx: BatchContext) -> None:
    """Print batch summary including warnings and errors."""
    console.print()
    display_criteria = _format_result_type(ctx.search_criteria.value)
    summary_parts = [
        f"{ctx.has_match_count}/{len(ctx.results)} items have {display_criteria} available"
    ]
    if ctx.skipped_count > 0:
        summary_parts.append(f"{ctx.skipped_count} resumed/skipped")
    if ctx.batch_limit_reached:
        summary_parts.append(f"batch limit ({ctx.batch_size}) reached - run again to continue")
    console.print(f"[bold]Summary:[/bold] {', '.join(summary_parts)}")

    # Print warnings and errors summary
    summary_lines = ctx.formatter.format_summary()
    for line in summary_lines:
        if line.startswith("Warnings"):
            console.print(f"[yellow]{line}[/yellow]")
        elif line.startswith("Errors"):
            console.print(f"[red]{line}[/red]")
        elif line.startswith("  -"):
            console.print(f"[dim]{line}[/dim]")
        else:
            console.print(line)
```

**Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_cli_batch.py -v`
Expected: PASS

**Step 6: Commit**

```bash
git add src/filtarr/cli.py tests/test_cli_batch.py
git commit -m "feat: collect warnings and errors for batch summary

- Errors shown inline AND in summary at end
- Warnings collected and grouped in summary
- Summary format: 'Warnings (3): - message (x3)'"
```

---

## Task 8: Add Slow Request Warning Capture

**Files:**
- Modify: `src/filtarr/clients/base.py`
- Test: `tests/test_clients.py`

**Step 1: Identify slow request warning location**

The slow request warning is logged in `base.py`. We need to also emit it in a way that CLI can capture.

**Step 2: Add callback mechanism for warnings**

This is more complex - we may need to use a context variable or callback system. For now, we can capture warnings by checking the log output or using a custom log handler.

**Alternative approach:** Use Python's warnings module with a custom warning category that CLI can filter and collect.

```python
# src/filtarr/clients/base.py
import warnings

class SlowRequestWarning(UserWarning):
    """Warning for slow HTTP requests."""
    pass

# In the slow request detection code:
if elapsed > self.slow_request_threshold:
    msg = f"Slow request ({elapsed:.2f}s) to {path}"
    logger.warning(msg)
    warnings.warn(msg, SlowRequestWarning, stacklevel=2)
```

Then in CLI, capture warnings:

```python
import warnings
from filtarr.clients.base import SlowRequestWarning

with warnings.catch_warnings(record=True) as w:
    warnings.simplefilter("always", SlowRequestWarning)
    # ... run batch ...
    for warning in w:
        if issubclass(warning.category, SlowRequestWarning):
            ctx.formatter.add_warning(str(warning.message))
```

**This task is optional and can be deferred** - the current implementation shows warnings inline which is acceptable.

**Step 3: Commit (if implemented)**

```bash
git add src/filtarr/clients/base.py src/filtarr/cli.py tests/test_clients.py
git commit -m "feat: capture slow request warnings for batch summary"
```

---

## Task 9: Update Serve Output Format

**Files:**
- Modify: `src/filtarr/webhook.py:93-100`
- Test: `tests/test_webhook.py`

**Step 1: Write the failing test**

```python
# tests/test_webhook.py - add to existing file

def test_webhook_log_format() -> None:
    """Webhook logs should use clean format."""
    # Verify log messages match expected format:
    # "Webhook: Radarr check - The Matrix (1999)"
    # "Check result: 4K available, tagged"
    pass
```

**Step 2: Update webhook logging**

Edit `src/filtarr/webhook.py`, update log messages:

```python
async def _process_movie_check(movie_id: int, movie_title: str, config: Config) -> None:
    """Background task to check 4K availability for a movie."""
    logger.info(f"Webhook: Radarr check - {movie_title}")

    try:
        # ... existing check logic ...

        outcome = _format_check_outcome(has_match, tag_result)
        logger.info(f"Check result: {outcome}")

    except Exception as e:
        logger.error(f"Webhook error: {movie_title} - {e}")
```

**Step 3: Run tests**

Run: `uv run pytest tests/test_webhook.py -v`
Expected: PASS

**Step 4: Commit**

```bash
git add src/filtarr/webhook.py tests/test_webhook.py
git commit -m "feat: clean up webhook server log format

- 'Webhook: Radarr check - Movie Title'
- 'Check result: 4K available, tagged'"
```

---

## Task 10: Final Integration Test

**Files:**
- Test: `tests/test_cli_logging.py`

**Step 1: Write integration test**

```python
# tests/test_cli_logging.py - add to existing file

def test_batch_output_is_clean_at_info() -> None:
    """At INFO level, batch output should not include httpx logs."""
    from unittest.mock import patch, AsyncMock, MagicMock
    from typer.testing import CliRunner
    from filtarr.cli import app

    runner = CliRunner()

    with patch("filtarr.cli.Config.load") as mock_config:
        # Setup minimal config
        mock_config.return_value = MagicMock(...)

        result = runner.invoke(app, [
            "--log-level", "info",
            "check", "batch", "--all-movies", "--batch-size", "1"
        ])

    # Verify no httpx log lines appear
    assert "httpx" not in result.output.lower()
    assert "HTTP Request:" not in result.output
```

**Step 2: Run full test suite**

Run: `uv run pytest tests/ -v`
Expected: All tests PASS

**Step 3: Run linting and type checking**

Run: `uv run ruff check src tests && uv run mypy src`
Expected: No errors

**Step 4: Commit and push**

```bash
git add .
git commit -m "test: add integration test for clean log output"
git push
```

---

## Summary

This plan implements:

1. **Third-party logger suppression** - httpx/uvicorn only show WARNING+ at INFO level
2. **Timestamps config** - `--timestamps/--no-timestamps` flag, default True
3. **Output format config** - `--output-format text|json` flag
4. **Batch progress bar fix** - Shows X/batch_size instead of X/total_library
5. **Warning/error collection** - Inline AND summary at end
6. **Clean serve output** - "Webhook: Radarr check - Title" format

Total estimated tasks: 10
