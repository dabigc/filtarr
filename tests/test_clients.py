"""Tests for API clients."""

import pytest
import respx
from httpx import Response

from findarr.clients.radarr import RadarrClient
from findarr.clients.sonarr import SonarrClient


class TestRadarrClient:
    """Tests for RadarrClient."""

    @respx.mock
    @pytest.mark.asyncio
    async def test_get_movie_releases(self, sample_radarr_response: list[dict]) -> None:
        """Should parse releases from Radarr API response."""
        respx.get("http://radarr:7878/api/v3/release", params={"movieId": "123"}).mock(
            return_value=Response(200, json=sample_radarr_response)
        )

        async with RadarrClient("http://radarr:7878", "test-api-key") as client:
            releases = await client.get_movie_releases(123)

        assert len(releases) == 2
        assert releases[0].title == "Movie.Name.2024.2160p.UHD.BluRay.x265-GROUP"
        assert releases[0].is_4k() is True
        assert releases[1].is_4k() is False

    @respx.mock
    @pytest.mark.asyncio
    async def test_has_4k_releases_true(self, sample_radarr_response: list[dict]) -> None:
        """Should return True when 4K releases exist."""
        respx.get("http://radarr:7878/api/v3/release", params={"movieId": "123"}).mock(
            return_value=Response(200, json=sample_radarr_response)
        )

        async with RadarrClient("http://radarr:7878", "test-api-key") as client:
            has_4k = await client.has_4k_releases(123)

        assert has_4k is True

    @respx.mock
    @pytest.mark.asyncio
    async def test_has_4k_releases_false(self) -> None:
        """Should return False when no 4K releases exist."""
        respx.get("http://radarr:7878/api/v3/release", params={"movieId": "123"}).mock(
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

        async with RadarrClient("http://radarr:7878", "test-api-key") as client:
            has_4k = await client.has_4k_releases(123)

        assert has_4k is False

    @pytest.mark.asyncio
    async def test_client_not_in_context_raises(self) -> None:
        """Should raise when client used outside context manager."""
        client = RadarrClient("http://radarr:7878", "test-api-key")
        with pytest.raises(RuntimeError, match="must be used within async context"):
            _ = client.client


class TestRadarrClientSearch:
    """Tests for RadarrClient search functionality."""

    @respx.mock
    @pytest.mark.asyncio
    async def test_get_all_movies(self) -> None:
        """Should fetch and parse all movies."""
        respx.get("http://radarr:7878/api/v3/movie").mock(
            return_value=Response(
                200,
                json=[
                    {"id": 1, "title": "The Matrix", "year": 1999, "tmdbId": 603,
                     "imdbId": "tt0133093", "monitored": True, "hasFile": True},
                    {"id": 2, "title": "The Matrix Reloaded", "year": 2003, "tmdbId": 604,
                     "imdbId": "tt0234215", "monitored": True, "hasFile": False},
                ],
            )
        )

        async with RadarrClient("http://radarr:7878", "test-api-key") as client:
            movies = await client.get_all_movies()

        assert len(movies) == 2
        assert movies[0].title == "The Matrix"
        assert movies[0].year == 1999
        assert movies[1].title == "The Matrix Reloaded"

    @respx.mock
    @pytest.mark.asyncio
    async def test_search_movies_case_insensitive(self) -> None:
        """Should search movies case-insensitively."""
        respx.get("http://radarr:7878/api/v3/movie").mock(
            return_value=Response(
                200,
                json=[
                    {"id": 1, "title": "The Matrix", "year": 1999},
                    {"id": 2, "title": "The Matrix Reloaded", "year": 2003},
                    {"id": 3, "title": "Inception", "year": 2010},
                ],
            )
        )

        async with RadarrClient("http://radarr:7878", "test-api-key") as client:
            results = await client.search_movies("matrix")

        assert len(results) == 2
        assert all("matrix" in m.title.lower() for m in results)

    @respx.mock
    @pytest.mark.asyncio
    async def test_search_movies_no_matches(self) -> None:
        """Should return empty list when no matches."""
        respx.get("http://radarr:7878/api/v3/movie").mock(
            return_value=Response(
                200,
                json=[
                    {"id": 1, "title": "The Matrix", "year": 1999},
                ],
            )
        )

        async with RadarrClient("http://radarr:7878", "test-api-key") as client:
            results = await client.search_movies("inception")

        assert results == []

    @respx.mock
    @pytest.mark.asyncio
    async def test_find_movie_by_name_exact_match(self) -> None:
        """Should return exact match when found."""
        respx.get("http://radarr:7878/api/v3/movie").mock(
            return_value=Response(
                200,
                json=[
                    {"id": 1, "title": "The Matrix", "year": 1999},
                    {"id": 2, "title": "The Matrix Reloaded", "year": 2003},
                ],
            )
        )

        async with RadarrClient("http://radarr:7878", "test-api-key") as client:
            movie = await client.find_movie_by_name("The Matrix")

        assert movie is not None
        assert movie.id == 1
        assert movie.title == "The Matrix"

    @respx.mock
    @pytest.mark.asyncio
    async def test_find_movie_by_name_closest_match(self) -> None:
        """Should return shortest title when no exact match."""
        respx.get("http://radarr:7878/api/v3/movie").mock(
            return_value=Response(
                200,
                json=[
                    {"id": 1, "title": "The Matrix Reloaded", "year": 2003},
                    {"id": 2, "title": "The Matrix Revolutions", "year": 2003},
                ],
            )
        )

        async with RadarrClient("http://radarr:7878", "test-api-key") as client:
            movie = await client.find_movie_by_name("Matrix")

        assert movie is not None
        # Returns shortest matching title
        assert movie.id == 1
        assert movie.title == "The Matrix Reloaded"

    @respx.mock
    @pytest.mark.asyncio
    async def test_find_movie_by_name_not_found(self) -> None:
        """Should return None when movie not found."""
        respx.get("http://radarr:7878/api/v3/movie").mock(
            return_value=Response(
                200,
                json=[{"id": 1, "title": "The Matrix", "year": 1999}],
            )
        )

        async with RadarrClient("http://radarr:7878", "test-api-key") as client:
            movie = await client.find_movie_by_name("Inception")

        assert movie is None


class TestSonarrClientSearch:
    """Tests for SonarrClient search functionality."""

    @respx.mock
    @pytest.mark.asyncio
    async def test_get_all_series(self) -> None:
        """Should fetch and parse all series."""
        respx.get("http://sonarr:8989/api/v3/series").mock(
            return_value=Response(
                200,
                json=[
                    {"id": 1, "title": "Breaking Bad", "year": 2008, "monitored": True,
                     "seasons": [{"seasonNumber": 1, "monitored": True}]},
                    {"id": 2, "title": "Better Call Saul", "year": 2015, "monitored": True,
                     "seasons": []},
                ],
            )
        )

        async with SonarrClient("http://sonarr:8989", "test-api-key") as client:
            series = await client.get_all_series()

        assert len(series) == 2
        assert series[0].title == "Breaking Bad"
        assert series[1].title == "Better Call Saul"

    @respx.mock
    @pytest.mark.asyncio
    async def test_search_series_case_insensitive(self) -> None:
        """Should search series case-insensitively."""
        respx.get("http://sonarr:8989/api/v3/series").mock(
            return_value=Response(
                200,
                json=[
                    {"id": 1, "title": "Breaking Bad", "year": 2008, "seasons": []},
                    {"id": 2, "title": "Better Call Saul", "year": 2015, "seasons": []},
                    {"id": 3, "title": "The Office", "year": 2005, "seasons": []},
                ],
            )
        )

        async with SonarrClient("http://sonarr:8989", "test-api-key") as client:
            results = await client.search_series("breaking")

        assert len(results) == 1
        assert results[0].title == "Breaking Bad"

    @respx.mock
    @pytest.mark.asyncio
    async def test_find_series_by_name_exact_match(self) -> None:
        """Should return exact match when found."""
        respx.get("http://sonarr:8989/api/v3/series").mock(
            return_value=Response(
                200,
                json=[
                    {"id": 1, "title": "Breaking Bad", "year": 2008, "seasons": []},
                    {"id": 2, "title": "Breaking Bad: El Camino", "year": 2019, "seasons": []},
                ],
            )
        )

        async with SonarrClient("http://sonarr:8989", "test-api-key") as client:
            series = await client.find_series_by_name("Breaking Bad")

        assert series is not None
        assert series.id == 1
        assert series.title == "Breaking Bad"

    @respx.mock
    @pytest.mark.asyncio
    async def test_find_series_by_name_not_found(self) -> None:
        """Should return None when series not found."""
        respx.get("http://sonarr:8989/api/v3/series").mock(
            return_value=Response(
                200,
                json=[{"id": 1, "title": "Breaking Bad", "year": 2008, "seasons": []}],
            )
        )

        async with SonarrClient("http://sonarr:8989", "test-api-key") as client:
            series = await client.find_series_by_name("The Office")

        assert series is None


class TestSonarrClient:
    """Tests for SonarrClient."""

    @respx.mock
    @pytest.mark.asyncio
    async def test_get_series_releases(self) -> None:
        """Should parse releases from Sonarr API response."""
        respx.get("http://sonarr:8989/api/v3/release", params={"seriesId": "456"}).mock(
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

        async with SonarrClient("http://sonarr:8989", "test-api-key") as client:
            releases = await client.get_series_releases(456)

        assert len(releases) == 1
        assert releases[0].is_4k() is True
