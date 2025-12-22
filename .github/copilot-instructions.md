# Copilot Instructions for findarr

## Quick Reference

```bash
# Install dependencies
uv sync --all-extras --dev

# Run tests
uv run pytest

# Lint
uv run ruff check src tests

# Format
uv run ruff format src tests

# Type check
uv run mypy src
```

## Code Style Requirements

- **Line length**: 100 characters
- **Target Python**: 3.11+
- **Import sorting**: isort via ruff (first-party: `findarr`)
- **Type annotations**: Required everywhere (mypy strict mode)

## Async Patterns

All HTTP operations are async. Use `async def` and `await`:

```python
async def fetch_releases(self, movie_id: int) -> list[Release]:
    response = await self._client.get(f"/api/v3/release", params={"movieId": movie_id})
    response.raise_for_status()
    return [Release.model_validate(r) for r in response.json()]
```

## Pydantic v2 Usage

- Use `model_validate()` not `parse_obj()` (v2 API)
- Use `model_dump()` not `dict()` (v2 API)
- Field aliases via `Field(alias="jsonFieldName")`
- Use `ConfigDict(populate_by_name=True)` for alias support

## Testing Conventions

- Mock HTTP with `respx` (not `responses` or `aioresponses`)
- Fixtures in `tests/fixtures/` as JSON files
- Mark integration tests with `@pytest.mark.integration`
- Use `pytest.mark.asyncio` is automatic via `asyncio_mode = "auto"`

## Error Handling

Use custom exceptions from `findarr.exceptions`:
- `FindarrError` - base exception
- `APIError` - API communication failures
- `AuthenticationError` - invalid API key
- `NotFoundError` - resource not found

## Additional Context

See `CLAUDE.md` for:
- Detailed project structure
- Radarr/Sonarr API specifics
- Architecture decisions
