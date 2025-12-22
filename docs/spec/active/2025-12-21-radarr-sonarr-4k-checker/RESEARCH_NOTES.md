---
document_type: research
project_id: SPEC-2025-12-21-001
last_updated: 2025-12-21T23:59:00Z
---

# findarr - Research Notes

## Research Summary

Research was conducted to understand the Radarr and Sonarr v3 APIs, identify the existing codebase gaps, and evaluate library choices for retry logic, caching, and CLI implementation.

## Radarr API Research

### Release Endpoint

**Endpoint**: `GET /api/v3/release`

| Parameter | Type | Description |
|-----------|------|-------------|
| `movieId` | int | Filter releases by movie database ID |

**Key Findings**:
- Releases are cached by Radarr for 30 minutes
- If no cached releases exist, returns 404
- To trigger fresh search, use `POST /api/v3/command` with `{"name": "MoviesSearch", "movieIds": [123]}`

### Release Response Structure

```json
{
  "guid": "unique-identifier",
  "title": "Movie.Name.2024.2160p.UHD.BluRay.x265-GROUP",
  "quality": {
    "quality": {
      "id": 31,
      "name": "Bluray-2160p",
      "resolution": 2160
    }
  },
  "size": 15000000000,
  "indexer": "IndexerName",
  "seeders": 50,
  "rejected": false
}
```

### 4K Detection in Radarr

Three reliable methods:
1. **Resolution field**: `quality.quality.resolution == 2160`
2. **Quality name**: Contains "2160p" (e.g., "Bluray-2160p", "WEBDL-2160p")
3. **Title parsing**: Contains "2160p", "4k", "uhd"

**Known issue**: Releases with only "4K" in title (without "2160p") may be incorrectly parsed as 480p (GitHub issue #5639).

## Sonarr API Research

### Release Endpoint

**Endpoint**: `GET /api/v3/release`

| Parameter | Type | Description |
|-----------|------|-------------|
| `episodeId` | int | Specific episode ID to search |
| `seriesId` | int64 | Series database ID |
| `seasonNumber` | int | Season number filter |

**Key Finding**: Episode-level searches require `episodeId`, not just `seriesId`.

### Episode Endpoint

**Endpoint**: `GET /api/v3/episode`

| Parameter | Type | Description |
|-----------|------|-------------|
| `seriesId` | int | Series ID (required for listing) |
| `seasonNumber` | int | Filter by season (optional) |

### Episode Response Structure

```json
{
  "id": 12345,
  "seriesId": 67,
  "seasonNumber": 1,
  "episodeNumber": 5,
  "title": "Episode Title",
  "airDate": "2024-01-15",
  "airDateUtc": "2024-01-15T20:00:00Z",
  "hasFile": false,
  "monitored": true
}
```

### Series Endpoint

**Endpoint**: `GET /api/v3/series/{id}`

Returns full series metadata including seasons list.

## Codebase Analysis

### Existing Implementation (findarr scaffold)

| Component | Location | Status |
|-----------|----------|--------|
| RadarrClient | `src/findarr/clients/radarr.py` | Basic implementation |
| SonarrClient | `src/findarr/clients/sonarr.py` | Basic (series-level only) |
| Quality model | `src/findarr/models/common.py` | Complete with is_4k() |
| Release model | `src/findarr/models/common.py` | Complete with is_4k() |
| FourKChecker | `src/findarr/checker.py` | Basic facade |

### Implementation Gaps

1. **Episode-based TV checking**: SonarrClient only supports series-level queries, not episode-level
2. **No retry logic**: Raw httpx calls without retry handling
3. **No caching**: Every API call hits the server
4. **No CLI**: Library-only, no command-line interface

### Existing Patterns

- Async context managers for resource cleanup
- Pydantic models for response validation
- Nested quality structure parsing (`quality.quality`)
- Dual 4K detection (quality name + title fallback)

## Library Evaluation

### CLI Framework

| Library | Pros | Cons | Verdict |
|---------|------|------|---------|
| typer | Type hints → auto help, async support, clean syntax | Newer, smaller community | **Selected** |
| click | Mature, large community | More verbose, manual type handling | Alternative |
| argparse | Stdlib, no deps | Very verbose, no color output | Not recommended |

**Decision**: typer - better fit for typed Python codebase

### Retry Library

| Library | Pros | Cons | Verdict |
|---------|------|------|---------|
| tenacity | Industry standard, async support, flexible | Slightly verbose config | **Selected** |
| stamina | Simpler API | Less flexible, newer | Alternative |
| Custom | No dependencies | More code to maintain | Not recommended |

**Decision**: tenacity - proven reliability, excellent async support

### Caching Library

| Library | Pros | Cons | Verdict |
|---------|------|------|---------|
| cachetools | Lightweight, TTLCache built-in | Sync only (need lock for async) | **Selected** |
| aiocache | Async-native | Heavier, more deps | Alternative |
| diskcache | Persistent | Overkill for ephemeral cache | Not needed |

**Decision**: cachetools with asyncio.Lock wrapper - simple and effective

## API Versioning

Both Radarr and Sonarr use API v3. The library should:
- Pin to v3 API paths
- Check API version on init (optional)
- Document minimum supported Radarr/Sonarr versions

## Rate Limiting Considerations

| Source | Limit | Impact |
|--------|-------|--------|
| Radarr API | No limit | Safe to call frequently |
| Sonarr API | No limit | Safe to call frequently |
| Indexers (via arr) | Varies | Radarr/Sonarr handle this |
| TMDB (internal) | 40/s | Not our concern |

**Conclusion**: Rate limiting is not a concern for findarr since Radarr/Sonarr manage indexer communication.

## Sources

- [Radarr API Documentation](https://radarr.video/docs/api/)
- [Sonarr API Documentation](https://sonarr.tv/docs/api/)
- [pyarr Documentation](https://docs.totaldebug.uk/pyarr/)
- [devopsarr/radarr-py](https://github.com/devopsarr/radarr-py)
- [devopsarr/sonarr-py](https://github.com/devopsarr/sonarr-py)
- [golift.io/starr](https://pkg.go.dev/golift.io/starr)
- [Radarr GitHub Issues](https://github.com/Radarr/Radarr/issues)
