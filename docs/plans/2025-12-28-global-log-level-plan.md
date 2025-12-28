# Global Log Level Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a global `--log-level` / `-l` option to the filtarr CLI that works for all commands, replacing the serve-specific flag.

**Architecture:** Global Typer app callback captures `--log-level` before any command runs, configures logging via existing `configure_logging()`, and stores the level in Typer context for commands that need it (serve passes it to uvicorn).

**Tech Stack:** Python 3.11+, Typer, filtarr.logging module

---

## Key Decisions

- **Global flag only** - No separate `--debug` shortcut
- **Priority chain:** CLI > environment variable > config.toml > default (INFO)
- **Remove serve-specific flag** - Breaking change for users using `filtarr serve --log-level`
- **Context passing** - Store log level in Typer context for commands that need it

## Files Overview

| File | Action |
|------|--------|
| `src/filtarr/cli.py:47-57` | Add app callback with global `--log-level` |
| `src/filtarr/cli.py:1707-1714` | Remove `log_level` parameter from serve |
| `src/filtarr/cli.py:1760-1769` | Remove serve's log level validation/calculation |
| `tests/test_cli_serve.py:180-196` | Update `test_serve_with_log_level` to use global flag |
| `tests/test_cli_logging.py` | Create new file with global log level tests |

---

## Task 1: Add Failing Test for Global Log Level Flag

**Files:**
- Create: `tests/test_cli_logging.py`

**Step 1: Write the failing test**

```python
"""Tests for CLI global logging configuration."""

import logging
from unittest.mock import patch

from typer.testing import CliRunner

from filtarr.cli import app

runner = CliRunner()


class TestGlobalLogLevel:
    """Tests for global --log-level flag."""

    @patch("filtarr.cli.configure_logging")
    def test_global_log_level_flag_configures_logging(
        self, mock_configure: patch
    ) -> None:
        """Global --log-level flag should configure logging before command runs."""
        result = runner.invoke(app, ["--log-level", "debug", "version"])

        assert result.exit_code == 0
        mock_configure.assert_called_once()
        call_args = mock_configure.call_args
        # Check level was passed (either positional or keyword)
        assert "debug" in str(call_args).lower() or logging.DEBUG in str(call_args)
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_cli_logging.py::TestGlobalLogLevel::test_global_log_level_flag_configures_logging -v`

Expected: FAIL - `configure_logging` not called (no global flag exists yet)

**Step 3: Commit the failing test**

```bash
git add tests/test_cli_logging.py
git commit -m "test: add failing test for global --log-level flag"
```

---

## Task 2: Implement Global Log Level in App Callback

**Files:**
- Modify: `src/filtarr/cli.py:47-57`

**Step 1: Add import for configure_logging**

In `src/filtarr/cli.py`, add to imports (around line 20-27):

```python
from filtarr.logging import configure_logging
```

**Step 2: Add app callback after line 57**

Insert after line 57 (after `console = Console()` block, before `class OutputFormat`):

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

    # Validate
    if effective_level.upper() not in VALID_LOG_LEVELS:
        error_console.print(
            f"[red]Invalid log level: {effective_level}[/red]\n"
            f"Valid options: {', '.join(sorted(VALID_LOG_LEVELS))}"
        )
        raise typer.Exit(1)

    # Configure logging
    configure_logging(level=effective_level)

    # Store in context for commands that need it (e.g., serve for uvicorn)
    ctx.ensure_object(dict)
    ctx.obj["log_level"] = effective_level.upper()
```

**Step 3: Run test to verify it passes**

Run: `uv run pytest tests/test_cli_logging.py::TestGlobalLogLevel::test_global_log_level_flag_configures_logging -v`

Expected: PASS

**Step 4: Commit**

```bash
git add src/filtarr/cli.py
git commit -m "feat: add global --log-level flag to CLI"
```

---

## Task 3: Add Test for Short Flag -l

**Files:**
- Modify: `tests/test_cli_logging.py`

**Step 1: Write the failing test**

Add to `TestGlobalLogLevel` class:

```python
    @patch("filtarr.cli.configure_logging")
    def test_global_log_level_short_flag(self, mock_configure: patch) -> None:
        """Short -l flag should work as alias for --log-level."""
        result = runner.invoke(app, ["-l", "warning", "version"])

        assert result.exit_code == 0
        mock_configure.assert_called_once()
