"""Extended tests for checker.py edge cases."""

from __future__ import annotations

from datetime import date, timedelta

import httpx
import pytest
import respx
from httpx import Response

from filtarr.checker import ReleaseChecker, SearchResult
from filtarr.config import TagConfig
from filtarr.criteria import ResultType, SearchCriteria
from filtarr.models.common import Quality, Release


class TestSearchResultMatchedReleasesProperty:
    """Tests for SearchResult.matched_releases property edge cases."""

    def test_matched_releases_with_none_criteria_defaults_to_4k(self) -> None:
        """When _criteria is None, matched_releases should default to 4K filtering."""
        releases = [
            Release(
                guid="1",
                title="Movie.2160p.UHD",
                indexer="Test",
                size=5000,
                quality=Quality(id=19, name="WEBDL-2160p"),
            ),
            Release(
                guid="2",
                title="Movie.1080p.BluRay",
                indexer="Test",
                size=2000,
                quality=Quality(id=7, name="Bluray-1080p"),
            ),
        ]

        result = SearchResult(
            item_id=123,
            item_type="movie",
            has_match=True,
            releases=releases,
            _criteria=None,
        )

        matched = result.matched_releases
        assert len(matched) == 1
        assert matched[0].guid == "1"
        assert matched[0].is_4k()

    def test_matched_releases_with_search_criteria_enum(self) -> None:
        """When _criteria is a SearchCriteria enum, use the appropriate matcher."""
        releases = [
            Release(
                guid="1",
                title="Movie.2160p.HDR.UHD",
                indexer="Test",
                size=5000,
                quality=Quality(id=19, name="WEBDL-2160p"),
            ),
            Release(
                guid="2",
                title="Movie.2160p.SDR",
                indexer="Test",
                size=4000,
                quality=Quality(id=19, name="WEBDL-2160p"),
            ),
        ]

        result = SearchResult(
            item_id=123,
            item_type="movie",
            has_match=True,
            releases=releases,
            _criteria=SearchCriteria.HDR,
        )

        matched = result.matched_releases
        assert len(matched) == 1
        assert matched[0].guid == "1"
        assert "HDR" in matched[0].title

    def test_matched_releases_with_custom_callable(self) -> None:
        """When _criteria is a custom callable, use it for filtering."""

        def remux_matcher(release: Release) -> bool:
            return "REMUX" in release.title.upper()

        releases = [
            Release(
                guid="1",
                title="Movie.2160p.REMUX.BluRay",
                indexer="Test",
                size=50000,
                quality=Quality(id=31, name="Bluray-2160p"),
            ),
            Release(
                guid="2",
                title="Movie.2160p.BluRay",
                indexer="Test",
                size=5000,
                quality=Quality(id=31, name="Bluray-2160p"),
            ),
        ]

        result = SearchResult(
            item_id=123,
            item_type="movie",
            has_match=True,
            releases=releases,
            _criteria=remux_matcher,
        )

        matched = result.matched_releases
        assert len(matched) == 1
        assert matched[0].guid == "1"
        assert "REMUX" in matched[0].title

    def test_matched_releases_with_dolby_vision_criteria(self) -> None:
        """Test matched_releases with Dolby Vision criteria."""
        releases = [
            Release(
                guid="1",
                title="Movie.2160p.DV.HDR",
                indexer="Test",
                size=5000,
                quality=Quality(id=19, name="WEBDL-2160p"),
            ),
            Release(
                guid="2",
                title="Movie.2160p.HDR10",
                indexer="Test",
                size=4000,
                quality=Quality(id=19, name="WEBDL-2160p"),
            ),
        ]

        result = SearchResult(
            item_id=123,
            item_type="movie",
            has_match=True,
            releases=releases,
            _criteria=SearchCriteria.DOLBY_VISION,
        )

        matched = result.matched_releases
        assert len(matched) == 1
        assert matched[0].guid == "1"


