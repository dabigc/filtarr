# Filtarr

[![CI](https://github.com/dabigc/filtarr/actions/workflows/ci.yml/badge.svg)](https://github.com/dabigc/filtarr/actions/workflows/ci.yml)
[![PyPI version](https://img.shields.io/pypi/v/filtarr.svg)](https://pypi.org/project/filtarr/)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Docker](https://img.shields.io/badge/docker-ghcr.io-blue.svg)](https://github.com/dabigc/filtarr/pkgs/container/filtarr)
[![codecov](https://codecov.io/gh/dabigc/filtarr/branch/main/graph/badge.svg)](https://codecov.io/gh/dabigc/filtarr)

**Running multiple Radarr/Sonarr instances?** You know the problem: your 4K instance fills up with movies that will *never* be available in 4K, your indexers get hammered searching for releases that don't exist, and tools like [Huntarr](https://github.com/plexguide/Huntarr.io) waste API calls hunting for content you'll never find.

**Filtarr solves this.** Instead of blindly syncing your entire library to secondary instances, filtarr checks what's *actually available* from your indexers and tags items accordingly. Filter by 4K, HDR, Director's Cut, IMAX, Special Editions, and more. Only sync what you can actually get.

## How It Works

### Movies (Radarr)

```
┌─────────────────┐     ┌──────────┐     ┌─────────────────────────┐
│  Primary Radarr │────▶│  Filtarr │────▶│  Tags Applied           │
│  (All Movies)   │     │          │     │  • 4k-available         │
└─────────────────┘     │ Searches │     │  • directors-cut-available│
                        │ Indexers │     │  • imax-available       │
                        └──────────┘     └────────────┬────────────┘
                                                      │
                                                      ▼
                              ┌─────────────────────────────┐
                              │  Secondary Radarr (4K)      │
                              │  Import List filtered by    │
                              │  "4k-available" tag         │
                              └─────────────────────────────┘
```

### TV Shows (Sonarr)

```
┌─────────────────┐     ┌──────────┐     ┌─────────────────────────┐
│  Primary Sonarr │────▶│  Filtarr │────▶│  Tags Applied           │
│  (All Shows)    │     │          │     │  • 4k-available         │
└─────────────────┘     │ Searches │     │  • 4k-unavailable       │
                        │ Indexers │     │                         │
                        └──────────┘     └────────────┬────────────┘
                                                      │
                                                      ▼
                              ┌─────────────────────────────┐
                              │  Secondary Sonarr (4K)      │
                              │  Import List filtered by    │
                              │  "4k-available" tag         │
                              └─────────────────────────────┘
```

> **Note:** For TV shows, 4K is the primary use case. Movie-specific criteria like Director's Cut, IMAX, and Special Edition are not applicable to series.

1. **Filtarr queries your indexers** through Radarr/Sonarr's search API—using the same sources *you* have access to
2. **Tags are applied** based on availability (e.g., `4k-available`, `imax-available`, `directors-cut-unavailable`)
3. **Use import lists** with tag filters to sync only available content to secondary instances

## Why Filtarr?

| Problem | Filtarr Solution |
|---------|------------------|
| Secondary instance cluttered with unavailable content | Only syncs what's actually available |
| Wasted API calls searching for non-existent releases | Fewer items = fewer searches |
| Manual checking is tedious | Automated via webhooks, schedules, or batch operations |
| Don't know if content will ever be available | Clear tagging shows availability at a glance |

## Use Cases

- **4K Instance Management** — Only add movies/shows that have 4K releases on your indexers
- **Special Edition Hunting** — Tag content with Director's Cuts, IMAX editions, or remasters available
- **HDR/DV Filtering** — Separate HDR/Dolby Vision content from SDR libraries
- **Smart Huntarr Integration** — Stop Huntarr from searching for content that doesn't exist

## Features

- **Multiple Check Methods**: CLI, Python API, webhooks, or scheduled jobs
- **Flexible Criteria**: Built-in presets (4K, HDR, Dolby Vision, Director's Cut, Extended, IMAX, Remaster, Special Edition) or custom matching functions
- **Smart Tagging**: Automatic criteria-specific tag creation (e.g., `imax-available`, `directors-cut-unavailable`)
- **Series Sampling**: Efficiently check TV shows without querying every season
- **Resume Support**: Batch operations can be interrupted and resumed
- **Docker Ready**: Official image at `ghcr.io/dabigc/filtarr`

## Quick Start

### 1. Install

```bash
# Install with CLI support
pip install filtarr[cli]

# Or for development
pip install -e ".[dev]"
```

### 2. Configure

Set environment variables:

```bash
# Radarr (for movies)
export FILTARR_RADARR_URL="http://localhost:7878"
export FILTARR_RADARR_API_KEY="your-radarr-api-key"

# Sonarr (for TV series)
export FILTARR_SONARR_URL="http://localhost:8989"
export FILTARR_SONARR_API_KEY="your-sonarr-api-key"
```

Or create a config file at `~/.config/filtarr/config.toml`:

```toml
[radarr]
url = "http://localhost:7878"
api_key = "your-radarr-api-key"

[sonarr]
url = "http://localhost:8989"
api_key = "your-sonarr-api-key"
```

> Environment variables take precedence over the config file.

### 3. Check Release Availability

```bash
# Check a movie for 4K (default)
filtarr check movie 123

# Check a movie for Director's Cut
filtarr check movie 123 --criteria directors-cut

# Check a movie for IMAX
filtarr check movie "The Dark Knight" --criteria imax

# Check a TV series for 4K
filtarr check series 456

# Check multiple items from a file
filtarr check batch --file items.txt

# Check all movies for Special Edition
filtarr check batch --all-movies --criteria special-edition
```

## CLI Usage

### Check Movie

```bash
filtarr check movie <MOVIE_ID> [OPTIONS]

Options:
  -c, --criteria TEXT               Search criteria (default: 4k)
  -f, --format [json|table|simple]  Output format (default: table)
  --no-tag                          Disable automatic tagging
  --dry-run                         Show what tags would be applied
```

Available criteria: `4k`, `hdr`, `dolby-vision`, `directors-cut`, `extended`, `remaster`, `imax`, `special-edition`

Example:
```bash
$ filtarr check movie 123 --format simple
movie:123: 4K available

$ filtarr check movie 123 --criteria directors-cut --format simple
movie:123: Director's Cut available
```

### Check Series

```bash
filtarr check series <SERIES_ID> [OPTIONS]

Options:
  -c, --criteria TEXT               Search criteria (default: 4k)
  -s, --seasons INTEGER             Seasons to check (default: 3)
  --strategy [recent|distributed|all]  Sampling strategy (default: recent)
  -f, --format [json|table|simple]  Output format (default: table)
  --no-tag                          Disable automatic tagging
  --dry-run                         Show what tags would be applied
```

Available criteria for series: `4k`, `hdr`, `dolby-vision`

> **Note:** Movie-only criteria (directors-cut, extended, remaster, imax, special-edition) cannot be used for TV series.

Strategies:
- `recent` - Check most recent N seasons (fastest)
- `distributed` - Sample across all seasons evenly
- `all` - Check every season (slowest, most thorough)

Example:
```bash
$ filtarr check series 456 --strategy recent --seasons 2 --format json
{
  "item_id": 456,
  "item_type": "series",
  "has_match": true,
  "result_type": "4k",
  "releases_count": 42,
  "matched_releases_count": 8,
  "seasons_checked": [3, 4],
  "strategy_used": "recent"
}
```

### Batch Check

Process your entire library or a subset with automatic tagging and resume support.

```bash
filtarr check batch [OPTIONS]

Options:
  -f, --file PATH                   File with items to check (optional)
  --all-movies                      Check all movies in Radarr
  --all-series                      Check all series in Sonarr
  -c, --criteria TEXT               Search criteria (default: 4k)
  --batch-size INTEGER              Max items per run (0=unlimited, default: 0)
  -d, --delay FLOAT                 Delay between checks in seconds (default: 0.5)
  --skip-tagged/--no-skip-tagged    Skip items with existing tags (default: skip)
  --resume/--no-resume              Resume interrupted batch run (default: resume)
  --no-tag                          Disable automatic tagging
  --dry-run                         Show what would be tagged without making changes
  --format [json|table|simple]      Output format (default: simple)
  -s, --seasons INTEGER             Seasons to check for series (default: 3)
  --strategy [recent|distributed|all]  Strategy for series (default: recent)
```

> **Note:** Movie-only criteria cannot be used with `--all-series`.

Examples:
```bash
# Check all movies for 4K and tag them
filtarr check batch --all-movies

# Check all movies for IMAX
filtarr check batch --all-movies --criteria imax

# Check all movies for Director's Cut, 100 at a time
filtarr check batch --all-movies --criteria directors-cut --batch-size 100

# Check all series with 1 second delay between checks
filtarr check batch --all-series --delay 1.0

# Check specific items from a file
filtarr check batch --file items.txt

# Preview what would be tagged (no changes made)
filtarr check batch --all-movies --dry-run
```

Batch file format (one item per line):
```
# Comments start with #
movie:123
movie:456
series:789
```

### Automatic Tagging

Batch operations automatically tag items in Radarr/Sonarr based on the criteria used:

| Criteria | Available Tag | Unavailable Tag |
|----------|---------------|-----------------|
| 4k | `4k-available` | `4k-unavailable` |
| hdr | `hdr-available` | `hdr-unavailable` |
| dolby-vision | `dolby-vision-available` | `dolby-vision-unavailable` |
| directors-cut | `directors-cut-available` | `directors-cut-unavailable` |
| extended | `extended-available` | `extended-unavailable` |
| remaster | `remaster-available` | `remaster-unavailable` |
| imax | `imax-available` | `imax-unavailable` |
| special-edition | `special-edition-available` | `special-edition-unavailable` |

Tags are created automatically if they don't exist. Use `--no-tag` to disable tagging.

### Resume Support

Batch operations track progress and can resume after interruption:

- Progress is saved to `~/.config/filtarr/state.json` (or `/config/state.json` in Docker)
- Use `--resume` (default) to continue where you left off
- Use `--no-resume` to start fresh
- Items are marked with check timestamps to avoid re-checking recently scanned items

### Exit Codes

| Code | Meaning |
|------|---------|
| 0    | Matching releases found |
| 1    | No matching releases found |
| 2    | Error (config, API, etc.) |

Use exit codes in scripts:
```bash
if filtarr check movie 123 --criteria imax --format simple; then
  echo "IMAX is available!"
else
  echo "No IMAX found"
fi
```

## Webhook Server

Run a webhook server to automatically check release availability when new movies or series are added to Radarr/Sonarr.

### Installation

```bash
# Install with webhook support
pip install filtarr[webhook]
```

### Starting the Server

```bash
# Start with default settings (port 8080)
filtarr serve

# Custom host and port
filtarr serve --host 0.0.0.0 --port 9000

# With debug logging
filtarr serve --log-level debug
```

### Configuring Webhooks in Radarr

1. Go to **Settings > Connect > Add > Webhook**
2. Configure:
   - **Name**: `filtarr`
   - **URL**: `http://<filtarr-host>:8080/webhook/radarr`
   - **Method**: `POST`
   - **On Movie Added**: ✓ (enable)
3. Add custom header:
   - **Key**: `X-Api-Key`
   - **Value**: Your Radarr API key (same one in your filtarr config)
4. Save and test

### Configuring Webhooks in Sonarr

1. Go to **Settings > Connect > Add > Webhook**
2. Configure:
   - **Name**: `filtarr`
   - **URL**: `http://<filtarr-host>:8080/webhook/sonarr`
   - **Method**: `POST`
   - **On Series Add**: ✓ (enable)
3. Add custom header:
   - **Key**: `X-Api-Key`
   - **Value**: Your Sonarr API key (same one in your filtarr config)
4. Save and test

### Webhook Configuration

Add to your `~/.config/filtarr/config.toml`:

```toml
[webhook]
host = "0.0.0.0"  # Listen on all interfaces
port = 8080       # Default port
```

Or use environment variables:

```bash
export FILTARR_WEBHOOK_HOST="0.0.0.0"
export FILTARR_WEBHOOK_PORT="8080"
```

### How It Works

1. When you add a movie/series to Radarr/Sonarr, it sends a webhook to filtarr
2. filtarr immediately returns `200 OK` and processes the check in the background
3. After checking, filtarr applies the appropriate tag (`4k-available` or `4k-unavailable`)

The webhook uses your existing tag configuration from `[tags]` section.

### Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check (returns `{"status": "healthy"}`) |
| `/webhook/radarr` | POST | Receive Radarr webhooks |
| `/webhook/sonarr` | POST | Receive Sonarr webhooks |

### Running as a Service (systemd)

Create `/etc/systemd/system/filtarr-webhook.service`:

```ini
[Unit]
Description=filtarr Webhook Server
After=network.target

[Service]
Type=simple
User=your-user
ExecStart=/path/to/filtarr serve --host 0.0.0.0 --port 8080
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Then:
```bash
sudo systemctl daemon-reload
sudo systemctl enable filtarr-webhook
sudo systemctl start filtarr-webhook
```

### Running with Docker

The official Docker image is available on GitHub Container Registry.

#### Quick Start

```bash
docker run -d \
  --name filtarr \
  -p 8080:8080 \
  -e FILTARR_RADARR_URL="http://radarr:7878" \
  -e FILTARR_RADARR_API_KEY="your-radarr-key" \
  -e FILTARR_SONARR_URL="http://sonarr:8989" \
  -e FILTARR_SONARR_API_KEY="your-sonarr-key" \
  ghcr.io/dabigc/filtarr:latest
```

#### Using a Config File

Mount your config file to `/config/config.toml`:

```bash
docker run -d \
  --name filtarr \
  -p 8080:8080 \
  -v /path/to/config.toml:/config/config.toml:ro \
  ghcr.io/dabigc/filtarr:latest
```

#### Docker Compose

Copy the example environment file and add your API keys:

```bash
cp .env.example .env
# Edit .env with your Radarr/Sonarr API keys
```

Then start the container:

```yaml
services:
  filtarr:
    image: ghcr.io/dabigc/filtarr:latest
    container_name: filtarr
    env_file: .env  # Required - Docker Compose doesn't auto-read .env
    ports:
      - "8080:8080"
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

> **Note:** The `env_file: .env` directive is required. Docker Compose does not automatically load `.env` files for variable substitution in the compose file.

#### Using Bind Mounts

If you prefer bind mounts over named volumes for easier access to config files:

```yaml
services:
  filtarr:
    image: ghcr.io/dabigc/filtarr:latest
    volumes:
      - ./filtarr:/config  # Must be owned by UID 1000
```

**Important:** The container runs as user `filtarr` (UID 1000). The bind mount directory must be writable by this user:

```bash
# Create the directory with correct ownership
mkdir -p ./filtarr
chown 1000:1000 ./filtarr
```

#### Troubleshooting

**Permission denied errors on `/config/state.json`:**

This occurs when the `/config` directory is not writable by the container user (UID 1000).

For bind mounts:
```bash
# Fix ownership of an existing directory
chown -R 1000:1000 ./filtarr
```

For named volumes (first-time setup issues):
```bash
# Fix permissions inside the container
docker exec -u root filtarr chown -R filtarr:filtarr /config

# Or recreate the volume
docker compose down -v
docker compose up -d
```

#### Building Locally

```bash
# Build the image
docker build -t filtarr .

# Run it
docker run -d -p 8080:8080 \
  -e FILTARR_RADARR_URL="http://radarr:7878" \
  -e FILTARR_RADARR_API_KEY="your-key" \
  filtarr
```

## Scheduler

Run batch operations automatically on configurable schedules.

### Installation

```bash
# Install with scheduler support
pip install filtarr[scheduler]

# Or with everything (CLI, webhook, scheduler)
pip install filtarr[cli,webhook,scheduler]
```

### Quick Start

Add schedules to your `~/.config/filtarr/config.toml`:

```toml
[scheduler]
enabled = true
history_limit = 100  # Keep last 100 run records

[[scheduler.schedules]]
name = "daily-movies"
target = "movies"
trigger = { type = "cron", expression = "0 3 * * *" }  # 3 AM daily
batch_size = 100
skip_tagged = true

[[scheduler.schedules]]
name = "weekly-series"
target = "series"
trigger = { type = "interval", hours = 168 }  # Every week
strategy = "recent"
seasons = 3
```

Then start the server with the scheduler:

```bash
filtarr serve  # Scheduler is enabled by default
filtarr serve --no-scheduler  # Webhooks only
```

### CLI Commands

```bash
# List all schedules
filtarr schedule list

# Add a dynamic schedule
filtarr schedule add daily-check --target movies --cron "0 3 * * *"
filtarr schedule add hourly-all --target both --interval 6h

# Remove a schedule
filtarr schedule remove daily-check

# Enable/disable a schedule
filtarr schedule enable daily-check
filtarr schedule disable daily-check

# Run a schedule immediately
filtarr schedule run daily-movies

# View run history
filtarr schedule history
filtarr schedule history --name daily-movies --limit 10

# Export to external schedulers
filtarr schedule export --format cron
filtarr schedule export --format systemd --output /etc/systemd/system/
```

### Schedule Triggers

**Cron expressions** (5 fields: minute hour day month weekday):
```toml
trigger = { type = "cron", expression = "0 3 * * *" }     # Daily at 3 AM
trigger = { type = "cron", expression = "0 */6 * * *" }   # Every 6 hours
trigger = { type = "cron", expression = "0 3 * * 0" }     # Sundays at 3 AM
```

**Interval triggers**:
```toml
trigger = { type = "interval", hours = 6 }                # Every 6 hours
trigger = { type = "interval", days = 1 }                 # Daily
trigger = { type = "interval", hours = 2, minutes = 30 }  # Every 2h 30m
```

CLI interval format: `6h`, `30m`, `1d`, `1w`, `2h30m`

### Schedule Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `name` | required | Unique schedule identifier |
| `target` | required | `movies`, `series`, or `both` |
| `trigger` | required | Cron or interval trigger |
| `enabled` | `true` | Whether schedule is active |
| `batch_size` | `0` | Max items per run (0=unlimited) |
| `delay` | `0.5` | Seconds between checks |
| `skip_tagged` | `true` | Skip items with existing tags |
| `include_rechecks` | `true` | Include stale unavailable items |
| `no_tag` | `false` | Disable automatic tagging |
| `dry_run` | `false` | Preview mode |
| `strategy` | `recent` | Series strategy: `recent`, `distributed`, `all` |
| `seasons` | `3` | Seasons to check for series |

### Behavior

- **Overlap prevention**: If a schedule is still running when the next run is due, the new run is skipped
- **Error resilience**: Failed runs are logged but don't stop the scheduler
- **History tracking**: All runs are recorded with timestamps, item counts, and errors
- **Graceful shutdown**: Completes current run before stopping

### Export to External Schedulers

If you prefer to use cron or systemd instead of the built-in scheduler:

```bash
# Generate cron configuration
filtarr schedule export --format cron
# Output:
# 0 3 * * * /usr/local/bin/filtarr check batch --all-movies --batch-size 100

# Generate systemd timers
filtarr schedule export --format systemd --output ./systemd-units/
# Creates:
#   filtarr-daily-movies.timer
#   filtarr-daily-movies.service
```

### Monitoring

The `/status` endpoint shows scheduler state:

```bash
curl http://localhost:8080/status
```

```json
{
  "status": "healthy",
  "scheduler": {
    "enabled": true,
    "running": true,
    "total_schedules": 2,
    "enabled_schedules": 2,
    "currently_running": [],
    "recent_runs": [
      {
        "schedule": "daily-movies",
        "status": "completed",
        "items_processed": 150,
        "items_with_4k": 42
      }
    ]
  }
}
```

## Python API

### Check movie 4K availability (Radarr)

```python
import asyncio
from filtarr import RadarrClient

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
from filtarr import SonarrClient

async def main():
    async with SonarrClient("http://localhost:8989", "your-api-key") as client:
        has_4k = await client.has_4k_releases(series_id=456)
        print(f"4K available: {has_4k}")

asyncio.run(main())
```

### Combined checker

```python
import asyncio
from filtarr import ReleaseChecker, SamplingStrategy

async def main():
    checker = ReleaseChecker(
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
| `FILTARR_RADARR_URL` | Radarr instance URL (e.g., `http://localhost:7878`) |
| `FILTARR_RADARR_API_KEY` | Radarr API key |
| `FILTARR_SONARR_URL` | Sonarr instance URL (e.g., `http://localhost:8989`) |
| `FILTARR_SONARR_API_KEY` | Sonarr API key |
| `FILTARR_TIMEOUT` | Request timeout in seconds (default: `120`) |

### Config File

Location: `~/.config/filtarr/config.toml`

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
# Tag patterns use {criteria} placeholder (e.g., "4k", "imax", "directors-cut")
pattern_available = "{criteria}-available"     # Pattern for available tags
pattern_unavailable = "{criteria}-unavailable" # Pattern for unavailable tags
create_if_missing = true                       # Create tags if they don't exist
recheck_days = 30                              # Days before rechecking tagged items

# State file location (optional)
# Default: ~/.config/filtarr/state.json (or /config/state.json in Docker)
[state]
path = "~/.config/filtarr/state.json"
```

### Timeout Considerations

Searching for releases on popular media (e.g., "The Matrix") can take significant time as Radarr/Sonarr queries multiple indexers. The default timeout is 120 seconds.

**If you're behind a reverse proxy** (nginx, Caddy, Traefik, Nginx Proxy Manager, etc.), you may need to increase the proxy timeout as well. The filtarr client timeout won't help if your reverse proxy times out first.

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
uv run pytest --cov=filtarr --cov-report=term-missing

# Lint
uv run ruff check src tests

# Format
uv run ruff format src tests

# Type check
uv run mypy src
```

## License

MIT
