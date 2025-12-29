"""filtarr - Check release availability via Radarr/Sonarr search results.

A Python library for checking whether movies (via Radarr) and TV shows
(via Sonarr) have releases matching specific criteria available from your indexers.

Supported Criteria
------------------
- **4K/2160p** - High resolution releases
- **HDR** - High Dynamic Range content
- **Dolby Vision** - Dolby Vision encoded releases
- **Director's Cut** - Director's cut editions (movies only)
- **Extended** - Extended edition releases (movies only)
- **Remaster** - Remastered editions (movies only)
- **IMAX** - IMAX format releases (movies only)
- **Special Edition** - Special/Collector's/Anniversary editions (movies only)

Quick Start
-----------
Check a movie for 4K by ID::

    from filtarr import ReleaseChecker

    checker = ReleaseChecker(
        radarr_url="http://localhost:7878",
        radarr_api_key="your-api-key",
    )
    result = await checker.check_movie(123)
    print(f"4K available: {result.has_match}")

Check a movie with different criteria::

    from filtarr import ReleaseChecker, SearchCriteria

    checker = ReleaseChecker(...)

    # Check for Director's Cut
    result = await checker.check_movie(123, criteria=SearchCriteria.DIRECTORS_CUT)

    # Check for IMAX
    result = await checker.check_movie(123, criteria=SearchCriteria.IMAX)

    # Check for Special Edition
    result = await checker.check_movie(123, criteria=SearchCriteria.SPECIAL_EDITION)

    # Custom criteria with callable
    result = await checker.check_movie(
        123,
        criteria=lambda r: "remaster" in r.title.lower()
    )

Check a movie by name::

    results = await checker.search_movies("The Matrix")
    # Returns list of (id, title, year) tuples

Check a TV series with sampling strategy::

    from filtarr.checker import SamplingStrategy

    checker = ReleaseChecker(
        sonarr_url="http://localhost:8989",
        sonarr_api_key="your-api-key",
    )
    result = await checker.check_series(
        456,
        strategy=SamplingStrategy.RECENT,
        seasons_to_check=3,
    )

CLI Usage
---------
The library includes a CLI for quick checks::

    filtarr check movie 123
    filtarr check movie "The Matrix" --criteria directors-cut
    filtarr check movie 123 --criteria imax
    filtarr check series "Breaking Bad" --strategy recent
    filtarr check batch --all-movies --criteria special-edition

Classes
-------
ReleaseChecker
    High-level interface for checking release availability.
SearchResult
    Result container for release searches.
SearchCriteria
    Predefined search criteria (FOUR_K, HDR, DOLBY_VISION, DIRECTORS_CUT,
    EXTENDED, REMASTER, IMAX, SPECIAL_EDITION).
ResultType
    Type of search result.
RadarrClient
    Low-level async client for the Radarr API.
SonarrClient
    Low-level async client for the Sonarr API.
"""

from filtarr.checker import ReleaseChecker, SamplingStrategy, SearchResult
from filtarr.clients.radarr import RadarrClient
from filtarr.clients.sonarr import SonarrClient
from filtarr.criteria import ResultType, SearchCriteria

__version__ = "2.1.0"

__all__ = [
    "RadarrClient",
    "ReleaseChecker",
    "ResultType",
    "SamplingStrategy",
    "SearchCriteria",
    "SearchResult",
    "SonarrClient",
    "__version__",
]
