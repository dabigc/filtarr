---
document_type: architecture
project_id: SPEC-2025-12-21-001
version: 1.0.0
last_updated: 2025-12-21T23:55:00Z
status: draft
---

# findarr - Technical Architecture

## System Overview

findarr is a Python library that queries Radarr and Sonarr APIs to determine 4K availability for movies and TV shows. It provides both a programmatic API and an optional CLI interface.

### Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              User Applications                               │
├─────────────────────────────────────────────────────────────────────────────┤
│  Python Scripts  │  Webhook Services  │  Media Dashboards  │  CLI Users    │
└────────┬─────────┴────────┬───────────┴─────────┬──────────┴───────┬───────┘
         │                  │                     │                  │
         ▼                  ▼                     ▼                  ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           findarr Library                                    │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │                         Public API Layer                              │   │
│  │  ┌─────────────┐  ┌──────────────┐  ┌──────────────┐                 │   │
│  │  │FourKChecker │  │ RadarrClient │  │ SonarrClient │                 │   │
│  │  │  (facade)   │  │   (movies)   │  │  (TV shows)  │                 │   │
│  │  └──────┬──────┘  └──────┬───────┘  └──────┬───────┘                 │   │
│  └─────────┼────────────────┼─────────────────┼─────────────────────────┘   │
│            │                │                 │                              │
│  ┌─────────┼────────────────┼─────────────────┼─────────────────────────┐   │
│  │         ▼                ▼                 ▼                          │   │
│  │  ┌─────────────────────────────────────────────────────────────────┐ │   │
│  │  │                      BaseArrClient                              │ │   │
│  │  │  ┌───────────┐  ┌───────────┐  ┌───────────┐                   │ │   │
│  │  │  │  Retry    │  │   Cache   │  │   HTTP    │                   │ │   │
│  │  │  │ (tenacity)│  │(cachetools)│  │  (httpx)  │                   │ │   │
│  │  │  └───────────┘  └───────────┘  └───────────┘                   │ │   │
│  │  └─────────────────────────────────────────────────────────────────┘ │   │
│  │                         Infrastructure Layer                          │   │
│  └───────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
│  ┌───────────────────────────────────────────────────────────────────────┐   │
│  │                          Models Layer                                  │   │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐              │   │
│  │  │ Release  │  │ Quality  │  │ Episode  │  │  Series  │              │   │
│  │  └──────────┘  └──────────┘  └──────────┘  └──────────┘              │   │
│  └───────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
         │                                                         │
         ▼                                                         ▼
┌─────────────────────────┐                         ┌─────────────────────────┐
│      Radarr API         │                         │      Sonarr API         │
│  /api/v3/release        │                         │  /api/v3/release        │
│  /api/v3/movie          │                         │  /api/v3/episode        │
└─────────────────────────┘                         │  /api/v3/series         │
                                                    └─────────────────────────┘
