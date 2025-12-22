---
document_type: implementation_plan
project_id: SPEC-2025-12-21-001
version: 1.0.0
last_updated: 2025-12-21T23:59:00Z
status: draft
---

# findarr - Implementation Plan

## Overview

This plan builds on the existing scaffold at `/Users/dabigc/projects/worktrees/4k-findarr/4k-findarr-radarr-sonarr-searc/`. The scaffold already includes basic RadarrClient, SonarrClient, and FourKChecker implementations. This plan adds the missing features: episode-based TV checking, retry logic, caching, and CLI.

## Current State (Already Implemented)

| Component | Status | Notes |
|-----------|--------|-------|
| RadarrClient (basic) | Done | `get_releases()`, `has_4k_releases()` |
| SonarrClient (basic) | Done | `get_series_releases()`, `has_4k_releases()` |
| Quality model | Done | `is_4k()` method |
| Release model | Done | `is_4k()` with fallback to title parsing |
| FourKChecker facade | Done | Basic `check_movie()`, `check_series()` |
| Test infrastructure | Done | respx fixtures, pytest-asyncio |

## Phase Summary

| Phase | Focus | Key Deliverables |
|-------|-------|------------------|
| Phase 1 | Infrastructure | BaseArrClient, retry, caching |
| Phase 2 | Sonarr Enhancement | Episode models, episode-based checking |
| Phase 3 | Checker Enhancement | Sampling strategies, detailed results |
| Phase 4 | CLI | Commands, config, output formatting |
| Phase 5 | Polish | Documentation, tests, release prep |

---

## Phase 1: Infrastructure Layer

**Goal**: Add shared infrastructure for retry and caching to both clients.

### Task 1.1: Add tenacity and cachetools dependencies

- **Description**: Update `pyproject.toml` to add tenacity and cachetools as runtime dependencies
- **Dependencies**: None
- **Acceptance Criteria**:
  - [ ] `pyproject.toml` includes `tenacity>=8.2.0` and `cachetools>=5.3.0`
  - [ ] `pip install -e .` succeeds with new dependencies
- **Files**: `pyproject.toml`

### Task 1.2: Create BaseArrClient abstract class

- **Description**: Extract common functionality from RadarrClient/SonarrClient into a base class
- **Dependencies**: Task 1.1
- **Acceptance Criteria**:
  - [ ] `BaseArrClient` class in `src/findarr/clients/base.py`
  - [ ] Common init (base_url, api_key, timeout, cache_ttl, max_retries)
  - [ ] HTTP client setup with connection pooling
  - [ ] Context manager protocol (`__aenter__`, `__aexit__`)
- **Files**: `src/findarr/clients/base.py`

### Task 1.3: Implement retry decorator with tenacity

- **Description**: Add retry logic to BaseArrClient for transient failures
- **Dependencies**: Task 1.2
- **Acceptance Criteria**:
  - [ ] Retry on connection errors, timeouts, 429, 5xx
  - [ ] Exponential backoff with max 3 attempts (configurable)
  - [ ] Logging on retry attempts
  - [ ] No retry on 401, 404 (fail fast)
- **Files**: `src/findarr/clients/base.py`

### Task 1.4: Implement TTL cache layer

- **Description**: Add per-client caching with TTLCache from cachetools
- **Dependencies**: Task 1.2
- **Acceptance Criteria**:
  - [ ] Cache wrapper for GET requests
  - [ ] Configurable TTL (default 300s)
  - [ ] Cache key based on endpoint + params
  - [ ] Method to invalidate cache entries
  - [ ] Thread-safe (asyncio.Lock for async safety)
- **Files**: `src/findarr/clients/base.py`

### Task 1.5: Refactor RadarrClient to use BaseArrClient

- **Description**: Update RadarrClient to inherit from BaseArrClient
- **Dependencies**: Task 1.4
- **Acceptance Criteria**:
  - [ ] RadarrClient extends BaseArrClient
  - [ ] All existing tests pass
  - [ ] Retry and caching automatically applied
- **Files**: `src/findarr/clients/radarr.py`

### Task 1.6: Refactor SonarrClient to use BaseArrClient

