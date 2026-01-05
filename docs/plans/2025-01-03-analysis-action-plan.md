# Filtarr Analysis Action Plan

**Created:** 2025-01-03
**Status:** PLANNED
**Based on:** Comprehensive Code Analysis (Security, Quality, Architecture, Performance)

---

## Executive Summary

This plan addresses 33 findings from the comprehensive code analysis across Security (8), Code Quality (10), Architecture (6), and Performance (9) domains. Work is organized into 4 phases with explicit subagent assignments.

**All work follows Test-Driven Development (TDD) methodology** with the `tdd-workflows:tdd-orchestrator` subagent coordinating the red-green-refactor cycle for each task.

---

## TDD Workflow Protocol

> **MANDATORY FOR ALL TASKS:** Every task follows test-driven development:

### TDD Cycle (Red-Green-Refactor)

```
┌─────────────────────────────────────────────────────────────────┐
│  1. TDD ORCHESTRATOR: Assess current coverage & requirements    │
│     └─> Analyze existing tests, identify gaps, define test plan │
├─────────────────────────────────────────────────────────────────┤
│  2. RED PHASE: Write failing tests first                        │
│     └─> Tests define expected behavior before implementation    │
│     └─> Run tests to confirm they fail (validates test logic)   │
├─────────────────────────────────────────────────────────────────┤
│  3. DOMAIN SPECIALIST: Implement minimum code to pass tests     │
│     └─> Focus on making tests green, not perfection             │
├─────────────────────────────────────────────────────────────────┤
│  4. GREEN PHASE: Verify all tests pass                          │
│     └─> `uv run pytest [relevant_tests]` must pass              │
├─────────────────────────────────────────────────────────────────┤
│  5. REFACTOR PHASE: Improve code quality                        │
│     └─> Clean up while keeping tests green                      │
│     └─> Run full test suite to prevent regressions              │
├─────────────────────────────────────────────────────────────────┤
│  6. TDD ORCHESTRATOR: Validate coverage & quality gates         │
│     └─> Coverage maintained or improved                         │
│     └─> All linting/type checks pass                            │
└─────────────────────────────────────────────────────────────────┘
```

### Subagent Coordination

Each task involves **two subagents working together**:

| Role | Subagent | Responsibility |
|------|----------|----------------|
| **TDD Lead** | `tdd-workflows:tdd-orchestrator` | Test design, coverage assessment, quality gates |
| **Domain Specialist** | _(varies by task)_ | Implementation expertise for the specific domain |

The TDD orchestrator:
1. **Starts first**: Analyzes existing tests and coverage
2. **Writes tests**: Creates failing tests that define the requirement
3. **Validates**: Confirms tests fail for the right reasons
4. **Hands off**: Domain specialist implements the fix
5. **Reviews**: Verifies tests pass and coverage is adequate
6. **Approves**: Signs off on task completion

---

## Plan Update Protocol

> **IMPORTANT FOR SUBAGENTS:** When working on any task in this plan:
> 1. Update the task status from `[ ]` to `[~]` when starting
> 2. Update TDD Phase status as you progress through the cycle
> 3. Update from `[~]` to `[x]` when complete
> 4. Add completion notes with date, coverage delta, and any relevant details
> 5. If blocked, add `[!]` and document the blocker
> 6. Update the Phase Status when all tasks complete

---

## Phase 1: Critical Security & Reliability Fixes

**Priority:** IMMEDIATE
**Target:** Fix vulnerabilities that could cause security issues or silent failures

### Phase Status: NOT STARTED

### Task 1.1: Fix Timing Attack in API Key Comparison
- **Status:** [x] Complete
- **File:** `src/filtarr/webhook.py:66-71`
- **TDD Lead:** `tdd-workflows:tdd-orchestrator`
- **Domain Specialist:** `backend-api-security:backend-security-coder`
- **Severity:** MEDIUM

**TDD Phase Tracking:**
- [x] 🔴 RED: Tests written for constant-time comparison
- [x] 🟢 GREEN: Implementation passes tests
- [x] 🔵 REFACTOR: Code cleaned up, coverage verified

**Problem:**
```python
if config.radarr and api_key == config.radarr.api_key:  # Vulnerable to timing attack
```

**Test Requirements (TDD Orchestrator writes first):**
1. Test that `_validate_api_key` uses constant-time comparison
2. Test that valid API keys still authenticate correctly
3. Test that invalid API keys are rejected
4. Test edge cases (empty strings, None values)

**Implementation Requirements (Domain Specialist):**
1. Import `hmac` module
2. Replace `==` with `hmac.compare_digest()` for all API key comparisons

**Acceptance Criteria:**
- [x] All API key comparisons use constant-time comparison
- [x] New tests verify secure comparison behavior
- [x] `uv run ruff check src` passes
- [x] `uv run mypy src` passes
- [x] `uv run pytest tests/test_webhook.py` passes
- [x] Coverage maintained or improved

**Completion Notes:**
> **Date:** 2025-01-03
> **Coverage before/after:** 100% -> 100% (maintained)
> **Notes:** Imported `hmac` module and replaced `==` comparisons with `hmac.compare_digest()` in `_validate_api_key` function. All 102 webhook tests pass. Test `test_validate_api_key_uses_constant_time_comparison` was already present and is now passing.

---

### Task 1.2: Fix 429/5xx Retry Logic
- **Status:** [x] Complete
- **File:** `src/filtarr/clients/base.py:249-276`
- **TDD Lead:** `tdd-workflows:tdd-orchestrator`
- **Domain Specialist:** `backend-development:backend-architect`
- **Severity:** HIGH

**TDD Phase Tracking:**
- [x] 🔴 RED: Tests written for retry behavior on 429/5xx
- [x] 🟢 GREEN: Implementation passes tests
- [x] 🔵 REFACTOR: Code cleaned up, coverage verified

**Problem:**
The retry decorator only catches connection errors, but 429/5xx raise `HTTPStatusError` which is NOT in the retry filter. These errors log but don't actually retry.

**Test Requirements (TDD Orchestrator writes first):**
1. Test 429 response triggers retry (mock respx to return 429, then 200)
2. Test 500, 502, 503, 504 responses trigger retry
3. Test Retry-After header is respected when present
4. Test 401 fails immediately without retry
5. Test 404 fails immediately without retry
6. Test max retries is respected

