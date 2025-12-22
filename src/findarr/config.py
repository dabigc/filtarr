"""Configuration loading for findarr CLI."""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
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
class Config:
    """Application configuration."""

    radarr: RadarrConfig | None = None
    sonarr: SonarrConfig | None = None

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

        return cls(radarr=radarr, sonarr=sonarr)

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

        return cls(radarr=radarr, sonarr=sonarr)

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
