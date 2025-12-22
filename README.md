# findarr

A Python library for checking 4K availability of media via Radarr/Sonarr search results.

## Installation

```bash
pip install findarr
```

Or for development:

```bash
pip install -e ".[dev]"
```

## Usage

### Check movie 4K availability (Radarr)

```python
import asyncio
from findarr import RadarrClient

async def main():
    async with RadarrClient("http://localhost:7878", "your-api-key") as client:
        # Check if movie ID 123 has 4K releases available
        has_4k = await client.has_4k_releases(movie_id=123)
        print(f"4K available: {has_4k}")

        # Get all releases for detailed inspection
        releases = await client.get_movie_releases(movie_id=123)
        for release in releases:
            if release.is_4k():
                print(f"4K: {release.title} ({release.indexer})")

asyncio.run(main())
```

### Check series 4K availability (Sonarr)

```python
import asyncio
from findarr import SonarrClient

async def main():
    async with SonarrClient("http://localhost:8989", "your-api-key") as client:
        has_4k = await client.has_4k_releases(series_id=456)
        print(f"4K available: {has_4k}")

asyncio.run(main())
```

### Combined checker

```python
import asyncio
from findarr import FourKChecker

async def main():
    checker = FourKChecker(
        radarr_url="http://localhost:7878",
        radarr_api_key="your-radarr-key",
        sonarr_url="http://localhost:8989",
        sonarr_api_key="your-sonarr-key",
    )

    # Check a movie
    result = await checker.check_movie(movie_id=123)
    print(f"Movie has 4K: {result.has_4k}")
    print(f"4K releases: {len(result.four_k_releases)}")

    # Check a series
    result = await checker.check_series(series_id=456)
    print(f"Series has 4K: {result.has_4k}")

asyncio.run(main())
```

## Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Run tests with coverage
pytest --cov=findarr --cov-report=term-missing

# Lint
ruff check src tests

# Format
ruff format src tests

# Type check
mypy src
```

## License

MIT
