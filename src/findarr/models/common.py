"""Common models shared between Radarr and Sonarr."""

from pydantic import BaseModel


class Quality(BaseModel):
    """Quality information for a release."""

    id: int
    name: str

    def is_4k(self) -> bool:
        """Check if this quality represents 4K/2160p."""
        return "2160p" in self.name.lower() or "4k" in self.name.lower()


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
