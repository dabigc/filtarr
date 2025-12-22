---
project_id: SPEC-2025-12-21-001
project_name: "findarr - Radarr/Sonarr 4K Availability Checker"
slug: radarr-sonarr-4k-checker
status: in-review
created: 2025-12-21T23:30:00Z
approved: null
started: null
completed: null
expires: 2026-03-21T23:30:00Z
superseded_by: null
tags: [radarr, sonarr, 4k, media-management, python, library, cli]
stakeholders: []
worktree:
  branch: plan/4k-findarr-radarr-sonarr-searc
  base_branch: main
---

# findarr - Radarr/Sonarr 4K Availability Checker

## Overview

**findarr** is a Python library (with optional CLI) that checks 4K availability for movies and TV shows by querying Radarr and Sonarr release search endpoints. It replaces an unreliable approach that depended on inconsistent public APIs (JustWatch, TMDb, Streaming Availability) with a direct integration that queries the user's own Radarr/Sonarr instances.

## Status

**In Review** - Specification complete, awaiting stakeholder approval

## Key Deliverables

| Document | Description | Status |
|----------|-------------|--------|
| [REQUIREMENTS.md](./REQUIREMENTS.md) | Product requirements document | Complete |
| [ARCHITECTURE.md](./ARCHITECTURE.md) | Technical design and data flow | Complete |
| [IMPLEMENTATION_PLAN.md](./IMPLEMENTATION_PLAN.md) | 5-phase task breakdown (27 tasks) | Complete |
| [RESEARCH_NOTES.md](./RESEARCH_NOTES.md) | API research and library evaluation | Complete |
| [DECISIONS.md](./DECISIONS.md) | Architecture decision records (7 ADRs) | Complete |

## Summary

### Problem

The existing 4k-finder service uses public APIs that are unreliable:
- JustWatch: Unofficial API, can break without notice
- TMDb: No native 4K field, relies on user notes
- Streaming API: Quota-limited, requires paid subscription

### Solution

Query Radarr/Sonarr `/api/v3/release` endpoints directly to determine 4K availability from the user's own indexer results.

### Key Features (Planned)

- **Movie 4K checking** via Radarr release endpoint
- **TV series 4K checking** with episode-based sampling
- **Configurable sampling strategy** (most recent 3 seasons by default)
- **Built-in retry with exponential backoff** (tenacity)
- **Per-client TTL caching** (cachetools)
- **CLI interface** with JSON/table/simple output (typer + rich)

### Implementation Phases

1. **Infrastructure** - BaseArrClient with retry and caching
2. **Sonarr Enhancement** - Episode models and episode-level queries
3. **Checker Enhancement** - Sampling strategies and detailed results
4. **CLI** - Commands, config loader, output formatting
5. **Polish** - Documentation, tests, release prep

### Technical Stack

- Python 3.11+
- httpx (async HTTP)
- pydantic v2 (validation)
- tenacity (retry)
- cachetools (caching)
- typer + rich (CLI, optional)

## Next Steps

1. Review specification documents
2. Approve or request changes
3. Run `/claude-spec:implement` to begin implementation
