"""Extended tests for common models edge cases."""

from filtarr.criteria import SearchCriteria
from filtarr.models.common import Quality, Release


class TestQualityMatchesResolution:
    """Tests for Quality.matches_resolution() method."""

    def test_matches_resolution_2160p(self) -> None:
        """Should match 2160p resolution."""
        quality = Quality(id=19, name="Bluray-2160p")
        assert quality.matches_resolution("2160p") is True

    def test_matches_resolution_1080p(self) -> None:
        """Should match 1080p resolution."""
        quality = Quality(id=7, name="Bluray-1080p")
        assert quality.matches_resolution("1080p") is True

    def test_matches_resolution_720p(self) -> None:
        """Should match 720p resolution."""
        quality = Quality(id=5, name="HDTV-720p")
        assert quality.matches_resolution("720p") is True

    def test_matches_resolution_480p(self) -> None:
        """Should match 480p resolution."""
        quality = Quality(id=2, name="DVD-480p")
        assert quality.matches_resolution("480p") is True

    def test_matches_resolution_case_insensitive(self) -> None:
        """Should match resolution case-insensitively."""
        quality = Quality(id=19, name="BLURAY-2160P")

        assert quality.matches_resolution("2160p") is True
        assert quality.matches_resolution("2160P") is True

    def test_matches_resolution_with_uppercase_quality_name(self) -> None:
        """Should match when quality name is uppercase."""
        quality = Quality(id=7, name="WEBDL-1080P")

        assert quality.matches_resolution("1080p") is True
        assert quality.matches_resolution("1080P") is True

    def test_matches_resolution_no_match(self) -> None:
        """Should return False when resolution doesn't match."""
        quality = Quality(id=7, name="Bluray-1080p")

        assert quality.matches_resolution("2160p") is False
        assert quality.matches_resolution("720p") is False
        assert quality.matches_resolution("4k") is False

    def test_matches_resolution_partial_match(self) -> None:
        """Should match partial resolution strings."""
        quality = Quality(id=19, name="Bluray-2160p HDR")

        assert quality.matches_resolution("2160p") is True
        assert quality.matches_resolution("hdr") is True

    def test_matches_resolution_empty_quality_name(self) -> None:
        """Should return False for empty quality name."""
        quality = Quality(id=0, name="")

        assert quality.matches_resolution("2160p") is False
        assert quality.matches_resolution("1080p") is False

    def test_matches_resolution_unknown_quality(self) -> None:
        """Should return False for unknown quality."""
        quality = Quality(id=0, name="Unknown")

        assert quality.matches_resolution("2160p") is False


