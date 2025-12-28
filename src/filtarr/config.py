"""Configuration loading for filtarr CLI."""

from __future__ import annotations

import os
import tomllib
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Self
from urllib.parse import urlparse


class ConfigurationError(Exception):
    """Raised when configuration is invalid or missing."""


def _get_config_base_path() -> Path:
    """Get the base path for configuration files.

    Uses /config if it exists (Docker container), otherwise ~/.config/filtarr.
    Can be overridden with FILTARR_CONFIG_DIR environment variable.

    Returns:
        Path to the configuration base directory
    """
    env_path = os.environ.get("FILTARR_CONFIG_DIR")
    if env_path:
        return Path(env_path)

    # Check for Docker bind-mount directory
    docker_config = Path("/config")
    if docker_config.is_dir():
        return docker_config

    # Default to user config directory
    return Path.home() / ".config" / "filtarr"


def _validate_url(url: str, allow_http_localhost: bool = True) -> str:
    """Validate and normalize URL, enforcing HTTPS by default.

    Args:
        url: The URL to validate
        allow_http_localhost: If True, allow HTTP for localhost URLs

    Returns:
        The validated and normalized URL (with trailing slashes removed)

    Raises:
        ConfigurationError: If URL scheme is invalid or HTTP is used for non-localhost
    """
    parsed = urlparse(url)

    if parsed.scheme not in ("http", "https"):
        raise ConfigurationError(f"Invalid URL scheme: {parsed.scheme}")

    if parsed.scheme == "http":
        is_localhost = parsed.hostname in ("localhost", "127.0.0.1", "::1")
        if not (allow_http_localhost and is_localhost):
            raise ConfigurationError(
                "HTTP URLs are only allowed for localhost. Use HTTPS for remote servers."
            )

    return url.rstrip("/")


@dataclass
class RadarrConfig:
    """Radarr connection configuration.

    Attributes:
        url: Radarr server URL (must be HTTPS for remote servers)
        api_key: Radarr API key
        allow_insecure: If True, allow HTTP for non-localhost URLs (not recommended)
    """

    url: str
    api_key: str
    allow_insecure: bool = False

    def __post_init__(self) -> None:
        """Validate URL after initialization."""
        if self.allow_insecure:
            # When allow_insecure is True, just validate scheme and normalize
            parsed = urlparse(self.url)
            if parsed.scheme not in ("http", "https"):
                raise ConfigurationError(f"Invalid URL scheme: {parsed.scheme}")
            self.url = self.url.rstrip("/")
        else:
            # Normal validation: HTTPS required for non-localhost
            self.url = _validate_url(self.url, allow_http_localhost=True)

    def __repr__(self) -> str:
        """Return string representation with masked API key."""
        return f"RadarrConfig(url={self.url!r}, api_key='***')"

    def __str__(self) -> str:
        """Return string representation with masked API key."""
        return self.__repr__()


@dataclass
class SonarrConfig:
    """Sonarr connection configuration.

    Attributes:
        url: Sonarr server URL (must be HTTPS for remote servers)
        api_key: Sonarr API key
        allow_insecure: If True, allow HTTP for non-localhost URLs (not recommended)
    """

    url: str
    api_key: str
    allow_insecure: bool = False

    def __post_init__(self) -> None:
        """Validate URL after initialization."""
        if self.allow_insecure:
            # When allow_insecure is True, just validate scheme and normalize
            parsed = urlparse(self.url)
            if parsed.scheme not in ("http", "https"):
                raise ConfigurationError(f"Invalid URL scheme: {parsed.scheme}")
            self.url = self.url.rstrip("/")
        else:
            # Normal validation: HTTPS required for non-localhost
            self.url = _validate_url(self.url, allow_http_localhost=True)

    def __repr__(self) -> str:
        """Return string representation with masked API key."""
        return f"SonarrConfig(url={self.url!r}, api_key='***')"

    def __str__(self) -> str:
        """Return string representation with masked API key."""
        return self.__repr__()


