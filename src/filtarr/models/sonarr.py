"""Sonarr-specific models for series and episode data."""

from datetime import date, datetime

from pydantic import BaseModel, Field


class Episode(BaseModel):
    """An episode within a series."""

    id: int
    series_id: int = Field(alias="seriesId")
    season_number: int = Field(alias="seasonNumber")
    episode_number: int = Field(alias="episodeNumber")
    title: str = ""
    air_date: date | None = Field(default=None, alias="airDate")
    air_date_utc: datetime | None = Field(default=None, alias="airDateUtc")
    has_file: bool = Field(default=False, alias="hasFile")
    monitored: bool = True

    model_config = {"populate_by_name": True}


class Season(BaseModel):
    """A season within a series."""

    season_number: int = Field(alias="seasonNumber")
    monitored: bool = True
    episode_count: int = Field(default=0, alias="statistics.episodeCount")
    episode_file_count: int = Field(default=0, alias="statistics.episodeFileCount")

    model_config = {"populate_by_name": True}


class Series(BaseModel):
    """A TV series from Sonarr."""

    id: int
    title: str
    year: int = 0
    seasons: list[Season] = Field(default_factory=list)
    monitored: bool = True
    tags: list[int] = Field(default_factory=list)

    model_config = {"populate_by_name": True}
