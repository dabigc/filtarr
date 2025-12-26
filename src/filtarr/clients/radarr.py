"""Radarr API client."""

from typing import Any

from filtarr.clients.base import BaseArrClient
from filtarr.models.common import Release, Tag
from filtarr.models.radarr import Movie


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
        return [self._parse_release(item) for item in data]

    async def has_4k_releases(self, movie_id: int) -> bool:
        """Check if a movie has any 4K releases available.

        Args:
            movie_id: The Radarr movie ID

        Returns:
            True if 4K releases are available
        """
        releases = await self.get_movie_releases(movie_id)
        return any(r.is_4k() for r in releases)

    # Tag management methods

    async def get_tags(self) -> list[Tag]:
        """Fetch all tags.

        Returns:
            List of Tag models
        """
        data = await self._get("/api/v3/tag")
        return [Tag.model_validate(item) for item in data]

    async def create_tag(self, label: str) -> Tag:
        """Create a new tag.

        Args:
            label: The tag label

        Returns:
            The created Tag model
        """
        data = await self._post("/api/v3/tag", json={"label": label})
        return Tag.model_validate(data)

    async def get_or_create_tag(self, label: str) -> Tag:
        """Get an existing tag by label or create it if it doesn't exist.

        Args:
            label: The tag label

        Returns:
            The existing or newly created Tag model
        """
        tags = await self.get_tags()
        for tag in tags:
            if tag.label.lower() == label.lower():
                return tag
        return await self.create_tag(label)

    async def get_movie_raw(self, movie_id: int) -> dict[str, Any]:
        """Fetch raw movie data for updating.

        Args:
            movie_id: The Radarr movie ID

        Returns:
            Raw movie data dictionary
        """
        data: dict[str, Any] = await self._get(f"/api/v3/movie/{movie_id}")
        return data

    async def update_movie(self, movie_data: dict[str, Any]) -> Movie:
        """Update a movie.

        Args:
            movie_data: The complete movie data dictionary with modifications

        Returns:
            The updated Movie model
        """
        movie_id = movie_data["id"]
        data = await self._put(f"/api/v3/movie/{movie_id}", json=movie_data)
        # Invalidate cache for this movie
        await self.invalidate_cache(f"/api/v3/movie/{movie_id}")
        await self.invalidate_cache("/api/v3/movie")
        return Movie.model_validate(data)

    async def add_tag_to_movie(self, movie_id: int, tag_id: int) -> Movie:
        """Add a tag to a movie.

        Args:
            movie_id: The Radarr movie ID
            tag_id: The tag ID to add

        Returns:
            The updated Movie model
        """
        movie_data = await self.get_movie_raw(movie_id)
        tags: list[int] = movie_data.get("tags", [])
        if tag_id not in tags:
            tags.append(tag_id)
            movie_data["tags"] = tags
            return await self.update_movie(movie_data)
        # Tag already exists - return properly validated Movie from server
        return await self.get_movie(movie_id)

    async def remove_tag_from_movie(self, movie_id: int, tag_id: int) -> Movie:
        """Remove a tag from a movie.

        Args:
            movie_id: The Radarr movie ID
            tag_id: The tag ID to remove

        Returns:
            The updated Movie model
        """
        movie_data = await self.get_movie_raw(movie_id)
        tags: list[int] = movie_data.get("tags", [])
        if tag_id in tags:
            tags.remove(tag_id)
            movie_data["tags"] = tags
            return await self.update_movie(movie_data)
        # Tag doesn't exist - return properly validated Movie from server
        return await self.get_movie(movie_id)

    # TaggableClient protocol methods (aliases for generic tag operations)

    async def add_tag_to_item(self, item_id: int, tag_id: int) -> Movie:
        """Add a tag to an item (movie).

        This is an alias for add_tag_to_movie to conform to TaggableClient protocol.

        Args:
            item_id: The movie ID
            tag_id: The tag ID to add

        Returns:
            The updated Movie model
        """
        return await self.add_tag_to_movie(item_id, tag_id)

    async def remove_tag_from_item(self, item_id: int, tag_id: int) -> Movie:
        """Remove a tag from an item (movie).

        This is an alias for remove_tag_from_movie to conform to TaggableClient protocol.

        Args:
            item_id: The movie ID
            tag_id: The tag ID to remove

        Returns:
            The updated Movie model
        """
        return await self.remove_tag_from_movie(item_id, tag_id)
