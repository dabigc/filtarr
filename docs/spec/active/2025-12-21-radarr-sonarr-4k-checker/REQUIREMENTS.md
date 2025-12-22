---
document_type: requirements
project_id: SPEC-2025-12-21-001
version: 1.0.0
last_updated: 2025-12-21T23:50:00Z
status: draft
---

# findarr - Product Requirements Document

## Executive Summary

**findarr** is a Python library (with optional CLI) that checks 4K availability for movies and TV shows by querying Radarr and Sonarr release search endpoints. It replaces an unreliable approach that depended on inconsistent public APIs (JustWatch, TMDb, Streaming Availability) with a direct integration that queries the user's own Radarr/Sonarr instances for indexer release data.

The library is designed for correctness over speed, with built-in retry logic, TTL caching, and configurable TV show episode sampling strategies.

## Problem Statement

### The Problem

Determining whether a movie or TV show is available in 4K resolution is unreliable when using public APIs:

- **JustWatch**: Unofficial GraphQL API that can break without notice
- **TMDb**: No native 4K availability field; relies on parsing user-contributed release notes
- **Streaming Availability API**: Quota-limited (100 requests/day on free tier) and requires paid subscription
- **Blu-ray.com**: Hostile to scraping with aggressive bot blocking

### Impact

Users of media management tools (Radarr/Sonarr) cannot reliably determine which items in their library are available in 4K, leading to:
- Missed opportunities to upgrade to 4K when available
- Wasted time manually checking availability
- Unreliable automation pipelines that depend on 4K status

### Current State

The existing 4k-finder service at `/Users/dabigc/projects/4k-finder` attempts to query multiple APIs with fallback logic, but frequently returns false negatives when APIs fail, hit quotas, or return incomplete data.

## Goals and Success Criteria

### Primary Goal

Provide a reliable, programmatic way to determine 4K availability by querying Radarr/Sonarr's indexer search results directly.

### Success Metrics

| Metric | Target | Measurement Method |
|--------|--------|-------------------|
| 4K Detection Accuracy | >95% | Manual spot-check against known 4K releases |
| API Reliability | >99% | Successful API calls / Total calls (with retries) |
| Response Time (cached) | <100ms | Library benchmark tests |
| Response Time (uncached) | <10s | Depends on indexer response time |

### Non-Goals (Explicit Exclusions)

- **Streaming service integration**: We do NOT query JustWatch, Netflix, etc.
- **Physical media databases**: We do NOT query Blu-ray.com or similar
- **Automatic downloading**: We only check availability; downloading is out of scope
- **Quality comparison**: We report presence of 4K; we don't rank releases
- **Multi-instance aggregation**: One Radarr + one Sonarr per checker instance

## User Analysis

### Primary Users

1. **Open Source Community**
   - **Who**: Developers and homelab enthusiasts using Radarr/Sonarr
   - **Needs**: A reliable library to integrate 4K checking into their automation
   - **Context**: Building scripts, webhooks, or dashboard integrations

2. **Other Applications/Services**
   - **Who**: Backend services that need 4K availability data
   - **Needs**: Programmatic API with clear responses
   - **Context**: Webhook handlers, media dashboards, sync services

### User Stories

1. As a **developer**, I want to check if a movie has 4K releases available so that I can decide whether to sync it to my 4K Radarr instance.

2. As a **developer**, I want to check if a TV series has 4K releases so that I can tag it appropriately in my library.

3. As a **CLI user**, I want to batch-check multiple items from a file so that I can audit my library efficiently.

4. As an **automation builder**, I want the library to handle transient errors gracefully so that my pipelines don't fail on temporary issues.

5. As an **integrator**, I want cached results so that repeated checks don't hammer my indexers.

## Functional Requirements

### Must Have (P0)

| ID | Requirement | Rationale | Acceptance Criteria |
|----|-------------|-----------|---------------------|
| FR-001 | Check movie 4K availability via Radarr | Core functionality | Given a movie ID, return whether 4K releases exist |
| FR-002 | Check TV series 4K availability via Sonarr | Core functionality | Given a series ID, return whether 4K releases exist |
| FR-003 | Episode-based TV checking | Accurate TV detection | Check latest aired episode first; if no 4K, spot-check additional episodes |
| FR-004 | Configurable season sampling | Flexibility | Allow caller to specify number of seasons to sample (default: 3) |
| FR-005 | Bounds checking on seasons | Robustness | If configured seasons > actual seasons, check all available |
| FR-006 | Return detailed results | Transparency | Include list of 4K releases found, not just boolean |
| FR-007 | Retry with exponential backoff | Reliability | Automatically retry on transient errors (connection, 429, 5xx) |
| FR-008 | TTL caching per client | Performance | Cache release lookups with configurable TTL (default: 5 minutes) |