- **Description**: Update SonarrClient to inherit from BaseArrClient
- **Dependencies**: Task 1.4
- **Acceptance Criteria**:
  - [ ] SonarrClient extends BaseArrClient
  - [ ] All existing tests pass
  - [ ] Retry and caching automatically applied
- **Files**: `src/findarr/clients/sonarr.py`

### Task 1.7: Add tests for retry and caching

- **Description**: Unit tests for the new infrastructure
- **Dependencies**: Task 1.5, Task 1.6
- **Acceptance Criteria**:
  - [ ] Test retry on 5xx responses
  - [ ] Test no retry on 401/404
  - [ ] Test cache hit/miss behavior
  - [ ] Test cache TTL expiration
- **Files**: `tests/test_infrastructure.py`

### Phase 1 Deliverables

- [ ] BaseArrClient with retry and caching
- [ ] Refactored RadarrClient and SonarrClient
- [ ] Infrastructure tests passing

### Phase 1 Exit Criteria

- [ ] `pytest` passes all tests
- [ ] `mypy src` passes with no errors
- [ ] `ruff check src tests` passes

---

## Phase 2: Sonarr Enhancement

**Goal**: Add episode-based 4K checking to SonarrClient.

### Task 2.1: Create Sonarr-specific models

- **Description**: Add Episode, Season, Series models for Sonarr API responses
- **Dependencies**: Phase 1 complete
- **Acceptance Criteria**:
  - [ ] `Episode` model with id, series_id, season_number, episode_number, air_date, air_date_utc
  - [ ] `Season` model with season_number, monitored, episode_count
  - [ ] `Series` model with id, title, seasons list
  - [ ] Models exported from `src/findarr/models/__init__.py`
- **Files**: `src/findarr/models/sonarr.py`, `src/findarr/models/__init__.py`

### Task 2.2: Add get_series() method to SonarrClient

- **Description**: Fetch series metadata including seasons
- **Dependencies**: Task 2.1
- **Acceptance Criteria**:
  - [ ] `GET /api/v3/series/{id}` call
  - [ ] Returns `Series` model
  - [ ] Cached with TTL
- **Files**: `src/findarr/clients/sonarr.py`

### Task 2.3: Add get_episodes() method to SonarrClient

- **Description**: Fetch all episodes for a series
- **Dependencies**: Task 2.1
- **Acceptance Criteria**:
  - [ ] `GET /api/v3/episode?seriesId={id}` call
  - [ ] Returns `list[Episode]`
  - [ ] Cached with TTL
- **Files**: `src/findarr/clients/sonarr.py`

### Task 2.4: Add get_episode_releases() method to SonarrClient

- **Description**: Fetch releases for a specific episode
- **Dependencies**: Task 2.1
- **Acceptance Criteria**:
  - [ ] `GET /api/v3/release?episodeId={id}` call
  - [ ] Returns `list[Release]`
  - [ ] Cached with TTL
- **Files**: `src/findarr/clients/sonarr.py`

### Task 2.5: Add get_latest_aired_episode() method

- **Description**: Find the most recently aired episode
- **Dependencies**: Task 2.3
- **Acceptance Criteria**:
  - [ ] Filters episodes by air_date <= today
  - [ ] Returns episode with most recent air_date
  - [ ] Returns None if no aired episodes
- **Files**: `src/findarr/clients/sonarr.py`

### Task 2.6: Add tests for new Sonarr methods

- **Description**: Unit tests with mocked responses
- **Dependencies**: Task 2.5
- **Acceptance Criteria**:
  - [ ] Test get_series() parsing
  - [ ] Test get_episodes() parsing
  - [ ] Test get_episode_releases() parsing
  - [ ] Test get_latest_aired_episode() logic
  - [ ] Test with fixtures for various series states
- **Files**: `tests/test_sonarr.py`, `tests/fixtures/sonarr/`

### Phase 2 Deliverables

- [ ] Sonarr models (Episode, Season, Series)
- [ ] Episode-level API methods
- [ ] Latest aired episode detection
- [ ] Tests for all new functionality

### Phase 2 Exit Criteria

- [ ] `pytest` passes all tests
- [ ] `mypy src` passes with no errors

---

## Phase 3: Checker Enhancement

**Goal**: Implement configurable episode sampling and detailed results.

### Task 3.1: Define SamplingStrategy enum

