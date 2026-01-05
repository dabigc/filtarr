"""Tests for data models."""

from filtarr.models.common import Quality, Release


class TestQuality:
    """Tests for Quality model."""

    def test_is_4k_with_2160p(self) -> None:
        """Quality with 2160p in name should be detected as 4K."""
        quality = Quality(id=19, name="Bluray-2160p")
        assert quality.is_4k() is True

    def test_is_4k_with_4k_label(self) -> None:
        """Quality with 4K in name should be detected as 4K."""
        quality = Quality(id=19, name="WEBDL-4K")
        assert quality.is_4k() is True

    def test_is_not_4k_with_1080p(self) -> None:
        """Quality with 1080p should not be detected as 4K."""
        quality = Quality(id=7, name="Bluray-1080p")
        assert quality.is_4k() is False


class TestRelease:
    """Tests for Release model."""

    def test_is_4k_from_quality(self, sample_4k_release: Release) -> None:
        """Release should be 4K if quality is 4K."""
        assert sample_4k_release.is_4k() is True

    def test_is_not_4k(self, sample_1080p_release: Release) -> None:
        """Release should not be 4K if quality is not 4K."""
        assert sample_1080p_release.is_4k() is False

    def test_is_4k_relies_on_quality_not_title(self) -> None:
        """Release 4K detection should rely on Quality, not title parsing.

        This test ensures we trust Radarr/Sonarr's quality parsing rather than
        doing our own naive title matching which can cause false positives.
        """
        # Quality says 4K -> is 4K (regardless of title)
        release_quality_4k = Release(
            guid="test1",
            title="Movie.2024.1080p.WEB-DL",  # Title says 1080p
            indexer="Test",
            size=1000,
            quality=Quality(id=19, name="Bluray-2160p"),  # Quality says 4K
        )
        assert release_quality_4k.is_4k() is True

        # Quality says 1080p -> NOT 4K (even if title has 2160p)
        release_quality_1080p = Release(
            guid="test2",
            title="Movie.2024.2160p.WEB-DL",  # Title says 2160p
            indexer="Test",
            size=1000,
            quality=Quality(id=7, name="Bluray-1080p"),  # Quality says 1080p
        )
        assert release_quality_1080p.is_4k() is False

    def test_is_4k_false_positive_release_group_4k4u(self) -> None:
        """Release group names containing '4K' should NOT trigger 4K detection.

        This is a regression test for the bug where releases from the '4K4U'
        release group were incorrectly marked as 4K content.
        """
        release = Release(
            guid="test",
            title="A.Beautiful.Mind.2001.Bluray.1080p.DTS-HD.MA.5.1-4K4U",
            indexer="TestIndexer",
            size=44_000_000_000,
            quality=Quality(id=7, name="Bluray-1080p"),
        )
        assert release.is_4k() is False

    def test_is_4k_false_positive_release_group_4k77(self) -> None:
        """Other release groups with '4K' in name should not trigger detection.

        4K77 is another release group known for Star Wars preservations.
        """
        release = Release(
            guid="test",
            title="Star.Wars.1977.Despecialized.1080p.x264-4K77",
            indexer="TestIndexer",
            size=20_000_000_000,
            quality=Quality(id=7, name="Bluray-1080p"),
        )
        assert release.is_4k() is False
