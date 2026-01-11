# Versioning Policy

## Version Philosophy

Filtarr follows **Semantic Versioning 2.0.0** (`MAJOR.MINOR.PATCH`) with a conservative approach to breaking changes.

**Current Status**: Despite being at v3.x, filtarr is a mature pre-1.0 project in spirit. We accept v3.x as our baseline and commit to stability going forward. Users should feel confident that upgrades within the v3.x series will not break their integrations.

**Guiding Principle**: *Stability over rapid iteration.* Breaking changes should be exceptionally rare and well-justified.

## Version Bump Rules

Version bumps are driven by [Conventional Commits](https://www.conventionalcommits.org/) and managed automatically by release-please:

| Commit Type | Version Bump | Example | Use Case |
|-------------|-------------|---------|----------|
| `fix:` | **PATCH** | 3.0.0 → 3.0.1 | Bug fixes, documentation, internal refactoring |
| `feat:` | **MINOR** | 3.0.0 → 3.1.0 | New features, backward-compatible enhancements |
| `feat!:` or `fix!:` | **MAJOR** | 3.0.0 → 4.0.0 | Breaking changes (**USE SPARINGLY**) |

**Note**: The `!` suffix indicates a breaking change. It should be rare. See the Breaking Changes Policy below.

## Breaking Changes Policy

**Definition**: A breaking change is any modification that could cause existing user code to fail:
- Removing public API methods, classes, or functions
- Changing function signatures (adding required parameters, removing parameters)
- Changing return types in incompatible ways
- Renaming public modules or classes

**Policy**:
1. **Avoid breaking changes unless absolutely necessary**
   - Justify with a clear use case in the PR description
   - Require maintainer approval before merging
   - Document the impact and migration path

2. **Use deprecation periods** (see Deprecation Strategy below)
   - Preferred over immediate removal
   - Gives users time to migrate

3. **Major version bumps should be infrequent**
   - Target: no more than 1-2 per year
   - Bundle multiple breaking changes when possible

## Commit Message Guidelines

Use conventional commits for all changes:

### Standard Commits (Most Common)

```
fix: prevent 4K false positives from release group names
feat: add support for Dolby Atmos audio criteria
docs: update CLI usage examples
chore: bump httpx dependency to 0.27.0
test: add coverage for SonarrClient.search_releases
refactor: extract common retry logic to BaseClient
```

### Breaking Change Commits (RARE)

Only use `!` when making **genuine breaking changes**:

```
feat!: require Python 3.11+ (drops 3.9/3.10 support)

BREAKING CHANGE: Minimum Python version is now 3.11.
Users on Python 3.9 or 3.10 must upgrade.
```

```
fix!: remove deprecated ReleaseChecker.check_sync method

BREAKING CHANGE: The synchronous check_sync() method has been
removed after a 6-month deprecation period. Use the async check()
method instead.
```

**When in doubt, do NOT use `!`**. Most changes can be made backward-compatible with careful design.

## Deprecation Strategy

Before removing any public API, follow this process:

### 1. Mark as Deprecated (Minor Version Bump)

Add deprecation warnings using Python's `warnings` module:

```python
import warnings

def old_function():
    warnings.warn(
        "old_function() is deprecated and will be removed in v4.0. "
        "Use new_function() instead.",
        DeprecationWarning,
        stacklevel=2
    )
    return new_function()
```

### 2. Document the Deprecation

- Add a `.. deprecated::` directive in docstrings
- Update `CHANGELOG.md` with migration instructions
- Announce in release notes

### 3. Wait at Least One Minor Version

Give users time to migrate:
- **Minimum**: 1 minor version (e.g., deprecated in 3.5.0, removed in 3.6.0)
- **Recommended**: 2-3 minor versions or 3-6 months
- **For critical APIs**: Longer deprecation periods (6+ months)

### 4. Remove in Next Major Version

When the deprecation period ends, remove the deprecated code in the next major version bump.

## Examples

### Good: Backward-Compatible Feature

```
feat: add --timeout flag to CLI commands

Adds optional --timeout parameter for HTTP requests.
Defaults to 30 seconds (existing behavior).
```

**Result**: 3.5.0 → 3.6.0 (minor bump, no breaking change)

### Bad: Unnecessary Breaking Change

```
feat!: rename --criteria to --filter

BREAKING CHANGE: The --criteria flag is now --filter.
```

**Problem**: This breaks user scripts for cosmetic reasons. Instead, support both flags and deprecate the old one.

### Better Alternative

```
feat: add --filter alias for --criteria flag

The --filter flag is now the preferred name, but --criteria
continues to work for backward compatibility.
```

**Result**: 3.5.0 → 3.6.0 (minor bump, fully compatible)

## Summary

- **Be conservative**: Avoid breaking changes whenever possible
- **Use deprecation**: Give users time to migrate before removing features
- **Communicate clearly**: Document all changes in CHANGELOG.md
- **Trust the tooling**: release-please automates version bumps based on commit messages

When in doubt, choose backward compatibility over breaking changes.