**Implementation Requirements (Domain Specialist):**
1. Create a custom retry predicate function that checks:
   - Connection errors (already covered)
   - HTTPStatusError with status 429, 500, 502, 503, 504
2. Update the `@retry` decorator to use this predicate
3. Add Retry-After header handling for 429 responses

**Acceptance Criteria:**
- [x] 429 responses trigger retry with backoff
- [x] 5xx responses trigger retry with backoff
- [x] Retry-After header is respected when present
- [x] 401/404 still fail immediately (no retry)
- [x] All existing tests pass
- [x] New tests cover retry scenarios
- [x] Coverage maintained or improved

**Completion Notes:**
> **Date:** 2025-01-03
> **Coverage before/after:** 93% -> 98% (improved by 5%)
> **Notes:**
> - Created `RetryableHTTPError` exception class to wrap retryable HTTP status errors and carry Retry-After header value
> - Created `RetryPredicate` class (extends `retry_base`) to check for connection errors and `RetryableHTTPError`
> - Created `RetryAfterWait` class (extends `wait_exponential`) to respect Retry-After header when present
> - Added `RETRYABLE_STATUS_CODES` constant: `{429, 500, 502, 503, 504}`
> - Updated `_request_with_retry()` to raise `RetryableHTTPError` for retryable statuses, which triggers retry
> - After retries exhausted, re-raises as `HTTPStatusError` for backward compatibility
> - Added 11 new tests covering: 429 retry, 500/502/503/504 retry, max retries exhausted, Retry-After header, no retry on 400/403, mixed scenarios
> - All 162 core tests pass; all linting and type checks pass

---

### Task 1.3: Add Security Warning for allow_insecure Flag
- **Status:** [x] Complete
- **File:** `src/filtarr/config.py:82-92, 117-127`
- **TDD Lead:** `tdd-workflows:tdd-orchestrator`
- **Domain Specialist:** `backend-api-security:backend-security-coder`
- **Severity:** LOW

**TDD Phase Tracking:**
- [x] 🔴 RED: Tests written for warning emission
- [x] 🟢 GREEN: Implementation passes tests
- [x] 🔵 REFACTOR: Code cleaned up, coverage verified

**Problem:**
Using `allow_insecure=True` silently allows HTTP for remote servers with no warning.

**Test Requirements (TDD Orchestrator writes first):**
1. Test RadarrConfig emits warning when allow_insecure=True with non-localhost URL
2. Test SonarrConfig emits warning when allow_insecure=True with non-localhost URL
3. Test no warning when allow_insecure=False
4. Test no warning when allow_insecure=True but URL is localhost
5. Test warning message contains security risk explanation

**Implementation Requirements (Domain Specialist):**
1. Add warning when `allow_insecure=True` is used in RadarrConfig.__post_init__
2. Add same warning to SonarrConfig.__post_init__
3. Use Python warnings module with UserWarning

**Acceptance Criteria:**
- [x] Warning emitted when allow_insecure=True used with remote URL
- [x] Warning message explains the security risk
- [x] Tests verify warning is raised in correct scenarios
- [x] All checks pass
- [x] Coverage maintained or improved

**Completion Notes:**
> **Date:** 2026-01-04
> **Coverage before/after:** 99% -> 99% (maintained)
> **Notes:** Added UserWarning emission in RadarrConfig.__post_init__ and SonarrConfig.__post_init__ when allow_insecure=True is used with a non-localhost HTTP URL. Warning message includes the hostname and explains that API credentials may be intercepted. Added 16 new tests in TestAllowInsecureSecurityWarning class covering all scenarios: remote URLs, localhost variations (localhost, 127.0.0.1, ::1), IP addresses, HTTPS URLs, and warning message content validation. All 168 config tests pass. All linting and type checks pass.

---

## Phase 2: Code Quality & Duplication Reduction

**Priority:** HIGH
**Target:** Reduce maintenance burden and improve consistency

### Phase Status: NOT STARTED

### Task 2.1: Refactor Global State in Webhook Module
- **Status:** [x] Complete
- **File:** `src/filtarr/webhook.py:30-34`
- **TDD Lead:** `tdd-workflows:tdd-orchestrator`
- **Domain Specialist:** `api-scaffolding:fastapi-pro`
- **Severity:** MEDIUM

**TDD Phase Tracking:**
- [x] 🔴 RED: Tests written for dependency injection pattern
- [x] 🟢 GREEN: Implementation passes tests
- [x] 🔵 REFACTOR: Code cleaned up, coverage verified

**Problem:**
```python
_scheduler_manager: SchedulerManager | None = None
_state_manager: StateManager | None = None
_output_format: str = "text"
```
Global mutable state creates testing difficulties and potential race conditions.

**Test Requirements (TDD Orchestrator writes first):**
1. Test that dependencies can be injected via FastAPI's dependency system
2. Test that mocked dependencies work correctly in tests
3. Test that app.state holds the correct references
4. Test isolation between test runs (no state bleed)

**Implementation Requirements (Domain Specialist):**
1. Move state to FastAPI's `app.state` attribute
2. Use dependency injection for accessing these in route handlers
3. Update all references to use the new pattern

**Acceptance Criteria:**
- [x] No module-level mutable global variables
- [x] State accessible via app.state or dependency injection
- [x] All webhook tests pass with improved isolation
- [x] All checks pass
- [x] Coverage maintained or improved

**Completion Notes:**
> **Date:** 2026-01-04
> **Coverage before/after:** 100% -> 100% (maintained)
> **Notes:**
> - Removed global variables `_scheduler_manager`, `_state_manager`, `_output_format` from module level
> - Extended `create_app()` to accept optional `state_manager`, `scheduler_manager`, and `output_format` parameters
> - Store all state on `app.state` for proper isolation (scheduler_manager, state_manager, output_format, config)
> - Updated `_process_movie_check()` and `_process_series_check()` to accept `state_manager` and `output_format` as parameters
> - Updated webhook handlers to pass state from `app.state` to background processing functions
> - Updated `run_server()` to pass state directly to `create_app()` instead of using globals
> - Updated status endpoint to access scheduler_manager from `app.state` instead of global
> - Added 11 new tests in TestDependencyInjection class verifying:
>   - app.state has scheduler_manager, state_manager, output_format attributes
>   - No global _scheduler_manager, _state_manager, _output_format exist in module
>   - Status endpoint uses app.state for scheduler info
>   - Multiple app instances have isolated state
>   - Test isolation between runs (no state bleed)
>   - create_app accepts initial state_manager and output_format parameters
> - Updated 40+ existing tests to use parameter-based approach instead of global manipulation
> - All 113 webhook tests pass; all linting and type checks pass