```

**Step 2: Run test to verify it passes**

Run: `uv run pytest tests/test_cli_logging.py::TestGlobalLogLevel::test_global_log_level_short_flag -v`

Expected: PASS (already implemented in Task 2)

**Step 3: Commit**

```bash
git add tests/test_cli_logging.py
git commit -m "test: add test for -l short flag"
```

---

## Task 4: Add Test for Invalid Log Level

**Files:**
- Modify: `tests/test_cli_logging.py`

**Step 1: Write the test**

Add to `TestGlobalLogLevel` class:

```python
    def test_global_log_level_invalid_exits_with_error(self) -> None:
        """Invalid log level should exit with error."""
        result = runner.invoke(app, ["--log-level", "verbose", "version"])

        assert result.exit_code == 1
        assert "invalid" in result.output.lower() or "verbose" in result.output.lower()
```

**Step 2: Run test to verify it passes**

Run: `uv run pytest tests/test_cli_logging.py::TestGlobalLogLevel::test_global_log_level_invalid_exits_with_error -v`

Expected: PASS

**Step 3: Commit**

```bash
git add tests/test_cli_logging.py
git commit -m "test: add test for invalid log level validation"
```

---

## Task 5: Add Test for Case Insensitivity

**Files:**
- Modify: `tests/test_cli_logging.py`

**Step 1: Write the test**

Add to `TestGlobalLogLevel` class:

```python
    @patch("filtarr.cli.configure_logging")
    def test_global_log_level_case_insensitive(self, mock_configure: patch) -> None:
        """Log level should be case insensitive."""
        result = runner.invoke(app, ["--log-level", "DEBUG", "version"])

        assert result.exit_code == 0
        mock_configure.assert_called_once()
```

**Step 2: Run test to verify it passes**

Run: `uv run pytest tests/test_cli_logging.py::TestGlobalLogLevel::test_global_log_level_case_insensitive -v`

Expected: PASS

**Step 3: Commit**

```bash
git add tests/test_cli_logging.py
git commit -m "test: add test for case-insensitive log level"
```

---

## Task 6: Add Tests for Priority Chain

**Files:**
- Modify: `tests/test_cli_logging.py`

**Step 1: Write the tests**

Add new test class:

```python
class TestLogLevelPriority:
    """Tests for log level priority chain: CLI > env > config > default."""

    @patch("filtarr.cli.configure_logging")
    @patch.dict("os.environ", {"FILTARR_LOG_LEVEL": "warning"})
    def test_cli_overrides_env_var(self, mock_configure: patch) -> None:
        """CLI flag should override environment variable."""
        result = runner.invoke(app, ["--log-level", "debug", "version"])

        assert result.exit_code == 0
        mock_configure.assert_called_once()
        # Verify debug was used, not warning from env
        call_args = str(mock_configure.call_args)
        assert "debug" in call_args.lower()

    @patch("filtarr.cli.configure_logging")
    @patch("filtarr.cli.Config.load")
    @patch.dict("os.environ", {"FILTARR_LOG_LEVEL": "error"}, clear=False)
    def test_env_overrides_config(
        self, mock_config_load: patch, mock_configure: patch
    ) -> None:
        """Environment variable should override config file."""
        from filtarr.config import Config, LoggingConfig

        mock_config = Config(logging=LoggingConfig(level="debug"))
        mock_config_load.return_value = mock_config

        result = runner.invoke(app, ["version"])

        assert result.exit_code == 0
        # Verify error from env was used, not debug from config
        call_args = str(mock_configure.call_args)
        assert "error" in call_args.lower()

    @patch("filtarr.cli.configure_logging")
    @patch("filtarr.cli.Config.load")
    @patch.dict("os.environ", {}, clear=True)
    def test_config_overrides_default(
        self, mock_config_load: patch, mock_configure: patch
    ) -> None:
        """Config file should override default when no CLI or env."""
        from filtarr.config import Config, LoggingConfig

        # Clear FILTARR_LOG_LEVEL if present
        import os
        os.environ.pop("FILTARR_LOG_LEVEL", None)

        mock_config = Config(logging=LoggingConfig(level="warning"))
        mock_config_load.return_value = mock_config

        result = runner.invoke(app, ["version"])

        assert result.exit_code == 0
        call_args = str(mock_configure.call_args)
        assert "warning" in call_args.lower()
