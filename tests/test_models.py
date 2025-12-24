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
        """Release should not be 4K if quality and title are not 4K."""
        assert sample_1080p_release.is_4k() is False

    def test_is_4k_from_title_only(self) -> None:
        """Release should be 4K if title contains 2160p even with wrong quality."""
        release = Release(
            guid="test",
            title="Movie.2024.2160p.WEB-DL",
            indexer="Test",
            size=1000,
            quality=Quality(id=0, name="Unknown"),
        )
        assert release.is_4k() is True