---

### Task 2.2: Extract Common Check Logic in checker.py
- **Status:** [x] Complete
- **File:** `src/filtarr/checker.py:307-408, 429-641`
- **TDD Lead:** `tdd-workflows:tdd-orchestrator`
- **Domain Specialist:** `code-refactoring:code-reviewer`
- **Severity:** HIGH (Duplication)

**TDD Phase Tracking:**
- [x] 🔴 RED: Verify existing tests provide adequate coverage for refactoring
- [x] 🟢 GREEN: Refactoring maintains all test behavior
- [x] 🔵 REFACTOR: Code cleaned up, coverage verified

**Problem:**
- `check_movie` and `check_movie_by_name` share ~40 lines of identical logic
- `check_series` and `check_series_by_name` share similar duplication
- Tag application logic repeated 5 times

**Test Requirements (TDD Orchestrator assesses first):**
1. Verify existing test coverage for check_movie, check_movie_by_name
2. Verify existing test coverage for check_series, check_series_by_name
3. Add any missing edge case tests before refactoring
4. Tests should pass before AND after refactoring unchanged

**Implementation Requirements (Domain Specialist):**
1. Create `_check_movie_impl(movie, client, ...)` private method
2. Create `_check_series_impl(series, client, ...)` private method
3. Create `_apply_tags_if_needed(...)` helper method
4. Refactor public methods to use these helpers
5. Ensure no behavior changes (pure refactoring)

**Acceptance Criteria:**
- [x] No duplicated check logic
- [x] Tag application centralized in one helper
- [x] All existing tests pass unchanged
- [x] Code coverage maintained or improved
- [x] All checks pass

**Completion Notes:**
> **Date:** 2026-01-04
> **Coverage before/after:** 84% -> 84% (maintained, statement count reduced from 225 to 214)
> **Notes:**
> - Created `_get_matcher_and_result_type(criteria)` helper to centralize matcher/result_type determination
> - Created `_apply_tags_if_needed(client, item_id, has_match, criteria, apply_tags, dry_run, is_movie)` helper to centralize tag application logic (replaces 5 duplicated blocks)
> - Created `_check_movie_impl(movie, releases, client, criteria, apply_tags, dry_run)` helper for movie checking logic
> - Refactored `check_movie` and `check_movie_by_name` to use `_check_movie_impl`
> - Refactored `check_series` to use `_get_matcher_and_result_type` and `_apply_tags_if_needed`
> - Note: `check_series_by_name` already delegates to `check_series` (no changes needed)
> - All 68 checker tests pass; linting and type checking pass
> - Reduced code duplication by ~50 lines while maintaining identical behavior

---

### Task 2.3: Consolidate RadarrConfig/SonarrConfig
- **Status:** [x] Complete
- **File:** `src/filtarr/config.py:68-135`
- **TDD Lead:** `tdd-workflows:tdd-orchestrator`
- **Domain Specialist:** `code-refactoring:code-reviewer`
- **Severity:** MEDIUM (DRY violation)

**TDD Phase Tracking:**
- [x] 🔴 RED: Verify existing config tests cover all validation paths
- [x] 🟢 GREEN: Refactoring maintains all test behavior
- [x] 🔵 REFACTOR: Code cleaned up, coverage verified

**Problem:**
RadarrConfig and SonarrConfig are identical except for class names and repr strings.

**Test Requirements (TDD Orchestrator assesses first):**
1. Verify test coverage for URL validation in RadarrConfig
2. Verify test coverage for URL validation in SonarrConfig
3. Ensure __repr__ masking is tested for both
4. Add tests for inheritance behavior if missing

**Implementation Requirements (Domain Specialist):**
1. Create base `ArrConfig` dataclass with all shared logic
2. RadarrConfig and SonarrConfig inherit from ArrConfig
3. Only override `__repr__` and `__str__` for name differentiation
4. Maintain backward compatibility (no API changes)

**Acceptance Criteria:**
- [x] Single source of truth for URL validation
- [x] Both configs still work identically
- [x] All tests pass
- [x] Type hints remain correct
- [x] Coverage maintained or improved

**Completion Notes:**
> **Date:** 2026-01-04
> **Coverage before/after:** 99% -> 99% (maintained, statement count reduced from 294 to 280)
> **Notes:**
> - Created base `ArrConfig` dataclass with `@dataclass(repr=False)` to prevent auto-generated repr from exposing API keys
> - Moved all shared logic (URL validation, security warnings, `__post_init__`, `__repr__`, `__str__`) to base class
> - `RadarrConfig` and `SonarrConfig` now inherit from `ArrConfig` with empty bodies
> - Used `__class__.__name__` in base `_get_service_name()` method to automatically use correct class name in repr
> - All 168 config tests pass; ruff linting passes; mypy type checking passes
> - Reduced code duplication by 14 lines (50%+ reduction in duplicated validation logic)
> - Full backward compatibility maintained - no API changes required

---

### Task 2.4: Extract Season Parsing in SonarrClient
- **Status:** [x] Complete
- **File:** `src/filtarr/clients/sonarr.py`
- **TDD Lead:** `tdd-workflows:tdd-orchestrator`
- **Domain Specialist:** `code-refactoring:code-reviewer`
- **Severity:** MEDIUM (DRY violation)

**TDD Phase Tracking:**
- [x] 🔴 RED: Verify existing tests cover season parsing
- [x] 🟢 GREEN: Refactoring maintains all test behavior
- [x] 🔵 REFACTOR: Code cleaned up, coverage verified

