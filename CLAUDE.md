# CLAUDE.md

Project-specific instructions for Claude Code.

## Project Overview

**findarr** is a Python library for checking 4K availability of media items via Radarr/Sonarr search results. It provides a programmatic API for querying whether movies (via Radarr) and TV shows (via Sonarr) are available in 4K resolution from indexers.

## Tech Stack

- **Language**: Python 3.11+
- **HTTP Client**: httpx (async)
- **Data Validation**: Pydantic v2
- **Testing**: pytest with pytest-asyncio
- **Linting**: ruff
- **Type Checking**: mypy (strict mode)

## Project Structure

```
src/findarr/
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

# Run tests
uv run pytest

# Run tests with coverage
uv run pytest --cov=findarr --cov-report=term-missing

# Lint
uv run ruff check src tests

# Format
uv run ruff format src tests

# Type check
uv run mypy src
```

## API Design Principles

1. **Async-first**: All network operations use async/await
2. **Type-safe**: Full type annotations, mypy strict mode
3. **Pydantic models**: All API responses parsed into validated models
4. **Minimal dependencies**: Only httpx and pydantic as runtime deps

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

## Completed Spec Projects

- `docs/spec/completed/2025-12-21-radarr-sonarr-4k-checker/` - findarr - Radarr/Sonarr 4K Availability Checker
  - Completed: 2025-12-22
  - Outcome: Success (All 6 phases complete, v0.1.0 ready)
  - Key docs: REQUIREMENTS.md, ARCHITECTURE.md, IMPLEMENTATION_PLAN.md, RETROSPECTIVE.md
  - Status: 109 tests, 91% coverage, ready for PyPI release