class TestCheckMovieWithCustomCallable:
    """Tests for check_movie with custom callable criteria."""

    @respx.mock
    @pytest.mark.asyncio
    async def test_check_movie_custom_callable_result_type_is_custom(self) -> None:
        """Custom callable should result in result_type=CUSTOM."""

        def size_matcher(release: Release) -> bool:
            return release.size > 10000

        respx.get("http://localhost:7878/api/v3/movie/123").mock(
            return_value=Response(
                200,
                json={"id": 123, "title": "Big Movie", "year": 2024, "tags": []},
            )
        )
        respx.get("http://localhost:7878/api/v3/release", params={"movieId": "123"}).mock(
            return_value=Response(
                200,
                json=[
                    {
                        "guid": "rel1",
                        "title": "Movie.Large.File",
                        "indexer": "Test",
                        "size": 50000,
                        "quality": {"quality": {"id": 31, "name": "Bluray-2160p"}},
                    }
                ],
            )
        )

        checker = ReleaseChecker(radarr_url="http://localhost:7878", radarr_api_key="test")
        result = await checker.check_movie(123, criteria=size_matcher, apply_tags=False)

        assert result.result_type == ResultType.CUSTOM
        assert result.has_match is True


class TestCheckMovieByNameWithCustomCallable:
    """Tests for check_movie_by_name with custom callable criteria."""

    @respx.mock
    @pytest.mark.asyncio
    async def test_check_movie_by_name_custom_callable_result_type(self) -> None:
        """check_movie_by_name with custom callable should set result_type=CUSTOM."""

        def dual_audio_matcher(release: Release) -> bool:
            title = release.title.upper()
            return "DUAL" in title or "DUB" in title

        respx.get("http://localhost:7878/api/v3/movie").mock(
            return_value=Response(
                200,
                json=[{"id": 456, "title": "Foreign Film", "year": 2023}],
            )
        )
        respx.get("http://localhost:7878/api/v3/release", params={"movieId": "456"}).mock(
            return_value=Response(
                200,
                json=[
                    {
                        "guid": "rel1",
                        "title": "Foreign.Film.2023.DualAudio.1080p",
                        "indexer": "Test",
                        "size": 3000,
                        "quality": {"quality": {"id": 7, "name": "Bluray-1080p"}},
                    }
                ],
            )
        )

        checker = ReleaseChecker(radarr_url="http://localhost:7878", radarr_api_key="test")
        result = await checker.check_movie_by_name(
            "Foreign Film", criteria=dual_audio_matcher, apply_tags=False
        )

        assert result.result_type == ResultType.CUSTOM
        assert result.has_match is True
        assert result.item_name == "Foreign Film"


class TestCheckSeriesWithCustomCallable:
    """Tests for check_series with custom callable criteria."""

    @respx.mock
    @pytest.mark.asyncio
    async def test_check_series_custom_callable_result_type_is_custom(self) -> None:
        """check_series with custom callable should set result_type=CUSTOM."""

        def hevc_matcher(release: Release) -> bool:
            title = release.title.upper()
            return "HEVC" in title or "X265" in title or "H.265" in title

        respx.get("http://127.0.0.1:8989/api/v3/series/123").mock(
            return_value=Response(
                200, json={"id": 123, "title": "Test Series", "year": 2020, "seasons": []}
            )
        )
        respx.get("http://127.0.0.1:8989/api/v3/episode", params={"seriesId": "123"}).mock(
            return_value=Response(
                200,
                json=[
                    {
                        "id": 101,
                        "seriesId": 123,
                        "seasonNumber": 1,
                        "episodeNumber": 1,
                        "airDate": "2020-01-01",
                        "monitored": True,
                    },
                ],
            )
        )
        respx.get("http://127.0.0.1:8989/api/v3/release", params={"episodeId": "101"}).mock(
            return_value=Response(
                200,
                json=[
                    {
                        "guid": "rel-101",
                        "title": "Show.S01E01.1080p.x265.HEVC",
                        "indexer": "Test",
                        "size": 1500,
                        "quality": {"quality": {"id": 7, "name": "WEBDL-1080p"}},
                    }
                ],
            )
        )

        checker = ReleaseChecker(sonarr_url="http://127.0.0.1:8989", sonarr_api_key="test")
        result = await checker.check_series(123, criteria=hevc_matcher, apply_tags=False)

        assert result.result_type == ResultType.CUSTOM
        assert result.has_match is True
        assert result.item_type == "series"