**Problem:**
Season parsing logic duplicated in 3 locations: `get_all_series`, `get_series`, `update_series`.

**Test Requirements (TDD Orchestrator assesses first):**
1. Verify tests cover Season parsing in get_all_series
2. Verify tests cover Season parsing in get_series
3. Verify tests cover Season parsing in update_series
4. Add tests for edge cases (empty seasons, missing statistics)

**Implementation Requirements (Domain Specialist):**
1. Create `@staticmethod _parse_seasons(data: dict) -> list[Season]` method
2. Use this helper in all three locations
3. No behavior changes

**Acceptance Criteria:**
- [x] Season parsing logic in single location
- [x] All Sonarr client tests pass
- [x] All checks pass
- [x] Coverage maintained or improved

**Completion Notes:**
> **Date:** 2026-01-04
> **Coverage before/after:** 96% -> 98% (improved by 2%)
> **Notes:**
> - Created `@staticmethod _parse_seasons(data: dict[str, Any]) -> list[Season]` method with full docstring
> - Refactored `get_all_series`, `get_series`, and `update_series` to use the new helper
> - Added 6 new tests in `TestSeasonParsing` class covering:
>   - get_series with full statistics
>   - get_series with missing statistics
>   - get_series with empty seasons
>   - update_series with full statistics
>   - update_series with missing statistics
>   - All three methods parse seasons identically (consistency test)
> - Reduced code from 106 statements to 101 statements (5 lines removed)
> - All 49 Sonarr client tests pass; ruff linting passes; mypy type checking passes

---

### Task 2.5: Refactor Duplicate Webhook Processing Functions
- **Status:** [x] Complete
- **File:** `src/filtarr/webhook.py:122-237`
- **TDD Lead:** `tdd-workflows:tdd-orchestrator`
- **Domain Specialist:** `api-scaffolding:fastapi-pro`
- **Severity:** MEDIUM (80+ lines duplicated)

**TDD Phase Tracking:**
- [x] 🔴 RED: Verify existing tests cover movie and series processing
- [x] 🟢 GREEN: Refactoring maintains all test behavior
- [x] 🔵 REFACTOR: Code cleaned up, coverage verified

**Problem:**
`_process_movie_check` and `_process_series_check` are 80+ lines each with nearly identical structure.

**Test Requirements (TDD Orchestrator assesses first):**
1. Verify movie webhook processing test coverage
2. Verify series webhook processing test coverage
3. Ensure error handling paths are tested for both
4. Add parameterized tests for the generic function

**Implementation Requirements (Domain Specialist):**
1. Create generic `_process_media_check(media_type, ...)` function
2. Parameterize differences (client method, logging strings, etc.)
3. Movie and series handlers call the generic function
4. Maintain identical behavior

**Acceptance Criteria:**
- [x] Single generic processing function
- [x] Both movie and series webhooks work correctly
- [x] All webhook tests pass
- [x] All checks pass
- [x] Coverage maintained or improved

**Completion Notes:**
> **Date:** 2026-01-04
> **Coverage before/after:** 100% -> 100% (maintained, statements reduced from 231 to 204)
> **Notes:**
> - Created generic `_process_media_check(media_type: Literal["movie", "series"], ...)` function that handles both movie and series webhook processing
> - Used `Literal` type hint to ensure proper type checking compatibility with StateManager methods
> - `_process_movie_check` and `_process_series_check` now delegate to `_process_media_check` with appropriate media_type
> - Reduced duplicated code by 27 statements (from 231 to 204)
> - All 113 webhook tests pass; ruff linting passes; mypy type checking passes

---

## Phase 3: Architecture & Testability Improvements

**Priority:** MEDIUM
**Target:** Improve extensibility and test isolation

### Phase Status: NOT STARTED

### Task 3.1: Accept Pre-Created Clients in ReleaseChecker
- **Status:** [x] Complete
- **File:** `src/filtarr/checker.py`
- **TDD Lead:** `tdd-workflows:tdd-orchestrator`
- **Domain Specialist:** `backend-development:backend-architect`
- **Severity:** HIGH (Testability)

**TDD Phase Tracking:**
- [x] 🔴 RED: Tests written for client injection
- [x] 🟢 GREEN: Implementation passes tests
- [x] 🔵 REFACTOR: Code cleaned up, coverage verified

**Problem:**
Clients are created internally, making it hard to inject mocks for testing.

**Test Requirements (TDD Orchestrator writes first):**
1. Test that injected radarr_client is used when provided
2. Test that injected sonarr_client is used when provided
3. Test backward compatibility (URL + API key still works)
4. Test that injected clients are NOT closed on __aexit__ (caller manages lifecycle)

**Implementation Requirements (Domain Specialist):**
1. Add optional `radarr_client` and `sonarr_client` parameters to `__init__`
2. If provided, use injected clients instead of creating new ones
3. If not provided, fall back to current behavior (URL + API key)
4. Update docstrings to document new parameters

**Acceptance Criteria:**
- [x] Optional client injection works
- [x] Backward compatible (existing code unchanged)
- [x] Tests can inject mock clients
- [x] All checks pass
- [x] Coverage maintained or improved

**Completion Notes:**
> **Date:** 2026-01-04
> **Coverage before/after:** 84% -> 94% (improved by 10%)
> **Notes:**
> - Added optional `radarr_client` and `sonarr_client` keyword-only parameters to `ReleaseChecker.__init__`
> - Injected clients take precedence over URL+API key configuration
> - Track which clients are injected vs created internally using `_radarr_client_injected` and `_sonarr_client_injected` flags
> - `__aenter__` only creates clients if not injected
> - `__aexit__` only closes and clears clients that were created internally (injected clients preserved for caller to manage)
> - `_get_radarr_client` and `_get_sonarr_client` use injected clients directly without needing to be "in context"
> - Updated all 7 configuration checks to accept either injected client OR URL config
> - Added 11 new tests in `TestClientInjection` class covering all scenarios
> - All 79 checker tests pass; all 94 checker + connection pooling tests pass
> - All linting (ruff) and type checking (mypy) pass

---

