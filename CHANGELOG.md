# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2024-12-22

### Added

- Initial release of findarr library
- **Core Features**
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

- **Configuration**
  - Environment variables: `RADARR_URL`, `RADARR_API_KEY`, `SONARR_URL`, `SONARR_API_KEY`
  - TOML config file support: `~/.config/findarr/config.toml`

- **Infrastructure**
  - Exponential backoff retry with tenacity (network resilience)
  - TTL cache for API responses (5-minute default)
  - Full async/await support with httpx
  - Type annotations and mypy strict mode
  - 91% test coverage with 109 tests

### Technical Details

- Python 3.11+ required
- Core dependencies: httpx, pydantic v2, tenacity, cachetools
- CLI dependencies: typer, rich (optional)