- **Description**: Create enum for TV show sampling strategies
- **Dependencies**: Phase 2 complete
- **Acceptance Criteria**:
  - [ ] `SamplingStrategy.RECENT` - most recent N seasons
  - [ ] `SamplingStrategy.DISTRIBUTED` - first, middle, last
  - [ ] `SamplingStrategy.ALL` - all seasons
  - [ ] Enum in `src/findarr/checker.py`
- **Files**: `src/findarr/checker.py`

### Task 3.2: Implement season sampling logic

- **Description**: Given a strategy and season count, select episodes to check
- **Dependencies**: Task 3.1
- **Acceptance Criteria**:
  - [ ] For RECENT: select latest aired episode from each of last N seasons
  - [ ] For DISTRIBUTED: select from first, middle, last seasons
  - [ ] For ALL: select one episode from each season
  - [ ] Bounds checking: if N > actual seasons, check all
  - [ ] Skip seasons with no aired episodes
- **Files**: `src/findarr/checker.py`

### Task 3.3: Update FourKResult dataclass

- **Description**: Enhance result to include episode information
- **Dependencies**: Task 3.1
- **Acceptance Criteria**:
  - [ ] Add `episodes_checked: list[int] | None` field
  - [ ] Add `seasons_checked: list[int] | None` field
  - [ ] Add `strategy_used: SamplingStrategy | None` field
- **Files**: `src/findarr/checker.py`

### Task 3.4: Implement enhanced check_series()

- **Description**: Rewrite check_series to use episode sampling
- **Dependencies**: Task 3.2, Task 3.3
- **Acceptance Criteria**:
  - [ ] Check latest aired episode first
  - [ ] If no 4K, apply sampling strategy
  - [ ] Short-circuit on first 4K found
  - [ ] Return detailed FourKResult with episodes checked
  - [ ] Configurable seasons_to_check parameter (default 3)
  - [ ] Configurable strategy parameter (default RECENT)
- **Files**: `src/findarr/checker.py`

### Task 3.5: Add tests for sampling strategies

- **Description**: Test all sampling scenarios
- **Dependencies**: Task 3.4
- **Acceptance Criteria**:
  - [ ] Test RECENT with 5-season show, check 3
  - [ ] Test RECENT with 2-season show, check 3 (bounds)
  - [ ] Test DISTRIBUTED strategy
  - [ ] Test ALL strategy
  - [ ] Test short-circuit on 4K found
  - [ ] Test series with no aired episodes
- **Files**: `tests/test_checker.py`

### Phase 3 Deliverables

- [ ] SamplingStrategy enum
- [ ] Episode sampling logic
- [ ] Enhanced check_series() with strategy support
- [ ] Comprehensive tests

### Phase 3 Exit Criteria

- [ ] `pytest` passes all tests
- [ ] `mypy src` passes with no errors

---

## Phase 4: CLI Implementation

**Goal**: Add command-line interface with typer.

### Task 4.1: Add CLI dependencies

- **Description**: Add typer and rich as optional CLI dependencies
- **Dependencies**: Phase 3 complete
- **Acceptance Criteria**:
  - [ ] `pyproject.toml` has `[project.optional-dependencies] cli = ["typer>=0.12.0", "rich>=13.0.0"]`
  - [ ] `pip install -e ".[cli]"` works
- **Files**: `pyproject.toml`

### Task 4.2: Create config loader

- **Description**: Load config from env vars and TOML file
- **Dependencies**: Task 4.1
- **Acceptance Criteria**:
  - [ ] Read from `~/.config/findarr/config.toml` if exists
  - [ ] Override with environment variables
  - [ ] Validate required fields
  - [ ] Raise ConfigurationError on invalid config
- **Files**: `src/findarr/config.py`

### Task 4.3: Implement CLI app structure

- **Description**: Set up typer app with check command group
- **Dependencies**: Task 4.2
- **Acceptance Criteria**:
  - [ ] `findarr --help` shows usage
  - [ ] `findarr check --help` shows subcommands
  - [ ] Entry point in `pyproject.toml`: `findarr = "findarr.cli:app"`
- **Files**: `src/findarr/cli.py`, `pyproject.toml`

### Task 4.4: Implement check movie command