```

**Step 2: Run tests to verify they pass**

Run: `uv run pytest tests/test_cli_logging.py::TestLogLevelPriority -v`

Expected: PASS

**Step 3: Commit**

```bash
git add tests/test_cli_logging.py
git commit -m "test: add tests for log level priority chain"
```

---

## Task 7: Add Failing Test for Serve Using Context

**Files:**
- Modify: `tests/test_cli_logging.py`

**Step 1: Write the failing test**

Add new test class:

```python
class TestServeUsesGlobalLogLevel:
    """Tests that serve command uses global log level from context."""

    @patch("filtarr.webhook.run_server")
    @patch("filtarr.cli.Config.load")
    @patch("filtarr.cli.configure_logging")
    def test_serve_uses_context_log_level(
        self,
        mock_configure: patch,
        mock_config_load: patch,
        mock_run_server: patch,
    ) -> None:
        """Serve should get log level from context, not its own flag."""
        from filtarr.config import Config, RadarrConfig, WebhookConfig

        mock_config = Config(
            radarr=RadarrConfig(url="http://localhost:7878", api_key="test"),
            webhook=WebhookConfig(host="127.0.0.1", port=8080),
        )
        mock_config_load.return_value = mock_config

        # Use global flag, not serve-specific flag
        runner.invoke(app, ["--log-level", "debug", "serve"])

        assert mock_run_server.called
        call_kwargs = mock_run_server.call_args.kwargs
        assert call_kwargs.get("log_level") == "DEBUG"
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_cli_logging.py::TestServeUsesGlobalLogLevel::test_serve_uses_context_log_level -v`

Expected: FAIL - serve still has its own `--log-level` and doesn't read from context

**Step 3: Commit the failing test**

```bash
git add tests/test_cli_logging.py
git commit -m "test: add failing test for serve using context log level"
```

---

## Task 8: Remove Log Level from Serve Command

**Files:**
- Modify: `src/filtarr/cli.py:1689-1806`

**Step 1: Remove log_level parameter from serve function signature**

Change lines 1689-1722 from:

```python
@app.command()
def serve(
    host: Annotated[
        str | None,
        typer.Option(
            "--host",
            "-h",
            help="Host to bind the webhook server to.",
        ),
    ] = None,
    port: Annotated[
        int | None,
        typer.Option(
            "--port",
            "-p",
            help="Port to listen on.",
        ),
    ] = None,
    log_level: Annotated[
        str | None,
        typer.Option(
            "--log-level",
            "-l",
            help="Logging level (debug, info, warning, error). Overrides config/env.",
        ),
    ] = None,
    scheduler: Annotated[
        bool,
        typer.Option(
            "--scheduler/--no-scheduler",
            help="Enable or disable the batch scheduler.",
        ),
    ] = True,
) -> None:
```

To:

```python
@app.command()
def serve(
    ctx: typer.Context,
    host: Annotated[
        str | None,
        typer.Option(
            "--host",
            "-h",
            help="Host to bind the webhook server to.",
        ),
    ] = None,
    port: Annotated[
        int | None,
        typer.Option(
            "--port",
            "-p",
            help="Port to listen on.",
        ),
    ] = None,
    scheduler: Annotated[
        bool,
        typer.Option(
            "--scheduler/--no-scheduler",
            help="Enable or disable the batch scheduler.",
        ),
    ] = True,
) -> None:
```

**Step 2: Update docstring examples (lines 1739-1742)**

Change:

```python
    Example:
        filtarr serve --port 8080
        filtarr serve --host 0.0.0.0 --port 9000 --log-level debug
        filtarr serve --no-scheduler  # Webhooks only, no scheduled batches
```

To:

```python
    Example:
        filtarr serve --port 8080
        filtarr --log-level debug serve --host 0.0.0.0 --port 9000
        filtarr serve --no-scheduler  # Webhooks only, no scheduled batches
```

**Step 3: Remove log level validation and calculation (lines 1760-1769)**

Remove these lines entirely:

```python
    # Validate CLI log level if provided
    if log_level and log_level.upper() not in VALID_LOG_LEVELS:
        error_console.print(
            f"[red]Invalid log level: {log_level}[/red]\n"
            f"Valid options: {', '.join(sorted(VALID_LOG_LEVELS))}"
        )
        raise typer.Exit(1)

    # Priority: CLI flag > config (which includes env var > config file > default)
    effective_log_level = log_level or config.logging.level
