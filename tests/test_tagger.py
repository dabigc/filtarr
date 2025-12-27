"""Tests for ReleaseTagger."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from filtarr.config import TagConfig
from filtarr.criteria import SearchCriteria
from filtarr.models.common import Tag
from filtarr.tagger import ReleaseTagger, TagResult


class MockTaggableClient:
    """Mock implementation of TaggableClient for testing."""

    def __init__(
        self, tags: list[Tag] | None = None, item_tags: dict[int, list[int]] | None = None
    ) -> None:
        self._tags = tags or []
        self._item_tags = item_tags or {}
        self.get_tags = AsyncMock(return_value=self._tags)
        self.create_tag = AsyncMock(side_effect=self._create_tag)
        self.add_tag_to_item = AsyncMock()
        self.remove_tag_from_item = AsyncMock()
        self._next_tag_id = 100

    def _create_tag(self, label: str) -> Tag:
        """Create a new tag with auto-incrementing ID."""
        tag = Tag(id=self._next_tag_id, label=label)
        self._next_tag_id += 1
        self._tags.append(tag)
        return tag

    async def get_movie_raw(self, movie_id: int) -> dict[str, Any]:
        """Get raw movie data including tags."""
        return {"id": movie_id, "tags": self._item_tags.get(movie_id, [])}

    async def get_series_raw(self, series_id: int) -> dict[str, Any]:
        """Get raw series data including tags."""
        return {"id": series_id, "tags": self._item_tags.get(series_id, [])}


class TestTagResult:
    """Tests for TagResult dataclass."""

    def test_default_values(self) -> None:
        """Should have sensible defaults."""
        result = TagResult()
        assert result.tag_applied is None
        assert result.tag_removed is None
        assert result.tag_created is False
        assert result.tag_already_present is False
        assert result.tag_error is None
        assert result.dry_run is False

    def test_with_values(self) -> None:
        """Should accept values correctly."""
        result = TagResult(
            tag_applied="4k-available",
            tag_removed="4k-unavailable",
            tag_created=True,
            tag_already_present=False,
            dry_run=False,
        )
        assert result.tag_applied == "4k-available"
        assert result.tag_removed == "4k-unavailable"
        assert result.tag_created is True
        assert result.tag_already_present is False
        assert result.dry_run is False

    def test_tag_already_present_field(self) -> None:
        """Should track when tag was already present."""
        result = TagResult(
            tag_applied="4k-available",
            tag_already_present=True,
        )
        assert result.tag_applied == "4k-available"
        assert result.tag_already_present is True


class TestReleaseTagger:
    """Tests for ReleaseTagger class."""

    def test_init_with_default_config(self) -> None:
        """Should initialize with default TagConfig."""
        tagger = ReleaseTagger(TagConfig())
        assert tagger._config is not None

    def test_init_with_custom_config(self) -> None:
        """Should initialize with custom TagConfig."""
        config = TagConfig(
            pattern_available="{criteria}-yes",
            pattern_unavailable="{criteria}-no",
        )
        tagger = ReleaseTagger(config)
        assert tagger._config.pattern_available == "{criteria}-yes"
        assert tagger._config.pattern_unavailable == "{criteria}-no"

    def test_clear_tag_cache(self) -> None:
        """Should clear the tag cache."""
        tagger = ReleaseTagger(TagConfig())
        # Simulate cached tags
        tagger._tag_cache = {"radarr": [Tag(id=1, label="test")]}
        tagger.clear_tag_cache()
        assert tagger._tag_cache is None


class TestApplyTags:
    """Tests for apply_tags method."""

    @pytest.mark.asyncio
    async def test_apply_tags_with_match(self) -> None:
        """Should apply available tag when has_match is True."""
        client = MockTaggableClient(
            tags=[
                Tag(id=1, label="4k-available"),
                Tag(id=2, label="4k-unavailable"),
            ]
        )
        tagger = ReleaseTagger(TagConfig())

        result = await tagger.apply_tags(
            client=client,
            item_id=123,
            item_type="movie",
            has_match=True,
            criteria=SearchCriteria.FOUR_K,
        )

        assert result.tag_applied == "4k-available"
        assert result.tag_removed == "4k-unavailable"
        assert result.tag_created is False
        assert result.tag_already_present is False
        assert result.tag_error is None
        client.add_tag_to_item.assert_called_once_with(123, 1)
        client.remove_tag_from_item.assert_called_once_with(123, 2)

    @pytest.mark.asyncio
    async def test_apply_tags_without_match(self) -> None:
        """Should apply unavailable tag when has_match is False."""
        client = MockTaggableClient(
            tags=[
                Tag(id=1, label="4k-available"),
                Tag(id=2, label="4k-unavailable"),
            ]
        )
        tagger = ReleaseTagger(TagConfig())

        result = await tagger.apply_tags(
            client=client,
            item_id=123,
            item_type="movie",
            has_match=False,
            criteria=SearchCriteria.FOUR_K,
        )

        assert result.tag_applied == "4k-unavailable"
        assert result.tag_removed == "4k-available"
        assert result.tag_created is False
        assert result.tag_already_present is False
        client.add_tag_to_item.assert_called_once_with(123, 2)
        client.remove_tag_from_item.assert_called_once_with(123, 1)

    @pytest.mark.asyncio
    async def test_apply_tags_creates_missing_tag(self) -> None:
        """Should create tag if it doesn't exist."""
        client = MockTaggableClient(tags=[])  # No existing tags
        tagger = ReleaseTagger(TagConfig())

        result = await tagger.apply_tags(
            client=client,
            item_id=123,
            item_type="movie",
            has_match=True,
            criteria=SearchCriteria.FOUR_K,
        )

        assert result.tag_applied == "4k-available"
        assert result.tag_created is True
        assert result.tag_already_present is False
        client.create_tag.assert_called_once_with("4k-available")
        client.add_tag_to_item.assert_called_once()

    @pytest.mark.asyncio
    async def test_apply_tags_dry_run(self) -> None:
        """Should not apply tags in dry_run mode."""
        client = MockTaggableClient(
            tags=[
                Tag(id=1, label="4k-available"),
                Tag(id=2, label="4k-unavailable"),
            ]
        )
        tagger = ReleaseTagger(TagConfig())

        result = await tagger.apply_tags(
            client=client,
            item_id=123,
            item_type="movie",
            has_match=True,
            criteria=SearchCriteria.FOUR_K,
            dry_run=True,
        )

        assert result.tag_applied == "4k-available"
        assert result.tag_removed == "4k-unavailable"
        assert result.dry_run is True
        client.add_tag_to_item.assert_not_called()
        client.remove_tag_from_item.assert_not_called()
        client.create_tag.assert_not_called()

    @pytest.mark.asyncio
    async def test_apply_tags_with_different_criteria(self) -> None:
        """Should use correct tag names for different criteria."""
        client = MockTaggableClient(
            tags=[
                Tag(id=1, label="imax-available"),
                Tag(id=2, label="imax-unavailable"),
            ]
        )
        tagger = ReleaseTagger(TagConfig())

        result = await tagger.apply_tags(
            client=client,
            item_id=123,
            item_type="movie",
            has_match=True,
            criteria=SearchCriteria.IMAX,
        )

        assert result.tag_applied == "imax-available"
        client.add_tag_to_item.assert_called_once_with(123, 1)

    @pytest.mark.asyncio
    async def test_apply_tags_with_custom_pattern(self) -> None:
        """Should use custom tag pattern from config."""
        config = TagConfig(
            pattern_available="has-{criteria}",
            pattern_unavailable="no-{criteria}",
        )
        client = MockTaggableClient(
            tags=[
                Tag(id=1, label="has-4k"),
            ]
        )
        tagger = ReleaseTagger(config)

        result = await tagger.apply_tags(
            client=client,
            item_id=123,
            item_type="movie",
            has_match=True,
            criteria=SearchCriteria.FOUR_K,
        )

        assert result.tag_applied == "has-4k"
        client.add_tag_to_item.assert_called_once_with(123, 1)

    @pytest.mark.asyncio
    async def test_apply_tags_case_insensitive_matching(self) -> None:
        """Should match tags case-insensitively."""
        client = MockTaggableClient(
            tags=[
                Tag(id=1, label="4K-Available"),  # Different case
            ]
        )
        tagger = ReleaseTagger(TagConfig())

        result = await tagger.apply_tags(
            client=client,
            item_id=123,
            item_type="movie",
            has_match=True,
            criteria=SearchCriteria.FOUR_K,
        )

        assert result.tag_applied == "4k-available"
        assert result.tag_created is False  # Should not create, just use existing
        client.add_tag_to_item.assert_called_once_with(123, 1)

    @pytest.mark.asyncio
    async def test_apply_tags_no_opposite_tag_to_remove(self) -> None:
        """Should handle case when opposite tag doesn't exist."""
        client = MockTaggableClient(
            tags=[
                Tag(id=1, label="4k-available"),
                # 4k-unavailable doesn't exist
            ]
        )
        tagger = ReleaseTagger(TagConfig())

        result = await tagger.apply_tags(
            client=client,
            item_id=123,
            item_type="movie",
            has_match=True,
            criteria=SearchCriteria.FOUR_K,
        )

        assert result.tag_applied == "4k-available"
        assert result.tag_removed is None  # No opposite tag to remove
        client.remove_tag_from_item.assert_not_called()

    @pytest.mark.asyncio
    async def test_apply_tags_uses_cache(self) -> None:
        """Should cache tags and not refetch on subsequent calls."""
        client = MockTaggableClient(
            tags=[
                Tag(id=1, label="4k-available"),
                Tag(id=2, label="4k-unavailable"),
            ]
        )
        tagger = ReleaseTagger(TagConfig())

        # First call
        await tagger.apply_tags(
            client=client,
            item_id=123,
            item_type="movie",
            has_match=True,
            criteria=SearchCriteria.FOUR_K,
        )

        # Second call
        await tagger.apply_tags(
            client=client,
            item_id=456,
            item_type="movie",
            has_match=True,
            criteria=SearchCriteria.FOUR_K,
        )

        # get_tags should only be called once due to caching
        assert client.get_tags.call_count == 1

    @pytest.mark.asyncio
    async def test_apply_tags_tag_already_present_on_item(self) -> None:
        """Should detect when tag is already present on item."""
        # Create client where movie 123 already has tag 1
        client = MockTaggableClient(
            tags=[
                Tag(id=1, label="4k-available"),
                Tag(id=2, label="4k-unavailable"),
            ],
            item_tags={123: [1]},  # Movie 123 already has tag 1
        )
        tagger = ReleaseTagger(TagConfig())

        result = await tagger.apply_tags(
            client=client,
            item_id=123,
            item_type="movie",
            has_match=True,
            criteria=SearchCriteria.FOUR_K,
        )

        assert result.tag_applied == "4k-available"
        assert result.tag_already_present is True
        # Should NOT call add_tag_to_item since tag is already present
        client.add_tag_to_item.assert_not_called()
        # Should still remove the opposite tag if present
        client.remove_tag_from_item.assert_called_once_with(123, 2)

    @pytest.mark.asyncio
    async def test_apply_tags_series_tag_already_present(self) -> None:
        """Should detect when tag is already present on series."""
        # Create client where series 456 already has tag 1
        client = MockTaggableClient(
            tags=[
                Tag(id=1, label="4k-available"),
            ],
            item_tags={456: [1]},  # Series 456 already has tag 1
        )
        tagger = ReleaseTagger(TagConfig())

        result = await tagger.apply_tags(
            client=client,
            item_id=456,
            item_type="series",
            has_match=True,
            criteria=SearchCriteria.FOUR_K,
        )

        assert result.tag_applied == "4k-available"
        assert result.tag_already_present is True
        client.add_tag_to_item.assert_not_called()


