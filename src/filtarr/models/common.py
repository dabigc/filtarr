"""Common models shared between Radarr and Sonarr."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel

if TYPE_CHECKING:
    from collections.abc import Callable

    from filtarr.criteria import SearchCriteria


class Quality(BaseModel):
    """Quality information for a release."""

    id: int
    name: str

    def is_4k(self) -> bool:
        """Check if this quality represents 4K/2160p."""
        return "2160p" in self.name.lower() or "4k" in self.name.lower()

    def matches_resolution(self, resolution: str) -> bool:
        """Check if this quality matches a specific resolution.

        Args:
            resolution: Resolution string to match (e.g., "2160p", "1080p", "720p")

        Returns:
            True if the quality name contains the resolution
        """
        return resolution.lower() in self.name.lower()


class Release(BaseModel):
    """A release from an indexer search result."""

    guid: str
    title: str
    indexer: str
    size: int
    quality: Quality

    def is_4k(self) -> bool:
        """Check if this release is 4K based on quality or title."""
        if self.quality.is_4k():
            return True
        title_lower = self.title.lower()
        return "2160p" in title_lower or "4k" in title_lower

    def matches_criteria(self, criteria: SearchCriteria | Callable[[Release], bool]) -> bool:
        """Check if this release matches the given criteria.

        Args:
            criteria: Either a SearchCriteria enum value or a custom callable
                that takes a Release and returns a bool

        Returns:
            True if the release matches the criteria
        """
        from filtarr.criteria import SearchCriteria, get_matcher_for_criteria

        if isinstance(criteria, SearchCriteria):
            matcher = get_matcher_for_criteria(criteria)
            return matcher(self)
        # Custom callable
        return criteria(self)


class Tag(BaseModel):
    """A tag in Radarr/Sonarr."""

    id: int
    label: str