class TestCheckSeriesNoSeasonsToCheck:
    """Tests for check_series when there are no seasons to check."""

    @respx.mock
    @pytest.mark.asyncio
    async def test_check_series_no_aired_episodes_returns_false(self) -> None:
        """Series with only future episodes should return has_match=False."""
        tomorrow = date.today() + timedelta(days=1)

        respx.get("http://127.0.0.1:8989/api/v3/series/123").mock(
            return_value=Response(
                200, json={"id": 123, "title": "Future Series", "year": 2025, "seasons": []}
            )
        )
        respx.get("http://127.0.0.1:8989/api/v3/episode", params={"seriesId": "123"}).mock(
            return_value=Response(
                200,
                json=[
                    {
                        "id": 101,
                        "seriesId": 123,
                        "seasonNumber": 1,
                        "episodeNumber": 1,
                        "airDate": tomorrow.isoformat(),
                        "monitored": True,
                    },
                ],
            )
        )

        checker = ReleaseChecker(sonarr_url="http://127.0.0.1:8989", sonarr_api_key="test")
        result = await checker.check_series(123, apply_tags=False)

        assert result.has_match is False
        assert result.episodes_checked == []
        assert result.seasons_checked == []

    @respx.mock
    @pytest.mark.asyncio
    async def test_check_series_no_episodes_at_all(self) -> None:
        """Series with no episodes returns has_match=False."""
        respx.get("http://127.0.0.1:8989/api/v3/series/123").mock(
            return_value=Response(
                200, json={"id": 123, "title": "Empty Series", "year": 2024, "seasons": []}
            )
        )
        respx.get("http://127.0.0.1:8989/api/v3/episode", params={"seriesId": "123"}).mock(
            return_value=Response(200, json=[])
        )

        checker = ReleaseChecker(sonarr_url="http://127.0.0.1:8989", sonarr_api_key="test")
        result = await checker.check_series(123, apply_tags=False)

        assert result.has_match is False
        assert result.episodes_checked == []