@dataclass
class TagConfig:
    """Configuration for release criteria tagging.

    Tags are generated using patterns with {criteria} placeholder.
    For example, with default patterns:
        - 4K criteria -> "4k-available" / "4k-unavailable"
        - IMAX criteria -> "imax-available" / "imax-unavailable"
        - Director's Cut -> "directors-cut-available" / "directors-cut-unavailable"

    Migration Guide:
        The ``available`` and ``unavailable`` fields are deprecated in favor of
        ``pattern_available`` and ``pattern_unavailable``. These legacy fields
        will be removed in filtarr 2.0.0.

        Old usage::
            TagConfig(available="4k-available", unavailable="4k-unavailable")

        New usage::
            TagConfig(
                pattern_available="{criteria}-available",
                pattern_unavailable="{criteria}-unavailable"
            )
    """

    pattern_available: str = "{criteria}-available"
    pattern_unavailable: str = "{criteria}-unavailable"
    create_if_missing: bool = True
    recheck_days: int = 30

    # Legacy fields for backward compatibility (deprecated).
    # These fields are scheduled for removal in filtarr 2.0.0.
    # Use ``pattern_available`` / ``pattern_unavailable`` instead.
    _available: str | None = field(default=None, repr=False)
    _unavailable: str | None = field(default=None, repr=False)

    @property
    def available(self) -> str:
        """Legacy property for backward compatibility.

        .. deprecated:: 1.0.0
            Use :meth:`get_tag_names` with ``pattern_available`` instead.
            This will be removed in filtarr 2.0.0.
        """
        warnings.warn(
            "TagConfig.available is deprecated. Use pattern_available with "
            "get_tag_names() instead. This will be removed in filtarr 2.0.0.",
            DeprecationWarning,
            stacklevel=2,
        )
        if self._available is not None:
            return self._available
        return self.pattern_available.format(criteria="4k")

    @available.setter
    def available(self, value: str) -> None:
        """Set legacy available field with deprecation warning."""
        warnings.warn(
            "TagConfig.available is deprecated. Use pattern_available instead. "
            "This will be removed in filtarr 2.0.0.",
            DeprecationWarning,
            stacklevel=2,
        )
        self._available = value

    @property
    def unavailable(self) -> str:
        """Legacy property for backward compatibility.

        .. deprecated:: 1.0.0
            Use :meth:`get_tag_names` with ``pattern_unavailable`` instead.
            This will be removed in filtarr 2.0.0.
        """
        warnings.warn(
            "TagConfig.unavailable is deprecated. Use pattern_unavailable with "
            "get_tag_names() instead. This will be removed in filtarr 2.0.0.",
            DeprecationWarning,
            stacklevel=2,
        )
        if self._unavailable is not None:
            return self._unavailable
        return self.pattern_unavailable.format(criteria="4k")

    @unavailable.setter
    def unavailable(self, value: str) -> None:
        """Set legacy unavailable field with deprecation warning."""
        warnings.warn(
            "TagConfig.unavailable is deprecated. Use pattern_unavailable instead. "
            "This will be removed in filtarr 2.0.0.",
            DeprecationWarning,
            stacklevel=2,
        )
        self._unavailable = value

    def get_tag_names(self, criteria_value: str) -> tuple[str, str]:
        """Get tag names for a specific criteria.

        Args:
            criteria_value: The criteria value (e.g., "4k", "imax", "directors_cut")

        Returns:
            Tuple of (available_tag, unavailable_tag)
        """
        # Convert underscores to hyphens for tag slugs (e.g., "directors_cut" -> "directors-cut")
        slug = criteria_value.replace("_", "-")
        return (
            self.pattern_available.format(criteria=slug),
            self.pattern_unavailable.format(criteria=slug),
        )


def _default_state_path() -> Path:
    """Get the default state file path."""
    return _get_config_base_path() / "state.json"


