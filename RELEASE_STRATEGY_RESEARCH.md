# Release Strategy Research

## Executive Summary

**Current State:** The project is at v3.0.0 using release-please with standard semantic versioning, which has resulted in major version bumps for relatively minor breaking changes.

**Key Finding:** Yes, release-please can be configured to treat the project as pre-1.0, where breaking changes only bump the minor version (0.x.y) instead of the major version. This would allow you to reset to v0.x.x versioning.

**Recommendation:** Use release-please's pre-major configuration options to stay in 0.x.x until the API is truly stable and ready for 1.0.0.

---

## Current Release Setup

### Configuration Analysis

The project currently uses:
- **Tool:** release-please v4
- **Current Version:** 3.0.0
- **Commit Convention:** Conventional Commits
- **Configuration:** Minimal (using defaults)
  - `.release-please-manifest.json` only contains version
  - No `.release-please-config.json` file exists
  - Using default versioning strategy

### Version History

Looking at the CHANGELOG, the major version bumps were triggered by:

1. **v2.0.0** - Breaking change: CLI flag placement (`--log-level` moved from command-specific to global)
   - `BREAKING CHANGE: filtarr serve --log-level debug is now filtarr --log-level debug serve`

2. **v3.0.0** - Breaking change: API type change
   - `BREAKING CHANGE: SearchResult.item_type is now MediaType enum (StrEnum, backward compatible for string comparison)`

While technically correct per semantic versioning, these are relatively minor API changes for a library that's still evolving.

---

## Option 1: Configure Release-Please for Pre-1.0 (RECOMMENDED)

Release-please provides specific configuration options for pre-1.0 projects that change how versions are bumped.

### How Pre-Major Versioning Works

When configured for pre-major (0.x.x) versioning:

| Commit Type | Default Behavior | Pre-Major Behavior |
|-------------|------------------|-------------------|
| `fix:` | 1.0.0 → 1.0.1 | 0.1.0 → 0.1.1 |
| `feat:` | 1.0.0 → 1.1.0 | 0.1.0 → 0.1.1 |
| `feat!:` or `BREAKING CHANGE:` | 1.0.0 → 2.0.0 | 0.1.0 → 0.2.0 |

**Key Benefits:**
- Breaking changes bump minor version (0.1.0 → 0.2.0), not major
- Features and fixes both bump patch version (0.1.0 → 0.1.1)
- Signals to users that the API is still evolving
- Allows you to reserve 1.0.0 for when the API is truly stable

### Configuration Options

Create a `.release-please-config.json` file with:

```json
{
  "release-type": "python",
  "bump-minor-pre-major": true,
  "bump-patch-for-minor-pre-major": true,
  "packages": {
    ".": {}
  }
}
```

**Configuration Breakdown:**

- `release-type: "python"` - Uses Python-specific release conventions
- `bump-minor-pre-major: true` - Breaking changes bump minor instead of major (0.1.0 → 0.2.0)
- `bump-patch-for-minor-pre-major: true` - Features bump patch instead of minor (0.1.0 → 0.1.1)

### Resetting to 0.x.x

To move from v3.0.0 back to v0.x.x:

**Option A: Manual Reset (Clean Slate)**
1. Create `.release-please-config.json` with pre-major options
2. Manually update version to `0.3.0` in:
   - `pyproject.toml`
   - `.release-please-manifest.json`
3. Create a release commit:
   ```bash
   git commit -m "chore: reset to 0.x.x pre-1.0 versioning

   This project is still evolving and not ready for 1.0.0.
   Resetting to 0.3.0 to better reflect maturity level.

   Release-As: 0.3.0"
   ```
4. Tag and release as v0.3.0
5. Future releases will follow pre-major conventions

**Option B: Continue from 3.x.x (Preserve History)**
1. Create `.release-please-config.json` with pre-major options
2. Keep current v3.0.0 version
3. Document in CHANGELOG that you're following SemVer's "anything may change" principle more strictly
4. Reserve 4.0.0 for your actual "stable 1.0.0 equivalent"
5. When ready for 1.0.0, manually reset

### Important Caveats

⚠️ **Initial Version Gotcha:** If starting from 0.0.0, pre-major options are ignored. Workaround:
- Start from 0.0.1 or 0.1.0 instead
- Or use `Release-As: 0.1.0` in the first commit

⚠️ **Existing Users:** If you reset to 0.x.x, users on v3.0.0 won't automatically upgrade since 0.x.x < 3.x.x in version comparison. You'd need to communicate this change clearly.