class TestApplyMovieTagsErrorHandling:
    """Tests for _apply_movie_tags HTTP error handling."""

    @respx.mock
    @pytest.mark.asyncio
    async def test_apply_movie_tags_http_500_error(self) -> None:
        """HTTP 500 error from tags API should be caught and recorded."""
        respx.get("http://localhost:7878/api/v3/movie/123").mock(
            return_value=Response(
                200,
                json={"id": 123, "title": "Test Movie", "year": 2024, "tags": []},
            )
        )
        respx.get("http://localhost:7878/api/v3/release", params={"movieId": "123"}).mock(
            return_value=Response(
                200,
                json=[
                    {
                        "guid": "rel1",
                        "title": "Movie.2160p.BluRay",
                        "indexer": "Test",
                        "size": 5000,
                        "quality": {"quality": {"id": 19, "name": "WEBDL-2160p"}},
                    }
                ],
            )
        )
        respx.get("http://localhost:7878/api/v3/tag").mock(
            return_value=Response(500, json={"error": "Internal Server Error"})
        )

        tag_config = TagConfig()
        checker = ReleaseChecker(
            radarr_url="http://localhost:7878",
            radarr_api_key="test",
            tag_config=tag_config,
        )

        result = await checker.check_movie(123, apply_tags=True, dry_run=False)

        assert result.has_match is True
        assert result.tag_result is not None
        assert result.tag_result.tag_error is not None
        assert "HTTP 500" in result.tag_result.tag_error

    @respx.mock
    @pytest.mark.asyncio
    async def test_apply_movie_tags_connect_error(self) -> None:
        """ConnectError should be caught and recorded in tag_error."""
        respx.get("http://localhost:7878/api/v3/movie/123").mock(
            return_value=Response(
                200,
                json={"id": 123, "title": "Test Movie", "year": 2024, "tags": []},
            )
        )
        respx.get("http://localhost:7878/api/v3/release", params={"movieId": "123"}).mock(
            return_value=Response(
                200,
                json=[
                    {
                        "guid": "rel1",
                        "title": "Movie.2160p.BluRay",
                        "indexer": "Test",
                        "size": 5000,
                        "quality": {"quality": {"id": 19, "name": "WEBDL-2160p"}},
                    }
                ],
            )
        )
        respx.get("http://localhost:7878/api/v3/tag").mock(
            side_effect=httpx.ConnectError("Connection refused")
        )

        tag_config = TagConfig()
        checker = ReleaseChecker(
            radarr_url="http://localhost:7878",
            radarr_api_key="test",
            tag_config=tag_config,
        )

        result = await checker.check_movie(123, apply_tags=True, dry_run=False)

        assert result.has_match is True
        assert result.tag_result is not None
        assert result.tag_result.tag_error is not None
        assert "Network error" in result.tag_result.tag_error

    @respx.mock
    @pytest.mark.asyncio
    async def test_apply_movie_tags_timeout_error(self) -> None:
        """TimeoutException should be caught and recorded in tag_error."""
        respx.get("http://localhost:7878/api/v3/movie/123").mock(
            return_value=Response(
                200,
                json={"id": 123, "title": "Test Movie", "year": 2024, "tags": []},
            )
        )
        respx.get("http://localhost:7878/api/v3/release", params={"movieId": "123"}).mock(
            return_value=Response(
                200,
                json=[
                    {
                        "guid": "rel1",
                        "title": "Movie.2160p.BluRay",
                        "indexer": "Test",
                        "size": 5000,
                        "quality": {"quality": {"id": 19, "name": "WEBDL-2160p"}},
                    }
                ],
            )
        )
        respx.get("http://localhost:7878/api/v3/tag").mock(
            side_effect=httpx.TimeoutException("Request timed out")
        )

        tag_config = TagConfig()
        checker = ReleaseChecker(
            radarr_url="http://localhost:7878",
            radarr_api_key="test",
            tag_config=tag_config,
        )

        result = await checker.check_movie(123, apply_tags=True, dry_run=False)

        assert result.has_match is True
        assert result.tag_result is not None
        assert result.tag_result.tag_error is not None
        assert "Network error" in result.tag_result.tag_error

    @respx.mock
    @pytest.mark.asyncio
    async def test_apply_movie_tags_validation_error(self) -> None:
        """ValidationError from pydantic should be caught and recorded."""
        respx.get("http://localhost:7878/api/v3/movie/123").mock(
            return_value=Response(
                200,
                json={"id": 123, "title": "Test Movie", "year": 2024, "tags": []},
            )
        )
        respx.get("http://localhost:7878/api/v3/release", params={"movieId": "123"}).mock(
            return_value=Response(
                200,
                json=[
                    {
                        "guid": "rel1",
                        "title": "Movie.2160p.BluRay",
                        "indexer": "Test",
                        "size": 5000,
                        "quality": {"quality": {"id": 19, "name": "WEBDL-2160p"}},
                    }
                ],
            )
        )
        # Return invalid data that will fail pydantic validation
        respx.get("http://localhost:7878/api/v3/tag").mock(
            return_value=Response(
                200,
                json=[{"invalid_field": "no id or label"}],
            )
        )

        tag_config = TagConfig()
        checker = ReleaseChecker(
            radarr_url="http://localhost:7878",
            radarr_api_key="test",
            tag_config=tag_config,
        )

        result = await checker.check_movie(123, apply_tags=True, dry_run=False)

        assert result.has_match is True
        assert result.tag_result is not None
        assert result.tag_result.tag_error is not None
        assert "Validation error" in result.tag_result.tag_error


