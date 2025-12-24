"""Configuration loading for filtarr CLI."""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Self


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
    """Configuration for release criteria tagging.

    Tags are generated using patterns with {criteria} placeholder.
    For example, with default patterns:
        - 4K criteria → "4k-available" / "4k-unavailable"
        - IMAX criteria → "imax-available" / "imax-unavailable"
        - Director's Cut → "directors-cut-available" / "directors-cut-unavailable"
    """

    pattern_available: str = "{criteria}-available"
    pattern_unavailable: str = "{criteria}-unavailable"
    create_if_missing: bool = True
    recheck_days: int = 30

    # Legacy fields for backward compatibility (deprecated)
    available: str = "4k-available"
    unavailable: str = "4k-unavailable"

    def get_tag_names(self, criteria_value: str) -> tuple[str, str]:
        """Get tag names for a specific criteria.

        Args:
            criteria_value: The criteria value (e.g., "4k", "imax", "directors_cut")

        Returns:
            Tuple of (available_tag, unavailable_tag)
        """
        # Convert underscores to hyphens for tag slugs (e.g., "directors_cut" → "directors-cut")
        slug = criteria_value.replace("_", "-")
        return (
            self.pattern_available.format(criteria=slug),
            self.pattern_unavailable.format(criteria=slug),
        )


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


# --- Helper functions for parsing config sections ---


def _parse_arr_config_from_dict(
    data: dict[str, Any],
    section: str,
) -> tuple[str, str] | None:
    """Parse URL and API key from a config dict section.

    Args:
        data: The full config dictionary
        section: The section name (e.g., "radarr", "sonarr")

    Returns:
        Tuple of (url, api_key) if both present, None otherwise
    """
    if section not in data:
        return None
    section_data = data[section]
    url = section_data.get("url")
    api_key = section_data.get("api_key")
    if url and api_key:
        return (url, api_key)
    return None


def _parse_arr_config_from_env(
    url_var: str,
    key_var: str,
) -> tuple[str, str] | None:
    """Parse URL and API key from environment variables.

    Args:
        url_var: Environment variable name for URL
        key_var: Environment variable name for API key

    Returns:
        Tuple of (url, api_key) if both present, None otherwise
    """
    url = os.environ.get(url_var)
    api_key = os.environ.get(key_var)
    if url and api_key:
        return (url, api_key)
    return None


def _parse_tags_from_dict(data: dict[str, Any], defaults: TagConfig) -> TagConfig:
    """Parse TagConfig from a config dictionary.

    Args:
        data: The full config dictionary
        defaults: Default TagConfig to use for missing values

    Returns:
        TagConfig instance
    """
    if "tags" not in data:
        return defaults
    tags_data = data["tags"]
    return TagConfig(
        pattern_available=tags_data.get("pattern_available", defaults.pattern_available),
        pattern_unavailable=tags_data.get("pattern_unavailable", defaults.pattern_unavailable),
        create_if_missing=tags_data.get("create_if_missing", defaults.create_if_missing),
        recheck_days=tags_data.get("recheck_days", defaults.recheck_days),
        available=tags_data.get("available", defaults.available),
        unavailable=tags_data.get("unavailable", defaults.unavailable),
    )


def _parse_tags_from_env(base: TagConfig) -> TagConfig:
    """Parse TagConfig from environment variables.

    Args:
        base: Base TagConfig to use for defaults

    Returns:
        TagConfig instance with environment overrides
    """
    pattern_available = os.environ.get("FILTARR_TAG_PATTERN_AVAILABLE")
    pattern_unavailable = os.environ.get("FILTARR_TAG_PATTERN_UNAVAILABLE")
    tag_available = os.environ.get("FILTARR_TAG_AVAILABLE")
    tag_unavailable = os.environ.get("FILTARR_TAG_UNAVAILABLE")

    # Return base if no env vars set
    if not any([pattern_available, pattern_unavailable, tag_available, tag_unavailable]):
        return base

    return TagConfig(
        pattern_available=pattern_available or base.pattern_available,
        pattern_unavailable=pattern_unavailable or base.pattern_unavailable,
        create_if_missing=base.create_if_missing,
        recheck_days=base.recheck_days,
        available=tag_available or base.available,
        unavailable=tag_unavailable or base.unavailable,
    )


def _parse_state_from_dict(data: dict[str, Any]) -> StateConfig:
    """Parse StateConfig from a config dictionary.

    Args:
        data: The full config dictionary

    Returns:
        StateConfig instance
    """
    if "state" not in data or "path" not in data["state"]:
        return StateConfig()
    return StateConfig(path=Path(data["state"]["path"]).expanduser())


def _parse_state_from_env(base: StateConfig) -> StateConfig:
    """Parse StateConfig from environment variables.

    Args:
        base: Base StateConfig to use for defaults

    Returns:
        StateConfig instance with environment overrides
    """
    state_path = os.environ.get("FILTARR_STATE_PATH")
    if not state_path:
        return base
    return StateConfig(path=Path(state_path).expanduser())


