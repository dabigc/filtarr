"""Configuration loading for filtarr CLI."""

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
    return Path.home() / ".config" / "filtarr" / "state.json"


@dataclass
class StateConfig:
    """Configuration for state persistence."""

    path: Path = field(default_factory=_default_state_path)


@dataclass
class WebhookConfig:
    """Configuration for webhook server."""

    host: str = "0.0.0.0"
    port: int = 8080


@dataclass
class SchedulerConfig:
    """Configuration for the batch scheduler."""

    enabled: bool = True
    history_limit: int = 100
    schedules: list[dict[str, object]] = field(default_factory=list)


DEFAULT_TIMEOUT = 120.0


@dataclass
class Config:
    """Application configuration."""

    radarr: RadarrConfig | None = None
    sonarr: SonarrConfig | None = None
    timeout: float = DEFAULT_TIMEOUT
    tags: TagConfig = field(default_factory=TagConfig)
    state: StateConfig = field(default_factory=StateConfig)
    webhook: WebhookConfig = field(default_factory=WebhookConfig)
    scheduler: SchedulerConfig = field(default_factory=SchedulerConfig)

    @classmethod
    def load(cls) -> Self:
        """Load configuration from environment and config file.

        Configuration precedence (highest to lowest):
        1. Environment variables
        2. Config file (~/.config/filtarr/config.toml)

        Environment variables:
        - FILTARR_RADARR_URL
        - FILTARR_RADARR_API_KEY
        - FILTARR_SONARR_URL
        - FILTARR_SONARR_API_KEY
        - FILTARR_TIMEOUT (request timeout in seconds)

        Returns:
            Config instance with loaded values

        Raises:
            ConfigurationError: If config file exists but is invalid
        """
        config = cls()

        # Load from config file first (lower precedence)
        config_file = Path.home() / ".config" / "filtarr" / "config.toml"
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

        # Parse webhook configuration
        webhook = WebhookConfig()
        if "webhook" in data:
            webhook_data = data["webhook"]
            webhook = WebhookConfig(
                host=webhook_data.get("host", webhook.host),
                port=webhook_data.get("port", webhook.port),
            )

        # Parse scheduler configuration
        scheduler = SchedulerConfig()
        if "scheduler" in data:
            scheduler_data = data["scheduler"]
            scheduler = SchedulerConfig(
                enabled=scheduler_data.get("enabled", scheduler.enabled),
                history_limit=scheduler_data.get("history_limit", scheduler.history_limit),
                schedules=scheduler_data.get("schedules", scheduler.schedules),
            )

        return cls(
            radarr=radarr,
            sonarr=sonarr,
            timeout=timeout,
            tags=tags,
            state=state,
            webhook=webhook,
            scheduler=scheduler,
        )

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
        webhook = base.webhook
        scheduler = base.scheduler

        # Check for Radarr env vars
        radarr_url = os.environ.get("FILTARR_RADARR_URL")
        radarr_key = os.environ.get("FILTARR_RADARR_API_KEY")
        if radarr_url and radarr_key:
            radarr = RadarrConfig(url=radarr_url, api_key=radarr_key)

        # Check for Sonarr env vars
        sonarr_url = os.environ.get("FILTARR_SONARR_URL")
        sonarr_key = os.environ.get("FILTARR_SONARR_API_KEY")
        if sonarr_url and sonarr_key:
            sonarr = SonarrConfig(url=sonarr_url, api_key=sonarr_key)

        # Check for timeout env var
        timeout_str = os.environ.get("FILTARR_TIMEOUT")
        if timeout_str:
            timeout = float(timeout_str)

        # Check for tag env vars
        tag_available = os.environ.get("FILTARR_TAG_AVAILABLE")
        tag_unavailable = os.environ.get("FILTARR_TAG_UNAVAILABLE")
        if tag_available or tag_unavailable:
            tags = TagConfig(
                available=tag_available or tags.available,
                unavailable=tag_unavailable or tags.unavailable,
                create_if_missing=tags.create_if_missing,
                recheck_days=tags.recheck_days,
            )

        # Check for state path env var
        state_path = os.environ.get("FILTARR_STATE_PATH")
        if state_path:
            state = StateConfig(path=Path(state_path).expanduser())

        # Check for webhook env vars
        webhook_host = os.environ.get("FILTARR_WEBHOOK_HOST")
        webhook_port = os.environ.get("FILTARR_WEBHOOK_PORT")
        if webhook_host or webhook_port:
            webhook = WebhookConfig(
                host=webhook_host or webhook.host,
                port=int(webhook_port) if webhook_port else webhook.port,
            )

        # Check for scheduler env var
        scheduler_enabled = os.environ.get("FILTARR_SCHEDULER_ENABLED")
        if scheduler_enabled is not None:
            scheduler = SchedulerConfig(
                enabled=scheduler_enabled.lower() in ("true", "1", "yes"),
                history_limit=scheduler.history_limit,
                schedules=scheduler.schedules,
            )

        return cls(
            radarr=radarr,
            sonarr=sonarr,
            timeout=timeout,
            tags=tags,
            state=state,
            webhook=webhook,
            scheduler=scheduler,
        )

    def require_radarr(self) -> RadarrConfig:
        """Get Radarr config, raising if not configured.

        Returns:
            RadarrConfig instance

        Raises:
            ConfigurationError: If Radarr is not configured
        """
        if self.radarr is None:
            raise ConfigurationError(
                "Radarr is not configured. Set FILTARR_RADARR_URL and "
                "FILTARR_RADARR_API_KEY environment variables, or create "
                "~/.config/filtarr/config.toml"
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
                "Sonarr is not configured. Set FILTARR_SONARR_URL and "
                "FILTARR_SONARR_API_KEY environment variables, or create "
                "~/.config/filtarr/config.toml"
            )
        return self.sonarr