class TestApplySeriesTagsErrorHandling:
    """Tests for _apply_series_tags HTTP error handling."""

    @respx.mock
    @pytest.mark.asyncio
    async def test_apply_series_tags_http_500_error(self) -> None:
        """HTTP 500 error from series tags API should be caught."""
        respx.get("http://127.0.0.1:8989/api/v3/series/123").mock(
            return_value=Response(
                200, json={"id": 123, "title": "Test Series", "year": 2020, "seasons": []}
            )
        )
        respx.get("http://127.0.0.1:8989/api/v3/episode", params={"seriesId": "123"}).mock(
            return_value=Response(
                200,
                json=[
                    {
                        "id": 101,
                        "seriesId": 123,
                        "seasonNumber": 1,
                        "episodeNumber": 1,
                        "airDate": "2020-01-01",
                        "monitored": True,
                    },
                ],
            )
        )
        respx.get("http://127.0.0.1:8989/api/v3/release", params={"episodeId": "101"}).mock(
            return_value=Response(
                200,
                json=[
                    {
                        "guid": "rel-101",
                        "title": "Show.S01.2160p.WEB-DL",
                        "indexer": "Test",
                        "size": 5000,
                        "quality": {"quality": {"id": 19, "name": "WEBDL-2160p"}},
                    }
                ],
            )
        )
        respx.get("http://127.0.0.1:8989/api/v3/tag").mock(
            return_value=Response(500, json={"error": "Internal Server Error"})
        )

        tag_config = TagConfig()
        checker = ReleaseChecker(
            sonarr_url="http://127.0.0.1:8989",
            sonarr_api_key="test",
            tag_config=tag_config,
        )

        result = await checker.check_series(123, apply_tags=True, dry_run=False)

        assert result.has_match is True
        assert result.tag_result is not None
        assert result.tag_result.tag_error is not None
        assert "HTTP 500" in result.tag_result.tag_error

    @respx.mock
    @pytest.mark.asyncio
    async def test_apply_series_tags_connect_error(self) -> None:
        """ConnectError for series tags should be caught."""
        respx.get("http://127.0.0.1:8989/api/v3/series/123").mock(
            return_value=Response(
                200, json={"id": 123, "title": "Test Series", "year": 2020, "seasons": []}
            )
        )
        respx.get("http://127.0.0.1:8989/api/v3/episode", params={"seriesId": "123"}).mock(
            return_value=Response(
                200,
                json=[
                    {
                        "id": 101,
                        "seriesId": 123,
                        "seasonNumber": 1,
                        "episodeNumber": 1,
                        "airDate": "2020-01-01",
                        "monitored": True,
                    },
                ],
            )
        )
        respx.get("http://127.0.0.1:8989/api/v3/release", params={"episodeId": "101"}).mock(
            return_value=Response(
                200,
                json=[
                    {
                        "guid": "rel-101",
                        "title": "Show.S01.2160p.WEB-DL",
                        "indexer": "Test",
                        "size": 5000,
                        "quality": {"quality": {"id": 19, "name": "WEBDL-2160p"}},
                    }
                ],
            )
        )
        respx.get("http://127.0.0.1:8989/api/v3/tag").mock(
            side_effect=httpx.ConnectError("Connection refused")
        )

        tag_config = TagConfig()
        checker = ReleaseChecker(
            sonarr_url="http://127.0.0.1:8989",
            sonarr_api_key="test",
            tag_config=tag_config,
        )

        result = await checker.check_series(123, apply_tags=True, dry_run=False)

        assert result.has_match is True
        assert result.tag_result is not None
        assert "Network error" in result.tag_result.tag_error

    @respx.mock
    @pytest.mark.asyncio
    async def test_apply_series_tags_timeout_error(self) -> None:
        """TimeoutException for series tags should be caught."""
        respx.get("http://127.0.0.1:8989/api/v3/series/123").mock(
            return_value=Response(
                200, json={"id": 123, "title": "Test Series", "year": 2020, "seasons": []}
            )
        )
        respx.get("http://127.0.0.1:8989/api/v3/episode", params={"seriesId": "123"}).mock(
            return_value=Response(
                200,
                json=[
                    {
                        "id": 101,
                        "seriesId": 123,
                        "seasonNumber": 1,
                        "episodeNumber": 1,
                        "airDate": "2020-01-01",
                        "monitored": True,
                    },
                ],
            )
        )
        respx.get("http://127.0.0.1:8989/api/v3/release", params={"episodeId": "101"}).mock(
            return_value=Response(
                200,
                json=[
                    {
                        "guid": "rel-101",
                        "title": "Show.S01.2160p.WEB-DL",
                        "indexer": "Test",
                        "size": 5000,
                        "quality": {"quality": {"id": 19, "name": "WEBDL-2160p"}},
                    }
                ],
            )
        )
        respx.get("http://127.0.0.1:8989/api/v3/tag").mock(
            side_effect=httpx.TimeoutException("Request timed out")
        )

        tag_config = TagConfig()
        checker = ReleaseChecker(
            sonarr_url="http://127.0.0.1:8989",
            sonarr_api_key="test",
            tag_config=tag_config,
        )

        result = await checker.check_series(123, apply_tags=True, dry_run=False)

        assert result.has_match is True
        assert result.tag_result is not None
        assert "Network error" in result.tag_result.tag_error

    @respx.mock
    @pytest.mark.asyncio
    async def test_apply_series_tags_validation_error(self) -> None:
        """ValidationError for series tags should be caught."""
        respx.get("http://127.0.0.1:8989/api/v3/series/123").mock(
            return_value=Response(
                200, json={"id": 123, "title": "Test Series", "year": 2020, "seasons": []}
            )
        )
        respx.get("http://127.0.0.1:8989/api/v3/episode", params={"seriesId": "123"}).mock(
            return_value=Response(
                200,
                json=[
                    {
                        "id": 101,
                        "seriesId": 123,
                        "seasonNumber": 1,
                        "episodeNumber": 1,
                        "airDate": "2020-01-01",
                        "monitored": True,
                    },
                ],
            )
        )
        respx.get("http://127.0.0.1:8989/api/v3/release", params={"episodeId": "101"}).mock(
            return_value=Response(
                200,
                json=[
                    {
                        "guid": "rel-101",
                        "title": "Show.S01.2160p.WEB-DL",
                        "indexer": "Test",
                        "size": 5000,
                        "quality": {"quality": {"id": 19, "name": "WEBDL-2160p"}},
                    }
                ],
            )
        )
        respx.get("http://127.0.0.1:8989/api/v3/tag").mock(
            return_value=Response(
                200,
                json=[{"invalid_field": "no id or label"}],
            )
        )

        tag_config = TagConfig()
        checker = ReleaseChecker(
            sonarr_url="http://127.0.0.1:8989",
            sonarr_api_key="test",
            tag_config=tag_config,
        )

        result = await checker.check_series(123, apply_tags=True, dry_run=False)

        assert result.has_match is True
        assert result.tag_result is not None
        assert "Validation error" in result.tag_result.tag_error


