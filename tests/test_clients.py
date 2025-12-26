"""Tests for API clients."""

import pytest
import respx
from httpx import Response

from filtarr.clients.radarr import RadarrClient
from filtarr.clients.sonarr import SonarrClient


class TestRadarrClient:
    """Tests for RadarrClient."""

    @respx.mock
    @pytest.mark.asyncio
    async def test_get_movie_releases(self, sample_radarr_response: list[dict]) -> None:
        """Should parse releases from Radarr API response."""
        respx.get("http://localhost:7878/api/v3/release", params={"movieId": "123"}).mock(
            return_value=Response(200, json=sample_radarr_response)
        )

        async with RadarrClient("http://localhost:7878", "test-api-key") as client:
            releases = await client.get_movie_releases(123)

        assert len(releases) == 2
        assert releases[0].title == "Movie.Name.2024.2160p.UHD.BluRay.x265-GROUP"
        assert releases[0].is_4k() is True
        assert releases[1].is_4k() is False

    @respx.mock
    @pytest.mark.asyncio
    async def test_has_4k_releases_true(self, sample_radarr_response: list[dict]) -> None:
        """Should return True when 4K releases exist."""
        respx.get("http://localhost:7878/api/v3/release", params={"movieId": "123"}).mock(
            return_value=Response(200, json=sample_radarr_response)
        )

        async with RadarrClient("http://localhost:7878", "test-api-key") as client:
            has_4k = await client.has_4k_releases(123)

        assert has_4k is True

    @respx.mock
    @pytest.mark.asyncio
    async def test_has_4k_releases_false(self) -> None:
        """Should return False when no 4K releases exist."""
        respx.get("http://localhost:7878/api/v3/release", params={"movieId": "123"}).mock(
            return_value=Response(
                200,
                json=[
                    {
                        "guid": "abc",
                        "title": "Movie.1080p",
                        "indexer": "Test",
                        "size": 1000,
                        "quality": {"quality": {"id": 7, "name": "Bluray-1080p"}},
                    }
                ],
            )
        )

        async with RadarrClient("http://localhost:7878", "test-api-key") as client:
            has_4k = await client.has_4k_releases(123)

        assert has_4k is False

    @pytest.mark.asyncio
    async def test_client_not_in_context_raises(self) -> None:
        """Should raise when client used outside context manager."""
        client = RadarrClient("http://localhost:7878", "test-api-key")
        with pytest.raises(RuntimeError, match="must be used within async context"):
            _ = client.client


