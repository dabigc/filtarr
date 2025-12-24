"""Pytest configuration and fixtures."""

import pytest

from filtarr.models.common import Quality, Release


@pytest.fixture
def sample_4k_release() -> Release:
    """A sample 4K release."""
    return Release(
        guid="abc123",
        title="Movie.Name.2024.2160p.UHD.BluRay.x265-GROUP",
        indexer="TestIndexer",
        size=50_000_000_000,
        quality=Quality(id=19, name="Bluray-2160p"),
    )


@pytest.fixture
def sample_1080p_release() -> Release:
    """A sample 1080p release."""
    return Release(
        guid="def456",
        title="Movie.Name.2024.1080p.BluRay.x264-GROUP",
        indexer="TestIndexer",
        size=15_000_000_000,
        quality=Quality(id=7, name="Bluray-1080p"),
    )


@pytest.fixture
def sample_radarr_response() -> list[dict]:
    """Sample Radarr API response for releases."""
    return [
        {
            "guid": "abc123",
            "title": "Movie.Name.2024.2160p.UHD.BluRay.x265-GROUP",
            "indexer": "TestIndexer",
            "size": 50_000_000_000,
            "quality": {"quality": {"id": 19, "name": "Bluray-2160p"}},
        },
        {
            "guid": "def456",
            "title": "Movie.Name.2024.1080p.BluRay.x264-GROUP",
            "indexer": "TestIndexer",
            "size": 15_000_000_000,
            "quality": {"quality": {"id": 7, "name": "Bluray-1080p"}},
        },
    ]
