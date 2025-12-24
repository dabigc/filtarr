"""Search criteria and result types for Filtarr."""

from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from collections.abc import Callable

    from filtarr.models.common import Release


class ResultType(Enum):
    """Type of search result.

    Attributes:
        FOUR_K: 4K/2160p resolution search
        HDR: HDR content search
        DOLBY_VISION: Dolby Vision content search
        DIRECTORS_CUT: Director's cut edition search
        EXTENDED: Extended edition search
        REMASTER: Remastered edition search
        IMAX: IMAX edition search
        SPECIAL_EDITION: Special/Collector's/Anniversary edition search
        CUSTOM: Custom criteria search
    """

    FOUR_K = "4k"
    HDR = "hdr"
    DOLBY_VISION = "dolby_vision"
    DIRECTORS_CUT = "directors_cut"
    EXTENDED = "extended"
    REMASTER = "remaster"
    IMAX = "imax"
    SPECIAL_EDITION = "special_edition"
    CUSTOM = "custom"


class SearchCriteria(Enum):
    """Predefined search criteria for common release filters.

    Attributes:
        FOUR_K: Match 4K/2160p releases
        HDR: Match HDR releases
        DOLBY_VISION: Match Dolby Vision releases
        DIRECTORS_CUT: Match Director's Cut releases (movie-only)
        EXTENDED: Match Extended Edition releases (movie-only)
        REMASTER: Match Remastered releases (movie-only)
        IMAX: Match IMAX releases (movie-only)
        SPECIAL_EDITION: Match Special/Collector's/Anniversary editions (movie-only)
    """

    FOUR_K = "4k"
    HDR = "hdr"
    DOLBY_VISION = "dolby_vision"
    DIRECTORS_CUT = "directors_cut"
    EXTENDED = "extended"
    REMASTER = "remaster"
    IMAX = "imax"
    SPECIAL_EDITION = "special_edition"


# Criteria that only apply to movies (not TV series)
MOVIE_ONLY_CRITERIA: frozenset[SearchCriteria] = frozenset(
    {
        SearchCriteria.DIRECTORS_CUT,
        SearchCriteria.EXTENDED,
        SearchCriteria.REMASTER,
        SearchCriteria.IMAX,
        SearchCriteria.SPECIAL_EDITION,
    }
)


class ReleaseMatcher(Protocol):
    """Protocol for release matching functions."""

    def __call__(self, release: Release) -> bool:
        """Check if a release matches the criteria."""
        ...


def get_matcher_for_criteria(criteria: SearchCriteria) -> Callable[[Release], bool]:
    """Get a matcher function for a predefined criteria.

    Args:
        criteria: The search criteria to get a matcher for

    Returns:
        A callable that takes a Release and returns True if it matches
    """
    matchers: dict[SearchCriteria, Callable[[Release], bool]] = {
        SearchCriteria.FOUR_K: _match_4k,
        SearchCriteria.HDR: _match_hdr,
        SearchCriteria.DOLBY_VISION: _match_dolby_vision,
        SearchCriteria.DIRECTORS_CUT: _match_directors_cut,
        SearchCriteria.EXTENDED: _match_extended,
        SearchCriteria.REMASTER: _match_remaster,
        SearchCriteria.IMAX: _match_imax,
        SearchCriteria.SPECIAL_EDITION: _match_special_edition,
    }
    return matchers[criteria]


def _match_4k(release: Release) -> bool:
    """Check if release is 4K/2160p."""
    return release.is_4k()


def _match_hdr(release: Release) -> bool:
    """Check if release is HDR."""
    title_lower = release.title.lower()
    return "hdr" in title_lower or "hdr10" in title_lower or "hdr10+" in title_lower


def _match_dolby_vision(release: Release) -> bool:
    """Check if release is Dolby Vision."""
    title_lower = release.title.lower()
    return "dv" in title_lower or "dolby vision" in title_lower or "dolbyvision" in title_lower


def _match_directors_cut(release: Release) -> bool:
    """Check if release is Director's Cut."""
    title_lower = release.title.lower()
    return "director" in title_lower and "cut" in title_lower


def _match_extended(release: Release) -> bool:
    """Check if release is Extended Edition."""
    title_lower = release.title.lower()
    return "extended" in title_lower


def _match_remaster(release: Release) -> bool:
    """Check if release is Remastered."""
    title_lower = release.title.lower()
    return "remaster" in title_lower


def _match_imax(release: Release) -> bool:
    """Check if release is IMAX."""
    title_lower = release.title.lower()
    return "imax" in title_lower


def _match_special_edition(release: Release) -> bool:
    """Check if release is a Special/Collector's/Anniversary/Ultimate/Definitive Edition."""
    title_lower = release.title.lower()
    return (
        "special edition" in title_lower
        or "special.edition" in title_lower
        or "collector's edition" in title_lower
        or "collectors edition" in title_lower
        or "collector edition" in title_lower
        or "anniversary edition" in title_lower
        or "ultimate edition" in title_lower
        or "definitive edition" in title_lower
    )
