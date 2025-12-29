# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.1.0](https://github.com/dabigc/filtarr/compare/v2.0.0...v2.1.0) (2025-12-29)


### Features

* clean log output with timestamps and error summaries ([#63](https://github.com/dabigc/filtarr/issues/63)) ([db773a5](https://github.com/dabigc/filtarr/commit/db773a507a04f0a8f2e1e167b7a85120dc027769))

## [2.0.0](https://github.com/dabigc/filtarr/compare/v1.4.0...v2.0.0) (2025-12-28)


### ⚠ BREAKING CHANGES

* `filtarr serve --log-level debug` is now `filtarr --log-level debug serve`

### Features

* add global --log-level flag to CLI ([#61](https://github.com/dabigc/filtarr/issues/61)) ([0f5ce9d](https://github.com/dabigc/filtarr/commit/0f5ce9d31a6a7dd47473d143b41b1fc8eb4a7773))

## [1.4.0](https://github.com/dabigc/filtarr/compare/v1.3.1...v1.4.0) (2025-12-27)


### Features

* Add Docker runtime testing to CI and pre-commit ([#56](https://github.com/dabigc/filtarr/issues/56)) ([170edfc](https://github.com/dabigc/filtarr/commit/170edfc52fce7d2809da2b4c13db9453e27697fd))


### Bug Fixes

* Improve batch error handling and add 502 troubleshooting ([#59](https://github.com/dabigc/filtarr/issues/59)) ([d8d9612](https://github.com/dabigc/filtarr/commit/d8d9612faee4e6cdffb213b60ae11210fe680647))

## [1.3.1](https://github.com/dabigc/filtarr/compare/v1.3.0...v1.3.1) (2025-12-26)


### Bug Fixes

* Convert log level to lowercase for uvicorn compatibility ([#54](https://github.com/dabigc/filtarr/issues/54)) ([9a96d48](https://github.com/dabigc/filtarr/commit/9a96d48f72d60e510cef471a05db1ec4df0ec653))

## [1.3.0](https://github.com/dabigc/filtarr/compare/v1.2.1...v1.3.0) (2025-12-26)


### Features

* Add observability and state management enhancements ([#51](https://github.com/dabigc/filtarr/issues/51)) ([3557259](https://github.com/dabigc/filtarr/commit/35572597e4866674c4dde47fc6e2ddd15803656f))

## [1.2.1](https://github.com/dabigc/filtarr/compare/v1.2.0...v1.2.1) (2025-12-26)


### Performance Improvements

* Phase 1 critical performance fixes ([#48](https://github.com/dabigc/filtarr/issues/48)) ([3e75db9](https://github.com/dabigc/filtarr/commit/3e75db9fcf829a845c5354a797df8153c12cd17d))

## [1.2.0](https://github.com/dabigc/filtarr/compare/v1.1.4...v1.2.0) (2025-12-26)


### Features

* add multi-criteria support beyond 4K ([#42](https://github.com/dabigc/filtarr/issues/42)) ([f0e6532](https://github.com/dabigc/filtarr/commit/f0e65320da45cde91595cbabc419c14015c3ca0c))

## [1.1.4](https://github.com/dabigc/filtarr/compare/v1.1.3...v1.1.4) (2025-12-24)


### Bug Fixes

* **ci:** inline PyPI publishing in release-please workflow ([#39](https://github.com/dabigc/filtarr/issues/39)) ([73507e3](https://github.com/dabigc/filtarr/commit/73507e38bcf7e9d4971f5a6a38fc877c05453095))

## [1.1.3](https://github.com/dabigc/filtarr/compare/v1.1.2...v1.1.3) (2025-12-24)


### Bug Fixes

* **ci:** trigger PyPI publish on release event ([#37](https://github.com/dabigc/filtarr/issues/37)) ([0725199](https://github.com/dabigc/filtarr/commit/07251992b505b2788ec14abea5a923361c446aef))

## [1.1.2](https://github.com/dabigc/filtarr/compare/v1.1.1...v1.1.2) (2025-12-24)


### Bug Fixes

* **ci:** use tag push trigger for PyPI publishing ([#35](https://github.com/dabigc/filtarr/issues/35)) ([e1e1cb6](https://github.com/dabigc/filtarr/commit/e1e1cb637f26660fe4973001b7a06c15b512758e))

## [1.1.1](https://github.com/dabigc/filtarr/compare/v1.1.0...v1.1.1) (2025-12-24)


### Bug Fixes

* clarify docstring wording ([#33](https://github.com/dabigc/filtarr/issues/33)) ([07576f3](https://github.com/dabigc/filtarr/commit/07576f350bad14a586b6f874addb08f200194434))

## [1.1.0](https://github.com/dabigc/filtarr/compare/v1.0.1...v1.1.0) (2025-12-24)


### Features

* add LICENSE, security policy, and dependabot configuration ([#27](https://github.com/dabigc/filtarr/issues/27)) ([9d0fa8b](https://github.com/dabigc/filtarr/commit/9d0fa8bbe8c46c7583a46d03a3865055453b3582))

## [1.0.1](https://github.com/dabigc/filtarr/compare/v1.0.0...v1.0.1) (2025-12-24)


### Bug Fixes

* remove remaining findarr references throughout codebase ([#25](https://github.com/dabigc/filtarr/issues/25)) ([c1b5c3b](https://github.com/dabigc/filtarr/commit/c1b5c3befdbe855b2b8cc0556717d14c77bacff4))

## [1.0.0](https://github.com/dabigc/4k-findarr/compare/v0.1.1...v1.0.0) (2025-12-24)


### ⚠ BREAKING CHANGES

* Package renamed. All imports, CLI commands, env vars updated.

### Features

* add batch operations, tagging, and state management ([#6](https://github.com/dabigc/4k-findarr/issues/6)) ([b43781a](https://github.com/dabigc/4k-findarr/commit/b43781acf6e66bb95fd346851528dc55d760f20c))
* add Release Please for automated release tagging ([#11](https://github.com/dabigc/4k-findarr/issues/11)) ([2afa2e4](https://github.com/dabigc/4k-findarr/commit/2afa2e45f16ae0ddba8ba47affd84c0814bd21fe))
* add scheduler for automated batch operations ([#9](https://github.com/dabigc/4k-findarr/issues/9)) ([77dca9c](https://github.com/dabigc/4k-findarr/commit/77dca9cda7366ad4f4c100af8bd7fba9e93a8458))
* add webhook endpoint and Docker container with CI/CD ([#8](https://github.com/dabigc/4k-findarr/issues/8)) ([bde879f](https://github.com/dabigc/4k-findarr/commit/bde879f22f7d12fa80050bdc3c935b6d1fa064dc))
* findarr 4K availability checker library ([#1](https://github.com/dabigc/4k-findarr/issues/1)) ([21961f6](https://github.com/dabigc/4k-findarr/commit/21961f65ef91faa1f078f7dc4033efda6b3309a7))
* rename package from findarr to filtarr with generic search criteria ([#23](https://github.com/dabigc/4k-findarr/issues/23)) ([31479cc](https://github.com/dabigc/4k-findarr/commit/31479cc3ce6380d44a394acfd238db1ee63e8ca0))


### Bug Fixes

* chain release workflow from release-please to trigger Docker builds ([#14](https://github.com/dabigc/4k-findarr/issues/14)) ([5a27363](https://github.com/dabigc/4k-findarr/commit/5a2736378962468830e26e86102a4d8d439d5b65))
* exclude non-code paths from triggering releases ([#19](https://github.com/dabigc/4k-findarr/issues/19)) ([351a533](https://github.com/dabigc/4k-findarr/commit/351a53310e2381dac8730af3fbf0a712a1a3dfa6))
* include scheduler extra in Docker image ([#12](https://github.com/dabigc/4k-findarr/issues/12)) ([0835992](https://github.com/dabigc/4k-findarr/commit/083599293149b3f4327822f08392a9ae1df6bd7e))

## [0.1.1](https://github.com/dabigc/filtarr/compare/v0.1.0...v0.1.1) (2025-12-23)


### Bug Fixes

* chain release workflow from release-please to trigger Docker builds ([#14](https://github.com/dabigc/filtarr/issues/14)) ([e1d4935](https://github.com/dabigc/filtarr/commit/e1d4935ede6e6bb4362547583d1c4d5e4ecd87b3))

## [0.1.0](https://github.com/dabigc/filtarr/compare/v0.0.2...v0.1.0) (2025-12-23)


### Features

* add Release Please for automated release tagging ([#11](https://github.com/dabigc/filtarr/issues/11)) ([9518d90](https://github.com/dabigc/filtarr/commit/9518d907f704936487f404774766d96057a7e5ea))


### Bug Fixes

* include scheduler extra in Docker image ([#12](https://github.com/dabigc/filtarr/issues/12)) ([8ca02a2](https://github.com/dabigc/filtarr/commit/8ca02a23c6f2148b7382f5d60e641f60c654a705))

## [Unreleased]

## [0.0.2] - 2025-12-23

### Added

- **Scheduler Module** (`pip install filtarr[scheduler]`)
  - Built-in job scheduler using APScheduler for automated batch operations
  - Support for cron expressions and interval-based triggers
  - Configurable schedules in config.toml with `[[scheduler.schedules]]` array
  - Dynamic schedule management via CLI commands
  - Schedule CLI commands:
    - `filtarr schedule list` - List all configured schedules
    - `filtarr schedule add <name>` - Add a new dynamic schedule
    - `filtarr schedule remove <name>` - Remove a dynamic schedule
    - `filtarr schedule enable/disable <name>` - Toggle schedule status
    - `filtarr schedule run <name>` - Execute a schedule immediately
    - `filtarr schedule history` - View run history with status and statistics
    - `filtarr schedule export --format cron|systemd` - Export for external schedulers

- **Server Integration**
  - Scheduler runs alongside webhook server in `filtarr serve`
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
- `filtarr serve` now shows scheduler status and schedule count

### Dependencies

- Added `apscheduler>=4.0.0a5` for scheduler optional dependency
- Added `croniter>=2.0.0` for cron expression parsing
- Added `pre-commit>=4.0.0` for development

## [0.0.1] - 2025-12-23

### Added

- **Core Library**
  - `ReleaseChecker` - High-level API for checking 4K availability
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

- **CLI Interface** (`pip install filtarr[cli]`)
  - `filtarr check movie <id_or_name>` - Check movie for 4K
  - `filtarr check series <id_or_name>` - Check series for 4K
  - `filtarr check batch --file <file>` - Batch check from file
  - Multiple output formats: `--format json|table|simple`
  - Strategy selection: `--strategy recent|distributed|all`

- **Batch Operations**
  - `filtarr batch check` - Check multiple items for 4K availability
  - `filtarr batch tag` - Tag items based on 4K status
  - `filtarr batch report` - Generate availability reports
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

- **Webhook Server** (`pip install filtarr[webhook]`)
  - FastAPI-based webhook endpoint
  - `filtarr serve` command to run the server
  - Receive notifications from Radarr/Sonarr
  - Docker container with GitHub Container Registry publishing

- **Configuration**
  - Environment variables: `RADARR_URL`, `RADARR_API_KEY`, `SONARR_URL`, `SONARR_API_KEY`
  - TOML config file support: `~/.config/filtarr/config.toml`

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
