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
├── __init__.py       # Public API exports
├── clients/          # Radarr/Sonarr API clients
│   ├── radarr.py
│   └── sonarr.py
├── models/           # Pydantic models
│   ├── common.py     # Shared models
│   ├── radarr.py     # Radarr-specific models
│   └── sonarr.py     # Sonarr-specific models
└── checker.py        # Main 4K availability checker
```

## Development Commands

**This project uses `uv` for dependency management. Always prefix commands with `uv run`.**

```bash
# Install with dev dependencies
uv sync --dev

# Install pre-commit hooks (required for contributors)
uv run pre-commit install

# Run tests
uv run pytest

# Run tests with coverage
uv run pytest --cov=filtarr --cov-report=term-missing

# Lint
uv run ruff check src tests

# Format
uv run ruff format src tests

# Type check
uv run mypy src

# Run all pre-commit hooks manually
uv run pre-commit run --all-files
```

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

This project uses pre-commit hooks that enforce these checks automatically. If a commit
is rejected by pre-commit, review the error output and fix the issues before retrying.

## API Design Principles

1. **Async-first**: All network operations use async/await
2. **Type-safe**: Full type annotations, mypy strict mode
3. **Pydantic models**: All API responses parsed into validated models
4. **Minimal dependencies**: Only httpx and pydantic as runtime deps

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