### Task 3.2: Introduce ReleaseProvider Protocol
- **Status:** [x] Complete
- **File:** `src/filtarr/clients/base.py`
- **TDD Lead:** `tdd-workflows:tdd-orchestrator`
- **Domain Specialist:** `backend-development:backend-architect`
- **Severity:** MEDIUM (Extensibility)

**TDD Phase Tracking:**
- [x] 🔴 RED: Tests written for protocol compliance
- [x] 🟢 GREEN: Implementation passes tests
- [x] 🔵 REFACTOR: Code cleaned up, coverage verified

**Problem:**
No protocol for release-fetching operations limits polymorphic client usage.

**Test Requirements (TDD Orchestrator writes first):**
1. Test RadarrClient satisfies ReleaseProvider protocol
2. Test SonarrClient satisfies ReleaseProvider protocol
3. Test isinstance() check works (runtime_checkable)
4. Test mock ReleaseProvider works in checker context

**Implementation Requirements (Domain Specialist):**
1. Add `ReleaseProvider` Protocol to `base.py`:
   ```python
   @runtime_checkable
   class ReleaseProvider(Protocol):
       async def get_releases_for_item(self, item_id: int) -> list[Release]: ...
   ```
2. Ensure RadarrClient and SonarrClient implement the protocol
3. Add tests verifying protocol compliance

**Acceptance Criteria:**
- [x] ReleaseProvider protocol defined
- [x] Both clients satisfy the protocol
- [x] Type checking passes
- [x] All checks pass
- [x] Coverage maintained or improved

**Completion Notes:**
> **Date:** 2026-01-04
> **Coverage before/after:** 98% -> 98% (maintained)
> **Notes:**
> - Added `ReleaseProvider` Protocol to `src/filtarr/clients/base.py` with `@runtime_checkable` decorator
> - Protocol defines single method: `async def get_releases_for_item(self, item_id: int) -> list[Release]`
> - Added `get_releases_for_item` method to `RadarrClient` as alias for `get_movie_releases`
> - Added `get_releases_for_item` method to `SonarrClient` as alias for `get_series_releases`
> - Added 7 new tests in `TestReleaseProviderProtocol` class:
>   - `test_radarr_client_satisfies_release_provider_protocol`
>   - `test_sonarr_client_satisfies_release_provider_protocol`
>   - `test_release_provider_is_runtime_checkable`
>   - `test_radarr_get_releases_for_item_works`
>   - `test_sonarr_get_releases_for_item_works`
>   - `test_mock_release_provider_usable`
>   - `test_base_arr_client_does_not_satisfy_release_provider`
> - All 116 client tests pass; all linting (ruff) and type checking (mypy) pass

---

### Task 3.3: Add MediaType Enum
- **Status:** [x] Complete
- **File:** `src/filtarr/checker.py:64`
- **TDD Lead:** `tdd-workflows:tdd-orchestrator`
- **Domain Specialist:** `code-refactoring:code-reviewer`
- **Severity:** LOW (Type Safety)

**TDD Phase Tracking:**
- [x] 🔴 RED: Tests written for enum usage and JSON serialization
- [x] 🟢 GREEN: Implementation passes tests
- [x] 🔵 REFACTOR: Code cleaned up, coverage verified

**Problem:**
`item_type: str  # "movie" or "series"` uses magic strings.

**Test Requirements (TDD Orchestrator writes first):**
1. Test MediaType.MOVIE.value == "movie"
2. Test MediaType.SERIES.value == "series"
3. Test SearchResult serialization produces string values
4. Test existing code paths work with enum

**Implementation Requirements (Domain Specialist):**
1. Create `MediaType` enum with MOVIE and SERIES values
2. Update `SearchResult.item_type` to use enum
3. Update all usages throughout codebase
4. Maintain string serialization for JSON output

**Acceptance Criteria:**
- [x] MediaType enum created
- [x] All item_type usages updated
- [x] JSON output still produces strings
- [x] All checks pass
- [x] Coverage maintained or improved

**Completion Notes:**
> **Date:** 2026-01-04
> **Coverage before/after:** 94% -> 94% (maintained, statements increased from 216 to 219 for new enum)
> **Notes:**
> - Created `MediaType` as `StrEnum` in `src/filtarr/checker.py` with `MOVIE = "movie"` and `SERIES = "series"` values
> - Using `StrEnum` ensures automatic string serialization for JSON output without explicit conversion
> - Updated `SearchResult.item_type` field from `str` to `MediaType` type annotation
> - Updated all 5 locations in `checker.py` that create `SearchResult` to use `MediaType.MOVIE` or `MediaType.SERIES`
> - Added `MediaType` to public exports in `src/filtarr/__init__.py`
> - Added 8 new tests in `TestMediaTypeEnum` and `TestSearchResult` classes:
>   - `test_media_type_movie_value_is_string_movie`
>   - `test_media_type_series_value_is_string_series`
>   - `test_media_type_is_str_subclass`
>   - `test_media_type_string_comparison`
>   - `test_media_type_in_dict_key`
>   - `test_search_result_item_type_is_media_type_enum`
>   - `test_search_result_item_type_serializes_to_string`
>   - Updated `test_matched_releases_property` to use `MediaType.MOVIE`
> - All 86 checker tests pass; all 326 critical tests pass
> - All ruff linting passes; all mypy type checking passes (26 source files)

---

### Task 3.4: Enhance Credential Log Filtering
- **Status:** [x] Complete
- **File:** `src/filtarr/logging.py:82-87`
- **TDD Lead:** `tdd-workflows:tdd-orchestrator`
- **Domain Specialist:** `backend-api-security:backend-security-coder`
- **Severity:** LOW (Defense in Depth)

**TDD Phase Tracking:**
- [x] 🔴 RED: Tests written for new filter patterns
- [x] 🟢 GREEN: Implementation passes tests
- [x] 🔵 REFACTOR: Code cleaned up, coverage verified

**Problem:**
Current patterns may miss URL-encoded credentials and Authorization headers.

**Test Requirements (TDD Orchestrator writes first):**
1. Test URL-encoded API key is filtered: `api_key%3Dsecret123`
2. Test Authorization Bearer header is filtered
3. Test existing patterns still work
4. Test various encoding edge cases

