# Contributing to filtarr

Thank you for your interest in contributing to filtarr! This document provides guidelines and best practices for contributing to the project.

## Development Setup

This project uses `uv` for dependency management. To get started:

```bash
# Clone the repository
git clone https://github.com/dabigc/filtarr.git
cd filtarr

# Install with dev dependencies
uv sync --dev

# Install pre-commit hooks (required)
uv run pre-commit install
```

The pre-commit hooks will automatically run linting, type checking, and tests before each commit to ensure code quality.

## Development Workflow

### Running Tests

Always run tests before submitting a pull request:

```bash
# Run all tests
uv run pytest

# Run with coverage report
uv run pytest --cov=filtarr --cov-report=term-missing

# Run integration tests
uv run pytest -m integration
```

### Code Quality Checks

The project enforces strict code quality standards:

```bash
# Lint and format
uv run ruff check src tests
uv run ruff format src tests

# Type checking (strict mode)
uv run mypy src

# Run all pre-commit hooks manually
uv run pre-commit run --all-files
```

**IMPORTANT**: All checks must pass before committing. The pre-commit hooks will enforce this automatically.

### Docker Testing

If you modify Docker-related files or core functionality:

```bash
# Run Docker runtime tests
./scripts/test-docker.sh

# Verbose output
./scripts/test-docker.sh --verbose
```

Docker tests run automatically via pre-commit hooks when relevant files change.

## Commit Message Conventions

This project uses [Conventional Commits](https://www.conventionalcommits.org/) format for all commit messages. This ensures clear, consistent version history and enables automated changelog generation.

### Basic Format

```
<type>(<scope>): <description>

[optional body]

[optional footer(s)]
```

### Commit Types

Use these prefixes for your commits:

- **feat**: New feature or enhancement
- **fix**: Bug fix
- **chore**: Maintenance tasks (dependencies, build config)
- **docs**: Documentation changes
- **test**: Adding or updating tests
- **refactor**: Code restructuring without functional changes
- **perf**: Performance improvements
- **ci**: CI/CD pipeline changes
- **style**: Code style/formatting changes (whitespace, etc.)

### Examples

```bash
# Good commit messages
feat(cli): add batch processing command for series
fix(checker): prevent 4K false positives from release group names
chore(deps): update httpx to 0.27.0
docs(readme): add webhook server usage examples
test(radarr): add coverage for error handling paths

# Feature with scope
feat(webhook): add support for Sonarr EpisodeDownload events

# Bug fix with detailed explanation
fix(state): handle concurrent state updates correctly

Previously, multiple simultaneous updates could cause race conditions.
Now using file locking to ensure atomicity.

Fixes #123
```

### Breaking Changes

**Breaking changes should be used VERY sparingly.** They require:

1. **Deprecation warning** in a prior release
2. **Clear migration path** documented in the commit body
3. **Strong justification** for why the breaking change is necessary

Use the `!` suffix to indicate breaking changes:

```bash
# Breaking change format
feat!(<scope>): breaking change description

BREAKING CHANGE: Detailed explanation of what broke and why.

Migration path:
- Old API: checker.check_movie(movie_id)
- New API: checker.check_movie(movie_id, criteria=SearchCriteria.UHD_4K)

Rationale: The new API provides explicit control over search criteria,
improving clarity and reducing ambiguity in availability checks.
```

**Before introducing a breaking change:**

1. Open an issue to discuss the change with maintainers
2. Ensure the benefit outweighs the migration cost
3. Add deprecation warnings in the current version
4. Update documentation with migration guides
5. Use semantic versioning (breaking changes trigger major version bumps)

### Scope Guidelines

Use scopes to indicate which part of the codebase is affected:

- `cli` - Command-line interface
- `webhook` - Webhook server
- `scheduler` - Scheduling system
- `checker` - ReleaseChecker logic
- `tagger` - ReleaseTagger logic
- `config` - Configuration system
- `state` - State management
- `radarr` - Radarr client
- `sonarr` - Sonarr client
- `models` - Data models
- `deps` - Dependencies
- `docker` - Docker configuration

Scope is optional but recommended for clarity.

### Commit Message Best Practices

1. **Use imperative mood**: "add feature" not "added feature"
2. **Keep the summary line under 72 characters**
3. **Capitalize the summary line**
4. **No period at the end of the summary**
5. **Separate summary from body with blank line**
6. **Wrap body at 72 characters**
7. **Use body to explain what and why, not how**

## Pull Request Process

1. **Fork the repository** and create a feature branch
2. **Make your changes** following the code quality guidelines
3. **Add tests** for new functionality
4. **Update documentation** if needed
5. **Ensure all checks pass** (tests, linting, type checking)
6. **Write clear commit messages** using Conventional Commits format
7. **Submit a pull request** with a descriptive title and summary

### Pull Request Title

Use the same format as commit messages:

```
feat(cli): add support for custom output formats
fix(radarr): handle empty release arrays correctly
```

### Pull Request Description

Include:

- **Summary** of changes
- **Motivation** for the change
- **Testing performed**
- **Related issues** (if any)
- **Breaking changes** (if any, with migration guide)

## Code Style Guidelines

- Follow **PEP 8** conventions
- Use **type hints** for all function signatures
- Prefer **descriptive names** over abbreviations
- Keep **functions focused** on a single responsibility
- Write **docstrings** for public APIs (Google style)
- Use **async/await** for I/O operations

## Questions or Issues?

- Check existing [issues](https://github.com/dabigc/filtarr/issues)
- Open a new issue for bugs or feature requests
- Join discussions in pull requests

Thank you for contributing to filtarr!