@dataclass
class StateConfig:
    """Configuration for state persistence.

    Attributes:
        path: Path to the state file
        ttl_hours: Hours before rechecking an item (0 to disable TTL caching)
    """

    path: Path = field(default_factory=_default_state_path)
    ttl_hours: int = 24

    def __post_init__(self) -> None:
        """Validate ttl_hours after initialization."""
        if self.ttl_hours < 0:
            raise ConfigurationError(
                f"Invalid ttl_hours: {self.ttl_hours}. Value must be 0 or greater."
            )


# Valid log level names (case-insensitive)
VALID_LOG_LEVELS = frozenset({"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"})

# Valid output format values
VALID_OUTPUT_FORMATS = frozenset({"text", "json"})


@dataclass
class LoggingConfig:
    """Configuration for logging.

    Attributes:
        level: Log level name (DEBUG, INFO, WARNING, ERROR, CRITICAL).
        timestamps: Whether to show timestamps in output. Default True.
        output_format: Output format ('text' or 'json'). Default 'text'.
    """

    level: str = "INFO"
    timestamps: bool = True
    output_format: str = "text"

    def __post_init__(self) -> None:
        """Validate log level and output format after initialization."""
        self.level = self.level.upper()
        if self.level not in VALID_LOG_LEVELS:
            raise ConfigurationError(
                f"Invalid log level: {self.level}. "
                f"Valid options: {', '.join(sorted(VALID_LOG_LEVELS))}"
            )

        self.output_format = self.output_format.lower()
        if self.output_format not in VALID_OUTPUT_FORMATS:
            raise ConfigurationError(
                f"Invalid output format: {self.output_format}. "
                f"Valid options: {', '.join(sorted(VALID_OUTPUT_FORMATS))}"
            )


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
) -> tuple[str, str, bool] | None:
    """Parse URL, API key, and allow_insecure from a config dict section.

    Args:
        data: The full config dictionary
        section: The section name (e.g., "radarr", "sonarr")

    Returns:
        Tuple of (url, api_key, allow_insecure) if url and api_key present, None otherwise
    """
    if section not in data:
        return None
    section_data = data[section]
    url = section_data.get("url")
    api_key = section_data.get("api_key")
    allow_insecure = section_data.get("allow_insecure", False)
    if url and api_key:
        return (url, api_key, allow_insecure)
    return None