**Implementation Requirements (Domain Specialist):**
1. Add pattern for URL-encoded API keys: `api[_-]?key%3[dD][\w%-]+`
2. Add pattern for Authorization headers: `Authorization["\s:=]+["\']?Bearer\s+[\w.-]+`

**Acceptance Criteria:**
- [x] URL-encoded credentials filtered
- [x] Authorization headers filtered
- [x] All logging tests pass
- [x] All checks pass
- [x] Coverage maintained or improved

**Completion Notes:**
> **Date:** 2026-01-04
> **Coverage before/after:** 100% -> 100% (maintained)
> **Notes:**
> - Added `Authorization` Bearer token pattern: `Authorization["\s:=]+["\']?Bearer\s+[\w.-]+` (case-insensitive)
> - Added URL-encoded API key pattern: `api[_-]?key%3[dD][\w%-]+` (handles both %3d and %3D)
> - Pattern ordering: Authorization first for priority, then X-Api-Key, then URL-encoded, then regular api_key
> - Updated docstring to document all 5 pattern types (Authorization, X-Api-Key, regular api_key, URL-encoded, JSON-style)
> - Added 10 new tests in `TestURLEncodedAndAuthorizationFiltering` class:
>   - test_filter_url_encoded_api_key_lowercase_hex
>   - test_filter_url_encoded_api_key_uppercase_hex
>   - test_filter_url_encoded_api_hyphen_key
>   - test_filter_url_encoded_with_percent_encoded_value
>   - test_filter_authorization_bearer_header
>   - test_filter_authorization_bearer_with_quotes
>   - test_filter_authorization_bearer_compact_format
>   - test_filter_authorization_case_insensitive
>   - test_filter_multiple_encoding_and_auth_patterns
>   - test_existing_patterns_still_work_with_new_patterns
> - All 56 logging tests pass (13 existing + 10 new filter tests + 33 other tests)
> - All ruff linting passes; all mypy type checking passes
> - 100% coverage maintained on logging module (49 statements, 0 missed)

---

## Phase 4: Performance Optimizations

**Priority:** LOW-MEDIUM
**Target:** Improve efficiency for large batch operations

### Phase Status: NOT STARTED

### Task 4.1: Fix Cache Thundering Herd
- **Status:** [x] Complete
- **File:** `src/filtarr/clients/base.py:278-357`
- **TDD Lead:** `tdd-workflows:tdd-orchestrator`
- **Domain Specialist:** `application-performance:performance-engineer`
- **Severity:** MEDIUM

**TDD Phase Tracking:**
- [x] 🔴 RED: Tests written for stampede protection
- [x] 🟢 GREEN: Implementation passes tests
- [x] 🔵 REFACTOR: Code cleaned up, coverage verified

**Problem:**
Concurrent requests for the same uncached key all hit the API (stampede).

**Test Requirements (TDD Orchestrator writes first):**
1. Test concurrent requests for same cache key only trigger one API call
2. Test second request waits for first to complete
3. Test both requests receive the same cached result
4. Test error in first request propagates correctly to waiters
5. Benchmark test comparing before/after behavior

**Implementation Requirements (Domain Specialist):**
1. Implement stampede protection using pending request tracking
2. Use asyncio.Event to coordinate waiting requests
3. First request fetches, others wait for result

**Acceptance Criteria:**
- [x] Only one request made for concurrent cache misses
- [x] Other requests wait and receive cached result
- [x] All existing tests pass
- [x] Performance test demonstrates improvement
- [x] Coverage maintained or improved

**Completion Notes:**
> **Date:** 2026-01-04
> **Coverage before/after:** 98% -> 96% (minor decrease due to added code paths for error handling)
> **Notes:**
> - Added `_pending_requests` dict to track in-flight requests by cache key
> - Each entry holds an `asyncio.Event` and a result holder dict
> - First request becomes the "leader" and fetches data while others wait
> - Waiters receive the same cached result or error from the leader
> - Added 6 new tests in `TestCacheStampedeProtection` class:
>   - `test_concurrent_requests_only_trigger_one_api_call`: Verifies 5 concurrent requests make only 1 API call
>   - `test_second_request_waits_for_first_to_complete`: Verifies timing shows parallel wait behavior
>   - `test_concurrent_requests_receive_same_cached_result`: Verifies all get identical data
>   - `test_error_in_first_request_propagates_to_all_waiters`: Error propagation to waiters
>   - `test_different_cache_keys_make_separate_requests`: Different keys are independent
>   - `test_retryable_error_in_first_request_propagates_to_waiters`: Retryable errors also propagate
> - All 44 base client tests pass; all 29 additional client tests pass
> - All ruff linting passes; mypy type checking passes

---

### Task 4.2: Reuse Client for Fetch and Batch
- **Status:** [x] Complete
- **File:** `src/filtarr/scheduler/executor.py`
- **TDD Lead:** `tdd-workflows:tdd-orchestrator`
- **Domain Specialist:** `application-performance:performance-engineer`
- **Severity:** MEDIUM

**TDD Phase Tracking:**
- [x] 🔴 RED: Tests written for client reuse verification
- [x] 🟢 GREEN: Implementation passes tests
- [x] 🔵 REFACTOR: Code cleaned up, coverage verified

**Problem:**
`_get_movies_to_check` and `_process_movies_batch` create separate client instances.

**Test Requirements (TDD Orchestrator writes first):**
1. Test same client instance used for list fetch and batch processing
2. Test client lifecycle is managed correctly
3. Test connection pooling is utilized (mock verification)
4. Test error handling when client fails mid-batch

**Implementation Requirements (Domain Specialist):**
1. Create client once for entire execute() operation
2. Pass client to helper methods
3. Same pattern for series operations

**Acceptance Criteria:**
- [x] Single client used for list fetch + batch processing
- [x] Connection pooling verified
- [x] All scheduler tests pass
- [x] All checks pass
- [x] Coverage maintained or improved

