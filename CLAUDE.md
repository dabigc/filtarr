# CLAUDE.md

Project-specific instructions for Claude Code.

## Project Overview

**filtarr** is a Python library for checking media availability via Radarr/Sonarr search results using configurable search criteria. It provides a programmatic API for querying whether movies (via Radarr) and TV shows (via Sonarr) match specific criteria (e.g., 4K resolution, HDR, Dolby Vision) from indexers.

## Tech Stack

- **Language**: Python 3.11+
- **HTTP Client**: httpx (async)
- **Data Validation**: Pydantic v2
- **Testing**: pytest with pytest-asyncio
- **Linting**: ruff
- **Type Checking**: mypy (strict mode)

## Project Structure

```
src/filtarr/
├── __init__.py          # Public API exports
├── checker.py           # ReleaseChecker - main availability checking logic
├── criteria.py          # SearchCriteria enum and ResultType definitions
├── tagger.py            # ReleaseTagger - applies tags to matching media
├── config.py            # FiltarrConfig - environment-based configuration
├── state.py             # StateManager - persistent state tracking (JSON/Redis)
├── logging.py           # Structured logging with credential filtering
├── cli.py               # Typer CLI application (check, batch, schedule, serve)
├── webhook.py           # FastAPI webhook server for Radarr/Sonarr events
├── clients/
│   ├── base.py          # BaseClient - shared HTTP client logic
│   ├── factory.py       # ClientFactory - dynamic client creation
│   ├── radarr.py        # RadarrClient - Radarr API v3
│   └── sonarr.py        # SonarrClient - Sonarr API v3
├── models/
│   ├── common.py        # Shared Pydantic models
│   ├── radarr.py        # Radarr-specific models
│   ├── sonarr.py        # Sonarr-specific models
│   └── webhook.py       # Webhook payload models
└── scheduler/
    ├── manager.py       # SchedulerManager - job orchestration
    ├── executor.py      # BatchExecutor - runs batch checks
    ├── triggers.py      # Trigger definitions (cron, interval)
    ├── exporter.py      # Prometheus metrics exporter
    └── models.py        # Scheduler-specific models
```

## Development Commands

**This project uses `uv` for dependency management. Always prefix commands with `uv run`.**

```bash
# Install with dev dependencies (includes all optional deps)
uv sync --dev

# Install for production with specific features
uv sync --extra cli                    # CLI only
uv sync --extra webhook                # Webhook server only
uv sync --extra scheduler              # Scheduler only
uv sync --extra cli --extra webhook    # Multiple extras

# Install pre-commit hooks (required for contributors)
uv run pre-commit install

# Run tests
uv run pytest

# Run tests with coverage
uv run pytest --cov=filtarr --cov-report=term-missing

# Lint and format
uv run ruff check src tests
uv run ruff format src tests

# Type check
uv run mypy src

# Run all pre-commit hooks manually
uv run pre-commit run --all-files
```

## Docker Development

The project includes Docker support for containerized deployment and testing.

```bash
# Build and run with docker-compose
docker-compose up --build

# Run Docker runtime tests manually
./scripts/test-docker.sh

# Run with specific test options
./scripts/test-docker.sh --verbose      # Detailed output
./scripts/test-docker.sh --quick        # Skip some checks for speed
./scripts/test-docker.sh --pre-commit   # Mode used by pre-commit hook
```

**Docker test coverage:**
- Container builds successfully
- Application starts and responds to health checks
- Environment variable configuration works
- Graceful shutdown behavior

**Pre-commit integration:** The Docker tests run automatically when you modify `Dockerfile`, `docker-compose.yml`, source files, or dependency files. Tests are skipped gracefully if Docker is not available.

## Pre-Commit Checklist (CRITICAL)

**BEFORE creating any commit, Claude MUST run these checks and fix all errors:**

1. **Lint check**: `uv run ruff check src tests`
   - Fix any lint errors before proceeding
   - Common issues: Yoda conditions (SIM300), import ordering (I001)

2. **Type check**: `uv run mypy src`
   - Fix any type errors before proceeding
   - Common issues: Missing type stubs, incorrect type narrowing

3. **Tests**: `uv run pytest`
   - Ensure all tests pass

**DO NOT commit if any of these checks fail.** Fix issues first, then commit.

