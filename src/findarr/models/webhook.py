"""Webhook payload models for Radarr/Sonarr events."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class RadarrMovie(BaseModel):
    """Movie data from Radarr webhook payload."""

    id: int
    title: str
    year: int = 0
    tmdb_id: int = Field(default=0, alias="tmdbId")
    imdb_id: str = Field(default="", alias="imdbId")

    model_config = {"populate_by_name": True}


class RadarrWebhookPayload(BaseModel):
    """Radarr webhook payload for movie events.

    See: https://wiki.servarr.com/radarr/settings#connections
    """

    event_type: str = Field(alias="eventType")
    movie: RadarrMovie

    model_config = {"populate_by_name": True}

    def is_movie_added(self) -> bool:
        """Check if this is a MovieAdded event."""
        return self.event_type == "MovieAdded"


class SonarrSeries(BaseModel):
    """Series data from Sonarr webhook payload."""

    id: int
    title: str
    year: int = 0
    tvdb_id: int = Field(default=0, alias="tvdbId")
    imdb_id: str = Field(default="", alias="imdbId")

    model_config = {"populate_by_name": True}


class SonarrWebhookPayload(BaseModel):
    """Sonarr webhook payload for series events.

    See: https://wiki.servarr.com/sonarr/settings#connections
    """

    event_type: str = Field(alias="eventType")
    series: SonarrSeries

    model_config = {"populate_by_name": True}

    def is_series_add(self) -> bool:
        """Check if this is a SeriesAdd event."""
        return self.event_type == "SeriesAdd"


class WebhookResponse(BaseModel):
    """Standard response for webhook endpoints."""

    status: Literal["accepted", "ignored", "error"]
    message: str
    media_id: int | None = None
    media_title: str | None = None