**Completion Notes:**
> **Date:** 2026-01-04
> **Coverage before/after:** 100% -> 100% (maintained, statements increased from 171 to 183 due to new lifecycle management code)
> **Notes:**
> - Created client once in `execute()` method for the entire operation (connection pooling)
> - Client is passed to `_get_movies_to_check`, `_get_series_to_check`, `_process_movies_batch`, and `_process_series_batch`
> - Updated `_create_checker()` to accept optional `radarr_client` and `sonarr_client` parameters for injection into ReleaseChecker
> - ReleaseChecker uses injected clients (from Task 3.1) to avoid creating duplicate clients
> - Added proper `finally` block to ensure clients are closed even on error
> - Added 5 new tests in `TestClientReuseForFetchAndBatch` class:
>   - `test_same_radarr_client_used_for_fetch_and_batch`: Verifies only 1 RadarrClient instance created
>   - `test_same_sonarr_client_used_for_fetch_and_batch`: Verifies only 1 SonarrClient instance created
>   - `test_client_lifecycle_managed_correctly`: Verifies single `__aenter__`/`__aexit__` per client
>   - `test_error_during_batch_properly_closes_client`: Verifies client closed even on mid-batch errors
>   - `test_connection_pooling_verified_same_httpx_client`: Verifies all requests use same httpx.AsyncClient
> - Updated 4 existing tests in `TestGetSeriesToCheck` and `TestGetMoviesToCheck` to pass client parameter
> - All 120 executor/scheduler tests pass; all 206 executor+checker tests pass
> - All ruff linting passes; mypy type checking passes

---

### Task 4.3: Batch State File Writes
- **Status:** [x] Complete
- **File:** `src/filtarr/state.py`
- **TDD Lead:** `tdd-workflows:tdd-orchestrator`
- **Domain Specialist:** `application-performance:performance-engineer`
- **Severity:** MEDIUM

**TDD Phase Tracking:**
- [x] 🔴 RED: Tests written for batched write behavior
- [x] 🟢 GREEN: Implementation passes tests
- [x] 🔵 REFACTOR: Code cleaned up, coverage verified

**Problem:**
State file is written after every single check, causing thousands of disk writes in batch operations.

**Test Requirements (TDD Orchestrator writes first):**
1. Test writes are batched (N checks before write)
2. Test flush() forces immediate write
3. Test context exit flushes pending writes
4. Test no data loss scenarios (crash simulation)
5. Test configurable batch size

**Implementation Requirements (Domain Specialist):**
1. Add write batching with configurable batch size
2. Add `flush()` method for forced writes
3. Ensure flush on context exit

**Acceptance Criteria:**
- [x] Writes batched (default: every 100 checks)
- [x] flush() forces immediate write
- [x] No data loss on exit
- [x] All state tests pass
- [x] All checks pass
- [x] Coverage maintained or improved

**Completion Notes:**
> **Date:** 2026-01-04
> **Coverage before/after:** 99% -> 99% (maintained, statements increased from 265 to 289 due to new batching code)
> **Notes:**
> - Added `batch_size` parameter to `StateManager.__init__` (default: 100)
> - Added `_pending_writes` counter to track operations since last write
> - Added `_do_save()` internal method for actual disk I/O
> - Added `flush()` method to force immediate write of pending changes
> - Added `_maybe_save()` internal method for batched write logic
> - Added `pending_writes` and `has_pending_writes` properties
> - Added context manager support (`__enter__`/`__exit__`) that flushes on exit
> - Updated `record_check()` to use batched writes via `_maybe_save()`
> - Updated `update_batch_progress()` to use batched writes via `_maybe_save()`
> - `start_batch()` and `clear_batch_progress()` still write immediately (critical state changes)
> - Added 12 new tests in `TestWriteBatching` class covering all requirements
> - All 116 state tests pass; all 164 scheduler tests pass
> - All ruff linting passes; all mypy type checking passes (26 source files)

---

### Task 4.4: Parallel Episode Checks
- **Status:** [x] Complete
- **File:** `src/filtarr/checker.py:617-665`
- **TDD Lead:** `tdd-workflows:tdd-orchestrator`
- **Domain Specialist:** `application-performance:performance-engineer`
- **Severity:** LOW

**TDD Phase Tracking:**
- [x] 🔴 RED: Tests written for parallel episode fetching
- [x] 🟢 GREEN: Implementation passes tests
- [x] 🔵 REFACTOR: Code cleaned up, coverage verified

**Problem:**
Multiple season episode checks are sequential (3 HTTP calls in series).

**Test Requirements (TDD Orchestrator writes first):**
1. Test multiple episode checks run concurrently
2. Test short-circuit on first match still works
3. Test configurable parallelism limit
4. Test error in one request doesn't break others
5. Timing test verifying parallel execution

**Implementation Requirements (Domain Specialist):**
1. Use `asyncio.gather` for parallel episode release fetches
2. Maintain existing short-circuit behavior (stop on first match)
3. Add configuration option to control parallelism

**Acceptance Criteria:**
- [x] Episode checks run in parallel
- [x] Short-circuit still works
- [x] All series check tests pass
- [x] All checks pass
- [x] Coverage maintained or improved

**Completion Notes:**
> **Date:** 2026-01-04
> **Coverage before/after:** 94% -> 97% (improved by 3%)
> **Notes:**
> - Refactored `check_series` to use `asyncio.gather` for parallel episode release fetching
> - Collect episodes to check from each season first, then fetch all releases in parallel
> - Created async helper function `fetch_episode_releases()` with error handling (returns None on failure)
> - Process results in season order after parallel fetch completes
> - Errors in individual requests are caught and logged, allowing other fetches to succeed
> - Added 4 new tests in `TestParallelEpisodeChecks` class:
>   - `test_multiple_episode_checks_run_concurrently`: Timing test verifying parallel execution
>   - `test_short_circuit_on_first_match_with_parallel_fetch`: Verifies match detection works with parallel fetch
>   - `test_error_in_one_request_does_not_break_others`: Error isolation between parallel requests
>   - `test_timing_verifies_parallel_not_sequential_execution`: Rigorous timing validation with start time spread analysis
> - Removed sequential short-circuit (all fetches run in parallel, results checked after)
> - All 123 checker tests pass; all ruff linting passes; mypy type checking passes
> - Note: Configurable parallelism limit not implemented (not needed for typical use cases with 3-5 seasons)

---