```

### Key Design Decisions

1. **Async-first**: All I/O operations are async to support non-blocking integrations
2. **Per-client caching**: Each client instance maintains its own cache for isolation
3. **Multiple 4K detection methods**: Resolution field → quality name → title parsing
4. **Configurable sampling**: TV show episode checking strategy is caller-configurable

## Component Design

### Component 1: FourKChecker (Facade)

- **Purpose**: High-level orchestrator for 4K availability checks
- **Responsibilities**:
  - Coordinate movie checks via RadarrClient
  - Coordinate series checks via SonarrClient with episode sampling
  - Return unified result objects
- **Interfaces**:
  - `check_movie(movie_id: int) -> FourKResult`
  - `check_series(series_id: int, seasons_to_check: int = 3, strategy: SamplingStrategy = SamplingStrategy.RECENT) -> FourKResult`
- **Dependencies**: RadarrClient, SonarrClient
- **Technology**: Pure Python, Pydantic models

### Component 2: RadarrClient

- **Purpose**: Interface with Radarr API for movie release searches
- **Responsibilities**:
  - Fetch releases for a movie ID
  - Detect 4K releases from results
  - Handle caching and retries
- **Interfaces**:
  - `get_releases(movie_id: int) -> list[Release]`
  - `has_4k_releases(movie_id: int) -> bool`
  - `get_movie(movie_id: int) -> Movie` (for metadata)
- **Dependencies**: BaseArrClient (inherits)
- **Technology**: httpx, tenacity, cachetools

### Component 3: SonarrClient

- **Purpose**: Interface with Sonarr API for TV series release searches
- **Responsibilities**:
  - Fetch series metadata and episode lists
  - Fetch releases for specific episodes
  - Determine latest aired episode
  - Implement episode sampling strategies
- **Interfaces**:
  - `get_series(series_id: int) -> Series`
  - `get_episodes(series_id: int) -> list[Episode]`
  - `get_episode_releases(episode_id: int) -> list[Release]`
  - `get_latest_aired_episode(series_id: int) -> Episode | None`
  - `has_4k_releases_for_episode(episode_id: int) -> bool`
- **Dependencies**: BaseArrClient (inherits)
- **Technology**: httpx, tenacity, cachetools

### Component 4: BaseArrClient (Abstract)

- **Purpose**: Shared infrastructure for Radarr/Sonarr clients
- **Responsibilities**:
  - HTTP client management with connection pooling
  - Retry logic with exponential backoff
  - TTL caching layer
  - Authentication handling
  - Error normalization
- **Interfaces**:
  - `_get(endpoint: str, params: dict) -> Any` (cached)
  - `_get_uncached(endpoint: str, params: dict) -> Any`
  - `_invalidate_cache(key: str) -> None`
- **Dependencies**: httpx, tenacity, cachetools
- **Technology**: Abstract base class pattern

### Component 5: CLI Module

- **Purpose**: Command-line interface for interactive use
- **Responsibilities**:
  - Parse configuration from env vars and config file
  - Execute check commands
  - Format output (JSON, table, simple)
- **Interfaces**:
  - `findarr check movie <id> [--format json|table|simple]`
  - `findarr check series <id> [--format json|table|simple]`
  - `findarr check --file <path> [--format json|table|simple]`
- **Dependencies**: FourKChecker, typer, rich
- **Technology**: typer CLI framework

## Data Design

### Data Models

```python
# models/common.py
class Quality(BaseModel):
    id: int
    name: str
    resolution: int | None = None

    def is_4k(self) -> bool:
        """Check if this quality represents 4K/2160p."""
        if self.resolution == 2160:
            return True
        name_lower = self.name.lower()
        return "2160p" in name_lower or "4k" in name_lower

class Release(BaseModel):
    guid: str
    title: str
    indexer: str
    size: int
    quality: Quality
    seeders: int | None = None
    age_days: int | None = None

    def is_4k(self) -> bool:
        """Check if this release is 4K via quality or title."""
        if self.quality.is_4k():
            return True
        title_lower = self.title.lower()
        return "2160p" in title_lower or "4k" in title_lower

# models/sonarr.py
class Episode(BaseModel):
    id: int
    series_id: int
    season_number: int
    episode_number: int
    title: str
    air_date: date | None = None
    air_date_utc: datetime | None = None
    has_file: bool = False
    monitored: bool = True

class Season(BaseModel):
    season_number: int
    monitored: bool
    episode_count: int
    episode_file_count: int

class Series(BaseModel):
    id: int
    title: str
    seasons: list[Season]

    @property
    def season_count(self) -> int:
        return len([s for s in self.seasons if s.season_number > 0])

# models/radarr.py
class Movie(BaseModel):
    id: int
    title: str
    tmdb_id: int | None = None
    imdb_id: str | None = None
    year: int | None = None

# checker.py
class SamplingStrategy(Enum):
    RECENT = "recent"           # Most recent N seasons
    DISTRIBUTED = "distributed" # First, middle, last
    ALL = "all"                 # All seasons

@dataclass
class FourKResult:
    item_id: int
    item_type: Literal["movie", "series"]
    has_4k: bool
    releases: list[Release]
    episodes_checked: list[int] | None = None  # For series

    @property
    def four_k_releases(self) -> list[Release]:
        return [r for r in self.releases if r.is_4k()]
```

### Data Flow

```
┌──────────────────────────────────────────────────────────────────────────┐
│                           Movie Check Flow                                │
└──────────────────────────────────────────────────────────────────────────┘

