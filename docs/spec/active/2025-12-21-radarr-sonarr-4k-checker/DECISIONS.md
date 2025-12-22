---
document_type: decisions
project_id: SPEC-2025-12-21-001
---

# findarr - Architecture Decision Records

## ADR-001: Use Radarr/Sonarr Release API Instead of Public APIs

**Date**: 2025-12-21
**Status**: Accepted
**Deciders**: User, Claude

### Context

The original 4k-finder project attempted to determine 4K availability using public APIs (JustWatch, TMDb, Streaming Availability). These APIs proved unreliable due to unofficial status, quota limits, and lack of native 4K data fields.

### Decision

Query Radarr and Sonarr's `/api/v3/release` endpoints directly to determine 4K availability from indexer search results.

### Consequences

**Positive:**
- Reliable data source (user's own indexers)
- No quota limits or API costs
- Real-time availability from active indexers
- Simpler architecture (one integration point)

**Negative:**
- Requires user to have Radarr/Sonarr instances
- Depends on indexer availability and coverage
- Cannot check availability for items not in user's library

**Neutral:**
- Different from streaming 4K (this checks download availability)

---

## ADR-002: Episode-Based TV Show Checking with Configurable Sampling

**Date**: 2025-12-21
**Status**: Accepted
**Deciders**: User, Claude

### Context

TV shows have varying 4K availability across seasons. Checking all episodes would be slow and unnecessary. Need a strategy that balances accuracy with performance.

### Decision

1. Check the latest aired episode first (most likely to have active seeders)
2. If no 4K found, apply a configurable sampling strategy:
   - Default: Check one episode from each of the 3 most recent seasons
   - Configurable: Number of seasons and selection strategy
3. Short-circuit on first 4K release found

### Consequences

**Positive:**
- Fast for shows with 4K (stops on first hit)
- Configurable for user needs
- Handles shows with partial 4K availability

**Negative:**
- May miss 4K if only available for older seasons (configurable mitigation)
- Additional API calls compared to simple series-level check

### Alternatives Considered

1. **Series-level search only**: Fast but inaccurate (series search may not show 4K)
2. **Check all episodes**: Accurate but slow
3. **Check latest season only**: Misses shows where older seasons have 4K

---

## ADR-003: Per-Client Instance Caching

**Date**: 2025-12-21
**Status**: Accepted
**Deciders**: User

### Context

Need to decide cache scope for release lookups:
- Per-client instance (each RadarrClient has own cache)
- Global singleton (shared across all instances)
- Disk-backed (persistent across process restarts)

### Decision

Per-client instance caching using cachetools.TTLCache with configurable TTL (default 300 seconds).

### Consequences

**Positive:**
- Simple implementation (no shared state)
- Predictable behavior (cache tied to client lifecycle)
- No cross-contamination between different Radarr/Sonarr instances

**Negative:**
- No cache sharing between clients pointing to same instance
- Cache lost when client is destroyed

### Alternatives Considered

1. **Global cache**: Risk of cache key collision between instances
2. **Disk cache**: Adds complexity, overkill for short-lived cache

---

## ADR-004: tenacity for Retry Logic

**Date**: 2025-12-21
**Status**: Accepted
**Deciders**: Claude (based on research)

### Context

Need retry logic for transient failures (network issues, 5xx errors, rate limits). Options evaluated: tenacity, stamina, custom implementation.

### Decision

Use tenacity library with:
- Exponential backoff (1s, 2s, 4s)
- Max 3 attempts (configurable)
- Retry on: connection errors, timeouts, 429, 5xx
- No retry on: 401, 404 (fail fast)

### Consequences

**Positive:**
- Industry-proven library
- Excellent async support
- Flexible configuration
- Good logging integration

**Negative:**
- Additional dependency

---

## ADR-005: typer + rich for CLI

**Date**: 2025-12-21
**Status**: Accepted
**Deciders**: User (via requirements), Claude

### Context

CLI framework needed for command-line interface. Options: typer, click, argparse.

### Decision

Use typer (with rich for formatting) as optional dependency group `[cli]`.

### Consequences

**Positive:**
- Type hints generate help automatically
- Clean, minimal syntax
- Beautiful output with rich
- Async-friendly

**Negative:**
- Optional dependency adds complexity
- Less common than click

---

## ADR-006: Multiple 4K Detection Methods

**Date**: 2025-12-21
**Status**: Accepted
**Deciders**: Claude (based on research)

### Context

4K releases can be identified multiple ways:
- `quality.quality.resolution` field
- Quality name containing "2160p"
- Release title containing "2160p", "4k", "uhd"

Some releases have incomplete quality parsing (known Radarr bug).

### Decision

Implement cascading 4K detection:
1. Check `resolution == 2160` (most reliable)
2. Check quality name for "2160p"
3. Check title for "2160p", "4k", "uhd" (case-insensitive)

Return true if any method matches.

### Consequences

**Positive:**
- Catches edge cases where quality parsing fails
- Maximizes true positive rate
- Works with various indexer formats

**Negative:**
- Slight risk of false positives (title contains "4k" but isn't)
- Additional string parsing per release

---

## ADR-007: Configuration via Environment Variables + Config File

**Date**: 2025-12-21
**Status**: Accepted
**Deciders**: User

### Context

CLI needs Radarr/Sonarr connection details. Options:
- Environment variables only
- Config file only
- Both with precedence

### Decision

Support both:
1. Config file at `~/.config/findarr/config.toml` (persistent)
2. Environment variables (override config file)
3. Precedence: env vars > config file > defaults

### Consequences

**Positive:**
- Flexible for different use cases
- Secure (env vars for CI/containers)
- Convenient (config file for interactive use)

**Negative:**
- More configuration code
- Need to document precedence rules
