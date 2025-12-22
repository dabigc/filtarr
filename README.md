# findarr

A Python library and CLI for checking 4K availability of media via Radarr/Sonarr search results.

## Quick Start

### 1. Install

```bash
# Install with CLI support
pip install findarr[cli]

# Or for development
pip install -e ".[dev]"
```

### 2. Configure

Set environment variables:

```bash
# Radarr (for movies)
export FINDARR_RADARR_URL="http://localhost:7878"
export FINDARR_RADARR_API_KEY="your-radarr-api-key"

# Sonarr (for TV series)
export FINDARR_SONARR_URL="http://localhost:8989"
export FINDARR_SONARR_API_KEY="your-sonarr-api-key"
```

Or create a config file at `~/.config/findarr/config.toml`:

```toml
[radarr]
url = "http://localhost:7878"
api_key = "your-radarr-api-key"

[sonarr]
url = "http://localhost:8989"
api_key = "your-sonarr-api-key"
```

> Environment variables take precedence over the config file.

### 3. Check 4K Availability

```bash
# Check a movie by Radarr ID
findarr check movie 123

# Check a TV series by Sonarr ID
findarr check series 456

# Check multiple items from a file
findarr check batch --file items.txt
```

## CLI Usage

### Check Movie

```bash
findarr check movie <MOVIE_ID> [OPTIONS]

Options:
  -f, --format [json|table|simple]  Output format (default: table)
```

Example:
```bash
$ findarr check movie 123 --format simple
movie:123: 4K available
```

### Check Series

```bash
findarr check series <SERIES_ID> [OPTIONS]

Options:
  -s, --seasons INTEGER             Seasons to check (default: 3)
  --strategy [recent|distributed|all]  Sampling strategy (default: recent)
  -f, --format [json|table|simple]  Output format (default: table)
```

Strategies:
- `recent` - Check most recent N seasons (fastest)
- `distributed` - Sample across all seasons evenly
- `all` - Check every season (slowest, most thorough)

Example:
```bash
$ findarr check series 456 --strategy recent --seasons 2 --format json
{
  "item_id": 456,
  "item_type": "series",
  "has_4k": true,
  "releases_count": 42,
  "four_k_releases_count": 8,
  "seasons_checked": [3, 4],
  "strategy_used": "recent"
}
```

### Batch Check

```bash
findarr check batch --file <FILE> [OPTIONS]

Options:
  -f, --file PATH                   File with items to check (required)
  --format [json|table|simple]      Output format (default: simple)
  -s, --seasons INTEGER             Seasons to check for series (default: 3)
  --strategy [recent|distributed|all]  Strategy for series (default: recent)
```

Batch file format (one item per line):
```
# Comments start with #
movie:123
movie:456
series:789
```

### Exit Codes

| Code | Meaning |
|------|---------|
| 0    | 4K releases found |
| 1    | No 4K releases found |
| 2    | Error (config, API, etc.) |

Use exit codes in scripts:
```bash
if findarr check movie 123 --format simple; then
  echo "4K is available!"
else
  echo "No 4K found"
fi
```

## Python API

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
from findarr import FourKChecker, SamplingStrategy

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

    # Check a series with sampling strategy
    result = await checker.check_series(
        series_id=456,
        strategy=SamplingStrategy.RECENT,
        seasons_to_check=3,
    )
    print(f"Series has 4K: {result.has_4k}")

asyncio.run(main())
```

## Configuration Reference

### Environment Variables

| Variable | Description |
|----------|-------------|
| `FINDARR_RADARR_URL` | Radarr instance URL (e.g., `http://localhost:7878`) |
| `FINDARR_RADARR_API_KEY` | Radarr API key |
| `FINDARR_SONARR_URL` | Sonarr instance URL (e.g., `http://localhost:8989`) |
| `FINDARR_SONARR_API_KEY` | Sonarr API key |
| `FINDARR_TIMEOUT` | Request timeout in seconds (default: `120`) |

### Config File

Location: `~/.config/findarr/config.toml`

```toml
# Request timeout in seconds (default: 120)
timeout = 120

[radarr]
url = "http://localhost:7878"
api_key = "your-radarr-api-key"

[sonarr]
url = "http://localhost:8989"
api_key = "your-sonarr-api-key"
```

### Timeout Considerations

Searching for releases on popular media (e.g., "The Matrix") can take significant time as Radarr/Sonarr queries multiple indexers. The default timeout is 120 seconds.

**If you're behind a reverse proxy** (nginx, Caddy, Traefik, Nginx Proxy Manager, etc.), you may need to increase the proxy timeout as well. The findarr client timeout won't help if your reverse proxy times out first.

#### Nginx Proxy Manager

Add to the **Advanced** tab of your proxy host:

```nginx
proxy_connect_timeout 300;
proxy_send_timeout 300;
proxy_read_timeout 300;
send_timeout 300;
```

#### Nginx

```nginx
location / {
    proxy_connect_timeout 300;
    proxy_send_timeout 300;
    proxy_read_timeout 300;
    send_timeout 300;
    # ... other proxy settings
}
```

#### Caddy

```
reverse_proxy localhost:7878 {
    transport http {
        read_timeout 300s
        write_timeout 300s
    }
}
```

#### Traefik

```yaml
http:
  middlewares:
    slow-timeout:
      forwardedHeaders:
        trustedIPs: []
  serversTransports:
    slow-transport:
      forwardingTimeouts:
        dialTimeout: 300s
        responseHeaderTimeout: 300s
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
