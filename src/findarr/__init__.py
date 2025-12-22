"""findarr - Check 4K availability via Radarr/Sonarr search results."""

from findarr.checker import FourKChecker
from findarr.clients.radarr import RadarrClient
from findarr.clients.sonarr import SonarrClient

__version__ = "0.1.0"

__all__ = [
    "FourKChecker",
    "RadarrClient",
    "SonarrClient",
    "__version__",
]