```

**Step 4: Get log level from context instead**

After `config = Config.load()` (around line 1753), add:

```python
    # Get log level from global context (set by app callback)
    effective_log_level = ctx.obj.get("log_level", "INFO") if ctx.obj else "INFO"
```

**Step 5: Run test to verify it passes**

Run: `uv run pytest tests/test_cli_logging.py::TestServeUsesGlobalLogLevel::test_serve_uses_context_log_level -v`

Expected: PASS

**Step 6: Commit**

```bash
git add src/filtarr/cli.py
git commit -m "refactor: remove --log-level from serve, use global flag"
```

---

## Task 9: Update Existing Serve Tests

**Files:**
- Modify: `tests/test_cli_serve.py:180-196`

**Step 1: Update test_serve_with_log_level to use global flag**

Change the test at lines 178-196 from:

```python
    @patch("filtarr.webhook.run_server")
    @patch("filtarr.cli.Config.load")
    def test_serve_with_log_level(
        self, mock_config_load: MagicMock, mock_run_server: MagicMock
    ) -> None:
        """Should pass log level to server."""
        from filtarr.config import Config, RadarrConfig, WebhookConfig

        mock_config = Config(
            radarr=RadarrConfig(url="http://localhost:7878", api_key="test"),
            webhook=WebhookConfig(host="127.0.0.1", port=8080),
        )
        mock_config_load.return_value = mock_config

        runner.invoke(app, ["serve", "--log-level", "debug"])

        assert mock_run_server.called
        call_kwargs = mock_run_server.call_args.kwargs
        assert call_kwargs.get("log_level") == "debug"
```

To:

```python
    @patch("filtarr.webhook.run_server")
    @patch("filtarr.cli.Config.load")
    @patch("filtarr.cli.configure_logging")
    def test_serve_with_global_log_level(
        self,
        mock_configure: MagicMock,
        mock_config_load: MagicMock,
        mock_run_server: MagicMock,
    ) -> None:
        """Should pass global log level to server."""
        from filtarr.config import Config, RadarrConfig, WebhookConfig

        mock_config = Config(
            radarr=RadarrConfig(url="http://localhost:7878", api_key="test"),
            webhook=WebhookConfig(host="127.0.0.1", port=8080),
        )
        mock_config_load.return_value = mock_config

        runner.invoke(app, ["--log-level", "debug", "serve"])

        assert mock_run_server.called
        call_kwargs = mock_run_server.call_args.kwargs
        assert call_kwargs.get("log_level") == "DEBUG"
```

**Step 2: Run test to verify it passes**

Run: `uv run pytest tests/test_cli_serve.py::TestServeCommand::test_serve_with_global_log_level -v`

Expected: PASS

**Step 3: Commit**

```bash
git add tests/test_cli_serve.py
git commit -m "test: update serve tests to use global --log-level flag"
```

---

## Task 10: Run Full Test Suite

**Step 1: Run all tests**

Run: `uv run pytest`

Expected: All tests PASS

**Step 2: If any failures, fix and re-run**

Common issues:
- Other tests using `serve --log-level` need updating
- Mock order may need adjustment

**Step 3: Commit any fixes**

```bash
git add -A
git commit -m "fix: resolve test failures from log level refactor"
```

---

## Task 11: Run Lint and Type Checks

**Step 1: Run ruff**

Run: `uv run ruff check src tests`

Expected: No errors

**Step 2: Run mypy**

Run: `uv run mypy src`

Expected: No errors

**Step 3: Fix any issues and commit**

```bash
git add -A
git commit -m "fix: resolve lint/type errors"
```

---

## Task 12: Manual Smoke Test

**Step 1: Test global flag with check command**

Run: `uv run filtarr --log-level debug version`

Expected: Shows version (debug logging configured but no visible output for version command)

**Step 2: Test global flag with serve (if Radarr/Sonarr configured)**

Run: `uv run filtarr --log-level debug serve`

Expected: Shows "Log level: DEBUG" in startup output

**Step 3: Verify old serve flag is removed**

Run: `uv run filtarr serve --log-level debug`

Expected: Error about unrecognized option `--log-level`

---

## Progress Log

| Date | Agent | Task | Status | Notes |
|------|-------|------|--------|-------|
| 2025-12-28 | - | Plan created | COMPLETED | Initial design from brainstorming |
| 2025-12-28 | - | Plan rewritten | COMPLETED | Converted to TDD bite-sized tasks |