class TestRadarrClientSearch:
    """Tests for RadarrClient search functionality."""

    @respx.mock
    @pytest.mark.asyncio
    async def test_get_all_movies(self) -> None:
        """Should fetch and parse all movies."""
        respx.get("http://localhost:7878/api/v3/movie").mock(
            return_value=Response(
                200,
                json=[
                    {
                        "id": 1,
                        "title": "The Matrix",
                        "year": 1999,
                        "tmdbId": 603,
                        "imdbId": "tt0133093",
                        "monitored": True,
                        "hasFile": True,
                    },
                    {
                        "id": 2,
                        "title": "The Matrix Reloaded",
                        "year": 2003,
                        "tmdbId": 604,
                        "imdbId": "tt0234215",
                        "monitored": True,
                        "hasFile": False,
                    },
                ],
            )
        )

        async with RadarrClient("http://localhost:7878", "test-api-key") as client:
            movies = await client.get_all_movies()

        assert len(movies) == 2
        assert movies[0].title == "The Matrix"
        assert movies[0].year == 1999
        assert movies[1].title == "The Matrix Reloaded"

    @respx.mock
    @pytest.mark.asyncio
    async def test_search_movies_case_insensitive(self) -> None:
        """Should search movies case-insensitively."""
        respx.get("http://localhost:7878/api/v3/movie").mock(
            return_value=Response(
                200,
                json=[
                    {"id": 1, "title": "The Matrix", "year": 1999},
                    {"id": 2, "title": "The Matrix Reloaded", "year": 2003},
                    {"id": 3, "title": "Inception", "year": 2010},
                ],
            )
        )

        async with RadarrClient("http://localhost:7878", "test-api-key") as client:
            results = await client.search_movies("matrix")

        assert len(results) == 2
        assert all("matrix" in m.title.lower() for m in results)

    @respx.mock
    @pytest.mark.asyncio
    async def test_search_movies_no_matches(self) -> None:
        """Should return empty list when no matches."""
        respx.get("http://localhost:7878/api/v3/movie").mock(
            return_value=Response(
                200,
                json=[
                    {"id": 1, "title": "The Matrix", "year": 1999},
                ],
            )
        )

        async with RadarrClient("http://localhost:7878", "test-api-key") as client:
            results = await client.search_movies("inception")

        assert results == []

    @respx.mock
    @pytest.mark.asyncio
    async def test_find_movie_by_name_exact_match(self) -> None:
        """Should return exact match when found."""
        respx.get("http://localhost:7878/api/v3/movie").mock(
            return_value=Response(
                200,
                json=[
                    {"id": 1, "title": "The Matrix", "year": 1999},
                    {"id": 2, "title": "The Matrix Reloaded", "year": 2003},
                ],
            )
        )

        async with RadarrClient("http://localhost:7878", "test-api-key") as client:
            movie = await client.find_movie_by_name("The Matrix")

        assert movie is not None
        assert movie.id == 1
        assert movie.title == "The Matrix"

    @respx.mock
    @pytest.mark.asyncio
    async def test_find_movie_by_name_closest_match(self) -> None:
        """Should return shortest title when no exact match."""
        respx.get("http://localhost:7878/api/v3/movie").mock(
            return_value=Response(
                200,
                json=[
                    {"id": 1, "title": "The Matrix Reloaded", "year": 2003},
                    {"id": 2, "title": "The Matrix Revolutions", "year": 2003},
                ],
            )
        )

        async with RadarrClient("http://localhost:7878", "test-api-key") as client:
            movie = await client.find_movie_by_name("Matrix")

        assert movie is not None
        # Returns shortest matching title
        assert movie.id == 1
        assert movie.title == "The Matrix Reloaded"

    @respx.mock
    @pytest.mark.asyncio
    async def test_find_movie_by_name_not_found(self) -> None:
        """Should return None when movie not found."""
        respx.get("http://localhost:7878/api/v3/movie").mock(
            return_value=Response(
                200,
                json=[{"id": 1, "title": "The Matrix", "year": 1999}],
            )
        )

        async with RadarrClient("http://localhost:7878", "test-api-key") as client:
            movie = await client.find_movie_by_name("Inception")

        assert movie is None


