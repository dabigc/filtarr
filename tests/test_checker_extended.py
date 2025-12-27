"""Extended tests for checker.py edge cases."""

from __future__ import annotations

from datetime import date, timedelta

import httpx
import pytest
import respx
from httpx import Response

from filtarr.checker import ReleaseChecker, SamplingStrategy, SearchResult, select_seasons_to_check
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
        assert result.tag_result.tag_error is not None
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
        assert result.tag_result.tag_error is not None
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
        assert result.tag_result.tag_error is not None
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


class TestSelectSeasonsToCheckFallback:
    """Tests for select_seasons_to_check fallback path (L139).

    The fallback `return sorted_seasons` on line 139 is the default case when
    no strategy matches. Since SamplingStrategy is an enum, this is defensive
    code that handles potential future strategy additions.
    """

    def test_select_seasons_with_one_season_recent_strategy(self) -> None:
        """Single season with RECENT strategy should return that season."""
        result = select_seasons_to_check([5], SamplingStrategy.RECENT, max_seasons=3)
        assert result == [5]

    def test_select_seasons_with_two_seasons_recent_strategy(self) -> None:
        """Two seasons with RECENT strategy should return both."""
        result = select_seasons_to_check([2, 4], SamplingStrategy.RECENT, max_seasons=3)
        assert result == [2, 4]

    def test_select_seasons_with_three_seasons_recent_strategy(self) -> None:
        """Three seasons with RECENT strategy should return all three."""
        result = select_seasons_to_check([1, 2, 3], SamplingStrategy.RECENT, max_seasons=3)
        assert result == [1, 2, 3]

    def test_select_seasons_with_three_seasons_distributed_strategy(self) -> None:
        """Three seasons with DISTRIBUTED: first=1, middle=2, last=3 (deduped)."""
        result = select_seasons_to_check([1, 2, 3], SamplingStrategy.DISTRIBUTED)
        # first=1, middle=2, last=3 -> {1, 2, 3} -> [1, 2, 3]
        assert result == [1, 2, 3]


class TestCheckMovieByNameRadarrNotConfigured:
    """Tests for check_movie_by_name when Radarr is not configured (L371)."""

    @pytest.mark.asyncio
    async def test_check_movie_by_name_radarr_not_configured(self) -> None:
        """Should raise ValueError when Radarr not configured for check_movie_by_name."""
        # Create checker with only Sonarr configured (no Radarr)
        checker = ReleaseChecker(sonarr_url="http://127.0.0.1:8989", sonarr_api_key="test")

        with pytest.raises(ValueError, match="Radarr is not configured"):
            await checker.check_movie_by_name("The Matrix")

    @pytest.mark.asyncio
    async def test_check_movie_by_name_no_config_at_all(self) -> None:
        """Should raise ValueError when no config at all for check_movie_by_name."""
        checker = ReleaseChecker()  # No configuration

        with pytest.raises(ValueError, match="Radarr is not configured"):
            await checker.check_movie_by_name("Inception")


class TestCheckSeriesEmptySeasonEpisodes:
    """Tests for check_series when a season has no episodes (L530 continue path).

    This tests the edge case where episodes_by_season.get(season_number, [])
    returns an empty list, triggering the continue statement.
    """

    @respx.mock
    @pytest.mark.asyncio
    async def test_check_series_season_in_selection_but_no_episodes(self) -> None:
        """Season is selected but has no episodes (edge case L530).

        This can occur when:
        1. The select_seasons_to_check function returns a season number
        2. But that season number is not in episodes_by_season dict

        We simulate this by having aired episodes that create certain seasons
        in the dict, but the strategy selects additional seasons not present.
        """
        # This is a bit contrived but tests the defensive code path.
        # In practice, this would require a bug or race condition,
        # but the code handles it gracefully.

        respx.get("http://127.0.0.1:8989/api/v3/series/123").mock(
            return_value=Response(
                200, json={"id": 123, "title": "Test Series", "year": 2020, "seasons": []}
            )
        )
        # Only have episodes for season 1, but none for season 2 or 3
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
        # Mock release for season 1
        respx.get("http://127.0.0.1:8989/api/v3/release", params={"episodeId": "101"}).mock(
            return_value=Response(
                200,
                json=[
                    {
                        "guid": "rel-101",
                        "title": "Show.S01.1080p",
                        "indexer": "Test",
                        "size": 1000,
                        "quality": {"quality": {"id": 7, "name": "WEBDL-1080p"}},
                    }
                ],
            )
        )

        checker = ReleaseChecker(sonarr_url="http://127.0.0.1:8989", sonarr_api_key="test")
        # Using RECENT strategy with only 1 season available
        result = await checker.check_series(
            123, strategy=SamplingStrategy.RECENT, seasons_to_check=3, apply_tags=False
        )

        # Should complete without error, checking only season 1
        assert result.has_match is False
        assert result.seasons_checked == [1]
        assert 101 in result.episodes_checked