- **Description**: CLI command to check a single movie
- **Dependencies**: Task 4.3
- **Acceptance Criteria**:
  - [ ] `findarr check movie <id>` works
  - [ ] `--format json|table|simple` option
  - [ ] Loads config automatically
  - [ ] Clear error messages on failure
- **Files**: `src/findarr/cli.py`

### Task 4.5: Implement check series command

- **Description**: CLI command to check a single series
- **Dependencies**: Task 4.3
- **Acceptance Criteria**:
  - [ ] `findarr check series <id>` works
  - [ ] `--seasons` option (default 3)
  - [ ] `--strategy recent|distributed|all` option
  - [ ] `--format json|table|simple` option
- **Files**: `src/findarr/cli.py`

### Task 4.6: Implement batch check command

- **Description**: Check multiple items from a file
- **Dependencies**: Task 4.4, Task 4.5
- **Acceptance Criteria**:
  - [ ] `findarr check --file items.txt` works
  - [ ] File format: one item per line, `movie:123` or `series:456`
  - [ ] Progress indicator for large files
  - [ ] Summary at end
- **Files**: `src/findarr/cli.py`

### Task 4.7: Implement output formatters

- **Description**: JSON, table, and simple output modes
- **Dependencies**: Task 4.4
- **Acceptance Criteria**:
  - [ ] JSON: full FourKResult as JSON
  - [ ] Table: pretty rich table with key fields
  - [ ] Simple: `<id>: 4K available` or `<id>: No 4K`
- **Files**: `src/findarr/cli.py`

### Task 4.8: Add CLI tests

- **Description**: Test CLI commands with mocked checker
- **Dependencies**: Task 4.7
- **Acceptance Criteria**:
  - [ ] Test check movie command
  - [ ] Test check series command with options
  - [ ] Test batch check
  - [ ] Test all output formats
  - [ ] Test config loading
- **Files**: `tests/test_cli.py`

### Phase 4 Deliverables

- [ ] Config loader
- [ ] CLI commands: check movie, check series, batch
- [ ] Output formatters
- [ ] CLI tests

### Phase 4 Exit Criteria

- [ ] `findarr --help` works after install
- [ ] All CLI tests pass

---

## Phase 5: Polish and Release

**Goal**: Documentation, final testing, and release preparation.

### Task 5.1: Update README with full usage

- **Description**: Comprehensive README with all features documented
- **Dependencies**: Phase 4 complete
- **Acceptance Criteria**:
  - [ ] Installation instructions (library and CLI)
  - [ ] Quick start examples
  - [ ] Full API documentation
  - [ ] CLI reference
  - [ ] Configuration guide
- **Files**: `README.md`

### Task 5.2: Add docstrings to public API

- **Description**: Complete docstrings for all public classes and methods
- **Dependencies**: Phase 4 complete
- **Acceptance Criteria**:
  - [ ] All public classes have docstrings
  - [ ] All public methods have docstrings with Args, Returns, Raises
  - [ ] Examples in docstrings where helpful
- **Files**: All source files

### Task 5.3: Integration tests

- **Description**: Tests against real Radarr/Sonarr (skipped in CI)
- **Dependencies**: Phase 4 complete
- **Acceptance Criteria**:
  - [ ] Test against local Radarr instance
  - [ ] Test against local Sonarr instance
  - [ ] Marked with `@pytest.mark.integration`
  - [ ] Skip if env vars not set
- **Files**: `tests/test_integration.py`

### Task 5.4: Achieve test coverage target

- **Description**: Ensure 90%+ test coverage
- **Dependencies**: Task 5.3
- **Acceptance Criteria**:
  - [ ] `pytest --cov=findarr --cov-report=term-missing` shows >90%
  - [ ] Critical paths have 100% coverage
- **Files**: Tests

### Task 5.5: Final type checking and linting

- **Description**: Clean mypy and ruff reports
- **Dependencies**: Task 5.4
- **Acceptance Criteria**:
  - [ ] `mypy src --strict` passes with no errors
  - [ ] `ruff check src tests` passes with no errors
  - [ ] `ruff format --check src tests` passes
- **Files**: All source files

### Task 5.6: Update pyproject.toml for release

- **Description**: Finalize package metadata
- **Dependencies**: Task 5.5
- **Acceptance Criteria**:
  - [ ] Version set to 1.0.0
  - [ ] Description, keywords, classifiers complete
  - [ ] URLs (homepage, repository) set
  - [ ] License classifier set