class TestReleaseMatchesCriteriaWithSearchCriteria:
    """Tests for Release.matches_criteria() with SearchCriteria enum."""

    def test_matches_criteria_four_k(self) -> None:
        """Should match FOUR_K criteria for 4K releases."""
        release = Release(
            guid="test",
            title="Movie.2024.2160p.WEB-DL",
            indexer="Test",
            size=5000,
            quality=Quality(id=19, name="WEBDL-2160p"),
        )

        assert release.matches_criteria(SearchCriteria.FOUR_K) is True

    def test_matches_criteria_four_k_no_match(self) -> None:
        """Should not match FOUR_K criteria for non-4K releases."""
        release = Release(
            guid="test",
            title="Movie.2024.1080p.WEB-DL",
            indexer="Test",
            size=2000,
            quality=Quality(id=7, name="WEBDL-1080p"),
        )

        assert release.matches_criteria(SearchCriteria.FOUR_K) is False

    def test_matches_criteria_hdr(self) -> None:
        """Should match HDR criteria for HDR releases."""
        release = Release(
            guid="test",
            title="Movie.2024.2160p.HDR.WEB-DL",
            indexer="Test",
            size=5000,
            quality=Quality(id=19, name="WEBDL-2160p"),
        )

        assert release.matches_criteria(SearchCriteria.HDR) is True

    def test_matches_criteria_hdr_no_match(self) -> None:
        """Should not match HDR criteria for non-HDR releases."""
        release = Release(
            guid="test",
            title="Movie.2024.2160p.WEB-DL",
            indexer="Test",
            size=5000,
            quality=Quality(id=19, name="WEBDL-2160p"),
        )

        assert release.matches_criteria(SearchCriteria.HDR) is False

    def test_matches_criteria_dolby_vision(self) -> None:
        """Should match DOLBY_VISION criteria for DV releases."""
        release = Release(
            guid="test",
            title="Movie.2024.2160p.DV.WEB-DL",
            indexer="Test",
            size=5000,
            quality=Quality(id=19, name="WEBDL-2160p"),
        )

        assert release.matches_criteria(SearchCriteria.DOLBY_VISION) is True

    def test_matches_criteria_directors_cut(self) -> None:
        """Should match DIRECTORS_CUT criteria for director's cut releases."""
        release = Release(
            guid="test",
            title="Movie.2024.Directors.Cut.1080p.BluRay",
            indexer="Test",
            size=5000,
            quality=Quality(id=7, name="Bluray-1080p"),
        )

        assert release.matches_criteria(SearchCriteria.DIRECTORS_CUT) is True

    def test_matches_criteria_extended(self) -> None:
        """Should match EXTENDED criteria for extended releases."""
        release = Release(
            guid="test",
            title="Movie.2024.Extended.Edition.1080p.BluRay",
            indexer="Test",
            size=5000,
            quality=Quality(id=7, name="Bluray-1080p"),
        )

        assert release.matches_criteria(SearchCriteria.EXTENDED) is True

    def test_matches_criteria_remaster(self) -> None:
        """Should match REMASTER criteria for remastered releases."""
        release = Release(
            guid="test",
            title="Movie.1990.Remastered.1080p.BluRay",
            indexer="Test",
            size=5000,
            quality=Quality(id=7, name="Bluray-1080p"),
        )

        assert release.matches_criteria(SearchCriteria.REMASTER) is True

    def test_matches_criteria_imax(self) -> None:
        """Should match IMAX criteria for IMAX releases."""
        release = Release(
            guid="test",
            title="Movie.2024.IMAX.1080p.BluRay",
            indexer="Test",
            size=5000,
            quality=Quality(id=7, name="Bluray-1080p"),
        )

        assert release.matches_criteria(SearchCriteria.IMAX) is True

    def test_matches_criteria_special_edition(self) -> None:
        """Should match SPECIAL_EDITION criteria for special edition releases."""
        release = Release(
            guid="test",
            title="Movie.2024.Special.Edition.1080p.BluRay",
            indexer="Test",
            size=5000,
            quality=Quality(id=7, name="Bluray-1080p"),
        )

        assert release.matches_criteria(SearchCriteria.SPECIAL_EDITION) is True


class TestReleaseMatchesCriteriaWithCallable:
    """Tests for Release.matches_criteria() with custom callable."""

    def test_matches_criteria_with_simple_callable(self) -> None:
        """Should work with simple callable that returns True."""
        release = Release(
            guid="test",
            title="Movie.2024.1080p.WEB-DL",
            indexer="Test",
            size=5000,
            quality=Quality(id=7, name="WEBDL-1080p"),
        )

        # Simple callable that always returns True
        matcher = lambda _: True  # noqa: E731
        assert release.matches_criteria(matcher) is True

    def test_matches_criteria_with_callable_false(self) -> None:
        """Should work with callable that returns False."""
        release = Release(
            guid="test",
            title="Movie.2024.1080p.WEB-DL",
            indexer="Test",
            size=5000,
            quality=Quality(id=7, name="WEBDL-1080p"),
        )

        # Callable that always returns False
        matcher = lambda _: False  # noqa: E731
        assert release.matches_criteria(matcher) is False

    def test_matches_criteria_with_title_check_callable(self) -> None:
        """Should work with callable that checks title."""
        release = Release(
            guid="test",
            title="Movie.2024.REMUX.1080p.BluRay",
            indexer="Test",
            size=50000,
            quality=Quality(id=7, name="Bluray-1080p"),
        )

        # Custom callable to match REMUX
        def match_remux(r: Release) -> bool:
            return "remux" in r.title.lower()

        assert release.matches_criteria(match_remux) is True

    def test_matches_criteria_with_size_check_callable(self) -> None:
        """Should work with callable that checks file size."""
        small_release = Release(
            guid="small",
            title="Movie.2024.1080p.WEB-DL",
            indexer="Test",
            size=1_000_000_000,  # 1 GB
            quality=Quality(id=7, name="WEBDL-1080p"),
        )

        large_release = Release(
            guid="large",
            title="Movie.2024.1080p.BluRay",
            indexer="Test",
            size=50_000_000_000,  # 50 GB
            quality=Quality(id=7, name="Bluray-1080p"),
        )

        # Custom callable to match large files (> 10 GB)
        def match_large_file(r: Release) -> bool:
            return r.size > 10_000_000_000

        assert small_release.matches_criteria(match_large_file) is False
        assert large_release.matches_criteria(match_large_file) is True

    def test_matches_criteria_with_indexer_check_callable(self) -> None:
        """Should work with callable that checks indexer."""
        release = Release(
            guid="test",
            title="Movie.2024.1080p.WEB-DL",
            indexer="PreferredIndexer",
            size=5000,
            quality=Quality(id=7, name="WEBDL-1080p"),
        )

        # Custom callable to match preferred indexer
        def match_indexer(r: Release) -> bool:
            return r.indexer == "PreferredIndexer"

        assert release.matches_criteria(match_indexer) is True

    def test_matches_criteria_with_complex_callable(self) -> None:
        """Should work with complex callable checking multiple conditions."""
        release = Release(
            guid="test",
            title="Movie.2024.2160p.HDR.REMUX.BluRay",
            indexer="QualityIndexer",
            size=60_000_000_000,  # 60 GB
            quality=Quality(id=19, name="Bluray-2160p"),
        )

        # Complex callable: 4K + HDR + large file
        def match_high_quality(r: Release) -> bool:
            is_4k = r.is_4k()
            has_hdr = "hdr" in r.title.lower()
            is_large = r.size > 40_000_000_000
            return is_4k and has_hdr and is_large

        assert release.matches_criteria(match_high_quality) is True

    def test_matches_criteria_with_callable_accessing_quality(self) -> None:
        """Should work with callable that accesses quality attributes."""
        release = Release(
            guid="test",
            title="Movie.2024.2160p.WEB-DL",
            indexer="Test",
            size=5000,
            quality=Quality(id=19, name="WEBDL-2160p"),
        )

        # Callable that checks quality ID
        def match_quality_id(r: Release) -> bool:
            return r.quality.id >= 15

        assert release.matches_criteria(match_quality_id) is True