### Should Have (P1)

| ID | Requirement | Rationale | Acceptance Criteria |
|----|-------------|-----------|---------------------|
| FR-101 | CLI for single item check | Usability | `findarr check movie 123` returns 4K status |
| FR-102 | CLI batch check from file | Efficiency | `findarr check --file ids.txt` processes multiple items |
| FR-103 | CLI config file support | Convenience | Load settings from `~/.config/findarr/config.toml` |
| FR-104 | CLI environment variable config | Flexibility | Support `FINDARR_RADARR_URL`, `FINDARR_RADARR_API_KEY`, etc. |
| FR-105 | CLI JSON output format | Automation | `--format json` outputs machine-readable JSON |
| FR-106 | CLI table output format | Readability | `--format table` outputs pretty terminal table |
| FR-107 | CLI simple output format | Scripting | `--format simple` outputs one-line status per item |

### Nice to Have (P2)

| ID | Requirement | Rationale | Acceptance Criteria |
|----|-------------|-----------|---------------------|
| FR-201 | Configurable 4K detection patterns | Extensibility | Allow custom regex patterns for 4K detection |
| FR-202 | Webhook trigger mode | Integration | Option to trigger Radarr/Sonarr search before checking |
| FR-203 | Async batch operations | Performance | Check multiple items concurrently |

## Non-Functional Requirements

### Performance

- Cached lookups must complete in <100ms
- Uncached lookups depend on Radarr/Sonarr + indexer response time (typically 2-10s)
- Library should not block event loops; all operations are async

### Security

- API keys are never logged or exposed in error messages
- HTTPS connections should verify certificates by default
- No sensitive data stored in cache (only release metadata)

### Reliability

- Retry up to 3 times with exponential backoff on transient errors
- Graceful degradation: if one episode check fails, continue with others
- Clear error types for different failure modes (connection, auth, not found)

### Maintainability

- 100% type coverage with mypy strict mode
- Minimum 80% test coverage
- Pydantic models for all API responses
- Comprehensive docstrings on public API

## Technical Constraints

### Technology Stack

- **Language**: Python 3.11+
- **HTTP Client**: httpx (async)
- **Data Validation**: Pydantic v2
- **Retry Logic**: tenacity
- **Caching**: cachetools (TTLCache)
- **CLI**: typer + rich (optional dependency)
- **Testing**: pytest + pytest-asyncio + respx

### API Compatibility

- Radarr API v3 (`/api/v3/release`, `/api/v3/movie`)
- Sonarr API v3 (`/api/v3/release`, `/api/v3/episode`, `/api/v3/series`)

### Integration Requirements

- Must work with self-hosted Radarr/Sonarr instances
- Support both HTTP and HTTPS connections
- Handle various authentication methods (X-Api-Key header)

## Dependencies

### Internal Dependencies

- None (standalone library)

### External Dependencies

| Dependency | Purpose | Version |
|------------|---------|---------|
| httpx | Async HTTP client | >=0.27.0 |
| pydantic | Data validation | >=2.0.0 |
| tenacity | Retry logic | >=8.2.0 |
| cachetools | TTL caching | >=5.3.0 |
| typer | CLI framework (optional) | >=0.12.0 |
| rich | Terminal formatting (optional) | >=13.0.0 |

## Risks and Mitigations

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Radarr/Sonarr API changes | Low | High | Pin to v3 API; monitor release notes |
| Indexer returns no results | Medium | Medium | Clear messaging; suggest triggering search first |
| Rate limiting by indexers | Medium | Medium | Built-in TTL cache reduces repeat queries |
| 4K detection false negatives | Low | Medium | Multiple detection methods (resolution, name, title) |
| Network timeouts | Medium | Low | Configurable timeouts with retries |

## Open Questions

- [x] Episode selection strategy for TV shows - **Resolved**: Configurable, default to most recent 3 seasons
- [x] Cache scope (per-client vs global) - **Resolved**: Per-client instance
- [x] CLI configuration approach - **Resolved**: Environment variables + config file

## Appendix

### Glossary

| Term | Definition |
|------|------------|
| Radarr | Media management software for movies |
| Sonarr | Media management software for TV series |
| Indexer | Service that provides release information (NZB/torrent) |
| Release | A specific version of media available for download |
| 4K / 2160p | Ultra HD resolution (3840x2160 pixels) |
| TTL | Time-to-live; duration before cached data expires |

### References

- [Radarr API Documentation](https://radarr.video/docs/api/)
- [Sonarr API Documentation](https://sonarr.tv/docs/api/)
- [pyarr - Existing Python wrapper](https://github.com/totaldebug/pyarr)
- [Original 4k-finder service](/Users/dabigc/projects/4k-finder)