User calls: checker.check_movie(movie_id=123)
                │
                ▼
        ┌───────────────┐
        │ FourKChecker  │
        │ check_movie() │
        └───────┬───────┘
                │
                ▼
        ┌───────────────┐     ┌─────────────┐
        │ RadarrClient  │────▶│    Cache    │ (TTL check)
        │ get_releases()│     └──────┬──────┘
        └───────┬───────┘            │
                │                    │ cache miss
                ▼                    ▼
        ┌───────────────┐     ┌─────────────┐
        │   Retry       │────▶│   httpx     │
        │  (tenacity)   │     │ GET /release│
        └───────┬───────┘     └──────┬──────┘
                │                    │
                ▼                    ▼
        ┌───────────────┐     ┌─────────────┐
        │ Parse to      │◀────│  Radarr API │
        │ Release[]     │     │  Response   │
        └───────┬───────┘     └─────────────┘
                │
                ▼
        ┌───────────────┐
        │ Store in      │
        │ Cache (TTL)   │
        └───────┬───────┘
                │
                ▼
        ┌───────────────┐
        │ Filter 4K     │
        │ Build Result  │
        └───────┬───────┘
                │
                ▼
        Return FourKResult(has_4k=True/False, releases=[...])


┌──────────────────────────────────────────────────────────────────────────┐
│                          Series Check Flow                                │
└──────────────────────────────────────────────────────────────────────────┘

User calls: checker.check_series(series_id=456, seasons_to_check=3)
                │
                ▼
        ┌────────────────────┐
        │   FourKChecker     │
        │   check_series()   │
        └─────────┬──────────┘
                  │
        ┌─────────┴─────────┐
        │                   │
        ▼                   ▼
┌───────────────┐   ┌───────────────┐
│ get_series()  │   │ get_episodes()│
│ (metadata)    │   │ (all episodes)│
└───────┬───────┘   └───────┬───────┘
        │                   │
        ▼                   ▼
┌───────────────┐   ┌───────────────────────┐
│ Season count  │   │ Filter: aired,        │
│ (for bounds)  │   │ sort by air_date desc │
└───────┬───────┘   └───────────┬───────────┘
        │                       │
        └───────────┬───────────┘
                    │
                    ▼
        ┌───────────────────────┐
        │ Apply sampling        │
        │ strategy to select    │
        │ episodes to check     │
        └───────────┬───────────┘
                    │
        ┌───────────┴───────────┐
        │   For each episode    │
        │   (short-circuit on   │
        │   first 4K found)     │
        └───────────┬───────────┘
                    │
                    ▼
        ┌───────────────────────┐
        │ get_episode_releases()│
        │ (with caching)        │
        └───────────┬───────────┘
                    │
                    ▼
        ┌───────────────────────┐
        │ Check for 4K releases │
        │ If found: return True │
        │ Else: continue        │
        └───────────┬───────────┘
                    │
                    ▼
        Return FourKResult(has_4k=..., episodes_checked=[...])
```

### Storage Strategy

- **Primary Store**: None (library is stateless)
- **Caching**: In-memory TTLCache per client instance
  - Default TTL: 300 seconds (5 minutes)
  - Configurable via client initialization
  - Keys: `f"{endpoint}:{sorted_params}"`
- **File Storage**: CLI config file only (`~/.config/findarr/config.toml`)

## API Design

### Library API Overview

```python
from findarr import FourKChecker, RadarrClient, SonarrClient, SamplingStrategy

# Direct client usage
async with RadarrClient(
    base_url="http://radarr:7878",
    api_key="your-api-key",
    cache_ttl=300,
    max_retries=3
) as radarr:
    releases = await radarr.get_releases(movie_id=123)
    has_4k = any(r.is_4k() for r in releases)

# Orchestrator usage
async with FourKChecker(
    radarr_url="http://radarr:7878",
    radarr_api_key="radarr-key",
    sonarr_url="http://sonarr:8989",
    sonarr_api_key="sonarr-key"
) as checker:
    movie_result = await checker.check_movie(123)
    series_result = await checker.check_series(
        456,
        seasons_to_check=3,
        strategy=SamplingStrategy.RECENT
    )
```

### CLI Interface

```bash
# Environment setup
export FINDARR_RADARR_URL="http://radarr:7878"
export FINDARR_RADARR_API_KEY="your-radarr-key"
export FINDARR_SONARR_URL="http://sonarr:8989"
export FINDARR_SONARR_API_KEY="your-sonarr-key"

# Single checks
findarr check movie 123
findarr check series 456 --seasons 5

# Batch check
findarr check --file items.txt --format json

# Output formats
findarr check movie 123 --format table   # Pretty table
findarr check movie 123 --format json    # JSON object
findarr check movie 123 --format simple  # "123: 4K available" or "123: No 4K"
```

### Error Types

```python
class FindarrError(Exception):
    """Base exception for all findarr errors."""

