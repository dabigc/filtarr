"""Configuration loading for findarr CLI."""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Self


class ConfigurationError(Exception):
    """Raised when configuration is invalid or missing."""


@dataclass
class RadarrConfig:
    """Radarr connection configuration."""

    url: str
    api_key: str


@dataclass
class SonarrConfig:
    """Sonarr connection configuration."""

    url: str
    api_key: str


@dataclass
class TagConfig:
    """Configuration for 4K availability tagging."""

    available: str = "4k-available"
    unavailable: str = "4k-unavailable"
    create_if_missing: bool = True
    recheck_days: int = 30


def _default_state_path() -> Path:
    """Get the default state file path."""
    return Path.home() / ".config" / "findarr" / "state.json"


@dataclass
class StateConfig:
    """Configuration for state persistence."""

    path: Path = field(default_factory=_default_state_path)


DEFAULT_TIMEOUT = 120.0


@dataclass
class Config:
    """Application configuration."""

    radarr: RadarrConfig | None = None
    sonarr: SonarrConfig | None = None
    timeout: float = DEFAULT_TIMEOUT
    tags: TagConfig = field(default_factory=TagConfig)
    state: StateConfig = field(default_factory=StateConfig)

    @classmethod
    def load(cls) -> Self:
        """Load configuration from environment and config file.

        Configuration precedence (highest to lowest):
        1. Environment variables
        2. Config file (~/.config/findarr/config.toml)

        Environment variables:
        - FINDARR_RADARR_URL
        - FINDARR_RADARR_API_KEY
        - FINDARR_SONARR_URL
        - FINDARR_SONARR_API_KEY
        - FINDARR_TIMEOUT (request timeout in seconds)

        Returns:
            Config instance with loaded values

        Raises:
            ConfigurationError: If config file exists but is invalid
        """
        config = cls()

        # Load from config file first (lower precedence)
        config_file = Path.home() / ".config" / "findarr" / "config.toml"
        if config_file.exists():
            config = cls._load_from_file(config_file)

        # Override with environment variables (higher precedence)
        config = cls._load_from_env(config)

        return config

    @classmethod
    def _load_from_file(cls, path: Path) -> Self:
        """Load configuration from TOML file.

        Args:
            path: Path to the TOML config file

        Returns:
            Config instance

        Raises:
            ConfigurationError: If file cannot be parsed
        """
        try:
            with path.open("rb") as f:
                data = tomllib.load(f)
        except tomllib.TOMLDecodeError as e:
            raise ConfigurationError(f"Invalid config file: {e}") from e

        radarr = None
        sonarr = None

        if "radarr" in data:
            radarr_data = data["radarr"]
            if "url" in radarr_data and "api_key" in radarr_data:
                radarr = RadarrConfig(
                    url=radarr_data["url"],
                    api_key=radarr_data["api_key"],
                )

        if "sonarr" in data:
            sonarr_data = data["sonarr"]
            if "url" in sonarr_data and "api_key" in sonarr_data:
                sonarr = SonarrConfig(
                    url=sonarr_data["url"],
                    api_key=sonarr_data["api_key"],
                )

        timeout = DEFAULT_TIMEOUT
        if "timeout" in data:
            timeout = float(data["timeout"])

        # Parse tags configuration
        tags = TagConfig()
        if "tags" in data:
            tags_data = data["tags"]
            tags = TagConfig(
                available=tags_data.get("available", tags.available),
                unavailable=tags_data.get("unavailable", tags.unavailable),
                create_if_missing=tags_data.get("create_if_missing", tags.create_if_missing),
                recheck_days=tags_data.get("recheck_days", tags.recheck_days),
            )

        # Parse state configuration
        state = StateConfig()
        if "state" in data:
            state_data = data["state"]
            if "path" in state_data:
                state = StateConfig(path=Path(state_data["path"]).expanduser())

        return cls(radarr=radarr, sonarr=sonarr, timeout=timeout, tags=tags, state=state)

    @classmethod
    def _load_from_env(cls, base: Self) -> Self:
        """Override configuration with environment variables.

        Args:
            base: Base config to override

        Returns:
            Config instance with environment overrides
        """
        radarr = base.radarr
        sonarr = base.sonarr
        timeout = base.timeout
        tags = base.tags
        state = base.state

        # Check for Radarr env vars
        radarr_url = os.environ.get("FINDARR_RADARR_URL")
        radarr_key = os.environ.get("FINDARR_RADARR_API_KEY")
        if radarr_url and radarr_key:
            radarr = RadarrConfig(url=radarr_url, api_key=radarr_key)

        # Check for Sonarr env vars
        sonarr_url = os.environ.get("FINDARR_SONARR_URL")
        sonarr_key = os.environ.get("FINDARR_SONARR_API_KEY")
        if sonarr_url and sonarr_key:
            sonarr = SonarrConfig(url=sonarr_url, api_key=sonarr_key)

        # Check for timeout env var
        timeout_str = os.environ.get("FINDARR_TIMEOUT")
        if timeout_str:
            timeout = float(timeout_str)

        # Check for tag env vars
        tag_available = os.environ.get("FINDARR_TAG_AVAILABLE")
        tag_unavailable = os.environ.get("FINDARR_TAG_UNAVAILABLE")
        if tag_available or tag_unavailable:
            tags = TagConfig(
                available=tag_available or tags.available,
                unavailable=tag_unavailable or tags.unavailable,
                create_if_missing=tags.create_if_missing,
                recheck_days=tags.recheck_days,
            )

        # Check for state path env var
        state_path = os.environ.get("FINDARR_STATE_PATH")
        if state_path:
            state = StateConfig(path=Path(state_path).expanduser())

        return cls(radarr=radarr, sonarr=sonarr, timeout=timeout, tags=tags, state=state)

    def require_radarr(self) -> RadarrConfig:
        """Get Radarr config, raising if not configured.

        Returns:
            RadarrConfig instance

        Raises:
            ConfigurationError: If Radarr is not configured
        """
        if self.radarr is None:
            raise ConfigurationError(
                "Radarr is not configured. Set FINDARR_RADARR_URL and "
                "FINDARR_RADARR_API_KEY environment variables, or create "
                "~/.config/findarr/config.toml"
            )
        return self.radarr

    def require_sonarr(self) -> SonarrConfig:
        """Get Sonarr config, raising if not configured.

        Returns:
            SonarrConfig instance

        Raises:
            ConfigurationError: If Sonarr is not configured
        """
        if self.sonarr is None:
            raise ConfigurationError(
                "Sonarr is not configured. Set FINDARR_SONARR_URL and "
                "FINDARR_SONARR_API_KEY environment variables, or create "
                "~/.config/findarr/config.toml"
            )
        return self.sonarr