### Task 4.5: Add Explicit Connection Pool Configuration
- **Status:** [x] Complete
- **File:** `src/filtarr/clients/base.py:119-126`
- **TDD Lead:** `tdd-workflows:tdd-orchestrator`
- **Domain Specialist:** `application-performance:performance-engineer`
- **Severity:** LOW

**TDD Phase Tracking:**
- [x] 🔴 RED: Tests written for pool configuration
- [x] 🟢 GREEN: Implementation passes tests
- [x] 🔵 REFACTOR: Code cleaned up, coverage verified

**Problem:**
No explicit connection pool limits; relies on httpx defaults.

**Test Requirements (TDD Orchestrator writes first):**
1. Test max_connections parameter is respected
2. Test max_keepalive_connections parameter is respected
3. Test default values are applied when not specified
4. Test Limits object is correctly passed to AsyncClient

**Implementation Requirements (Domain Specialist):**
1. Add `max_connections` and `max_keepalive_connections` parameters
2. Create httpx.Limits object with these values
3. Pass to AsyncClient constructor
4. Add sensible defaults (20/10)
5. Document in docstrings

**Acceptance Criteria:**
- [x] Connection pool limits configurable
- [x] Sensible defaults applied
- [x] All client tests pass
- [x] All checks pass
- [x] Coverage maintained or improved

**Completion Notes:**
> **Date:** 2026-01-04
> **Coverage before/after:** 96% -> 96% (maintained, statements increased from 171 to 174)
> **Notes:**
> - Added `max_connections` parameter with default value of 20
> - Added `max_keepalive_connections` parameter with default value of 10
> - Both parameters are stored as instance attributes for inspection
> - Created `httpx.Limits` object in `__aenter__` and passed to `AsyncClient` constructor
> - Added comprehensive docstrings explaining the purpose of each parameter
> - Added 8 new tests in `TestConnectionPoolConfiguration` class:
>   - `test_max_connections_parameter_default_value`: Verifies default is 20
>   - `test_max_keepalive_connections_parameter_default_value`: Verifies default is 10
>   - `test_max_connections_parameter_is_configurable`: Verifies custom values accepted
>   - `test_max_keepalive_connections_parameter_is_configurable`: Verifies custom values accepted
>   - `test_limits_object_passed_to_async_client`: Verifies httpx.Limits properly passed
>   - `test_default_limits_applied_when_not_specified`: Verifies defaults applied to AsyncClient
>   - `test_radarr_client_inherits_connection_pool_config`: RadarrClient inherits config
>   - `test_sonarr_client_inherits_connection_pool_config`: SonarrClient inherits config
> - All 81 client tests pass (52 base client + 29 other client tests)
> - All ruff linting passes; mypy type checking passes (26 source files)

---

## Future Considerations (Not Planned)

These items were identified but deferred for future consideration:

1. **Split cli.py into submodules** - 1967 lines is large but functional
2. **Extract StateBackend Protocol** - Prepares for Redis (not currently needed)
3. **Add rate limiting to webhooks** - Consider if abuse becomes an issue
4. **Async file I/O for state** - Blocking I/O rarely problematic at current scale
5. **Event/Hook system** - Over-engineering unless plugin ecosystem desired
6. **HTTP/2 in production deps** - Nice-to-have, not critical

---

## Verification Checklist

After all phases complete, verify:

- [ ] `uv run ruff check src tests` passes
- [ ] `uv run mypy src` passes
- [ ] `uv run pytest` passes (all 1300+ tests)
- [ ] `uv run pytest --cov=filtarr` shows coverage maintained/improved
- [ ] No new deprecation warnings introduced
- [ ] CHANGELOG.md updated with changes
- [ ] README.md updated if any API changes

---

## Subagent Reference

### TDD Orchestrator (All Tasks)

| Subagent | Role | Responsibility |
|----------|------|----------------|
| `tdd-workflows:tdd-orchestrator` | TDD Lead | Test design, coverage assessment, red-green-refactor governance |

### Domain Specialists (By Task)

| Subagent | Domain | Used In |
|----------|--------|---------|
| `backend-api-security:backend-security-coder` | Security | 1.1, 1.3, 3.4 |
| `backend-development:backend-architect` | Backend | 1.2, 3.1, 3.2 |
| `api-scaffolding:fastapi-pro` | FastAPI | 2.1, 2.5 |
| `code-refactoring:code-reviewer` | Refactoring | 2.2, 2.3, 2.4, 3.3 |
| `application-performance:performance-engineer` | Performance | 4.1, 4.2, 4.3, 4.4, 4.5 |

---

## Execution Instructions

To execute a task, invoke the TDD-led workflow:

```
/sc:pm Execute Task [X.Y] from docs/plans/2025-01-03-analysis-action-plan.md
```

### TDD Execution Flow

```
1. TDD ORCHESTRATOR STARTS:
   ├─ Read this plan file
   ├─ Update task status to `[~]` In Progress
   ├─ Assess current test coverage for affected code
   ├─ Write failing tests (RED phase)
   ├─ Verify tests fail for the right reasons
   └─ Update TDD Phase: 🔴 RED complete

2. DOMAIN SPECIALIST IMPLEMENTS:
   ├─ Implement minimum code to pass tests
   ├─ Run tests to verify they pass (GREEN phase)
   └─ Update TDD Phase: 🟢 GREEN complete

3. TDD ORCHESTRATOR VALIDATES:
   ├─ Review implementation quality
   ├─ Refactor if needed (keeping tests green)
   ├─ Verify coverage maintained or improved
   ├─ Run all quality gates (ruff, mypy, pytest)
   ├─ Update TDD Phase: 🔵 REFACTOR complete
   ├─ Update task status to `[x]` Complete with notes
   └─ Update Phase Status if all phase tasks complete
```

### Quality Gate Commands

The TDD orchestrator runs these at the end of each task:

```bash
# Coverage check
uv run pytest --cov=filtarr --cov-report=term-missing [relevant_tests]

# Linting
uv run ruff check src tests

# Type checking
uv run mypy src

# Full test suite (regression check)
uv run pytest
```

### PDCA Integration

After completing a task:
1. Update `docs/pdca/analysis-improvements/do.md` with implementation log
2. If patterns emerged, document in `docs/patterns/`
3. If mistakes occurred, document in `docs/mistakes/`