def _parse_arr_config_from_env(
    url_var: str,
    key_var: str,
    insecure_var: str,
) -> tuple[str, str, bool] | None:
    """Parse URL, API key, and allow_insecure from environment variables.

    Args:
        url_var: Environment variable name for URL
        key_var: Environment variable name for API key
        insecure_var: Environment variable name for allow_insecure flag

    Returns:
        Tuple of (url, api_key, allow_insecure) if url and api_key present, None otherwise
    """
    url = os.environ.get(url_var)
    api_key = os.environ.get(key_var)
    allow_insecure_str = os.environ.get(insecure_var, "")
    allow_insecure = allow_insecure_str.lower() in ("true", "1", "yes")
    if url and api_key:
        return (url, api_key, allow_insecure)
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

    # Check for deprecated legacy fields and emit warnings
    legacy_available: str | None = None
    legacy_unavailable: str | None = None

    if "available" in tags_data:
        warnings.warn(
            "Config key 'tags.available' is deprecated. Use 'tags.pattern_available' "
            "instead. This will be removed in filtarr 2.0.0.",
            DeprecationWarning,
            stacklevel=3,
        )
        legacy_available = tags_data["available"]

    if "unavailable" in tags_data:
        warnings.warn(
            "Config key 'tags.unavailable' is deprecated. Use 'tags.pattern_unavailable' "
            "instead. This will be removed in filtarr 2.0.0.",
            DeprecationWarning,
            stacklevel=3,
        )
        legacy_unavailable = tags_data["unavailable"]

    return TagConfig(
        pattern_available=tags_data.get("pattern_available", defaults.pattern_available),
        pattern_unavailable=tags_data.get("pattern_unavailable", defaults.pattern_unavailable),
        create_if_missing=tags_data.get("create_if_missing", defaults.create_if_missing),
        recheck_days=tags_data.get("recheck_days", defaults.recheck_days),
        _available=legacy_available or defaults._available,
        _unavailable=legacy_unavailable or defaults._unavailable,
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

    # Check for deprecated legacy environment variables and emit warnings
    legacy_available: str | None = base._available
    legacy_unavailable: str | None = base._unavailable

    if tag_available:
        warnings.warn(
            "Environment variable 'FILTARR_TAG_AVAILABLE' is deprecated. "
            "Use 'FILTARR_TAG_PATTERN_AVAILABLE' instead. "
            "This will be removed in filtarr 2.0.0.",
            DeprecationWarning,
            stacklevel=3,
        )
        legacy_available = tag_available

    if tag_unavailable:
        warnings.warn(
            "Environment variable 'FILTARR_TAG_UNAVAILABLE' is deprecated. "
            "Use 'FILTARR_TAG_PATTERN_UNAVAILABLE' instead. "
            "This will be removed in filtarr 2.0.0.",
            DeprecationWarning,
            stacklevel=3,
        )
        legacy_unavailable = tag_unavailable

    return TagConfig(
        pattern_available=pattern_available or base.pattern_available,
        pattern_unavailable=pattern_unavailable or base.pattern_unavailable,
        create_if_missing=base.create_if_missing,
        recheck_days=base.recheck_days,
        _available=legacy_available,
        _unavailable=legacy_unavailable,
    )


def _parse_state_from_dict(data: dict[str, Any]) -> StateConfig:
    """Parse StateConfig from a config dictionary.

    Args:
        data: The full config dictionary

    Returns:
        StateConfig instance
    """
    if "state" not in data:
        return StateConfig()
    state_data = data["state"]
    defaults = StateConfig()
    path = Path(state_data["path"]).expanduser() if "path" in state_data else defaults.path
    ttl_hours = state_data.get("ttl_hours", defaults.ttl_hours)
    return StateConfig(path=path, ttl_hours=ttl_hours)


def _parse_state_from_env(base: StateConfig) -> StateConfig:
    """Parse StateConfig from environment variables.

    Args:
        base: Base StateConfig to use for defaults

    Returns:
        StateConfig instance with environment overrides

    Raises:
        ConfigurationError: If FILTARR_STATE_TTL_HOURS is not a valid integer
    """
    state_path = os.environ.get("FILTARR_STATE_PATH")
    ttl_hours_str = os.environ.get("FILTARR_STATE_TTL_HOURS")

    if not state_path and not ttl_hours_str:
        return base

    path = Path(state_path).expanduser() if state_path else base.path

    ttl_hours = base.ttl_hours
    if ttl_hours_str:
        try:
            ttl_hours = int(ttl_hours_str)
        except ValueError as e:
            raise ConfigurationError(
                f"Invalid FILTARR_STATE_TTL_HOURS: '{ttl_hours_str}'. "
                "Value must be a valid integer."
            ) from e

    return StateConfig(path=path, ttl_hours=ttl_hours)


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


def _parse_logging_from_dict(data: dict[str, Any]) -> LoggingConfig:
    """Parse LoggingConfig from a config dictionary.

    Args:
        data: The full config dictionary

    Returns:
        LoggingConfig instance
    """
    if "logging" not in data:
        return LoggingConfig()
    logging_data = data["logging"]
    defaults = LoggingConfig()
    return LoggingConfig(
        level=logging_data.get("level", defaults.level),
        timestamps=logging_data.get("timestamps", defaults.timestamps),
        output_format=logging_data.get("output_format", defaults.output_format),
    )


def _parse_logging_from_env(base: LoggingConfig) -> LoggingConfig:
    """Parse LoggingConfig from environment variables.

    Args:
        base: Base LoggingConfig to use for defaults

    Returns:
        LoggingConfig instance with environment overrides
    """
    log_level = os.environ.get("FILTARR_LOG_LEVEL")
    timestamps_str = os.environ.get("FILTARR_LOG_TIMESTAMPS")
    output_format = os.environ.get("FILTARR_LOG_OUTPUT_FORMAT")

    # Return base if no env vars set
    if log_level is None and timestamps_str is None and output_format is None:
        return base

    # Parse timestamps from env var
    timestamps = base.timestamps
    if timestamps_str is not None:
        timestamps = timestamps_str.lower() in ("true", "1", "yes")

    return LoggingConfig(
        level=log_level if log_level is not None else base.level,
        timestamps=timestamps,
        output_format=output_format if output_format is not None else base.output_format,
    )


@dataclass
class Config:
    """Application configuration."""

    radarr: RadarrConfig | None = None
    sonarr: SonarrConfig | None = None
    timeout: float = DEFAULT_TIMEOUT
    tags: TagConfig = field(default_factory=TagConfig)
    state: StateConfig = field(default_factory=StateConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    webhook: WebhookConfig = field(default_factory=WebhookConfig)
    scheduler: SchedulerConfig = field(default_factory=SchedulerConfig)

    @classmethod
    def load(cls) -> Self:
        """Load configuration from environment and config file.

        Configuration precedence (highest to lowest):
        1. Environment variables
        2. Config file (FILTARR_CONFIG_FILE or auto-detected path)

        Config file location (in order of precedence):
        1. FILTARR_CONFIG_FILE environment variable (exact path)
        2. FILTARR_CONFIG_DIR environment variable + config.toml
        3. /config/config.toml (if /config directory exists - Docker)
        4. ~/.config/filtarr/config.toml (default)

        Environment variables:
        - FILTARR_RADARR_URL
        - FILTARR_RADARR_API_KEY
        - FILTARR_SONARR_URL
        - FILTARR_SONARR_API_KEY
        - FILTARR_TIMEOUT (request timeout in seconds)
        - FILTARR_LOG_LEVEL (logging level)
        - FILTARR_CONFIG_DIR (base directory for config/state files)
        - FILTARR_CONFIG_FILE (exact path to config file)

        Returns:
            Config instance with loaded values

        Raises:
            ConfigurationError: If config file exists but is invalid
        """
        config = cls()

        # Determine config file path
        config_file_env = os.environ.get("FILTARR_CONFIG_FILE")
        if config_file_env:
            config_file = Path(config_file_env)
        else:
            config_file = _get_config_base_path() / "config.toml"

        # Load from config file first (lower precedence)
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
            logging=_parse_logging_from_dict(data),
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
                _parse_arr_config_from_env(
                    "FILTARR_RADARR_URL",
                    "FILTARR_RADARR_API_KEY",
                    "FILTARR_RADARR_ALLOW_INSECURE",
                )
            )
            or base.radarr
        )

        sonarr = (
            _build_sonarr_config(
                _parse_arr_config_from_env(
                    "FILTARR_SONARR_URL",
                    "FILTARR_SONARR_API_KEY",
                    "FILTARR_SONARR_ALLOW_INSECURE",
                )
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
            logging=_parse_logging_from_env(base.logging),
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
                "a config.toml file"
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
                "a config.toml file"
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
    parsed: tuple[str, str, bool] | None,
) -> RadarrConfig | None:
    """Build RadarrConfig from parsed URL, API key, and allow_insecure.

    Args:
        parsed: Tuple of (url, api_key, allow_insecure) or None

    Returns:
        RadarrConfig instance or None
    """
    if parsed is None:
        return None
    return RadarrConfig(url=parsed[0], api_key=parsed[1], allow_insecure=parsed[2])


def _build_sonarr_config(
    parsed: tuple[str, str, bool] | None,
) -> SonarrConfig | None:
    """Build SonarrConfig from parsed URL, API key, and allow_insecure.

    Args:
        parsed: Tuple of (url, api_key, allow_insecure) or None

    Returns:
        SonarrConfig instance or None
    """
    if parsed is None:
        return None
    return SonarrConfig(url=parsed[0], api_key=parsed[1], allow_insecure=parsed[2])
