"""Radarr-specific models."""

from pydantic import BaseModel, Field


class Movie(BaseModel):
    """Radarr movie model."""

    id: int
    title: str
    year: int = 0
    tmdb_id: int = Field(0, alias="tmdbId")
    imdb_id: str = Field("", alias="imdbId")
    monitored: bool = True
    has_file: bool = Field(False, alias="hasFile")
    tags: list[int] = Field(default_factory=list)

    model_config = {"populate_by_name": True}