class TestCheckSeriesByNameSonarrNotConfigured:
    """Tests for check_series_by_name when Sonarr is not configured (L620)."""

    @pytest.mark.asyncio
    async def test_check_series_by_name_sonarr_not_configured(self) -> None:
        """Should raise ValueError when Sonarr not configured for check_series_by_name."""
        # Create checker with only Radarr configured (no Sonarr)
        checker = ReleaseChecker(radarr_url="http://localhost:7878", radarr_api_key="test")

        with pytest.raises(ValueError, match="Sonarr is not configured"):
            await checker.check_series_by_name("Breaking Bad")

    @pytest.mark.asyncio
    async def test_check_series_by_name_no_config_at_all(self) -> None:
        """Should raise ValueError when no config at all for check_series_by_name."""
        checker = ReleaseChecker()  # No configuration

        with pytest.raises(ValueError, match="Sonarr is not configured"):
            await checker.check_series_by_name("The Wire")


class TestCheckSeriesByNameMovieOnlyCriteria:
    """Tests for check_series_by_name with movie-only criteria (L624)."""

    @pytest.mark.asyncio
    async def test_check_series_by_name_directors_cut_criteria_raises(self) -> None:
        """DIRECTORS_CUT criteria should raise ValueError for series by name."""
        checker = ReleaseChecker(sonarr_url="http://127.0.0.1:8989", sonarr_api_key="test")

        with pytest.raises(ValueError, match="DIRECTORS_CUT criteria is only applicable to movies"):
            await checker.check_series_by_name(
                "Breaking Bad", criteria=SearchCriteria.DIRECTORS_CUT
            )

    @pytest.mark.asyncio
    async def test_check_series_by_name_extended_criteria_raises(self) -> None:
        """EXTENDED criteria should raise ValueError for series by name."""
        checker = ReleaseChecker(sonarr_url="http://127.0.0.1:8989", sonarr_api_key="test")

        with pytest.raises(ValueError, match="EXTENDED criteria is only applicable to movies"):
            await checker.check_series_by_name("Game of Thrones", criteria=SearchCriteria.EXTENDED)

    @pytest.mark.asyncio
    async def test_check_series_by_name_remaster_criteria_raises(self) -> None:
        """REMASTER criteria should raise ValueError for series by name."""
        checker = ReleaseChecker(sonarr_url="http://127.0.0.1:8989", sonarr_api_key="test")

        with pytest.raises(ValueError, match="REMASTER criteria is only applicable to movies"):
            await checker.check_series_by_name("The Sopranos", criteria=SearchCriteria.REMASTER)

    @pytest.mark.asyncio
    async def test_check_series_by_name_imax_criteria_raises(self) -> None:
        """IMAX criteria should raise ValueError for series by name."""
        checker = ReleaseChecker(sonarr_url="http://127.0.0.1:8989", sonarr_api_key="test")

        with pytest.raises(ValueError, match="IMAX criteria is only applicable to movies"):
            await checker.check_series_by_name("Band of Brothers", criteria=SearchCriteria.IMAX)

    @pytest.mark.asyncio
    async def test_check_series_by_name_special_edition_criteria_raises(self) -> None:
        """SPECIAL_EDITION criteria should raise ValueError for series by name."""
        checker = ReleaseChecker(sonarr_url="http://127.0.0.1:8989", sonarr_api_key="test")

        with pytest.raises(
            ValueError, match="SPECIAL_EDITION criteria is only applicable to movies"
        ):
            await checker.check_series_by_name("Lost", criteria=SearchCriteria.SPECIAL_EDITION)

    @respx.mock
    @pytest.mark.asyncio
    async def test_check_series_by_name_valid_criteria_works(self) -> None:
        """Valid criteria (HDR) should work for series by name."""
        respx.get("http://127.0.0.1:8989/api/v3/series").mock(
            return_value=Response(
                200,
                json=[{"id": 123, "title": "Breaking Bad", "year": 2008, "seasons": []}],
            )
        )
        respx.get("http://127.0.0.1:8989/api/v3/series/123").mock(
            return_value=Response(
                200, json={"id": 123, "title": "Breaking Bad", "year": 2008, "seasons": []}
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
                        "airDate": "2008-01-20",
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
                        "title": "Breaking.Bad.S01E01.2160p.HDR",
                        "indexer": "Test",
                        "size": 5000,
                        "quality": {"quality": {"id": 19, "name": "WEBDL-2160p"}},
                    }
                ],
            )
        )

        checker = ReleaseChecker(sonarr_url="http://127.0.0.1:8989", sonarr_api_key="test")
        result = await checker.check_series_by_name(
            "Breaking Bad", criteria=SearchCriteria.HDR, apply_tags=False
        )

        assert result.has_match is True
        assert result.item_name == "Breaking Bad"