class TestApplyTagsErrorHandling:
    """Tests for error handling in apply_tags."""

    @pytest.mark.asyncio
    async def test_http_error_handling(self) -> None:
        """Should handle HTTP errors gracefully."""
        client = MockTaggableClient(
            tags=[
                Tag(id=1, label="4k-available"),
            ]
        )
        # Make add_tag_to_item raise an HTTP error
        response = MagicMock()
        response.status_code = 500
        response.reason_phrase = "Internal Server Error"
        client.add_tag_to_item.side_effect = httpx.HTTPStatusError(
            "Server error", request=MagicMock(), response=response
        )
        tagger = ReleaseTagger(TagConfig())

        result = await tagger.apply_tags(
            client=client,
            item_id=123,
            item_type="movie",
            has_match=True,
            criteria=SearchCriteria.FOUR_K,
        )

        assert result.tag_error is not None
        assert "HTTP 500" in result.tag_error

    @pytest.mark.asyncio
    async def test_network_error_handling(self) -> None:
        """Should handle network errors gracefully."""
        client = MockTaggableClient(
            tags=[
                Tag(id=1, label="4k-available"),
            ]
        )
        client.add_tag_to_item.side_effect = httpx.ConnectError("Connection failed")
        tagger = ReleaseTagger(TagConfig())

        result = await tagger.apply_tags(
            client=client,
            item_id=123,
            item_type="movie",
            has_match=True,
            criteria=SearchCriteria.FOUR_K,
        )

        assert result.tag_error is not None
        assert "Network error" in result.tag_error

    @pytest.mark.asyncio
    async def test_timeout_error_handling(self) -> None:
        """Should handle timeout errors gracefully."""
        client = MockTaggableClient(
            tags=[
                Tag(id=1, label="4k-available"),
            ]
        )
        client.add_tag_to_item.side_effect = httpx.TimeoutException("Request timed out")
        tagger = ReleaseTagger(TagConfig())

        result = await tagger.apply_tags(
            client=client,
            item_id=123,
            item_type="movie",
            has_match=True,
            criteria=SearchCriteria.FOUR_K,
        )

        assert result.tag_error is not None
        assert "Network error" in result.tag_error


