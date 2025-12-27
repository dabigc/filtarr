"""Tag operations for movies and series.

This module provides the ReleaseTagger class that handles all tag operations
for both movies and series. It separates tagging concerns from release checking,
allowing for better modularity and testing.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal, cast

import httpx
from pydantic import ValidationError

from filtarr.criteria import SearchCriteria

if TYPE_CHECKING:
    from filtarr.clients.base import TaggableClient
    from filtarr.config import TagConfig
    from filtarr.models.common import Tag

logger = logging.getLogger(__name__)


@dataclass
class TagResult:
    """Result of a tag operation."""

    tag_applied: str | None = None
    tag_removed: str | None = None
    tag_created: bool = False
    tag_already_present: bool = False
    tag_error: str | None = None
    dry_run: bool = False


class ReleaseTagger:
    """Handles tag operations for movies and series.

    This class encapsulates all tag-related operations, including:
    - Applying tags based on release availability
    - Creating tags if they don't exist
    - Removing opposite tags when availability changes
    - Caching tags to minimize API calls

    Usage:
        tagger = ReleaseTagger(tag_config)
        result = await tagger.apply_tags(
            client=radarr_client,
            item_id=123,
            item_type="movie",
            has_match=True,
            criteria=SearchCriteria.FOUR_K,
        )
    """

    def __init__(self, config: TagConfig) -> None:
        """Initialize the release tagger.

        Args:
            config: Configuration for tagging behavior
        """
        self._config = config
        self._tag_cache: dict[str, list[Tag]] | None = None
        self._tag_cache_lock = asyncio.Lock()

    async def _get_cached_tags(self, client: TaggableClient, cache_key: str) -> list[Tag]:
        """Get tags from cache or fetch from client.

        Tags are cached per client type (radarr/sonarr) to avoid repeated
        API calls when processing batches of items.

        Uses a lock to prevent race conditions when multiple concurrent
        calls check the cache simultaneously.

        Args:
            client: A client implementing the TaggableClient protocol
            cache_key: Key for caching ("radarr" or "sonarr")

        Returns:
            List of Tag models
        """
        async with self._tag_cache_lock:
            if self._tag_cache is None:
                self._tag_cache = {}
            if cache_key not in self._tag_cache:
                self._tag_cache[cache_key] = await client.get_tags()
            return self._tag_cache[cache_key]

    def clear_tag_cache(self) -> None:
        """Clear the tag cache.

        Call this method when you need to refresh tag data, for example
        after creating new tags or if tags may have been modified externally.
        """
        self._tag_cache = None

    async def _get_item_tag_ids(
        self, client: Any, item_id: int, item_type: Literal["movie", "series"]
    ) -> list[int]:
        """Get the current tag IDs for an item.

        Args:
            client: A client that may have get_movie_raw or get_series_raw methods
            item_id: The item ID
            item_type: Type of item ("movie" or "series")

        Returns:
            List of tag IDs currently on the item
        """
        # Use duck typing to get raw item data
        # Works with RadarrClient, SonarrClient, and mock clients
        if item_type == "movie" and hasattr(client, "get_movie_raw"):
            item_data = await client.get_movie_raw(item_id)
            tags = item_data.get("tags", [])
            return cast("list[int]", tags)
        elif item_type == "series" and hasattr(client, "get_series_raw"):
            item_data = await client.get_series_raw(item_id)
            tags = item_data.get("tags", [])
            return cast("list[int]", tags)
        return []

    async def apply_tags(
        self,
        client: TaggableClient,
        item_id: int,
        item_type: Literal["movie", "series"],
        has_match: bool,
        criteria: SearchCriteria = SearchCriteria.FOUR_K,
        dry_run: bool = False,
    ) -> TagResult:
        """Apply appropriate tags to an item based on release availability.

        This method handles tag application for both movies and series
        using the TaggableClient protocol.

        Args:
            client: A client implementing the TaggableClient protocol
            item_id: The item ID to tag (movie or series)
            item_type: Type of item ("movie" or "series") for logging/caching
            has_match: Whether the item has matching releases available
            criteria: The search criteria used (determines tag names)
            dry_run: If True, don't actually apply tags

        Returns:
            TagResult with the operation details
        """
        available_tag, unavailable_tag = self._config.get_tag_names(criteria.value)
        tag_to_apply = available_tag if has_match else unavailable_tag
        tag_to_remove = unavailable_tag if has_match else available_tag

        # Cache key based on item type (radarr for movies, sonarr for series)
        cache_key = "radarr" if item_type == "movie" else "sonarr"

        result = TagResult(dry_run=dry_run)

        try:
            if dry_run:
                # Just report what would happen
                result.tag_applied = tag_to_apply
                result.tag_removed = tag_to_remove
                return result

            # Get existing tags from cache (or fetch once per batch)
            tags = await self._get_cached_tags(client, cache_key)
            existing_labels = {t.label.lower(): t for t in tags}

            # Check if tag already exists before creating
            tag_already_exists = tag_to_apply.lower() in existing_labels

            if tag_already_exists:
                tag = existing_labels[tag_to_apply.lower()]
            else:
                # Create the tag since it doesn't exist
                tag = await client.create_tag(tag_to_apply)
                result.tag_created = True
                # Update cache with the new tag
                if self._tag_cache is not None and cache_key in self._tag_cache:
                    self._tag_cache[cache_key].append(tag)

            result.tag_applied = tag_to_apply

            # Check if the item already has this tag
            # Skip redundant API call if we just created the tag - the item can't possibly have it
            if result.tag_created:
                # Tag was just created, so item definitely doesn't have it yet
                await client.add_tag_to_item(item_id, tag.id)
            else:
                # Tag already existed, check if item has it
                item_tag_ids = await self._get_item_tag_ids(client, item_id, item_type)
                if tag.id in item_tag_ids:
                    result.tag_already_present = True
                else:
                    # Apply the tag using the protocol method
                    await client.add_tag_to_item(item_id, tag.id)

            # Remove the opposite tag if it exists
            if tag_to_remove.lower() in existing_labels:
                opposite_tag = existing_labels[tag_to_remove.lower()]
                await client.remove_tag_from_item(item_id, opposite_tag.id)
                result.tag_removed = tag_to_remove

        except httpx.HTTPStatusError as e:
            logger.warning(
                "HTTP error applying tags to %s %d: %s %s",
                item_type,
                item_id,
                e.response.status_code,
                e.response.reason_phrase,
            )
            result.tag_error = f"HTTP {e.response.status_code}: {e.response.reason_phrase}"
        except (httpx.ConnectError, httpx.TimeoutException) as e:
            logger.warning("Network error applying tags to %s %d: %s", item_type, item_id, e)
            result.tag_error = f"Network error: {e}"
        except ValidationError as e:
            logger.warning("Validation error applying tags to %s %d: %s", item_type, item_id, e)
            result.tag_error = f"Validation error: {e}"

        return result

    async def apply_movie_tags(
        self,
        client: TaggableClient,
        movie_id: int,
        has_match: bool,
        criteria: SearchCriteria = SearchCriteria.FOUR_K,
        dry_run: bool = False,
    ) -> TagResult:
        """Apply appropriate tags to a movie based on release availability.

        This is a convenience wrapper around apply_tags for movies.

        Args:
            client: A client implementing the TaggableClient protocol
            movie_id: The movie ID to tag
            has_match: Whether the movie has matching releases available
            criteria: The search criteria used (determines tag names)
            dry_run: If True, don't actually apply tags

        Returns:
            TagResult with the operation details
        """
        return await self.apply_tags(client, movie_id, "movie", has_match, criteria, dry_run)

    async def apply_series_tags(
        self,
        client: TaggableClient,
        series_id: int,
        has_match: bool,
        criteria: SearchCriteria = SearchCriteria.FOUR_K,
        dry_run: bool = False,
    ) -> TagResult:
        """Apply appropriate tags to a series based on release availability.

        This is a convenience wrapper around apply_tags for series.

        Args:
            client: A client implementing the TaggableClient protocol
            series_id: The series ID to tag
            has_match: Whether the series has matching releases available
            criteria: The search criteria used (determines tag names)
            dry_run: If True, don't actually apply tags

        Returns:
            TagResult with the operation details
        """
        return await self.apply_tags(client, series_id, "series", has_match, criteria, dry_run)