class ConnectionError(FindarrError):
    """Failed to connect to Radarr/Sonarr."""

class AuthenticationError(FindarrError):
    """Invalid API key or unauthorized."""

class NotFoundError(FindarrError):
    """Requested movie/series/episode not found."""

class RateLimitError(FindarrError):
    """Too many requests (after retries exhausted)."""

class ConfigurationError(FindarrError):
    """Invalid configuration."""
```

## Security Design

### Authentication

- API keys passed via `X-Api-Key` header (Radarr/Sonarr standard)
- Keys loaded from environment variables or config file
- Config file permissions should be 600 (user-only read/write)

### Data Protection

- No sensitive data stored in cache (only release metadata)
- API keys never logged, even at DEBUG level
- Error messages sanitize URLs to remove API keys if accidentally included

### Security Considerations

- **HTTPS by default**: Warn if HTTP used (but allow for local instances)
- **Certificate verification**: Enabled by default, configurable for self-signed certs
- **No credential exposure**: API keys masked in logs and error traces

## Reliability & Operations

### Retry Strategy

```python
@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception_type((
        httpx.ConnectError,
        httpx.ConnectTimeout,
        httpx.ReadTimeout,
    )) | retry_if_result(lambda r: r.status_code in (429, 500, 502, 503, 504)),
    before_sleep=before_sleep_log(logger, logging.WARNING)
)
async def _request(self, method: str, url: str, **kwargs) -> httpx.Response:
    ...
```

### Failure Modes

| Failure | Impact | Recovery |
|---------|--------|----------|
| Radarr/Sonarr unreachable | Cannot check items | Retry with backoff; raise ConnectionError after exhaustion |
| Invalid API key | All requests fail | Raise AuthenticationError immediately (no retry) |
| Movie/Series not found | Single item fails | Raise NotFoundError; caller decides handling |
| Rate limited (429) | Temporary block | Retry with backoff; raise RateLimitError after exhaustion |
| Indexer returns no releases | No 4K data | Return has_4k=False with empty releases list |
| Network timeout | Request fails | Retry with backoff |

### Logging

```python
import structlog

logger = structlog.get_logger("findarr")

# Log levels:
# DEBUG: All HTTP requests/responses (sanitized)
# INFO: Check operations started/completed
# WARNING: Retries, cache misses on hot paths
# ERROR: Failures after retry exhaustion
```

## Testing Strategy

### Unit Testing

- Mock httpx responses with respx
- Test all Pydantic model validation
- Test 4K detection logic with edge cases
- Test caching behavior (hits, misses, expiration)
- Test retry behavior with simulated failures

### Integration Testing

- Marked with `@pytest.mark.integration`
- Require live Radarr/Sonarr instances
- Test actual API communication
- Verify response parsing against real data

### Test Coverage

- Target: 90%+ line coverage
- Required: 100% coverage on public API
- Required: 100% coverage on 4K detection logic

## Deployment Considerations

### Installation

```bash
# Library only
pip install findarr

# With CLI
pip install findarr[cli]

# Development
pip install findarr[dev]
```

### Configuration

```toml
# ~/.config/findarr/config.toml
[radarr]
url = "http://radarr:7878"
api_key = "your-radarr-api-key"

[sonarr]
url = "http://sonarr:8989"
api_key = "your-sonarr-api-key"

[cache]
ttl_seconds = 300

[retry]
max_attempts = 3
```

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `FINDARR_RADARR_URL` | Radarr base URL | None |
| `FINDARR_RADARR_API_KEY` | Radarr API key | None |
| `FINDARR_SONARR_URL` | Sonarr base URL | None |
| `FINDARR_SONARR_API_KEY` | Sonarr API key | None |
| `FINDARR_CACHE_TTL` | Cache TTL in seconds | 300 |
| `FINDARR_MAX_RETRIES` | Max retry attempts | 3 |
| `FINDARR_CONFIG_PATH` | Config file path | ~/.config/findarr/config.toml |

## Future Considerations

1. **Multi-instance support**: Check against multiple Radarr/Sonarr instances
2. **Prowlarr integration**: Query indexers directly via Prowlarr
3. **Custom quality profiles**: User-defined 4K detection rules
4. **Webhook mode**: Listen for Radarr/Sonarr webhooks and check automatically
5. **Prometheus metrics**: Expose metrics for monitoring integrations