def _parse_webhook_from_dict(data: dict[str, Any]) -> WebhookConfig:
    """Parse WebhookConfig from a config dictionary.

    Args:
        data: The full config dictionary

    Returns:
        WebhookConfig instance
    """
    if "webhook" not in data:
        return WebhookConfig()
    webhook_data = data["webhook"]
    defaults = WebhookConfig()
    return WebhookConfig(
        host=webhook_data.get("host", defaults.host),
        port=webhook_data.get("port", defaults.port),
    )


def _parse_webhook_from_env(base: WebhookConfig) -> WebhookConfig:
    """Parse WebhookConfig from environment variables.

    Args:
        base: Base WebhookConfig to use for defaults

    Returns:
        WebhookConfig instance with environment overrides
    """
    host = os.environ.get("FILTARR_WEBHOOK_HOST")
    port_str = os.environ.get("FILTARR_WEBHOOK_PORT")

    if not host and not port_str:
        return base

    return WebhookConfig(
        host=host or base.host,
        port=int(port_str) if port_str else base.port,
    )


def _parse_scheduler_from_dict(data: dict[str, Any]) -> SchedulerConfig:
    """Parse SchedulerConfig from a config dictionary.

    Args:
        data: The full config dictionary

    Returns:
        SchedulerConfig instance
    """
    if "scheduler" not in data:
        return SchedulerConfig()
    scheduler_data = data["scheduler"]
    defaults = SchedulerConfig()
    return SchedulerConfig(
        enabled=scheduler_data.get("enabled", defaults.enabled),
        history_limit=scheduler_data.get("history_limit", defaults.history_limit),
        schedules=scheduler_data.get("schedules", defaults.schedules),
    )


def _parse_scheduler_from_env(base: SchedulerConfig) -> SchedulerConfig:
    """Parse SchedulerConfig from environment variables.

    Args:
        base: Base SchedulerConfig to use for defaults

    Returns:
        SchedulerConfig instance with environment overrides
    """
    scheduler_enabled = os.environ.get("FILTARR_SCHEDULER_ENABLED")
    if scheduler_enabled is None:
        return base

    return SchedulerConfig(
        enabled=scheduler_enabled.lower() in ("true", "1", "yes"),
        history_limit=base.history_limit,
        schedules=base.schedules,
    )


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
        data = _load_toml_file(path)

        # Parse *arr configs
        radarr = _build_radarr_config(_parse_arr_config_from_dict(data, "radarr"))
        sonarr = _build_sonarr_config(_parse_arr_config_from_dict(data, "sonarr"))

        # Parse timeout
        timeout = float(data.get("timeout", DEFAULT_TIMEOUT))

        return cls(
            radarr=radarr,
            sonarr=sonarr,
            timeout=timeout,
            tags=_parse_tags_from_dict(data, TagConfig()),
            state=_parse_state_from_dict(data),
            webhook=_parse_webhook_from_dict(data),
            scheduler=_parse_scheduler_from_dict(data),
        )

    @classmethod
    def _load_from_env(cls, base: Self) -> Self:
        """Override configuration with environment variables.

        Args:
            base: Base config to override

        Returns:
            Config instance with environment overrides
        """
        # Parse *arr configs from env
        radarr = (
            _build_radarr_config(
                _parse_arr_config_from_env("FILTARR_RADARR_URL", "FILTARR_RADARR_API_KEY")
            )
            or base.radarr
        )

        sonarr = (
            _build_sonarr_config(
                _parse_arr_config_from_env("FILTARR_SONARR_URL", "FILTARR_SONARR_API_KEY")
            )
            or base.sonarr
        )

        # Parse timeout from env
        timeout_str = os.environ.get("FILTARR_TIMEOUT")
        timeout = float(timeout_str) if timeout_str else base.timeout

        return cls(
            radarr=radarr,
            sonarr=sonarr,
            timeout=timeout,
            tags=_parse_tags_from_env(base.tags),
            state=_parse_state_from_env(base.state),
            webhook=_parse_webhook_from_env(base.webhook),
            scheduler=_parse_scheduler_from_env(base.scheduler),
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


def _load_toml_file(path: Path) -> dict[str, Any]:
    """Load and parse a TOML file.

    Args:
        path: Path to the TOML file

    Returns:
        Parsed TOML data as dictionary

    Raises:
        ConfigurationError: If file cannot be parsed
    """
    try:
        with path.open("rb") as f:
            return tomllib.load(f)
    except tomllib.TOMLDecodeError as e:
        raise ConfigurationError(f"Invalid config file: {e}") from e


def _build_radarr_config(
    parsed: tuple[str, str] | None,
) -> RadarrConfig | None:
    """Build RadarrConfig from parsed URL and API key.

    Args:
        parsed: Tuple of (url, api_key) or None

    Returns:
        RadarrConfig instance or None
    """
    if parsed is None:
        return None
    return RadarrConfig(url=parsed[0], api_key=parsed[1])


def _build_sonarr_config(
    parsed: tuple[str, str] | None,
) -> SonarrConfig | None:
    """Build SonarrConfig from parsed URL and API key.

    Args:
        parsed: Tuple of (url, api_key) or None

    Returns:
        SonarrConfig instance or None
    """
    if parsed is None:
        return None
    return SonarrConfig(url=parsed[0], api_key=parsed[1])