class TestApplyMovieTags:
    """Tests for apply_movie_tags convenience method."""

    @pytest.mark.asyncio
    async def test_apply_movie_tags(self) -> None:
        """Should delegate to apply_tags with movie item_type."""
        client = MockTaggableClient(
            tags=[
                Tag(id=1, label="4k-available"),
            ]
        )
        tagger = ReleaseTagger(TagConfig())

        result = await tagger.apply_movie_tags(
            client=client,
            movie_id=123,
            has_match=True,
            criteria=SearchCriteria.FOUR_K,
        )

        assert result.tag_applied == "4k-available"
        client.add_tag_to_item.assert_called_once_with(123, 1)


class TestApplySeriesTags:
    """Tests for apply_series_tags convenience method."""

    @pytest.mark.asyncio
    async def test_apply_series_tags(self) -> None:
        """Should delegate to apply_tags with series item_type."""
        client = MockTaggableClient(
            tags=[
                Tag(id=1, label="hdr-available"),
            ]
        )
        tagger = ReleaseTagger(TagConfig())

        result = await tagger.apply_series_tags(
            client=client,
            series_id=456,
            has_match=True,
            criteria=SearchCriteria.HDR,
        )

        assert result.tag_applied == "hdr-available"
        client.add_tag_to_item.assert_called_once_with(456, 1)


class TestTagCacheIsolation:
    """Tests for tag cache isolation between radarr and sonarr."""

    @pytest.mark.asyncio
    async def test_cache_isolation_movie_and_series(self) -> None:
        """Should maintain separate caches for movies and series."""
        # Separate clients for radarr and sonarr
        radarr_client = MockTaggableClient(
            tags=[
                Tag(id=1, label="4k-available"),
            ]
        )
        sonarr_client = MockTaggableClient(
            tags=[
                Tag(id=10, label="4k-available"),
            ]
        )
        tagger = ReleaseTagger(TagConfig())

        # Apply tags for movie
        await tagger.apply_movie_tags(
            client=radarr_client,
            movie_id=123,
            has_match=True,
        )

        # Apply tags for series (should fetch tags separately)
        await tagger.apply_series_tags(
            client=sonarr_client,
            series_id=456,
            has_match=True,
        )

        # Both clients should have had get_tags called
        radarr_client.get_tags.assert_called_once()
        sonarr_client.get_tags.assert_called_once()

        # Verify correct tag IDs were used
        radarr_client.add_tag_to_item.assert_called_once_with(123, 1)
        sonarr_client.add_tag_to_item.assert_called_once_with(456, 10)
