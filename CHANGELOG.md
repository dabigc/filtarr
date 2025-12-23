# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