class TestSonarrClientSearch:
    """Tests for SonarrClient search functionality."""

    @respx.mock
    @pytest.mark.asyncio
    async def test_get_all_series(self) -> None:
        """Should fetch and parse all series."""
        respx.get("http://127.0.0.1:8989/api/v3/series").mock(
            return_value=Response(
                200,
                json=[
                    {
                        "id": 1,
                        "title": "Breaking Bad",
                        "year": 2008,
                        "monitored": True,
                        "seasons": [{"seasonNumber": 1, "monitored": True}],
                    },
                    {
                        "id": 2,
                        "title": "Better Call Saul",
                        "year": 2015,
                        "monitored": True,
                        "seasons": [],
                    },
                ],
            )
        )

        async with SonarrClient("http://127.0.0.1:8989", "test-api-key") as client:
            series = await client.get_all_series()

        assert len(series) == 2
        assert series[0].title == "Breaking Bad"
        assert series[1].title == "Better Call Saul"

    @respx.mock
    @pytest.mark.asyncio
    async def test_search_series_case_insensitive(self) -> None:
        """Should search series case-insensitively."""
        respx.get("http://127.0.0.1:8989/api/v3/series").mock(
            return_value=Response(
                200,
                json=[
                    {"id": 1, "title": "Breaking Bad", "year": 2008, "seasons": []},
                    {"id": 2, "title": "Better Call Saul", "year": 2015, "seasons": []},
                    {"id": 3, "title": "The Office", "year": 2005, "seasons": []},
                ],
            )
        )

        async with SonarrClient("http://127.0.0.1:8989", "test-api-key") as client:
            results = await client.search_series("breaking")

        assert len(results) == 1
        assert results[0].title == "Breaking Bad"

    @respx.mock
    @pytest.mark.asyncio
    async def test_find_series_by_name_exact_match(self) -> None:
        """Should return exact match when found."""
        respx.get("http://127.0.0.1:8989/api/v3/series").mock(
            return_value=Response(
                200,
                json=[
                    {"id": 1, "title": "Breaking Bad", "year": 2008, "seasons": []},
                    {"id": 2, "title": "Breaking Bad: El Camino", "year": 2019, "seasons": []},
                ],
            )
        )

        async with SonarrClient("http://127.0.0.1:8989", "test-api-key") as client:
            series = await client.find_series_by_name("Breaking Bad")

        assert series is not None
        assert series.id == 1
        assert series.title == "Breaking Bad"

    @respx.mock
    @pytest.mark.asyncio
    async def test_find_series_by_name_not_found(self) -> None:
        """Should return None when series not found."""
        respx.get("http://127.0.0.1:8989/api/v3/series").mock(
            return_value=Response(
                200,
                json=[{"id": 1, "title": "Breaking Bad", "year": 2008, "seasons": []}],
            )
        )

        async with SonarrClient("http://127.0.0.1:8989", "test-api-key") as client:
            series = await client.find_series_by_name("The Office")

        assert series is None


class TestSonarrClient:
    """Tests for SonarrClient."""

    @respx.mock
    @pytest.mark.asyncio
    async def test_get_series_releases(self) -> None:
        """Should parse releases from Sonarr API response."""
        respx.get("http://127.0.0.1:8989/api/v3/release", params={"seriesId": "456"}).mock(
            return_value=Response(
                200,
                json=[
                    {
                        "guid": "xyz789",
                        "title": "Show.S01E01.2160p.WEB-DL",
                        "indexer": "TestIndexer",
                        "size": 5_000_000_000,
                        "quality": {"quality": {"id": 19, "name": "WEBDL-2160p"}},
                    }
                ],
            )
        )

        async with SonarrClient("http://127.0.0.1:8989", "test-api-key") as client:
            releases = await client.get_series_releases(456)

        assert len(releases) == 1
        assert releases[0].is_4k() is True


