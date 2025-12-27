# Troubleshooting 502 Bad Gateway Errors

This guide helps diagnose and resolve 502 Bad Gateway errors that occur during batch processing with filtarr.

## Understanding 502 Errors

A 502 Bad Gateway error occurs when your reverse proxy (nginx, Traefik, Caddy, Cloudflare, etc.) cannot get a valid response from your Radarr/Sonarr server within its timeout period.

### Common Symptoms

```
Retryable HTTP error 502 for /api/v3/release
Error checking movie:Movie Name: Server error '502 Bad Gateway' for url 'https://radarr.example.com/api/v3/release?movieId=123'
```

### Why 502 Errors Happen

1. **Slow indexer searches**: The `/api/v3/release` endpoint triggers indexer searches, which can take 30-60+ seconds
2. **Proxy timeout too short**: Default proxy timeouts (30-60s) may be shorter than indexer response times
3. **High concurrency**: Multiple concurrent requests can overwhelm Radarr/Sonarr
4. **Rate limiting**: Indexers may rate-limit requests, causing delays
5. **Resource constraints**: Radarr/Sonarr may be low on CPU/memory during heavy operations

## Diagnostic Steps

### 1. Check Request Timing

filtarr logs slow requests automatically. Enable debug logging to see timing information:

```bash
FILTARR_LOG_LEVEL=DEBUG filtarr check batch --all-movies --batch-size 5
```

Look for warnings like:
```
Slow request (45.23s) to /api/v3/release - may indicate proxy timeout risk
```

If requests are taking >30 seconds, your proxy timeout is likely the issue.

### 2. Test Direct Connection

If possible, test filtarr against Radarr/Sonarr directly (bypassing the reverse proxy):

```bash
# Set direct URL temporarily
FILTARR_RADARR_URL=http://localhost:7878 filtarr check movie 123
```

If direct connections work but proxied ones fail, the issue is your proxy configuration.

### 3. Check Radarr/Sonarr Logs

Look for slow queries or errors in:
- Radarr: `Settings > General > Log Level = Debug`, then check `System > Logs`
- Sonarr: Same location

## Solutions

### Solution 1: Increase Proxy Timeout (Recommended)

#### nginx

```nginx
location / {
    proxy_pass http://radarr:7878;
    proxy_read_timeout 120s;    # Increase from default 60s
    proxy_connect_timeout 30s;
    proxy_send_timeout 30s;
}
```

#### Traefik

```yaml
# traefik.yml or docker-compose labels
http:
  middlewares:
    radarr-timeout:
      buffering:
        retryExpression: "IsNetworkError() && Attempts() < 2"
  serversTransports:
    slow-transport:
      responseHeaderTimeout: 120s
```

Or with Docker labels:
```yaml
labels:
  - "traefik.http.middlewares.timeout.buffering.retryExpression=IsNetworkError() && Attempts() < 2"
```

#### Caddy

```caddyfile
radarr.example.com {
    reverse_proxy radarr:7878 {
        transport http {
            read_timeout 120s
            write_timeout 30s
        }
    }
}
```

#### Cloudflare

Cloudflare has fixed timeouts that cannot be changed:
- Free tier: 100 seconds
- Pro tier: 100 seconds
- Business/Enterprise: 600 seconds

If you're on Free/Pro and hitting timeouts, consider:
- Bypassing Cloudflare for API traffic (use direct URL)
- Upgrading to Business tier

### Solution 2: Reduce Concurrency

Lower the batch size to reduce load on Radarr/Sonarr:

```bash
# Default is batch_size=0 (unlimited), try lower values
filtarr check batch --all-movies --batch-size 1
filtarr check batch --all-movies --batch-size 2
```

### Solution 3: Add Delay Between Requests

Space out requests to avoid overwhelming the server:

```bash
# Add 2 seconds between each request
filtarr check batch --all-movies --delay 2.0
```

For heavily loaded systems, try longer delays:
```bash
filtarr check batch --all-movies --delay 5.0 --batch-size 1
```

### Solution 4: Increase filtarr Timeout

The default timeout is 120 seconds. For very slow indexers, increase it:

```bash
# Via environment variable
FILTARR_TIMEOUT=180 filtarr check batch --all-movies
```

Or in `config.toml`:
```toml
timeout = 180  # seconds
```

### Solution 5: Use Direct Connection

If your reverse proxy issues can't be resolved, connect directly to Radarr/Sonarr:

```toml
# config.toml
[radarr]
url = "http://localhost:7878"  # or internal Docker network URL
api_key = "your-api-key"
allow_insecure = true  # Required for HTTP
```

## Configuration Reference

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `FILTARR_TIMEOUT` | 120 | HTTP request timeout in seconds |
| `FILTARR_LOG_LEVEL` | INFO | Set to DEBUG for timing info |

### CLI Options

| Option | Default | Description |
|--------|---------|-------------|
| `--batch-size` | 0 (unlimited) | Max items per run |
| `--delay` | 0.5 | Seconds between requests |

### Config File (`config.toml`)

```toml
# Request timeout in seconds
timeout = 120

[logging]
level = "INFO"  # Set to "DEBUG" for timing diagnostics
```

## Recovery After 502 Errors

filtarr automatically handles 502 errors safely:

1. **Items are NOT marked as processed** - They will be retried on the next batch run
2. **Batch progress is preserved** - Use `--resume` (default) to continue where you left off
3. **Safe to re-run** - 502 errors stop that item for the current run, but it will be picked up again the next time you run the batch

Note: Exponential backoff is used only for retrying certain network errors (connection or read timeouts). HTTP 502 errors are not automatically retried within a single run.

If you've fixed the underlying issue, just run the batch again:

```bash
# This will resume from where it left off
filtarr check batch --all-movies
```

## Recommended Settings for Large Libraries

For libraries with 1000+ items, use conservative settings:

```bash
filtarr check batch --all-movies \
  --batch-size 50 \
  --delay 2.0
```

This processes 50 items per run with 2-second delays, reducing server load.

## Getting Help

If you're still experiencing issues:

1. Run with debug logging: `FILTARR_LOG_LEVEL=DEBUG`
2. Note the timing of slow requests
3. Check your reverse proxy logs for timeout errors
4. Report issues at: https://github.com/your-repo/filtarr/issues
