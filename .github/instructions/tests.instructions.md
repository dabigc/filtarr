---
applyTo: "tests/**/*.py"
---

# Test Guidelines

## Test Structure

```python
import pytest
import respx
from httpx import Response

from filtarr.clients.radarr import RadarrClient


@pytest.fixture
def radarr_client() -> RadarrClient:
    return RadarrClient(base_url="http://localhost:7878", api_key="test-key")


class TestRadarrClient:
    @respx.mock
    async def test_search_releases_returns_results(
        self, radarr_client: RadarrClient
    ) -> None:
        # Arrange
        respx.get("http://localhost:7878/api/v3/release").mock(
            return_value=Response(200, json=[{"id": 1, "title": "Movie.2024.2160p"}])
        )

        # Act
        releases = await radarr_client.search_releases(movie_id=123)

        # Assert
        assert len(releases) == 1
        assert "2160p" in releases[0].title
```

## Mocking HTTP Requests

Always use `respx` for mocking httpx:

```python
@respx.mock
async def test_api_error_handling(self, client: RadarrClient) -> None:
    respx.get(url__startswith="http://localhost").mock(
        return_value=Response(500, json={"error": "Internal server error"})
    )

    with pytest.raises(APIError):
        await client.search_releases(movie_id=1)
```

## Integration Tests

Mark with `@pytest.mark.integration` and skip by default:

```python
@pytest.mark.integration
async def test_real_api_connection() -> None:
    """Requires RADARR_URL and RADARR_API_KEY environment variables."""
    ...
```

## Fixture Files

Store JSON fixtures in `tests/fixtures/`:
- `tests/fixtures/radarr_releases.json`
- `tests/fixtures/sonarr_series.json`

Load with:
```python
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures"

def load_fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())
```
