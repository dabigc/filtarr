---
applyTo: "**/*.py"
---

# Python Code Guidelines

## Type Annotations

All functions require complete type annotations:

```python
# Good
async def check_4k_available(movie_id: int) -> bool:
    ...

# Bad - missing return type
async def check_4k_available(movie_id: int):
    ...
```

## Async Best Practices

- Use `async with` for HTTP client context managers
- Never use `asyncio.run()` inside async functions
- Prefer `asyncio.gather()` for parallel operations

## Pydantic Models

Located in `src/filtarr/models/`. Follow these patterns:

```python
from pydantic import BaseModel, ConfigDict, Field

class Release(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    release_id: int = Field(alias="id")
    title: str
    quality_name: str = Field(alias="quality.quality.name")
```

## Import Order

Enforced by ruff. Order:
1. Standard library
2. Third-party (`httpx`, `pydantic`)
3. First-party (`filtarr`)

## Docstrings

Use Google style for public API methods:

```python
async def search_releases(self, movie_id: int) -> list[Release]:
    """Search for releases for a movie.

    Args:
        movie_id: The Radarr movie database ID.

    Returns:
        List of Release objects matching the search.

    Raises:
        APIError: If the API request fails.
    """
```
