"""filtarr - Check release availability via Radarr/Sonarr search results.

A Python library for checking whether movies (via Radarr) and TV shows
(via Sonarr) have releases matching specific criteria (4K, HDR, Dolby Vision,
Director's Cut, etc.) available from your indexers.

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

Check a movie with custom criteria::

    from filtarr import ReleaseChecker, SearchCriteria

    checker = ReleaseChecker(...)
    # Check for Director's Cut
    result = await checker.check_movie(123, criteria=SearchCriteria.DIRECTORS_CUT)

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
    filtarr check movie "The Matrix"
    filtarr check series "Breaking Bad" --strategy recent

Classes
-------
ReleaseChecker
    High-level interface for checking release availability.
SearchResult
    Result container for release searches.
SearchCriteria
    Predefined search criteria (FOUR_K, HDR, DIRECTORS_CUT, etc.).
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

__version__ = "1.1.1"

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