class TestApplySeriesTagsNoAiredEpisodes:
    """Tests for series tag application when no episodes are aired."""

    @respx.mock
    @pytest.mark.asyncio
    async def test_series_no_aired_episodes_applies_unavailable_tag(self) -> None:
        """Series with no aired episodes should apply unavailable tag."""
        tomorrow = date.today() + timedelta(days=1)

        respx.get("http://127.0.0.1:8989/api/v3/series/123").mock(
            return_value=Response(
                200, json={"id": 123, "title": "Future Show", "year": 2025, "seasons": []}
            )
        )
        respx.get("http://127.0.0.1:8989/api/v3/episode", params={"seriesId": "123"}).mock(
            return_value=Response(
                200,
                json=[
                    {
                        "id": 101,
                        "seriesId": 123,
                        "seasonNumber": 1,
                        "episodeNumber": 1,
                        "airDate": tomorrow.isoformat(),
                        "monitored": True,
                    },
                ],
            )
        )
        respx.get("http://127.0.0.1:8989/api/v3/tag").mock(return_value=Response(200, json=[]))
        respx.post("http://127.0.0.1:8989/api/v3/tag").mock(
            return_value=Response(201, json={"id": 1, "label": "4k-unavailable"})
        )
        respx.put("http://127.0.0.1:8989/api/v3/series/123").mock(
            return_value=Response(
                200,
                json={
                    "id": 123,
                    "title": "Future Show",
                    "year": 2025,
                    "seasons": [],
                    "tags": [1],
                },
            )
        )

        tag_config = TagConfig()
        checker = ReleaseChecker(
            sonarr_url="http://127.0.0.1:8989",
            sonarr_api_key="test",
            tag_config=tag_config,
        )

        result = await checker.check_series(123, apply_tags=True, dry_run=False)

        assert result.has_match is False
        assert result.tag_result is not None
        assert result.tag_result.tag_applied == "4k-unavailable"