---

## Option 2: Python Semantic Release

An alternative Python-native tool with similar functionality to release-please.

### Overview

- **Tool:** [python-semantic-release](https://github.com/python-semantic-release/python-semantic-release)
- **Language:** Python (vs release-please's JavaScript/Node)
- **Integration:** Tighter Python ecosystem integration
- **Automation:** Fully automated (no PR-based review)

### Key Differences from Release-Please

| Feature | Release-Please | Python-Semantic-Release |
|---------|----------------|------------------------|
| **Language** | JavaScript | Python |
| **Release Process** | PR-based (manual merge) | Fully automated |
| **Review Step** | Yes (approve PR) | No (auto-releases) |
| **Customization** | Configuration file | Plugin ecosystem |
| **GitHub Integration** | Native (GitHub Actions) | Configurable |
| **Python Support** | Generic | Python-specific |

### Configuration Example

```toml
# pyproject.toml
[tool.semantic_release]
version_variable = "pyproject.toml:version"
branch = "main"
upload_to_pypi = true
upload_to_release = true
build_command = "pip install build && python -m build"

# Pre-1.0 configuration
major_on_zero = false  # Breaking changes won't bump to 1.0.0
```

### When to Choose This

**Use python-semantic-release if:**
- You prefer Python tools over JavaScript tools
- You want fully automated releases (no PR review step)
- You need Python-specific features (e.g., automatic PyPI versioning)

**Stick with release-please if:**
- You like the PR-based review workflow
- You want to review changelogs before releasing
- Your team is comfortable with the current setup
- You have multi-language repos (release-please supports many languages)

---

## Option 3: Manual Versioning

Maintain full control over versioning decisions.

### Approach

1. Remove release-please automation
2. Manually update version in `pyproject.toml`
3. Manually maintain `CHANGELOG.md`
4. Create releases via GitHub UI or `gh` CLI
5. Keep CI/CD for build/publish steps

### Pros
- Complete control over version numbers
- No unexpected major bumps
- Can use any versioning scheme (SemVer, CalVer, etc.)

### Cons
- More manual work
- Risk of forgetting changelog updates
- No automated changelog generation
- Team must remember versioning conventions

### When to Choose This

**Use manual versioning if:**
- Team is very small (1-2 developers)
- Releases are infrequent (quarterly or less)
- You want complete control
- You have strict versioning requirements

---

## Option 4: Calendar Versioning (CalVer)

Use date-based versions instead of semantic versioning.

### Overview

- **Format:** `YYYY.MM.MICRO` or `YYYY.0M.MICRO` (zero-padded)
- **Examples:** `2026.01.0`, `2026.01.1`, `2026.02.0`
- **Used by:** pip, setuptools, Ubuntu, Twisted

### How It Works

```
2026.01.0 - First release in January 2026
2026.01.1 - Second release in January 2026
2026.02.0 - First release in February 2026
```

### Configuration with Release-Please

```json
{
  "release-type": "python",
  "versioning": "always-bump-patch",
  "packages": {
    ".": {}
  }
}
```

Then manually update to CalVer format when needed.

### Pros
- Makes age of release obvious
- No "breaking change" pressure
- Used by major Python tools
- Avoids "version number inflation"

### Cons
- Loses semantic meaning (breaking vs non-breaking)
- Users can't infer compatibility from version
- Less common in Python libraries (more common in applications)

### When to Choose This

**Use CalVer if:**
- The project is an application/tool (not a library)
- You release on a predictable schedule
- API stability guarantees are less important
- You want to avoid SemVer politics

**Don't use CalVer if:**
- You're building a library that others depend on
- Users need to understand compatibility from version numbers
- You have irregular release schedules

---

## Option 5: Custom Versioning Strategy

Release-please supports custom versioning strategies.

### Available Strategies

```json
{
  "versioning": "always-bump-patch"     // All changes bump patch
  "versioning": "always-bump-minor"     // All changes bump minor
  "versioning": "always-bump-major"     // All changes bump major
  "versioning": "default"               // Standard SemVer
  "versioning": "prerelease"            // Handle alpha/beta/rc versions
}
```

### Example: Ignore Breaking Changes

If you want to ignore breaking changes and only bump minor/patch:

```json
{
  "release-type": "python",
  "versioning": "always-bump-minor",  // Breaking changes only bump minor
  "packages": {
    ".": {}
  }
}
```

This would give you:
- `fix:` → 1.0.0 to 1.0.1
- `feat:` → 1.0.0 to 1.1.0
- `feat!:` → 1.0.0 to 1.1.0 (breaking change treated as feature)

### Limitations

⚠️ This doesn't truly achieve "only bump major manually" - it treats all breaking changes as features. You'd need to manually bump to 2.0.0 when ready.

---

## Comparison Matrix

| Strategy | Complexity | Flexibility | Breaking Change Handling | Best For |
|----------|-----------|-------------|-------------------------|----------|
| **Pre-Major Config** | Low | Medium | Minor bump in 0.x.x | Pre-1.0 projects (RECOMMENDED) |
| **Python-Semantic-Release** | Medium | High | Configurable | Python-specific automation |
| **Manual Versioning** | Low | Very High | Manual control | Small teams, full control |
| **CalVer** | Low | Medium | Not applicable | Applications, scheduled releases |
| **Custom Strategy** | Low | Low | Limited control | Specific use cases |

---

## Recommendation

**For your project (filtarr), I recommend Option 1: Pre-Major Configuration**

### Reasoning

1. **Minimal Disruption:** Keep using release-please (no tooling change)
2. **Signals Maturity Level:** 0.x.x clearly indicates "API still evolving"
3. **Prevents Version Inflation:** Won't reach v10.0.0 before API stabilizes
4. **Industry Standard:** Many projects stay in 0.x.x for years (e.g., Node.js was 0.x until 2015)
5. **Easy Transition:** When ready for 1.0.0, just remove pre-major config options

### Implementation Steps

1. **Create `.release-please-config.json`:**
   ```json
   {
     "release-type": "python",
     "bump-minor-pre-major": true,
     "bump-patch-for-minor-pre-major": true,
     "packages": {
       ".": {}
     }
   }
   ```

2. **Decide on version reset:**
   - **Option A (Recommended):** Keep v3.0.0, document that you're now following pre-1.0 semantics more strictly
   - **Option B:** Reset to v0.3.0 (requires manual version updates + user communication)

3. **Update documentation:**
   - Add note in README about versioning strategy
   - Explain when you'll bump to 1.0.0 (e.g., "when API is stable")

4. **Commit and test:**
   ```bash
   git add .release-please-config.json
   git commit -m "chore: configure pre-1.0 versioning strategy"
   git push
   ```

5. **Verify on next release:**
   - Next `feat!:` commit should bump minor (3.0.0 → 3.1.0)
   - Next `feat:` commit should bump patch (3.0.0 → 3.0.1)

### When to Bump to 1.0.0

Consider moving to 1.0.0 when:
- ✅ API is stable and unlikely to have breaking changes
- ✅ Core features are complete and well-tested
- ✅ Documentation is comprehensive
- ✅ Production users are relying on the library
- ✅ You're comfortable committing to SemVer stability guarantees

---

## Additional Resources

### Release-Please Documentation
- [Release-Please GitHub](https://github.com/googleapis/release-please)
- [Customizing Release-Please](https://github.com/googleapis/release-please/blob/main/docs/customizing.md)
- [Release-Please vs Semantic-Release Comparison](https://www.hamzak.xyz/blog-posts/release-please-vs-semantic-release)

### Pre-Major Versioning References
- [bump-minor-for-patch-pre-major Issue #1049](https://github.com/googleapis/release-please/issues/1049)
- [Initial version 0.0.0 Issue #2087](https://github.com/googleapis/release-please/issues/2087)

### Python-Semantic-Release
- [python-semantic-release GitHub](https://github.com/python-semantic-release/python-semantic-release)
- [Semantic Release Python Setup Guide](https://guicommits.com/semantic-release-to-automate-versioning-and-publishing-to-pypi-with-github-actions/)

### Semantic Versioning
- [Semantic Versioning 2.0.0](https://semver.org/)
- [Python Packaging Versioning Guide](https://packaging.python.org/en/latest/discussions/versioning/)

### Alternative Strategies
- [Calendar Versioning (CalVer)](https://calver.org/)
- [Python Versioning Discussion](https://packaging.python.org/en/latest/discussions/versioning/)

---

## Questions to Consider

Before implementing any strategy, consider:

1. **User Impact:** How will changing versioning strategy affect existing users?
2. **Stability Commitment:** When will the API be stable enough for 1.0.0?
3. **Release Frequency:** How often do you plan to release?
4. **Breaking Changes:** How frequently do you expect breaking changes?
5. **Team Workflow:** Does the team prefer automated releases or review-based releases?

---

**Generated:** 2026-01-05
**Status:** Research Complete - Ready for Implementation Decision
