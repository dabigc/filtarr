"""findarr - Check 4K availability via Radarr/Sonarr search results.

A Python library for checking whether movies (via Radarr) and TV shows
(via Sonarr) have 4K releases available from indexers.

Quick Start
-----------
Check a movie by ID::

    from findarr import FourKChecker

    checker = FourKChecker(
        radarr_url="http://localhost:7878",
        radarr_api_key="your-api-key",
    )
    result = await checker.check_movie(123)
    print(f"4K available: {result.has_4k}")

Check a movie by name::

    results = await checker.search_movies("The Matrix")
    # Returns list of (id, title, year) tuples

Check a TV series with sampling strategy::

    from findarr.checker import SamplingStrategy

    checker = FourKChecker(
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

    findarr check movie 123
    findarr check movie "The Matrix"
    findarr check series "Breaking Bad" --strategy recent

Classes
-------
FourKChecker
    High-level interface for checking 4K availability.
RadarrClient
    Low-level async client for the Radarr API.
SonarrClient
    Low-level async client for the Sonarr API.
"""

from findarr.checker import FourKChecker, FourKResult, SamplingStrategy
from findarr.clients.radarr import RadarrClient
from findarr.clients.sonarr import SonarrClient

__version__ = "0.2.0"

__all__ = [
    "FourKChecker",
    "FourKResult",
    "RadarrClient",
    "SamplingStrategy",
    "SonarrClient",
    "__version__",
]
