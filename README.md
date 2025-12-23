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

Process your entire library or a subset with automatic tagging and resume support.

```bash
findarr check batch [OPTIONS]

Options:
  -f, --file PATH                   File with items to check (optional)
  --all-movies                      Check all movies in Radarr
  --all-series                      Check all series in Sonarr
  --batch-size INTEGER              Max items per run (0=unlimited, default: 0)
  -d, --delay FLOAT                 Delay between checks in seconds (default: 0.5)
  --skip-tagged/--no-skip-tagged    Skip items with existing 4k tags (default: skip)
  --resume/--no-resume              Resume interrupted batch run (default: resume)
  --no-tag                          Disable automatic tagging
  --dry-run                         Show what would be tagged without making changes
  --format [json|table|simple]      Output format (default: simple)
  -s, --seasons INTEGER             Seasons to check for series (default: 3)
  --strategy [recent|distributed|all]  Strategy for series (default: recent)
```

Examples:
```bash
# Check all movies and tag them
findarr check batch --all-movies

# Check all movies, 100 at a time (good for large libraries)
findarr check batch --all-movies --batch-size 100

# Check all series with 1 second delay between checks
findarr check batch --all-series --delay 1.0

# Check specific items from a file
findarr check batch --file items.txt

# Preview what would be tagged (no changes made)
findarr check batch --all-movies --dry-run
```

Batch file format (one item per line):
```
# Comments start with #
movie:123
movie:456
series:789
```

### Automatic Tagging

Batch operations automatically tag items in Radarr/Sonarr based on 4K availability:

| Tag | Meaning |
|-----|---------|
| `4k-available` | 4K releases were found |
| `4k-unavailable` | No 4K releases found |

Tags are created automatically if they don't exist. Use `--no-tag` to disable tagging.

### Resume Support

Batch operations track progress and can resume after interruption:

- Progress is saved to `~/.config/findarr/state.json`
- Use `--resume` (default) to continue where you left off
- Use `--no-resume` to start fresh
- Items are marked with check timestamps to avoid re-checking recently scanned items

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

## Webhook Server

Run a webhook server to automatically check 4K availability when new movies or series are added to Radarr/Sonarr.

### Installation

```bash
# Install with webhook support
pip install findarr[webhook]
```

### Starting the Server

```bash
# Start with default settings (port 8080)
findarr serve

# Custom host and port
findarr serve --host 0.0.0.0 --port 9000

# With debug logging
findarr serve --log-level debug
```

### Configuring Webhooks in Radarr

1. Go to **Settings > Connect > Add > Webhook**
2. Configure:
   - **Name**: `findarr`
   - **URL**: `http://<findarr-host>:8080/webhook/radarr`
   - **Method**: `POST`
   - **On Movie Added**: ✓ (enable)
3. Add custom header:
   - **Key**: `X-Api-Key`
   - **Value**: Your Radarr API key (same one in your findarr config)
4. Save and test

### Configuring Webhooks in Sonarr

1. Go to **Settings > Connect > Add > Webhook**
2. Configure:
   - **Name**: `findarr`
   - **URL**: `http://<findarr-host>:8080/webhook/sonarr`
   - **Method**: `POST`
   - **On Series Add**: ✓ (enable)
3. Add custom header:
   - **Key**: `X-Api-Key`
   - **Value**: Your Sonarr API key (same one in your findarr config)
4. Save and test

### Webhook Configuration

Add to your `~/.config/findarr/config.toml`:

```toml
[webhook]
host = "0.0.0.0"  # Listen on all interfaces
port = 8080       # Default port
```

Or use environment variables:

```bash
export FINDARR_WEBHOOK_HOST="0.0.0.0"
export FINDARR_WEBHOOK_PORT="8080"
```

### How It Works

1. When you add a movie/series to Radarr/Sonarr, it sends a webhook to findarr
2. findarr immediately returns `200 OK` and processes the check in the background
3. After checking, findarr applies the appropriate tag (`4k-available` or `4k-unavailable`)

The webhook uses your existing tag configuration from `[tags]` section.

### Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check (returns `{"status": "healthy"}`) |
| `/webhook/radarr` | POST | Receive Radarr webhooks |
| `/webhook/sonarr` | POST | Receive Sonarr webhooks |

### Running as a Service (systemd)

Create `/etc/systemd/system/findarr-webhook.service`:

```ini
[Unit]
Description=findarr Webhook Server
After=network.target

[Service]
Type=simple
User=your-user
ExecStart=/path/to/findarr serve --host 0.0.0.0 --port 8080
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Then:
```bash
sudo systemctl daemon-reload
sudo systemctl enable findarr-webhook
sudo systemctl start findarr-webhook
```

### Running with Docker

The official Docker image is available on GitHub Container Registry.

#### Quick Start

```bash
docker run -d \
  --name findarr \
  -p 8080:8080 \
  -e FINDARR_RADARR_URL="http://radarr:7878" \
  -e FINDARR_RADARR_API_KEY="your-radarr-key" \
  -e FINDARR_SONARR_URL="http://sonarr:8989" \
  -e FINDARR_SONARR_API_KEY="your-sonarr-key" \
  ghcr.io/dabigc/4k-findarr:latest
```

#### Using a Config File

Mount your config file to `/config/config.toml`:

```bash
docker run -d \
  --name findarr \
  -p 8080:8080 \
  -v /path/to/config.toml:/config/config.toml:ro \
  ghcr.io/dabigc/4k-findarr:latest
```

#### Docker Compose

```yaml
services:
  findarr:
    image: ghcr.io/dabigc/4k-findarr:latest
    container_name: findarr
    ports:
      - "8080:8080"
    environment:
      - FINDARR_RADARR_URL=http://radarr:7878
      - FINDARR_RADARR_API_KEY=your-radarr-key
      - FINDARR_SONARR_URL=http://sonarr:8989
      - FINDARR_SONARR_API_KEY=your-sonarr-key
      # Optional: customize tags
      - FINDARR_TAG_AVAILABLE=4k-available
      - FINDARR_TAG_UNAVAILABLE=4k-unavailable
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8080/health"]
      interval: 30s
      timeout: 10s
      retries: 3

  # Example: Run alongside Radarr/Sonarr
  radarr:
    image: linuxserver/radarr:latest
    # ... your radarr config

  sonarr:
    image: linuxserver/sonarr:latest
    # ... your sonarr config
```

#### Building Locally

```bash
# Build the image
docker build -t findarr .

# Run it
docker run -d -p 8080:8080 \
  -e FINDARR_RADARR_URL="http://radarr:7878" \
  -e FINDARR_RADARR_API_KEY="your-key" \
  findarr
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

# Tag configuration (optional)
[tags]
available = "4k-available"       # Tag for items with 4K releases
unavailable = "4k-unavailable"   # Tag for items without 4K releases
create_if_missing = true         # Create tags if they don't exist
recheck_days = 30                # Days before rechecking tagged items

# State file location (optional)
[state]
path = "~/.config/findarr/state.json"
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

This project uses [uv](https://github.com/astral-sh/uv) for dependency management.

```bash
# Install dev dependencies
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

## License

MIT
