# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0](https://github.com/dabigc/4k-findarr/compare/v0.1.1...v0.2.0) (2025-12-24)


### Features

* add batch operations, tagging, and state management ([#6](https://github.com/dabigc/4k-findarr/issues/6)) ([6ab6e8f](https://github.com/dabigc/4k-findarr/commit/6ab6e8f4c75d4de9f301fdce6dc13b507482dace))
* add Release Please for automated release tagging ([#11](https://github.com/dabigc/4k-findarr/issues/11)) ([9c043fb](https://github.com/dabigc/4k-findarr/commit/9c043fbc9bad6145d1224a747b032fd701c94c31))
* add scheduler for automated batch operations ([#9](https://github.com/dabigc/4k-findarr/issues/9)) ([363031c](https://github.com/dabigc/4k-findarr/commit/363031cb8cb516190d281df045a24e801dc06dda))
* add webhook endpoint and Docker container with CI/CD ([#8](https://github.com/dabigc/4k-findarr/issues/8)) ([24c6ed9](https://github.com/dabigc/4k-findarr/commit/24c6ed9ac4d13d45a48cde509cbab6e5be474d40))
* findarr 4K availability checker library ([#1](https://github.com/dabigc/4k-findarr/issues/1)) ([3b0782d](https://github.com/dabigc/4k-findarr/commit/3b0782de934329ad8c7ea58f2e7caf6c84b1658d))


### Bug Fixes

* chain release workflow from release-please to trigger Docker builds ([#14](https://github.com/dabigc/4k-findarr/issues/14)) ([411744e](https://github.com/dabigc/4k-findarr/commit/411744e4514c382aafb557e03babc546f95f35e1))
* exclude non-code paths from triggering releases ([#19](https://github.com/dabigc/4k-findarr/issues/19)) ([cb01262](https://github.com/dabigc/4k-findarr/commit/cb01262476611e3df507b0319c045254c20be4be))
* include scheduler extra in Docker image ([#12](https://github.com/dabigc/4k-findarr/issues/12)) ([94b4609](https://github.com/dabigc/4k-findarr/commit/94b460971134133034dd747b476e8bfc10518c8c))

## [0.1.1](https://github.com/dabigc/4k-findarr/compare/v0.1.0...v0.1.1) (2025-12-23)


### Bug Fixes

* chain release workflow from release-please to trigger Docker builds ([#14](https://github.com/dabigc/4k-findarr/issues/14)) ([e1d4935](https://github.com/dabigc/4k-findarr/commit/e1d4935ede6e6bb4362547583d1c4d5e4ecd87b3))

## [0.1.0](https://github.com/dabigc/4k-findarr/compare/v0.0.2...v0.1.0) (2025-12-23)


### Features

* add Release Please for automated release tagging ([#11](https://github.com/dabigc/4k-findarr/issues/11)) ([9518d90](https://github.com/dabigc/4k-findarr/commit/9518d907f704936487f404774766d96057a7e5ea))


### Bug Fixes

* include scheduler extra in Docker image ([#12](https://github.com/dabigc/4k-findarr/issues/12)) ([8ca02a2](https://github.com/dabigc/4k-findarr/commit/8ca02a23c6f2148b7382f5d60e641f60c654a705))

## [Unreleased]

## [0.0.2] - 2025-12-23

### Added

- **Scheduler Module** (`pip install findarr[scheduler]`)
  - Built-in job scheduler using APScheduler for automated batch operations
  - Support for cron expressions and interval-based triggers
  - Configurable schedules in config.toml with `[[scheduler.schedules]]` array
  - Dynamic schedule management via CLI commands
  - Schedule CLI commands:
    - `findarr schedule list` - List all configured schedules
    - `findarr schedule add <name>` - Add a new dynamic schedule
    - `findarr schedule remove <name>` - Remove a dynamic schedule
    - `findarr schedule enable/disable <name>` - Toggle schedule status
    - `findarr schedule run <name>` - Execute a schedule immediately
    - `findarr schedule history` - View run history with status and statistics
    - `findarr schedule export --format cron|systemd` - Export for external schedulers

- **Server Integration**
  - Scheduler runs alongside webhook server in `findarr serve`
  - New `--scheduler/--no-scheduler` flag to enable/disable scheduler
  - `/status` endpoint for monitoring scheduler state
  - Graceful shutdown with job completion

- **Schedule Features**
  - Full batch parameter support per schedule (batch_size, delay, skip_tagged, etc.)
  - Overlap prevention - skips runs if previous still executing
  - Run history tracking with timestamps, item counts, and errors
  - Automatic history pruning (configurable limit)
  - Export to cron and systemd timer formats

- **Development**
  - Pre-commit hooks for automated linting and type checking
  - Docker Compose configuration with `.env.example`

### Changed

- State file version bumped to v2 with scheduler state fields
- `findarr serve` now shows scheduler status and schedule count

### Dependencies

- Added `apscheduler>=4.0.0a5` for scheduler optional dependency
- Added `croniter>=2.0.0` for cron expression parsing
- Added `pre-commit>=4.0.0` for development

## [0.0.1] - 2025-12-23

### Added

- **Core Library**
  - `FourKChecker` - High-level API for checking 4K availability
  - `RadarrClient` - Async client for Radarr API v3
  - `SonarrClient` - Async client for Sonarr API v3
  - Pydantic models for API responses (`Movie`, `Series`, `Episode`, `Release`)

- **Movie Support**
  - Check movies by numeric ID
  - Check movies by name with fuzzy search
  - Search movies in library by title

- **TV Series Support**
  - Check series by numeric ID or name
  - Configurable sampling strategies:
    - `RECENT` - Check most recent N seasons (default)
    - `DISTRIBUTED` - Check first, middle, and last seasons
    - `ALL` - Check all seasons
  - Episode-level release checking with short-circuit optimization
  - Search series in library by title

- **CLI Interface** (`pip install findarr[cli]`)
  - `findarr check movie <id_or_name>` - Check movie for 4K
  - `findarr check series <id_or_name>` - Check series for 4K
  - `findarr check batch --file <file>` - Batch check from file
  - Multiple output formats: `--format json|table|simple`
  - Strategy selection: `--strategy recent|distributed|all`

- **Batch Operations**
  - `findarr batch check` - Check multiple items for 4K availability
  - `findarr batch tag` - Tag items based on 4K status
  - `findarr batch report` - Generate availability reports
  - Configurable batch size and delay between requests
  - Progress tracking with rich console output

- **Tagging System**
  - Automatic tagging of items based on 4K availability
  - Configurable tag names (`4k-available`, `no-4k`, etc.)
  - Support for both Radarr and Sonarr tagging APIs

- **State Management**
  - Persistent state file for tracking checked items
  - Resume capability for interrupted batch operations
  - Configurable state file location

- **Webhook Server** (`pip install findarr[webhook]`)
  - FastAPI-based webhook endpoint
  - `findarr serve` command to run the server
  - Receive notifications from Radarr/Sonarr
  - Docker container with GitHub Container Registry publishing

- **Configuration**
  - Environment variables: `RADARR_URL`, `RADARR_API_KEY`, `SONARR_URL`, `SONARR_API_KEY`
  - TOML config file support: `~/.config/findarr/config.toml`

- **Infrastructure**
  - Exponential backoff retry with tenacity (network resilience)
  - TTL cache for API responses (5-minute default)
  - Full async/await support with httpx
  - Type annotations and mypy strict mode
  - GitHub Actions CI/CD pipeline
  - Docker image publishing to ghcr.io

### Technical Details

- Python 3.11+ required
- Core dependencies: httpx, pydantic v2, tenacity, cachetools
- CLI dependencies: typer, rich (optional)
- Webhook dependencies: fastapi, uvicorn (optional)