class TestQualityIs4k:
    """Additional tests for Quality.is_4k() method."""

    def test_is_4k_with_4k_in_name(self) -> None:
        """Should detect 4K in quality name."""
        quality = Quality(id=19, name="WEBDL-4K")
        assert quality.is_4k() is True

    def test_is_4k_with_2160p_in_name(self) -> None:
        """Should detect 2160p in quality name."""
        quality = Quality(id=19, name="Bluray-2160p")
        assert quality.is_4k() is True

    def test_is_4k_case_insensitive(self) -> None:
        """Should detect 4K case-insensitively."""
        test_cases = [
            ("WEBDL-4K", True),
            ("webdl-4k", True),
            ("BLURAY-2160P", True),
            ("bluray-2160p", True),
        ]

        for name, expected in test_cases:
            quality = Quality(id=19, name=name)
            assert quality.is_4k() is expected, f"Failed for {name}"

    def test_is_not_4k_1080p(self) -> None:
        """Should return False for 1080p quality."""
        quality = Quality(id=7, name="Bluray-1080p")
        assert quality.is_4k() is False

    def test_is_not_4k_720p(self) -> None:
        """Should return False for 720p quality."""
        quality = Quality(id=5, name="HDTV-720p")
        assert quality.is_4k() is False


class TestReleaseIs4k:
    """Additional tests for Release.is_4k() method."""

    def test_is_4k_from_quality(self) -> None:
        """Should be 4K if quality indicates 4K."""
        release = Release(
            guid="test",
            title="Movie.2024.WEB-DL",  # Title doesn't indicate 4K
            indexer="Test",
            size=5000,
            quality=Quality(id=19, name="WEBDL-2160p"),
        )

        assert release.is_4k() is True

    def test_is_4k_from_title_2160p(self) -> None:
        """Should be 4K if title contains 2160p."""
        release = Release(
            guid="test",
            title="Movie.2024.2160p.WEB-DL",
            indexer="Test",
            size=5000,
            quality=Quality(id=0, name="Unknown"),
        )

        assert release.is_4k() is True

    def test_is_4k_from_title_4k(self) -> None:
        """Should be 4K if title contains 4K."""
        release = Release(
            guid="test",
            title="Movie.2024.4K.WEB-DL",
            indexer="Test",
            size=5000,
            quality=Quality(id=0, name="Unknown"),
        )

        assert release.is_4k() is True

    def test_is_4k_case_insensitive_title(self) -> None:
        """Should detect 4K in title case-insensitively."""
        release = Release(
            guid="test",
            title="Movie.2024.4k.web-dl",
            indexer="Test",
            size=5000,
            quality=Quality(id=0, name="Unknown"),
        )

        assert release.is_4k() is True

    def test_is_not_4k(self) -> None:
        """Should return False when neither quality nor title indicate 4K."""
        release = Release(
            guid="test",
            title="Movie.2024.1080p.WEB-DL",
            indexer="Test",
            size=5000,
            quality=Quality(id=7, name="WEBDL-1080p"),
        )

        assert release.is_4k() is False
