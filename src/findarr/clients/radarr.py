"""Radarr API client."""

from findarr.clients.base import BaseArrClient
from findarr.models.common import Quality, Release
from findarr.models.radarr import Movie


class RadarrClient(BaseArrClient):
    """Client for interacting with the Radarr API.

    Inherits retry and caching functionality from BaseArrClient.

    Example:
        async with RadarrClient("http://localhost:7878", "api-key") as client:
            releases = await client.get_movie_releases(123)
            has_4k = await client.has_4k_releases(123)
            movies = await client.search_movies("The Matrix")
    """

    async def get_movie(self, movie_id: int) -> Movie:
        """Fetch a specific movie by ID.

        Args:
            movie_id: The Radarr movie ID

        Returns:
            Movie model with metadata
        """
        data = await self._get(f"/api/v3/movie/{movie_id}")
        return Movie.model_validate(data)

    async def get_all_movies(self) -> list[Movie]:
        """Fetch all movies in the library.

        Returns:
            List of Movie models
        """
        data = await self._get("/api/v3/movie")
        return [Movie.model_validate(item) for item in data]

    async def search_movies(self, term: str) -> list[Movie]:
        """Search for movies in the library by title.

        Args:
            term: Search term to match against movie titles

        Returns:
            List of matching Movie models
        """
        movies = await self.get_all_movies()
        term_lower = term.lower()
        return [m for m in movies if term_lower in m.title.lower()]

    async def find_movie_by_name(self, name: str) -> Movie | None:
        """Find a movie by exact or partial name match.

        If multiple movies match, returns the one with the closest title match.
        For exact matches, returns immediately.

        Args:
            name: Movie name to search for

        Returns:
            Movie if found, None otherwise
        """
        movies = await self.search_movies(name)
        if not movies:
            return None

        # Check for exact match first (case-insensitive)
        name_lower = name.lower()
        for movie in movies:
            if movie.title.lower() == name_lower:
                return movie

        # Return the movie with the shortest title (closest match)
        return min(movies, key=lambda m: len(m.title))

    async def get_movie_releases(self, movie_id: int) -> list[Release]:
        """Search for releases for a specific movie.

        Args:
            movie_id: The Radarr movie ID

        Returns:
            List of releases found by indexers
        """
        data = await self._get("/api/v3/release", params={"movieId": movie_id})

        releases = []
        for item in data:
            quality_data = item.get("quality", {}).get("quality", {})
            releases.append(
                Release(
                    guid=item["guid"],
                    title=item["title"],
                    indexer=item.get("indexer", "Unknown"),
                    size=item.get("size", 0),
                    quality=Quality(
                        id=quality_data.get("id", 0),
                        name=quality_data.get("name", "Unknown"),
                    ),
                )
            )
        return releases

    async def has_4k_releases(self, movie_id: int) -> bool:
        """Check if a movie has any 4K releases available.

        Args:
            movie_id: The Radarr movie ID

        Returns:
            True if 4K releases are available
        """
        releases = await self.get_movie_releases(movie_id)
        return any(r.is_4k() for r in releases)