- **Files**: `pyproject.toml`

### Task 5.7: Create CHANGELOG entry

- **Description**: Document v1.0.0 changes
- **Dependencies**: Task 5.6
- **Acceptance Criteria**:
  - [ ] CHANGELOG.md with v1.0.0 section
  - [ ] All features listed under Added
  - [ ] Breaking changes noted (if any)
- **Files**: `CHANGELOG.md`

### Phase 5 Deliverables

- [ ] Complete documentation
- [ ] Integration tests
- [ ] 90%+ test coverage
- [ ] Release-ready package

### Phase 5 Exit Criteria

- [ ] All tests pass
- [ ] All type checks pass
- [ ] All linting passes
- [ ] Documentation complete
- [ ] Ready for `pip install` or PyPI upload

---

## Dependency Graph

```
Phase 1: Infrastructure
  Task 1.1 ──────────────────────────────────────────────────┐
           ↓                                                  │
  Task 1.2 ─────────────────────┐                            │
           ↓                    │                            │
  Task 1.3 ─────────────────────┤                            │
           ↓                    │                            │
  Task 1.4 ─────────────────────┤                            │
                                ↓                            │
                       Task 1.5 + Task 1.6 (parallel)        │
                                ↓                            │
                          Task 1.7                           │
                                                             │
Phase 2: Sonarr Enhancement                                  │
  Task 2.1 ─────────────────────┐                            │
           ↓                    │                            │
  Task 2.2 ─────────────────────┤                            │
           ↓                    │                            │
  Task 2.3 ─────────────────────┤                            │
           ↓                    │                            │
  Task 2.4 ─────────────────────┤                            │
           ↓                    │                            │
  Task 2.5 ─────────────────────┤                            │
                                ↓                            │
                          Task 2.6                           │
                                                             │
Phase 3: Checker Enhancement                                 │
  Task 3.1 ─────────────────────┐                            │
           ↓                    │                            │
  Task 3.2 ─────────────────────┤                            │
           ↓                    │                            │
  Task 3.3 ─────────────────────┤                            │
           ↓                    │                            │
  Task 3.4 ─────────────────────┤                            │
                                ↓                            │
                          Task 3.5                           │
                                                             │
Phase 4: CLI                                                 │
  Task 4.1 ←─────────────────────────────────────────────────┘
           ↓
  Task 4.2 ─────────────────────┐
           ↓                    │
  Task 4.3 ─────────────────────┤
           ↓                    │
  Task 4.4 + Task 4.5 (parallel)│
           ↓                    │
  Task 4.6 ─────────────────────┤
           ↓                    │
  Task 4.7 ─────────────────────┤
                                ↓
                          Task 4.8

Phase 5: Polish
  Task 5.1 + Task 5.2 + Task 5.3 (parallel)
                   ↓
             Task 5.4
                   ↓
             Task 5.5
                   ↓
             Task 5.6
                   ↓
             Task 5.7
```

## Risk Mitigation Tasks

| Risk | Mitigation Task | Phase |
|------|-----------------|-------|
| Radarr/Sonarr API changes | Pin to v3, add version check on init | Phase 1 |
| Indexer returns no results | Document behavior, test empty response | Phase 2 |
| 4K detection false negatives | Test multiple detection methods | Phase 3 |
| CLI config complexity | Provide example config file | Phase 4 |

## Testing Checklist

- [ ] Unit tests for BaseArrClient retry logic
- [ ] Unit tests for BaseArrClient caching
- [ ] Unit tests for Sonarr episode models
- [ ] Unit tests for sampling strategies
- [ ] Unit tests for CLI commands
- [ ] Integration tests for Radarr (manual)
- [ ] Integration tests for Sonarr (manual)
- [ ] End-to-end CLI test

## Documentation Tasks

- [ ] Update README with all features
- [ ] Add CLI usage section to README
- [ ] Add configuration reference to README
- [ ] Docstrings on all public API
- [ ] Example config file in repo

## Launch Checklist

- [ ] All tests passing
- [ ] mypy strict passing
- [ ] ruff check passing
- [ ] Documentation complete
- [ ] CHANGELOG.md updated
- [ ] Version set to 1.0.0
- [ ] Ready for PyPI (optional)