class TestRadarrTagManagement:
    """Tests for RadarrClient tag management functionality."""

    @respx.mock
    @pytest.mark.asyncio
    async def test_get_tags(self) -> None:
        """Should fetch and parse all tags."""
        respx.get("http://localhost:7878/api/v3/tag").mock(
            return_value=Response(
                200,
                json=[
                    {"id": 1, "label": "4k-available"},
                    {"id": 2, "label": "4k-unavailable"},
                    {"id": 3, "label": "hdr"},
                ],
            )
        )

        async with RadarrClient("http://localhost:7878", "test-api-key") as client:
            tags = await client.get_tags()

        assert len(tags) == 3
        assert tags[0].id == 1
        assert tags[0].label == "4k-available"
        assert tags[2].label == "hdr"

    @respx.mock
    @pytest.mark.asyncio
    async def test_get_tags_empty(self) -> None:
        """Should return empty list when no tags exist."""
        respx.get("http://localhost:7878/api/v3/tag").mock(return_value=Response(200, json=[]))

        async with RadarrClient("http://localhost:7878", "test-api-key") as client:
            tags = await client.get_tags()

        assert tags == []

    @respx.mock
    @pytest.mark.asyncio
    async def test_create_tag(self) -> None:
        """Should create a new tag and return it."""
        respx.post("http://localhost:7878/api/v3/tag").mock(
            return_value=Response(201, json={"id": 5, "label": "new-tag"})
        )

        async with RadarrClient("http://localhost:7878", "test-api-key") as client:
            tag = await client.create_tag("new-tag")

        assert tag.id == 5
        assert tag.label == "new-tag"

    @respx.mock
    @pytest.mark.asyncio
    async def test_get_or_create_tag_existing(self) -> None:
        """Should return existing tag when it exists."""
        respx.get("http://localhost:7878/api/v3/tag").mock(
            return_value=Response(
                200,
                json=[
                    {"id": 1, "label": "4k-available"},
                    {"id": 2, "label": "4k-unavailable"},
                ],
            )
        )

        async with RadarrClient("http://localhost:7878", "test-api-key") as client:
            tag = await client.get_or_create_tag("4k-available")

        assert tag.id == 1
        assert tag.label == "4k-available"

    @respx.mock
    @pytest.mark.asyncio
    async def test_get_or_create_tag_case_insensitive(self) -> None:
        """Should find tag case-insensitively."""
        respx.get("http://localhost:7878/api/v3/tag").mock(
            return_value=Response(
                200,
                json=[{"id": 1, "label": "4K-Available"}],
            )
        )

        async with RadarrClient("http://localhost:7878", "test-api-key") as client:
            tag = await client.get_or_create_tag("4k-available")

        assert tag.id == 1
        assert tag.label == "4K-Available"

    @respx.mock
    @pytest.mark.asyncio
    async def test_get_or_create_tag_new(self) -> None:
        """Should create tag when it doesn't exist."""
        respx.get("http://localhost:7878/api/v3/tag").mock(return_value=Response(200, json=[]))
        respx.post("http://localhost:7878/api/v3/tag").mock(
            return_value=Response(201, json={"id": 1, "label": "new-tag"})
        )

        async with RadarrClient("http://localhost:7878", "test-api-key") as client:
            tag = await client.get_or_create_tag("new-tag")

        assert tag.id == 1
        assert tag.label == "new-tag"

    @respx.mock
    @pytest.mark.asyncio
    async def test_get_movie_raw(self) -> None:
        """Should fetch raw movie data as dict."""
        movie_data = {
            "id": 123,
            "title": "Test Movie",
            "year": 2024,
            "tmdbId": 999,
            "imdbId": "tt1234567",
            "monitored": True,
            "hasFile": True,
            "tags": [1, 2],
            "extraField": "ignored",
        }
        respx.get("http://localhost:7878/api/v3/movie/123").mock(
            return_value=Response(200, json=movie_data)
        )

        async with RadarrClient("http://localhost:7878", "test-api-key") as client:
            result = await client.get_movie_raw(123)

        assert result["id"] == 123
        assert result["title"] == "Test Movie"
        assert result["tags"] == [1, 2]
        assert result["extraField"] == "ignored"

    @respx.mock
    @pytest.mark.asyncio
    async def test_update_movie(self) -> None:
        """Should update movie and return validated model."""
        movie_data = {
            "id": 123,
            "title": "Test Movie",
            "year": 2024,
            "tmdbId": 999,
            "imdbId": "tt1234567",
            "monitored": True,
            "hasFile": True,
            "tags": [1, 2, 3],
        }
        respx.put("http://localhost:7878/api/v3/movie/123").mock(
            return_value=Response(200, json=movie_data)
        )

        async with RadarrClient("http://localhost:7878", "test-api-key") as client:
            movie = await client.update_movie(movie_data)

        assert movie.id == 123
        assert movie.tags == [1, 2, 3]

    @respx.mock
    @pytest.mark.asyncio
    async def test_add_tag_to_movie_new_tag(self) -> None:
        """Should add new tag to movie."""
        # First fetch the movie
        respx.get("http://localhost:7878/api/v3/movie/123").mock(
            return_value=Response(
                200,
                json={
                    "id": 123,
                    "title": "Test Movie",
                    "year": 2024,
                    "tags": [1],
                },
            )
        )
        # Then update with new tag
        respx.put("http://localhost:7878/api/v3/movie/123").mock(
            return_value=Response(
                200,
                json={
                    "id": 123,
                    "title": "Test Movie",
                    "year": 2024,
                    "tags": [1, 2],
                },
            )
        )

        async with RadarrClient("http://localhost:7878", "test-api-key") as client:
            movie = await client.add_tag_to_movie(123, 2)

        assert movie.id == 123
        assert 2 in movie.tags

    @respx.mock
    @pytest.mark.asyncio
    async def test_add_tag_to_movie_already_exists(self) -> None:
        """Should return movie unchanged when tag already exists."""
        # First fetch shows tag already exists
        respx.get("http://localhost:7878/api/v3/movie/123").mock(
            return_value=Response(
                200,
                json={
                    "id": 123,
                    "title": "Test Movie",
                    "year": 2024,
                    "tags": [1, 2],
                },
            )
        )

        async with RadarrClient("http://localhost:7878", "test-api-key") as client:
            movie = await client.add_tag_to_movie(123, 2)

        assert movie.id == 123
        assert movie.tags == [1, 2]

    @respx.mock
    @pytest.mark.asyncio
    async def test_remove_tag_from_movie(self) -> None:
        """Should remove tag from movie."""
        # First fetch the movie
        respx.get("http://localhost:7878/api/v3/movie/123").mock(
            return_value=Response(
                200,
                json={
                    "id": 123,
                    "title": "Test Movie",
                    "year": 2024,
                    "tags": [1, 2],
                },
            )
        )
        # Then update without the tag
        respx.put("http://localhost:7878/api/v3/movie/123").mock(
            return_value=Response(
                200,
                json={
                    "id": 123,
                    "title": "Test Movie",
                    "year": 2024,
                    "tags": [1],
                },
            )
        )

        async with RadarrClient("http://localhost:7878", "test-api-key") as client:
            movie = await client.remove_tag_from_movie(123, 2)

        assert movie.id == 123
        assert 2 not in movie.tags

    @respx.mock
    @pytest.mark.asyncio
    async def test_remove_tag_from_movie_not_present(self) -> None:
        """Should return movie unchanged when tag not present."""
        respx.get("http://localhost:7878/api/v3/movie/123").mock(
            return_value=Response(
                200,
                json={
                    "id": 123,
                    "title": "Test Movie",
                    "year": 2024,
                    "tags": [1],
                },
            )
        )

        async with RadarrClient("http://localhost:7878", "test-api-key") as client:
            movie = await client.remove_tag_from_movie(123, 99)

        assert movie.id == 123
        assert movie.tags == [1]

    @respx.mock
    @pytest.mark.asyncio
    async def test_add_tag_to_movie_empty_tags(self) -> None:
        """Should handle movie with no existing tags."""
        respx.get("http://localhost:7878/api/v3/movie/123").mock(
            return_value=Response(
                200,
                json={
                    "id": 123,
                    "title": "Test Movie",
                    "year": 2024,
                    "tags": [],
                },
            )
        )
        respx.put("http://localhost:7878/api/v3/movie/123").mock(
            return_value=Response(
                200,
                json={
                    "id": 123,
                    "title": "Test Movie",
                    "year": 2024,
                    "tags": [5],
                },
            )
        )

        async with RadarrClient("http://localhost:7878", "test-api-key") as client:
            movie = await client.add_tag_to_movie(123, 5)

        assert movie.tags == [5]

    @respx.mock
    @pytest.mark.asyncio
    async def test_remove_tag_from_movie_last_tag(self) -> None:
        """Should handle removing last tag from movie."""
        respx.get("http://localhost:7878/api/v3/movie/123").mock(
            return_value=Response(
                200,
                json={
                    "id": 123,
                    "title": "Test Movie",
                    "year": 2024,
                    "tags": [1],
                },
            )
        )
        respx.put("http://localhost:7878/api/v3/movie/123").mock(
            return_value=Response(
                200,
                json={
                    "id": 123,
                    "title": "Test Movie",
                    "year": 2024,
                    "tags": [],
                },
            )
        )

        async with RadarrClient("http://localhost:7878", "test-api-key") as client:
            movie = await client.remove_tag_from_movie(123, 1)

        assert movie.tags == []