**Pre-commit hooks:** This project uses pre-commit hooks that enforce these checks automatically. The hooks include:
- **ruff**: Linting and formatting
- **mypy**: Type checking
- **docker-test**: Runtime tests (only runs when Docker-related or source files change)

If Docker is unavailable, the docker-test hook skips gracefully. If a commit is rejected, review the error output and fix issues before retrying.

## CLI Usage

The library includes a full-featured CLI for checking availability and running services:

```bash
# Check a single movie by ID or name
filtarr check movie 123
filtarr check movie "The Matrix"
filtarr check movie 123 --criteria directors-cut

# Check a TV series
filtarr check series 456
filtarr check series "Breaking Bad" --strategy recent

# Batch operations
filtarr batch --all-movies
filtarr batch --all-series --criteria hdr
filtarr batch --tag-matches    # Apply tags to matching media

# Run the webhook server
filtarr serve --port 8080
filtarr serve --host 0.0.0.0 --port 8080

# Schedule automated checks
filtarr schedule start --cron "0 2 * * *"    # Daily at 2 AM

# Configuration
filtarr config show
filtarr config validate
```

Use `filtarr --help` or `filtarr <command> --help` for full options.

## API Design Principles

1. **Async-first**: All network operations use async/await
2. **Type-safe**: Full type annotations, mypy strict mode
3. **Pydantic models**: All API responses parsed into validated models
4. **Minimal dependencies**: Core library has few runtime deps; features use optional extras

## Architecture Patterns

The codebase follows these patterns to maintain consistency:

1. **Factory Pattern**: `ClientFactory` creates Radarr/Sonarr clients dynamically based on configuration. Use the factory rather than instantiating clients directly when client type is determined at runtime.

2. **Separation of Concerns**:
   - `ReleaseChecker` - orchestrates availability checks
   - `ReleaseTagger` - handles tag application logic separately
   - `StateManager` - manages persistent state independently
   - Clients handle only HTTP communication

3. **Base Client Extraction**: Common HTTP logic (retries, error handling, connection pooling) lives in `BaseClient`. Radarr/Sonarr clients inherit and add API-specific methods.

4. **Configuration Hierarchy**: `FiltarrConfig` loads from environment variables with sensible defaults. All components accept config objects rather than individual parameters.

5. **Async Context Managers**: Clients and managers implement `__aenter__`/`__aexit__` for proper resource cleanup. Always use `async with` when possible.

## Security Considerations

When contributing, maintain these security patterns:

1. **Credential Filtering**: The logging system automatically filters sensitive data (API keys, passwords) from log output. When adding new log statements, avoid logging full request/response objects that may contain credentials.

2. **Config Repr Safety**: `FiltarrConfig` masks API keys in `__repr__` and `__str__` methods. If adding new config classes with sensitive fields, implement similar masking.

3. **Environment Variables**: Secrets should come from environment variables, never hardcoded. The `.env.example` file documents required variables without exposing real values.

4. **API Key Headers**: API keys are passed via `X-Api-Key` header, never in URLs. This prevents accidental exposure in logs or browser history.

5. **Input Validation**: All external input (API responses, webhook payloads, CLI arguments) is validated through Pydantic models before use.

## Naming Conventions

1. **Use full names for variables**: Prefer descriptive names over abbreviations
   - `season_number` not `season_num`
   - `episode` not `ep`
   - `configuration` not `cfg` or `conf`

2. **Keep API field names as-is**: Radarr/Sonarr APIs use camelCase (e.g., `seasonNumber`, `episodeId`). Pydantic models use `Field(alias="camelCase")` to map to snake_case.

3. **Use snake_case for all internal Python code**: Following PEP 8 conventions for variables, functions, and methods.

4. **Short iterator variables in comprehensions are acceptable**: Single-letter or brief names like `r`, `s`, `e` in list comprehensions are idiomatic Python (e.g., `[r for r in releases if r.is_4k()]`).

## Radarr/Sonarr API Notes

- Radarr API v3: `/api/v3/release?movieId={id}` - search for releases
- Sonarr API v3: `/api/v3/release?seriesId={id}` - search for releases
- 4K detection: Look for "2160p" in quality name or release title
- API key passed via `X-Api-Key` header

## Testing Strategy

- Use `respx` for mocking httpx requests
- Fixtures for sample API responses in `tests/fixtures/`
- Test both success and error paths
- Integration tests marked with `@pytest.mark.integration`
