# Global Log Level Implementation Plan

## Status: PENDING
## Last Updated: 2025-12-28

## Overview

Add a global `--log-level` / `-l` option to the filtarr CLI that works for all commands. Currently only the `serve` command has log level control. This change enables debug logging for `check movie`, `check series`, `check batch`, and all `schedule` subcommands.

### Key Decisions

- **Global flag only** - No separate `--debug` shortcut
- **Priority chain:** CLI > environment variable > config.toml > default (INFO)
- **Remove serve-specific flag** - Breaking change for users using `filtarr serve --log-level`
- **Context passing** - Store log level in Typer context for commands that need it (serve/uvicorn)

## Files to Modify

| File | Changes |
|------|---------|
| `src/filtarr/cli.py` | Add global `--log-level` to app callback, remove from `serve`, add context passing |
| `tests/test_cli.py` | Remove obsolete tests, add new tests for global flag |

## Tasks

### Phase 1: Core Implementation

- [ ] **1.1** Add global `--log-level` to app callback
  - **Status:** PENDING
  - **File:** `src/filtarr/cli.py`
  - **Agent:**
  - **Notes:**
  - **Details:**
    - Add `log_level` parameter with `--log-level` / `-l` flags
    - Implement priority chain: CLI > env (`FILTARR_LOG_LEVEL`) > config.toml > default
    - Validate against `VALID_LOG_LEVELS`
    - Call `configure_logging(level=effective_level)`
    - Store level in `ctx.obj["log_level"]`

- [ ] **1.2** Remove `--log-level` from serve command
  - **Status:** PENDING
  - **File:** `src/filtarr/cli.py`
  - **Agent:**
  - **Notes:**
  - **Details:**
    - Remove `log_level` parameter from `serve` function signature
    - Remove validation logic for log level
    - Remove `effective_log_level` calculation
    - Add `ctx: typer.Context` parameter if not present
    - Read log level from `ctx.obj.get("log_level", "INFO")`
    - Pass to `run_server(..., log_level=log_level)`

### Phase 2: Testing

- [ ] **2.1** Identify and remove obsolete tests
  - **Status:** PENDING
  - **File:** `tests/test_cli.py`
  - **Agent:**
  - **Notes:**
  - **Details:**
    - Find tests for serve's `--log-level` parameter
    - Remove or update to use global flag

- [ ] **2.2** Add tests for global `--log-level` functionality
  - **Status:** PENDING
  - **File:** `tests/test_cli.py`
  - **Agent:**
  - **Notes:**
  - **Tests to add:**
    - `test_global_log_level_flag` - Verify `--log-level debug` configures logging at DEBUG
    - `test_global_log_level_short_flag` - Verify `-l debug` works as shorthand
    - `test_log_level_invalid` - Verify invalid level exits with error
    - `test_log_level_case_insensitive` - Both `DEBUG` and `debug` work

- [ ] **2.3** Add tests for priority chain
  - **Status:** PENDING
  - **File:** `tests/test_cli.py`
  - **Agent:**
  - **Notes:**
  - **Tests to add:**
    - `test_log_level_priority_cli_over_env` - CLI flag beats env var
    - `test_log_level_priority_env_over_config` - Env var beats config.toml
    - `test_log_level_priority_config_over_default` - Config.toml beats default

- [ ] **2.4** Add test for serve using context
  - **Status:** PENDING
  - **File:** `tests/test_cli.py`
  - **Agent:**
  - **Notes:**
  - **Tests to add:**
    - `test_serve_uses_context_log_level` - Serve command reads from context

### Phase 3: Validation

- [ ] **3.1** Run full test suite
  - **Status:** PENDING
  - **Command:** `uv run pytest`
  - **Agent:**
  - **Notes:**

- [ ] **3.2** Run lint and type checks
  - **Status:** PENDING
  - **Command:** `uv run ruff check src tests && uv run mypy src`
  - **Agent:**
  - **Notes:**

- [ ] **3.3** Manual smoke test
  - **Status:** PENDING
  - **Commands:**
    - `filtarr --log-level debug check movie 123`
    - `filtarr -l debug serve` (verify uvicorn uses debug)
  - **Agent:**
  - **Notes:**

## Implementation Reference

### App Callback Code

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
    """filtarr - Check media availability via Radarr/Sonarr."""
    # Priority: CLI > env var > config.toml > default
    if log_level:
        effective_level = log_level
    elif os.environ.get("FILTARR_LOG_LEVEL"):
        effective_level = os.environ["FILTARR_LOG_LEVEL"]
    else:
        config = FiltarrConfig.load()
        effective_level = config.logging.level  # defaults to "INFO"

    # Validate
    if effective_level.upper() not in VALID_LOG_LEVELS:
        typer.echo(f"Invalid log level: {effective_level}", err=True)
        raise typer.Exit(1)

    # Configure logging
    configure_logging(level=effective_level)

    # Store in context for commands that need it
    ctx.ensure_object(dict)
    ctx.obj["log_level"] = effective_level.upper()
```

### Serve Command Update

```python
@app.command()
def serve(
    ctx: typer.Context,
    # ... other params, but NOT log_level anymore
) -> None:
    # Get log level from context
    log_level = ctx.obj.get("log_level", "INFO")

    # Pass to run_server() for uvicorn
    run_server(..., log_level=log_level)
```

## Progress Log

| Date | Agent | Task | Status | Notes |
|------|-------|------|--------|-------|
| 2025-12-28 | - | Plan created | COMPLETED | Initial design from brainstorming session |
