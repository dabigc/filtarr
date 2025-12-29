"""Tests for configuration loading."""

import os
import warnings
from pathlib import Path
from unittest.mock import patch

import pytest

from filtarr.config import (
    Config,
    ConfigurationError,
    LoggingConfig,
    RadarrConfig,
    SonarrConfig,
    TagConfig,
)


class TestConfigFromEnv:
    """Tests for loading config from environment variables."""

    def test_load_radarr_from_env(self) -> None:
        """Should load Radarr config from environment."""
        with patch.dict(
            os.environ,
            {
                "FILTARR_RADARR_URL": "http://localhost:7878",
                "FILTARR_RADARR_API_KEY": "test-key",
            },
            clear=False,
        ):
            config = Config.load()

        assert config.radarr is not None
        assert config.radarr.url == "http://localhost:7878"
        assert config.radarr.api_key == "test-key"

    def test_load_sonarr_from_env(self) -> None:
        """Should load Sonarr config from environment."""
        with patch.dict(
            os.environ,
            {
                "FILTARR_SONARR_URL": "http://localhost:8989",
                "FILTARR_SONARR_API_KEY": "sonarr-key",
            },
            clear=False,
        ):
            config = Config.load()

        assert config.sonarr is not None
        assert config.sonarr.url == "http://localhost:8989"
        assert config.sonarr.api_key == "sonarr-key"

    def test_partial_env_vars_ignored(self, tmp_path: Path) -> None:
        """Should ignore partial config (only URL, no key)."""
        # Use tmp_path for home to avoid loading real config file
        with (
            patch.object(Path, "home", return_value=tmp_path),
            patch.dict(
                os.environ,
                {"FILTARR_RADARR_URL": "http://localhost:7878"},
                clear=True,
            ),
        ):
            config = Config.load()

        assert config.radarr is None


class TestConfigFromFile:
    """Tests for loading config from TOML file."""

    def test_load_from_toml_file(self, tmp_path: Path) -> None:
        """Should load config from TOML file."""
        config_dir = tmp_path / ".config" / "filtarr"
        config_dir.mkdir(parents=True)
        config_file = config_dir / "config.toml"
        config_file.write_text("""
[radarr]
url = "http://localhost:7878"
api_key = "file-radarr-key"

[sonarr]
url = "http://localhost:8989"
api_key = "file-sonarr-key"
""")

        with (
            patch.object(Path, "home", return_value=tmp_path),
            patch.dict(os.environ, {}, clear=True),
        ):
            config = Config.load()

        assert config.radarr is not None
        assert config.radarr.url == "http://localhost:7878"
        assert config.radarr.api_key == "file-radarr-key"
        assert config.sonarr is not None
        assert config.sonarr.url == "http://localhost:8989"

    def test_env_overrides_file(self, tmp_path: Path) -> None:
        """Environment variables should override file config."""
        config_dir = tmp_path / ".config" / "filtarr"
        config_dir.mkdir(parents=True)
        config_file = config_dir / "config.toml"
        config_file.write_text("""
[radarr]
url = "http://127.0.0.1:7878"
api_key = "file-key"
""")

        with (
            patch.object(Path, "home", return_value=tmp_path),
            patch.dict(
                os.environ,
                {
                    "FILTARR_RADARR_URL": "http://localhost:7878",
                    "FILTARR_RADARR_API_KEY": "env-key",
                },
                clear=True,
            ),
        ):
            config = Config.load()

        assert config.radarr is not None
        assert config.radarr.url == "http://localhost:7878"
        assert config.radarr.api_key == "env-key"

    def test_invalid_toml_raises_error(self, tmp_path: Path) -> None:
        """Should raise ConfigurationError for invalid TOML."""
        config_dir = tmp_path / ".config" / "filtarr"
        config_dir.mkdir(parents=True)
        config_file = config_dir / "config.toml"
        config_file.write_text("invalid [ toml content")

        with (
            patch.object(Path, "home", return_value=tmp_path),
            patch.dict(os.environ, {}, clear=True),
            pytest.raises(ConfigurationError, match="Invalid config file"),
        ):
            Config.load()


class TestConfigRequireMethods:
    """Tests for require_radarr and require_sonarr methods."""

    def test_require_radarr_when_configured(self) -> None:
        """Should return RadarrConfig when configured."""
        config = Config(radarr=RadarrConfig(url="http://localhost:7878", api_key="key"))
        radarr = config.require_radarr()
        assert radarr.url == "http://localhost:7878"

    def test_require_radarr_when_not_configured(self) -> None:
        """Should raise ConfigurationError when Radarr not configured."""
        config = Config()
        with pytest.raises(ConfigurationError, match="Radarr is not configured"):
            config.require_radarr()

    def test_require_sonarr_when_configured(self) -> None:
        """Should return SonarrConfig when configured."""
        config = Config(sonarr=SonarrConfig(url="http://localhost:8989", api_key="key"))
        sonarr = config.require_sonarr()
        assert sonarr.url == "http://localhost:8989"

    def test_require_sonarr_when_not_configured(self) -> None:
        """Should raise ConfigurationError when Sonarr not configured."""
        config = Config()
        with pytest.raises(ConfigurationError, match="Sonarr is not configured"):
            config.require_sonarr()


class TestTagConfig:
    """Tests for TagConfig get_tag_names method."""

    def test_get_tag_names_with_simple_criteria(self) -> None:
        """Should format tag names with simple criteria values."""
        tag_config = TagConfig()
        available, unavailable = tag_config.get_tag_names("4k")
        assert available == "4k-available"
        assert unavailable == "4k-unavailable"

    def test_get_tag_names_with_underscore_criteria(self) -> None:
        """Should convert underscores to hyphens in tag names."""
        tag_config = TagConfig()
        available, unavailable = tag_config.get_tag_names("directors_cut")
        assert available == "directors-cut-available"
        assert unavailable == "directors-cut-unavailable"

    def test_get_tag_names_with_imax(self) -> None:
        """Should format IMAX tag names correctly."""
        tag_config = TagConfig()
        available, unavailable = tag_config.get_tag_names("imax")
        assert available == "imax-available"
        assert unavailable == "imax-unavailable"

    def test_get_tag_names_with_special_edition(self) -> None:
        """Should format special_edition tag names correctly."""
        tag_config = TagConfig()
        available, unavailable = tag_config.get_tag_names("special_edition")
        assert available == "special-edition-available"
        assert unavailable == "special-edition-unavailable"

    def test_get_tag_names_with_custom_pattern(self) -> None:
        """Should use custom patterns if configured."""
        tag_config = TagConfig(
            pattern_available="has-{criteria}",
            pattern_unavailable="no-{criteria}",
        )
        available, unavailable = tag_config.get_tag_names("hdr")
        assert available == "has-hdr"
        assert unavailable == "no-hdr"

    def test_get_tag_names_with_multiple_underscores(self) -> None:
        """Should convert all underscores to hyphens."""
        tag_config = TagConfig()
        available, unavailable = tag_config.get_tag_names("very_long_criteria_name")
        assert available == "very-long-criteria-name-available"
        assert unavailable == "very-long-criteria-name-unavailable"


class TestWebhookConfigFromToml:
    """Tests for loading WebhookConfig from TOML file."""

    def test_load_webhook_with_host_and_port(self, tmp_path: Path) -> None:
        """Should load webhook with both host and port from TOML."""
        config_dir = tmp_path / ".config" / "filtarr"
        config_dir.mkdir(parents=True)
        config_file = config_dir / "config.toml"
        config_file.write_text("""
[webhook]
host = "127.0.0.1"
port = 9000
""")

        with (
            patch.object(Path, "home", return_value=tmp_path),
            patch.dict(os.environ, {}, clear=True),
        ):
            config = Config.load()

        assert config.webhook.host == "127.0.0.1"
        assert config.webhook.port == 9000

    def test_load_webhook_with_only_host(self, tmp_path: Path) -> None:
        """Should load webhook with only host (port uses default)."""
        config_dir = tmp_path / ".config" / "filtarr"
        config_dir.mkdir(parents=True)
        config_file = config_dir / "config.toml"
        config_file.write_text("""
[webhook]
host = "192.168.1.100"
""")

        with (
            patch.object(Path, "home", return_value=tmp_path),
            patch.dict(os.environ, {}, clear=True),
        ):
            config = Config.load()

        assert config.webhook.host == "192.168.1.100"
        assert config.webhook.port == 8080  # default port

    def test_load_webhook_with_only_port(self, tmp_path: Path) -> None:
        """Should load webhook with only port (host uses default)."""
        config_dir = tmp_path / ".config" / "filtarr"
        config_dir.mkdir(parents=True)
        config_file = config_dir / "config.toml"
        config_file.write_text("""
[webhook]
port = 3000
""")

        with (
            patch.object(Path, "home", return_value=tmp_path),
            patch.dict(os.environ, {}, clear=True),
        ):
            config = Config.load()

        assert config.webhook.host == "0.0.0.0"  # default host
        assert config.webhook.port == 3000

    def test_load_webhook_empty_section(self, tmp_path: Path) -> None:
        """Empty webhook section should use defaults."""
        config_dir = tmp_path / ".config" / "filtarr"
        config_dir.mkdir(parents=True)
        config_file = config_dir / "config.toml"
        config_file.write_text("""
[webhook]
""")

        with (
            patch.object(Path, "home", return_value=tmp_path),
            patch.dict(os.environ, {}, clear=True),
        ):
            config = Config.load()

        assert config.webhook.host == "0.0.0.0"
        assert config.webhook.port == 8080


class TestSchedulerConfigFromToml:
    """Tests for loading SchedulerConfig from TOML file."""

    def test_load_scheduler_enabled_true(self, tmp_path: Path) -> None:
        """Should load scheduler with enabled=true."""
        config_dir = tmp_path / ".config" / "filtarr"
        config_dir.mkdir(parents=True)
        config_file = config_dir / "config.toml"
        config_file.write_text("""
[scheduler]
enabled = true
""")

        with (
            patch.object(Path, "home", return_value=tmp_path),
            patch.dict(os.environ, {}, clear=True),
        ):
            config = Config.load()

        assert config.scheduler.enabled is True

    def test_load_scheduler_enabled_false(self, tmp_path: Path) -> None:
        """Should load scheduler with enabled=false."""
        config_dir = tmp_path / ".config" / "filtarr"
        config_dir.mkdir(parents=True)
        config_file = config_dir / "config.toml"
        config_file.write_text("""
[scheduler]
enabled = false
""")

        with (
            patch.object(Path, "home", return_value=tmp_path),
            patch.dict(os.environ, {}, clear=True),
        ):
            config = Config.load()

        assert config.scheduler.enabled is False

    def test_load_scheduler_with_custom_history_limit(self, tmp_path: Path) -> None:
        """Should load scheduler with custom history_limit."""
        config_dir = tmp_path / ".config" / "filtarr"
        config_dir.mkdir(parents=True)
        config_file = config_dir / "config.toml"
        config_file.write_text("""
[scheduler]
history_limit = 500
""")

        with (
            patch.object(Path, "home", return_value=tmp_path),
            patch.dict(os.environ, {}, clear=True),
        ):
            config = Config.load()

        assert config.scheduler.history_limit == 500
        assert config.scheduler.enabled is True  # default

    def test_load_scheduler_with_schedules_list(self, tmp_path: Path) -> None:
        """Should load scheduler with schedules list."""
        config_dir = tmp_path / ".config" / "filtarr"
        config_dir.mkdir(parents=True)
        config_file = config_dir / "config.toml"
        config_file.write_text("""
[scheduler]
enabled = true
history_limit = 50

[[scheduler.schedules]]
name = "daily-check"
cron = "0 2 * * *"

[[scheduler.schedules]]
name = "weekly-check"
cron = "0 3 * * 0"
""")

        with (
            patch.object(Path, "home", return_value=tmp_path),
            patch.dict(os.environ, {}, clear=True),
        ):
            config = Config.load()

        assert config.scheduler.enabled is True
        assert config.scheduler.history_limit == 50
        assert len(config.scheduler.schedules) == 2
        assert config.scheduler.schedules[0]["name"] == "daily-check"
        assert config.scheduler.schedules[0]["cron"] == "0 2 * * *"
        assert config.scheduler.schedules[1]["name"] == "weekly-check"
        assert config.scheduler.schedules[1]["cron"] == "0 3 * * 0"

    def test_load_scheduler_empty_section(self, tmp_path: Path) -> None:
        """Empty scheduler section should use defaults."""
        config_dir = tmp_path / ".config" / "filtarr"
        config_dir.mkdir(parents=True)
        config_file = config_dir / "config.toml"
        config_file.write_text("""
[scheduler]
""")

        with (
            patch.object(Path, "home", return_value=tmp_path),
            patch.dict(os.environ, {}, clear=True),
        ):
            config = Config.load()

        assert config.scheduler.enabled is True
        assert config.scheduler.history_limit == 100
        assert config.scheduler.schedules == []


class TestArrConfigFromTomlMissingFields:
    """Tests for missing fields in *arr config sections."""

    def test_radarr_section_missing_url(self, tmp_path: Path) -> None:
        """Section exists but url is missing should return None."""
        config_dir = tmp_path / ".config" / "filtarr"
        config_dir.mkdir(parents=True)
        config_file = config_dir / "config.toml"
        config_file.write_text("""
[radarr]
api_key = "some-key"
""")

        with (
            patch.object(Path, "home", return_value=tmp_path),
            patch.dict(os.environ, {}, clear=True),
        ):
            config = Config.load()

        assert config.radarr is None

    def test_radarr_section_missing_api_key(self, tmp_path: Path) -> None:
        """Section exists but api_key is missing should return None."""
        config_dir = tmp_path / ".config" / "filtarr"
        config_dir.mkdir(parents=True)
        config_file = config_dir / "config.toml"
        config_file.write_text("""
[radarr]
url = "http://localhost:7878"
""")

        with (
            patch.object(Path, "home", return_value=tmp_path),
            patch.dict(os.environ, {}, clear=True),
        ):
            config = Config.load()

        assert config.radarr is None

    def test_sonarr_section_missing_url(self, tmp_path: Path) -> None:
        """Section exists but url is missing should return None."""
        config_dir = tmp_path / ".config" / "filtarr"
        config_dir.mkdir(parents=True)
        config_file = config_dir / "config.toml"
        config_file.write_text("""
[sonarr]
api_key = "some-key"
""")

        with (
            patch.object(Path, "home", return_value=tmp_path),
            patch.dict(os.environ, {}, clear=True),
        ):
            config = Config.load()

        assert config.sonarr is None

    def test_sonarr_section_missing_api_key(self, tmp_path: Path) -> None:
        """Section exists but api_key is missing should return None."""
        config_dir = tmp_path / ".config" / "filtarr"
        config_dir.mkdir(parents=True)
        config_file = config_dir / "config.toml"
        config_file.write_text("""
[sonarr]
url = "http://127.0.0.1:8989"
""")

        with (
            patch.object(Path, "home", return_value=tmp_path),
            patch.dict(os.environ, {}, clear=True),
        ):
            config = Config.load()

        assert config.sonarr is None

    def test_radarr_section_empty_url(self, tmp_path: Path) -> None:
        """Section with empty url string should return None."""
        config_dir = tmp_path / ".config" / "filtarr"
        config_dir.mkdir(parents=True)
        config_file = config_dir / "config.toml"
        config_file.write_text("""
[radarr]
url = ""
api_key = "some-key"
""")

        with (
            patch.object(Path, "home", return_value=tmp_path),
            patch.dict(os.environ, {}, clear=True),
        ):
            config = Config.load()

        assert config.radarr is None

    def test_sonarr_section_empty_api_key(self, tmp_path: Path) -> None:
        """Section with empty api_key string should return None."""
        config_dir = tmp_path / ".config" / "filtarr"
        config_dir.mkdir(parents=True)
        config_file = config_dir / "config.toml"
        config_file.write_text("""
[sonarr]
url = "http://127.0.0.1:8989"
api_key = ""
""")

        with (
            patch.object(Path, "home", return_value=tmp_path),
            patch.dict(os.environ, {}, clear=True),
        ):
            config = Config.load()

        assert config.sonarr is None


class TestEnvironmentVariableOverrides:
    """Tests for environment variable overrides."""

    def test_webhook_host_env_override(self, tmp_path: Path) -> None:
        """FILTARR_WEBHOOK_HOST should override file config."""
        config_dir = tmp_path / ".config" / "filtarr"
        config_dir.mkdir(parents=True)
        config_file = config_dir / "config.toml"
        config_file.write_text("""
[webhook]
host = "127.0.0.1"
port = 9000
""")

        with (
            patch.object(Path, "home", return_value=tmp_path),
            patch.dict(
                os.environ,
                {"FILTARR_WEBHOOK_HOST": "10.0.0.1"},
                clear=True,
            ),
        ):
            config = Config.load()

        assert config.webhook.host == "10.0.0.1"
        assert config.webhook.port == 9000  # file value preserved

    def test_webhook_port_env_override(self, tmp_path: Path) -> None:
        """FILTARR_WEBHOOK_PORT should override file config."""
        config_dir = tmp_path / ".config" / "filtarr"
        config_dir.mkdir(parents=True)
        config_file = config_dir / "config.toml"
        config_file.write_text("""
[webhook]
host = "127.0.0.1"
port = 9000
""")

        with (
            patch.object(Path, "home", return_value=tmp_path),
            patch.dict(
                os.environ,
                {"FILTARR_WEBHOOK_PORT": "5555"},
                clear=True,
            ),
        ):
            config = Config.load()

        assert config.webhook.host == "127.0.0.1"  # file value preserved
        assert config.webhook.port == 5555

    def test_webhook_both_env_overrides(self, tmp_path: Path) -> None:
        """Both FILTARR_WEBHOOK_HOST and FILTARR_WEBHOOK_PORT should override."""
        config_dir = tmp_path / ".config" / "filtarr"
        config_dir.mkdir(parents=True)
        config_file = config_dir / "config.toml"
        config_file.write_text("""
[webhook]
host = "127.0.0.1"
port = 9000
""")

        with (
            patch.object(Path, "home", return_value=tmp_path),
            patch.dict(
                os.environ,
                {
                    "FILTARR_WEBHOOK_HOST": "10.0.0.1",
                    "FILTARR_WEBHOOK_PORT": "7777",
                },
                clear=True,
            ),
        ):
            config = Config.load()

        assert config.webhook.host == "10.0.0.1"
        assert config.webhook.port == 7777

    def test_scheduler_enabled_true_string(self, tmp_path: Path) -> None:
        """FILTARR_SCHEDULER_ENABLED=true should enable scheduler."""
        config_dir = tmp_path / ".config" / "filtarr"
        config_dir.mkdir(parents=True)
        config_file = config_dir / "config.toml"
        config_file.write_text("""
[scheduler]
enabled = false
""")

        with (
            patch.object(Path, "home", return_value=tmp_path),
            patch.dict(
                os.environ,
                {"FILTARR_SCHEDULER_ENABLED": "true"},
                clear=True,
            ),
        ):
            config = Config.load()

        assert config.scheduler.enabled is True

    def test_scheduler_enabled_1_string(self, tmp_path: Path) -> None:
        """FILTARR_SCHEDULER_ENABLED=1 should enable scheduler."""
        config_dir = tmp_path / ".config" / "filtarr"
        config_dir.mkdir(parents=True)
        config_file = config_dir / "config.toml"
        config_file.write_text("""
[scheduler]
enabled = false
""")

        with (
            patch.object(Path, "home", return_value=tmp_path),
            patch.dict(
                os.environ,
                {"FILTARR_SCHEDULER_ENABLED": "1"},
                clear=True,
            ),
        ):
            config = Config.load()

        assert config.scheduler.enabled is True

    def test_scheduler_enabled_yes_string(self, tmp_path: Path) -> None:
        """FILTARR_SCHEDULER_ENABLED=yes should enable scheduler."""
        config_dir = tmp_path / ".config" / "filtarr"
        config_dir.mkdir(parents=True)
        config_file = config_dir / "config.toml"
        config_file.write_text("""
[scheduler]
enabled = false
""")

        with (
            patch.object(Path, "home", return_value=tmp_path),
            patch.dict(
                os.environ,
                {"FILTARR_SCHEDULER_ENABLED": "yes"},
                clear=True,
            ),
        ):
            config = Config.load()

        assert config.scheduler.enabled is True

    def test_scheduler_enabled_false_string(self, tmp_path: Path) -> None:
        """FILTARR_SCHEDULER_ENABLED=false should disable scheduler."""
        config_dir = tmp_path / ".config" / "filtarr"
        config_dir.mkdir(parents=True)
        config_file = config_dir / "config.toml"
        config_file.write_text("""
[scheduler]
enabled = true
""")

        with (
            patch.object(Path, "home", return_value=tmp_path),
            patch.dict(
                os.environ,
                {"FILTARR_SCHEDULER_ENABLED": "false"},
                clear=True,
            ),
        ):
            config = Config.load()

        assert config.scheduler.enabled is False

    def test_scheduler_enabled_0_string(self, tmp_path: Path) -> None:
        """FILTARR_SCHEDULER_ENABLED=0 should disable scheduler."""
        config_dir = tmp_path / ".config" / "filtarr"
        config_dir.mkdir(parents=True)
        config_file = config_dir / "config.toml"
        config_file.write_text("""
[scheduler]
enabled = true
""")

        with (
            patch.object(Path, "home", return_value=tmp_path),
            patch.dict(
                os.environ,
                {"FILTARR_SCHEDULER_ENABLED": "0"},
                clear=True,
            ),
        ):
            config = Config.load()

        assert config.scheduler.enabled is False

    def test_scheduler_enabled_no_string(self, tmp_path: Path) -> None:
        """FILTARR_SCHEDULER_ENABLED=no should disable scheduler."""
        config_dir = tmp_path / ".config" / "filtarr"
        config_dir.mkdir(parents=True)
        config_file = config_dir / "config.toml"
        config_file.write_text("""
[scheduler]
enabled = true
""")

        with (
            patch.object(Path, "home", return_value=tmp_path),
            patch.dict(
                os.environ,
                {"FILTARR_SCHEDULER_ENABLED": "no"},
                clear=True,
            ),
        ):
            config = Config.load()

        assert config.scheduler.enabled is False

    def test_scheduler_enabled_uppercase_true(self, tmp_path: Path) -> None:
        """FILTARR_SCHEDULER_ENABLED=TRUE should enable scheduler (case insensitive)."""
        config_dir = tmp_path / ".config" / "filtarr"
        config_dir.mkdir(parents=True)
        config_file = config_dir / "config.toml"
        config_file.write_text("""
[scheduler]
enabled = false
""")

        with (
            patch.object(Path, "home", return_value=tmp_path),
            patch.dict(
                os.environ,
                {"FILTARR_SCHEDULER_ENABLED": "TRUE"},
                clear=True,
            ),
        ):
            config = Config.load()

        assert config.scheduler.enabled is True

    def test_state_path_env_override(self, tmp_path: Path) -> None:
        """FILTARR_STATE_PATH should override file config."""
        config_dir = tmp_path / ".config" / "filtarr"
        config_dir.mkdir(parents=True)
        config_file = config_dir / "config.toml"
        config_file.write_text("""
[state]
path = "/original/state.json"
""")

        with (
            patch.object(Path, "home", return_value=tmp_path),
            patch.dict(
                os.environ,
                {"FILTARR_STATE_PATH": "/custom/path/state.json"},
                clear=True,
            ),
        ):
            config = Config.load()

        assert config.state.path == Path("/custom/path/state.json")

    def test_state_path_env_with_tilde_expansion(self, tmp_path: Path) -> None:
        """FILTARR_STATE_PATH with ~ should expand to home directory."""
        config_dir = tmp_path / ".config" / "filtarr"
        config_dir.mkdir(parents=True)
        config_file = config_dir / "config.toml"
        config_file.write_text("")

        with (
            patch.object(Path, "home", return_value=tmp_path),
            patch.dict(
                os.environ,
                {"FILTARR_STATE_PATH": "~/my-state.json"},
                clear=True,
            ),
        ):
            config = Config.load()

        # expanduser should expand ~ to home directory
        assert str(config.state.path).endswith("my-state.json")
        assert "~" not in str(config.state.path)


class TestApiKeyMasking:
    """Tests for API key masking in config repr/str methods."""

    def test_radarr_config_repr_masks_api_key(self) -> None:
        """RadarrConfig.__repr__ should mask the API key."""
        config = RadarrConfig(url="http://localhost:7878", api_key="super-secret-key")
        repr_str = repr(config)
        assert "super-secret-key" not in repr_str
        assert "***" in repr_str
        assert "http://localhost:7878" in repr_str

    def test_radarr_config_str_masks_api_key(self) -> None:
        """RadarrConfig.__str__ should mask the API key."""
        config = RadarrConfig(url="http://localhost:7878", api_key="super-secret-key")
        str_str = str(config)
        assert "super-secret-key" not in str_str
        assert "***" in str_str
        assert "http://localhost:7878" in str_str

    def test_sonarr_config_repr_masks_api_key(self) -> None:
        """SonarrConfig.__repr__ should mask the API key."""
        config = SonarrConfig(url="http://localhost:8989", api_key="another-secret")
        repr_str = repr(config)
        assert "another-secret" not in repr_str
        assert "***" in repr_str
        assert "http://localhost:8989" in repr_str

    def test_sonarr_config_str_masks_api_key(self) -> None:
        """SonarrConfig.__str__ should mask the API key."""
        config = SonarrConfig(url="http://localhost:8989", api_key="another-secret")
        str_str = str(config)
        assert "another-secret" not in str_str
        assert "***" in str_str
        assert "http://localhost:8989" in str_str

    def test_config_with_radarr_masks_api_key_in_repr(self) -> None:
        """Config repr should not leak Radarr API key."""
        config = Config(radarr=RadarrConfig(url="http://localhost:7878", api_key="radarr-secret"))
        repr_str = repr(config)
        assert "radarr-secret" not in repr_str
        assert "***" in repr_str

    def test_config_with_sonarr_masks_api_key_in_repr(self) -> None:
        """Config repr should not leak Sonarr API key."""
        config = Config(sonarr=SonarrConfig(url="http://localhost:8989", api_key="sonarr-secret"))
        repr_str = repr(config)
        assert "sonarr-secret" not in repr_str
        assert "***" in repr_str

    def test_config_with_both_arr_masks_api_keys_in_repr(self) -> None:
        """Config repr should not leak any API keys when both are configured."""
        config = Config(
            radarr=RadarrConfig(url="http://localhost:7878", api_key="radarr-secret"),
            sonarr=SonarrConfig(url="http://localhost:8989", api_key="sonarr-secret"),
        )
        repr_str = repr(config)
        assert "radarr-secret" not in repr_str
        assert "sonarr-secret" not in repr_str

    def test_api_key_still_accessible(self) -> None:
        """API key should still be accessible as an attribute."""
        radarr = RadarrConfig(url="http://localhost:7878", api_key="my-secret-key")
        sonarr = SonarrConfig(url="http://localhost:8989", api_key="another-key")

        # API keys should still be accessible for actual use
        assert radarr.api_key == "my-secret-key"
        assert sonarr.api_key == "another-key"


class TestUrlValidation:
    """Tests for URL validation and HTTPS enforcement."""

    # --- Valid URL tests ---

    def test_https_url_accepted(self) -> None:
        """HTTPS URLs should be accepted for any host."""
        config = RadarrConfig(url="https://radarr.example.com:7878", api_key="key")
        assert config.url == "https://radarr.example.com:7878"

    def test_http_localhost_accepted(self) -> None:
        """HTTP URLs for localhost should be accepted."""
        config = RadarrConfig(url="http://localhost:7878", api_key="key")
        assert config.url == "http://localhost:7878"

    def test_http_127_0_0_1_accepted(self) -> None:
        """HTTP URLs for 127.0.0.1 should be accepted."""
        config = RadarrConfig(url="http://127.0.0.1:7878", api_key="key")
        assert config.url == "http://127.0.0.1:7878"

    def test_http_ipv6_localhost_accepted(self) -> None:
        """HTTP URLs for IPv6 localhost (::1) should be accepted."""
        config = RadarrConfig(url="http://[::1]:7878", api_key="key")
        assert config.url == "http://[::1]:7878"

    def test_trailing_slash_removed(self) -> None:
        """Trailing slashes should be removed from URLs."""
        config = RadarrConfig(url="https://radarr.example.com:7878/", api_key="key")
        assert config.url == "https://radarr.example.com:7878"

    def test_multiple_trailing_slashes_removed(self) -> None:
        """Multiple trailing slashes should be removed from URLs."""
        config = RadarrConfig(url="http://localhost:7878///", api_key="key")
        assert config.url == "http://localhost:7878"

    # --- Invalid URL tests ---

    def test_http_remote_host_rejected(self) -> None:
        """HTTP URLs for non-localhost hosts should be rejected."""
        with pytest.raises(ConfigurationError, match="HTTP URLs are only allowed for localhost"):
            RadarrConfig(url="http://radarr.example.com:7878", api_key="key")

    def test_http_ip_address_rejected(self) -> None:
        """HTTP URLs for remote IP addresses should be rejected."""
        with pytest.raises(ConfigurationError, match="HTTP URLs are only allowed for localhost"):
            RadarrConfig(url="http://192.168.1.100:7878", api_key="key")

    def test_ftp_scheme_rejected(self) -> None:
        """FTP URLs should be rejected."""
        with pytest.raises(ConfigurationError, match="Invalid URL scheme"):
            RadarrConfig(url="ftp://radarr.example.com:7878", api_key="key")

    def test_no_scheme_rejected(self) -> None:
        """URLs without scheme should be rejected."""
        with pytest.raises(ConfigurationError, match="Invalid URL scheme"):
            RadarrConfig(url="radarr.example.com:7878", api_key="key")

    # --- allow_insecure tests ---

    def test_allow_insecure_permits_http_remote(self) -> None:
        """allow_insecure=True should permit HTTP for remote hosts."""
        config = RadarrConfig(
            url="http://radarr.example.com:7878",
            api_key="key",
            allow_insecure=True,
        )
        assert config.url == "http://radarr.example.com:7878"

    def test_allow_insecure_still_validates_scheme(self) -> None:
        """allow_insecure=True should still reject invalid schemes."""
        with pytest.raises(ConfigurationError, match="Invalid URL scheme"):
            RadarrConfig(url="ftp://radarr.example.com", api_key="key", allow_insecure=True)

    def test_allow_insecure_still_removes_trailing_slash(self) -> None:
        """allow_insecure=True should still remove trailing slashes."""
        config = RadarrConfig(
            url="http://radarr.example.com:7878/",
            api_key="key",
            allow_insecure=True,
        )
        assert config.url == "http://radarr.example.com:7878"

    # --- SonarrConfig tests ---

    def test_sonarr_https_url_accepted(self) -> None:
        """SonarrConfig should accept HTTPS URLs."""
        config = SonarrConfig(url="https://sonarr.example.com:8989", api_key="key")
        assert config.url == "https://sonarr.example.com:8989"

    def test_sonarr_http_localhost_accepted(self) -> None:
        """SonarrConfig should accept HTTP for localhost."""
        config = SonarrConfig(url="http://localhost:8989", api_key="key")
        assert config.url == "http://localhost:8989"

    def test_sonarr_http_remote_rejected(self) -> None:
        """SonarrConfig should reject HTTP for remote hosts."""
        with pytest.raises(ConfigurationError, match="HTTP URLs are only allowed for localhost"):
            SonarrConfig(url="http://sonarr.example.com:8989", api_key="key")

    def test_sonarr_allow_insecure_permits_http(self) -> None:
        """SonarrConfig allow_insecure should permit HTTP for remote hosts."""
        config = SonarrConfig(
            url="http://sonarr.example.com:8989",
            api_key="key",
            allow_insecure=True,
        )
        assert config.url == "http://sonarr.example.com:8989"

    def test_sonarr_allow_insecure_still_validates_scheme(self) -> None:
        """SonarrConfig allow_insecure=True should still reject invalid schemes."""
        with pytest.raises(ConfigurationError, match="Invalid URL scheme"):
            SonarrConfig(url="ftp://sonarr.example.com", api_key="key", allow_insecure=True)


class TestUrlValidationFromToml:
    """Tests for URL validation when loading from TOML files."""

    def test_http_localhost_from_file(self, tmp_path: Path) -> None:
        """HTTP localhost URLs from TOML should be accepted."""
        config_dir = tmp_path / ".config" / "filtarr"
        config_dir.mkdir(parents=True)
        config_file = config_dir / "config.toml"
        config_file.write_text("""
[radarr]
url = "http://localhost:7878"
api_key = "test-key"
""")

        with (
            patch.object(Path, "home", return_value=tmp_path),
            patch.dict(os.environ, {}, clear=True),
        ):
            config = Config.load()

        assert config.radarr is not None
        assert config.radarr.url == "http://localhost:7878"

    def test_https_remote_from_file(self, tmp_path: Path) -> None:
        """HTTPS remote URLs from TOML should be accepted."""
        config_dir = tmp_path / ".config" / "filtarr"
        config_dir.mkdir(parents=True)
        config_file = config_dir / "config.toml"
        config_file.write_text("""
[radarr]
url = "https://radarr.example.com:7878"
api_key = "test-key"
""")

        with (
            patch.object(Path, "home", return_value=tmp_path),
            patch.dict(os.environ, {}, clear=True),
        ):
            config = Config.load()

        assert config.radarr is not None
        assert config.radarr.url == "https://radarr.example.com:7878"

    def test_http_remote_from_file_rejected(self, tmp_path: Path) -> None:
        """HTTP remote URLs from TOML should be rejected."""
        config_dir = tmp_path / ".config" / "filtarr"
        config_dir.mkdir(parents=True)
        config_file = config_dir / "config.toml"
        config_file.write_text("""
[radarr]
url = "http://radarr.example.com:7878"
api_key = "test-key"
""")

        with (
            patch.object(Path, "home", return_value=tmp_path),
            patch.dict(os.environ, {}, clear=True),
            pytest.raises(ConfigurationError, match="HTTP URLs are only allowed for localhost"),
        ):
            Config.load()

    def test_allow_insecure_from_file(self, tmp_path: Path) -> None:
        """allow_insecure=true from TOML should permit HTTP remote."""
        config_dir = tmp_path / ".config" / "filtarr"
        config_dir.mkdir(parents=True)
        config_file = config_dir / "config.toml"
        config_file.write_text("""
[radarr]
url = "http://radarr.example.com:7878"
api_key = "test-key"
allow_insecure = true
""")

        with (
            patch.object(Path, "home", return_value=tmp_path),
            patch.dict(os.environ, {}, clear=True),
        ):
            config = Config.load()

        assert config.radarr is not None
        assert config.radarr.url == "http://radarr.example.com:7878"
        assert config.radarr.allow_insecure is True


class TestUrlValidationFromEnv:
    """Tests for URL validation when loading from environment variables."""

    def test_http_localhost_from_env(self) -> None:
        """HTTP localhost URLs from env should be accepted."""
        with patch.dict(
            os.environ,
            {
                "FILTARR_RADARR_URL": "http://localhost:7878",
                "FILTARR_RADARR_API_KEY": "test-key",
            },
            clear=False,
        ):
            config = Config.load()

        assert config.radarr is not None
        assert config.radarr.url == "http://localhost:7878"

    def test_https_remote_from_env(self) -> None:
        """HTTPS remote URLs from env should be accepted."""
        with patch.dict(
            os.environ,
            {
                "FILTARR_RADARR_URL": "https://radarr.example.com:7878",
                "FILTARR_RADARR_API_KEY": "test-key",
            },
            clear=False,
        ):
            config = Config.load()

        assert config.radarr is not None
        assert config.radarr.url == "https://radarr.example.com:7878"

    def test_http_remote_from_env_rejected(self, tmp_path: Path) -> None:
        """HTTP remote URLs from env should be rejected."""
        with (
            patch.object(Path, "home", return_value=tmp_path),
            patch.dict(
                os.environ,
                {
                    "FILTARR_RADARR_URL": "http://radarr.example.com:7878",
                    "FILTARR_RADARR_API_KEY": "test-key",
                },
                clear=True,
            ),
            pytest.raises(ConfigurationError, match="HTTP URLs are only allowed for localhost"),
        ):
            Config.load()

    def test_allow_insecure_from_env(self, tmp_path: Path) -> None:
        """FILTARR_RADARR_ALLOW_INSECURE=true should permit HTTP remote."""
        with (
            patch.object(Path, "home", return_value=tmp_path),
            patch.dict(
                os.environ,
                {
                    "FILTARR_RADARR_URL": "http://radarr.example.com:7878",
                    "FILTARR_RADARR_API_KEY": "test-key",
                    "FILTARR_RADARR_ALLOW_INSECURE": "true",
                },
                clear=True,
            ),
        ):
            config = Config.load()

        assert config.radarr is not None
        assert config.radarr.url == "http://radarr.example.com:7878"

    def test_allow_insecure_env_values(self, tmp_path: Path) -> None:
        """FILTARR_*_ALLOW_INSECURE should accept true, 1, yes."""
        for value in ("true", "1", "yes", "TRUE", "Yes"):
            with (
                patch.object(Path, "home", return_value=tmp_path),
                patch.dict(
                    os.environ,
                    {
                        "FILTARR_SONARR_URL": "http://sonarr.example.com:8989",
                        "FILTARR_SONARR_API_KEY": "test-key",
                        "FILTARR_SONARR_ALLOW_INSECURE": value,
                    },
                    clear=True,
                ),
            ):
                config = Config.load()
                assert config.sonarr is not None
                assert config.sonarr.url == "http://sonarr.example.com:8989"


class TestTagConfigDeprecationWarnings:
    """Tests for deprecation warnings on legacy TagConfig fields."""

    def test_accessing_available_property_emits_warning(self) -> None:
        """Accessing TagConfig.available should emit DeprecationWarning."""
        tag_config = TagConfig()
        with pytest.warns(DeprecationWarning, match="TagConfig.available is deprecated"):
            _ = tag_config.available

    def test_accessing_unavailable_property_emits_warning(self) -> None:
        """Accessing TagConfig.unavailable should emit DeprecationWarning."""
        tag_config = TagConfig()
        with pytest.warns(DeprecationWarning, match="TagConfig.unavailable is deprecated"):
            _ = tag_config.unavailable

    def test_setting_available_property_emits_warning(self) -> None:
        """Setting TagConfig.available should emit DeprecationWarning."""
        tag_config = TagConfig()
        with pytest.warns(DeprecationWarning, match="TagConfig.available is deprecated"):
            tag_config.available = "custom-available"

    def test_setting_unavailable_property_emits_warning(self) -> None:
        """Setting TagConfig.unavailable should emit DeprecationWarning."""
        tag_config = TagConfig()
        with pytest.warns(DeprecationWarning, match="TagConfig.unavailable is deprecated"):
            tag_config.unavailable = "custom-unavailable"

    def test_available_returns_default_value_from_pattern(self) -> None:
        """TagConfig.available should return value formatted from pattern_available."""
        tag_config = TagConfig(pattern_available="{criteria}-is-ready")
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            assert tag_config.available == "4k-is-ready"

    def test_unavailable_returns_default_value_from_pattern(self) -> None:
        """TagConfig.unavailable should return value formatted from pattern_unavailable."""
        tag_config = TagConfig(pattern_unavailable="{criteria}-not-ready")
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            assert tag_config.unavailable == "4k-not-ready"

    def test_available_returns_legacy_value_when_set(self) -> None:
        """TagConfig.available should return legacy value when _available is set."""
        tag_config = TagConfig(_available="legacy-4k-available")
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            assert tag_config.available == "legacy-4k-available"

    def test_unavailable_returns_legacy_value_when_set(self) -> None:
        """TagConfig.unavailable should return legacy value when _unavailable is set."""
        tag_config = TagConfig(_unavailable="legacy-4k-unavailable")
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            assert tag_config.unavailable == "legacy-4k-unavailable"

    def test_setting_available_stores_in_private_field(self) -> None:
        """Setting available property should store value in _available."""
        tag_config = TagConfig()
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            tag_config.available = "my-custom-tag"
            assert tag_config._available == "my-custom-tag"
            assert tag_config.available == "my-custom-tag"

    def test_setting_unavailable_stores_in_private_field(self) -> None:
        """Setting unavailable property should store value in _unavailable."""
        tag_config = TagConfig()
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            tag_config.unavailable = "my-custom-unavailable-tag"
            assert tag_config._unavailable == "my-custom-unavailable-tag"
            assert tag_config.unavailable == "my-custom-unavailable-tag"

    def test_get_tag_names_does_not_emit_warnings(self) -> None:
        """get_tag_names() should not emit deprecation warnings."""
        tag_config = TagConfig()
        with warnings.catch_warnings():
            warnings.simplefilter("error", DeprecationWarning)
            # This should not raise any DeprecationWarning
            available, unavailable = tag_config.get_tag_names("4k")
            assert available == "4k-available"
            assert unavailable == "4k-unavailable"


class TestTagConfigDeprecationFromToml:
    """Tests for deprecation warnings when loading legacy config from TOML."""

    def test_legacy_available_in_toml_emits_warning(self, tmp_path: Path) -> None:
        """Using 'available' key in TOML should emit DeprecationWarning."""
        config_dir = tmp_path / ".config" / "filtarr"
        config_dir.mkdir(parents=True)
        config_file = config_dir / "config.toml"
        config_file.write_text("""
[tags]
available = "custom-4k-available"
""")

        with (
            patch.object(Path, "home", return_value=tmp_path),
            patch.dict(os.environ, {}, clear=True),
            pytest.warns(DeprecationWarning, match="tags.available.*deprecated"),
        ):
            config = Config.load()

        # Verify the legacy value is stored correctly
        assert config.tags._available == "custom-4k-available"

    def test_legacy_unavailable_in_toml_emits_warning(self, tmp_path: Path) -> None:
        """Using 'unavailable' key in TOML should emit DeprecationWarning."""
        config_dir = tmp_path / ".config" / "filtarr"
        config_dir.mkdir(parents=True)
        config_file = config_dir / "config.toml"
        config_file.write_text("""
[tags]
unavailable = "custom-4k-unavailable"
""")

        with (
            patch.object(Path, "home", return_value=tmp_path),
            patch.dict(os.environ, {}, clear=True),
            pytest.warns(DeprecationWarning, match="tags.unavailable.*deprecated"),
        ):
            config = Config.load()

        # Verify the legacy value is stored correctly
        assert config.tags._unavailable == "custom-4k-unavailable"

    def test_legacy_both_fields_in_toml_emit_warnings(self, tmp_path: Path) -> None:
        """Using both legacy keys in TOML should emit two DeprecationWarnings."""
        config_dir = tmp_path / ".config" / "filtarr"
        config_dir.mkdir(parents=True)
        config_file = config_dir / "config.toml"
        config_file.write_text("""
[tags]
available = "legacy-available"
unavailable = "legacy-unavailable"
""")

        with (
            patch.object(Path, "home", return_value=tmp_path),
            patch.dict(os.environ, {}, clear=True),
            warnings.catch_warnings(record=True) as caught_warnings,
        ):
            warnings.simplefilter("always", DeprecationWarning)
            config = Config.load()

        # Should have caught both deprecation warnings
        deprecation_warnings = [
            w for w in caught_warnings if issubclass(w.category, DeprecationWarning)
        ]
        assert len(deprecation_warnings) == 2

        # Verify values are stored
        assert config.tags._available == "legacy-available"
        assert config.tags._unavailable == "legacy-unavailable"

    def test_new_pattern_fields_do_not_emit_warnings(self, tmp_path: Path) -> None:
        """Using pattern_available/pattern_unavailable should not emit warnings."""
        config_dir = tmp_path / ".config" / "filtarr"
        config_dir.mkdir(parents=True)
        config_file = config_dir / "config.toml"
        config_file.write_text("""
[tags]
pattern_available = "{criteria}-is-available"
pattern_unavailable = "{criteria}-is-unavailable"
""")

        with (
            patch.object(Path, "home", return_value=tmp_path),
            patch.dict(os.environ, {}, clear=True),
            warnings.catch_warnings(),
        ):
            warnings.simplefilter("error", DeprecationWarning)
            # Should not raise DeprecationWarning
            config = Config.load()

        assert config.tags.pattern_available == "{criteria}-is-available"
        assert config.tags.pattern_unavailable == "{criteria}-is-unavailable"


class TestTagConfigDeprecationFromEnv:
    """Tests for deprecation warnings when loading legacy config from environment."""

    def test_legacy_filtarr_tag_available_env_emits_warning(self, tmp_path: Path) -> None:
        """Using FILTARR_TAG_AVAILABLE should emit DeprecationWarning."""
        with (
            patch.object(Path, "home", return_value=tmp_path),
            patch.dict(
                os.environ,
                {"FILTARR_TAG_AVAILABLE": "env-custom-available"},
                clear=True,
            ),
            pytest.warns(DeprecationWarning, match="FILTARR_TAG_AVAILABLE.*deprecated"),
        ):
            config = Config.load()

        assert config.tags._available == "env-custom-available"

    def test_legacy_filtarr_tag_unavailable_env_emits_warning(self, tmp_path: Path) -> None:
        """Using FILTARR_TAG_UNAVAILABLE should emit DeprecationWarning."""
        with (
            patch.object(Path, "home", return_value=tmp_path),
            patch.dict(
                os.environ,
                {"FILTARR_TAG_UNAVAILABLE": "env-custom-unavailable"},
                clear=True,
            ),
            pytest.warns(DeprecationWarning, match="FILTARR_TAG_UNAVAILABLE.*deprecated"),
        ):
            config = Config.load()

        assert config.tags._unavailable == "env-custom-unavailable"

    def test_legacy_both_env_vars_emit_warnings(self, tmp_path: Path) -> None:
        """Using both legacy env vars should emit two DeprecationWarnings."""
        with (
            patch.object(Path, "home", return_value=tmp_path),
            patch.dict(
                os.environ,
                {
                    "FILTARR_TAG_AVAILABLE": "env-available",
                    "FILTARR_TAG_UNAVAILABLE": "env-unavailable",
                },
                clear=True,
            ),
            warnings.catch_warnings(record=True) as caught_warnings,
        ):
            warnings.simplefilter("always", DeprecationWarning)
            config = Config.load()

        deprecation_warnings = [
            w for w in caught_warnings if issubclass(w.category, DeprecationWarning)
        ]
        assert len(deprecation_warnings) == 2

        assert config.tags._available == "env-available"
        assert config.tags._unavailable == "env-unavailable"

    def test_new_pattern_env_vars_do_not_emit_warnings(self, tmp_path: Path) -> None:
        """Using FILTARR_TAG_PATTERN_* env vars should not emit warnings."""
        with (
            patch.object(Path, "home", return_value=tmp_path),
            patch.dict(
                os.environ,
                {
                    "FILTARR_TAG_PATTERN_AVAILABLE": "{criteria}-env-available",
                    "FILTARR_TAG_PATTERN_UNAVAILABLE": "{criteria}-env-unavailable",
                },
                clear=True,
            ),
            warnings.catch_warnings(),
        ):
            warnings.simplefilter("error", DeprecationWarning)
            # Should not raise DeprecationWarning
            config = Config.load()

        assert config.tags.pattern_available == "{criteria}-env-available"
        assert config.tags.pattern_unavailable == "{criteria}-env-unavailable"


class TestTagConfigBackwardCompatibility:
    """Tests to ensure backward compatibility with legacy TagConfig usage."""

    def test_legacy_code_still_works_with_warnings(self) -> None:
        """Legacy code accessing .available/.unavailable should still work."""
        tag_config = TagConfig()

        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            # This simulates legacy code that accesses these properties
            available_tag = tag_config.available
            unavailable_tag = tag_config.unavailable

        assert available_tag == "4k-available"
        assert unavailable_tag == "4k-unavailable"

    def test_legacy_code_with_custom_pattern_still_works(self) -> None:
        """Legacy code works when pattern_available/unavailable are customized."""
        tag_config = TagConfig(
            pattern_available="has-{criteria}",
            pattern_unavailable="missing-{criteria}",
        )

        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            available_tag = tag_config.available
            unavailable_tag = tag_config.unavailable

        # Should return pattern formatted with "4k"
        assert available_tag == "has-4k"
        assert unavailable_tag == "missing-4k"

    def test_legacy_toml_config_loads_values_correctly(self, tmp_path: Path) -> None:
        """Legacy TOML config with available/unavailable loads correctly."""
        config_dir = tmp_path / ".config" / "filtarr"
        config_dir.mkdir(parents=True)
        config_file = config_dir / "config.toml"
        config_file.write_text("""
[tags]
available = "my-legacy-available"
unavailable = "my-legacy-unavailable"
""")

        with (
            patch.object(Path, "home", return_value=tmp_path),
            patch.dict(os.environ, {}, clear=True),
            warnings.catch_warnings(),
        ):
            warnings.simplefilter("ignore", DeprecationWarning)
            config = Config.load()
            # Accessing legacy properties still works
            available = config.tags.available
            unavailable = config.tags.unavailable

        assert available == "my-legacy-available"
        assert unavailable == "my-legacy-unavailable"

    def test_legacy_env_config_loads_values_correctly(self, tmp_path: Path) -> None:
        """Legacy env vars FILTARR_TAG_AVAILABLE/UNAVAILABLE load correctly."""
        with (
            patch.object(Path, "home", return_value=tmp_path),
            patch.dict(
                os.environ,
                {
                    "FILTARR_TAG_AVAILABLE": "env-legacy-available",
                    "FILTARR_TAG_UNAVAILABLE": "env-legacy-unavailable",
                },
                clear=True,
            ),
            warnings.catch_warnings(),
        ):
            warnings.simplefilter("ignore", DeprecationWarning)
            config = Config.load()
            available = config.tags.available
            unavailable = config.tags.unavailable

        assert available == "env-legacy-available"
        assert unavailable == "env-legacy-unavailable"


class TestLoggingConfig:
    """Tests for LoggingConfig validation."""

    def test_valid_log_level_debug(self) -> None:
        """LoggingConfig should accept DEBUG level."""
        config = LoggingConfig(level="DEBUG")
        assert config.level == "DEBUG"

    def test_valid_log_level_info(self) -> None:
        """LoggingConfig should accept INFO level."""
        config = LoggingConfig(level="INFO")
        assert config.level == "INFO"

    def test_valid_log_level_warning(self) -> None:
        """LoggingConfig should accept WARNING level."""
        config = LoggingConfig(level="WARNING")
        assert config.level == "WARNING"

    def test_valid_log_level_error(self) -> None:
        """LoggingConfig should accept ERROR level."""
        config = LoggingConfig(level="ERROR")
        assert config.level == "ERROR"

    def test_valid_log_level_critical(self) -> None:
        """LoggingConfig should accept CRITICAL level."""
        config = LoggingConfig(level="CRITICAL")
        assert config.level == "CRITICAL"

    def test_log_level_case_insensitive(self) -> None:
        """LoggingConfig should normalize log level to uppercase."""
        config = LoggingConfig(level="debug")
        assert config.level == "DEBUG"

        config = LoggingConfig(level="Info")
        assert config.level == "INFO"

    def test_invalid_log_level_raises_error(self) -> None:
        """LoggingConfig should raise ConfigurationError for invalid log level."""
        with pytest.raises(ConfigurationError, match="Invalid log level"):
            LoggingConfig(level="INVALID")

    def test_invalid_log_level_includes_valid_options_in_message(self) -> None:
        """Error message should include valid log level options."""
        with pytest.raises(ConfigurationError) as exc_info:
            LoggingConfig(level="TRACE")
        assert "DEBUG" in str(exc_info.value)
        assert "INFO" in str(exc_info.value)
        assert "WARNING" in str(exc_info.value)
        assert "ERROR" in str(exc_info.value)
        assert "CRITICAL" in str(exc_info.value)

    def test_default_log_level_is_info(self) -> None:
        """LoggingConfig default level should be INFO."""
        config = LoggingConfig()
        assert config.level == "INFO"


class TestLoggingConfigFromToml:
    """Tests for loading LoggingConfig from TOML file."""

    def test_load_log_level_from_file(self, tmp_path: Path) -> None:
        """Should load log level from TOML file."""
        config_dir = tmp_path / ".config" / "filtarr"
        config_dir.mkdir(parents=True)
        config_file = config_dir / "config.toml"
        config_file.write_text("""
[logging]
level = "DEBUG"
""")

        with (
            patch.object(Path, "home", return_value=tmp_path),
            patch.dict(os.environ, {}, clear=True),
        ):
            config = Config.load()

        assert config.logging.level == "DEBUG"

    def test_load_log_level_warning_from_file(self, tmp_path: Path) -> None:
        """Should load WARNING log level from TOML file."""
        config_dir = tmp_path / ".config" / "filtarr"
        config_dir.mkdir(parents=True)
        config_file = config_dir / "config.toml"
        config_file.write_text("""
[logging]
level = "WARNING"
""")

        with (
            patch.object(Path, "home", return_value=tmp_path),
            patch.dict(os.environ, {}, clear=True),
        ):
            config = Config.load()

        assert config.logging.level == "WARNING"

    def test_empty_logging_section_uses_default(self, tmp_path: Path) -> None:
        """Empty logging section should use default INFO level."""
        config_dir = tmp_path / ".config" / "filtarr"
        config_dir.mkdir(parents=True)
        config_file = config_dir / "config.toml"
        config_file.write_text("""
[logging]
""")

        with (
            patch.object(Path, "home", return_value=tmp_path),
            patch.dict(os.environ, {}, clear=True),
        ):
            config = Config.load()

        assert config.logging.level == "INFO"

    def test_missing_logging_section_uses_default(self, tmp_path: Path) -> None:
        """Missing logging section should use default INFO level."""
        config_dir = tmp_path / ".config" / "filtarr"
        config_dir.mkdir(parents=True)
        config_file = config_dir / "config.toml"
        config_file.write_text("""
[radarr]
url = "http://localhost:7878"
api_key = "test-key"
""")

        with (
            patch.object(Path, "home", return_value=tmp_path),
            patch.dict(os.environ, {}, clear=True),
        ):
            config = Config.load()

        assert config.logging.level == "INFO"

    def test_invalid_log_level_in_file_raises_error(self, tmp_path: Path) -> None:
        """Invalid log level in TOML file should raise ConfigurationError."""
        config_dir = tmp_path / ".config" / "filtarr"
        config_dir.mkdir(parents=True)
        config_file = config_dir / "config.toml"
        config_file.write_text("""
[logging]
level = "VERBOSE"
""")

        with (
            patch.object(Path, "home", return_value=tmp_path),
            patch.dict(os.environ, {}, clear=True),
            pytest.raises(ConfigurationError, match="Invalid log level"),
        ):
            Config.load()


class TestLoggingConfigFromEnv:
    """Tests for loading LoggingConfig from environment variables."""

    def test_log_level_from_env(self, tmp_path: Path) -> None:
        """Should load log level from FILTARR_LOG_LEVEL environment variable."""
        with (
            patch.object(Path, "home", return_value=tmp_path),
            patch.dict(
                os.environ,
                {"FILTARR_LOG_LEVEL": "DEBUG"},
                clear=True,
            ),
        ):
            config = Config.load()

        assert config.logging.level == "DEBUG"

    def test_log_level_warning_from_env(self, tmp_path: Path) -> None:
        """Should load WARNING level from FILTARR_LOG_LEVEL."""
        with (
            patch.object(Path, "home", return_value=tmp_path),
            patch.dict(
                os.environ,
                {"FILTARR_LOG_LEVEL": "WARNING"},
                clear=True,
            ),
        ):
            config = Config.load()

        assert config.logging.level == "WARNING"

    def test_log_level_case_insensitive_from_env(self, tmp_path: Path) -> None:
        """FILTARR_LOG_LEVEL should be case insensitive."""
        with (
            patch.object(Path, "home", return_value=tmp_path),
            patch.dict(
                os.environ,
                {"FILTARR_LOG_LEVEL": "error"},
                clear=True,
            ),
        ):
            config = Config.load()

        assert config.logging.level == "ERROR"

    def test_invalid_log_level_from_env_raises_error(self, tmp_path: Path) -> None:
        """Invalid log level from env should raise ConfigurationError."""
        with (
            patch.object(Path, "home", return_value=tmp_path),
            patch.dict(
                os.environ,
                {"FILTARR_LOG_LEVEL": "TRACE"},
                clear=True,
            ),
            pytest.raises(ConfigurationError, match="Invalid log level"),
        ):
            Config.load()


class TestLoggingConfigEnvOverridesFile:
    """Tests for environment variable overriding file config for logging."""

    def test_env_log_level_overrides_file(self, tmp_path: Path) -> None:
        """FILTARR_LOG_LEVEL should override logging.level from file."""
        config_dir = tmp_path / ".config" / "filtarr"
        config_dir.mkdir(parents=True)
        config_file = config_dir / "config.toml"
        config_file.write_text("""
[logging]
level = "WARNING"
""")

        with (
            patch.object(Path, "home", return_value=tmp_path),
            patch.dict(
                os.environ,
                {"FILTARR_LOG_LEVEL": "DEBUG"},
                clear=True,
            ),
        ):
            config = Config.load()

        assert config.logging.level == "DEBUG"

    def test_env_log_level_overrides_default_when_no_file(self, tmp_path: Path) -> None:
        """FILTARR_LOG_LEVEL should override default when no file exists."""
        with (
            patch.object(Path, "home", return_value=tmp_path),
            patch.dict(
                os.environ,
                {"FILTARR_LOG_LEVEL": "CRITICAL"},
                clear=True,
            ),
        ):
            config = Config.load()

        assert config.logging.level == "CRITICAL"

    def test_file_used_when_env_not_set(self, tmp_path: Path) -> None:
        """File config should be used when env var is not set."""
        config_dir = tmp_path / ".config" / "filtarr"
        config_dir.mkdir(parents=True)
        config_file = config_dir / "config.toml"
        config_file.write_text("""
[logging]
level = "ERROR"
""")

        with (
            patch.object(Path, "home", return_value=tmp_path),
            patch.dict(os.environ, {}, clear=True),
        ):
            config = Config.load()

        assert config.logging.level == "ERROR"


class TestStateConfigValidation:
    """Tests for StateConfig validation."""

    def test_valid_ttl_hours_zero(self) -> None:
        """StateConfig should accept ttl_hours=0 (disables TTL caching)."""
        from filtarr.config import StateConfig

        config = StateConfig(ttl_hours=0)
        assert config.ttl_hours == 0

    def test_valid_ttl_hours_positive(self) -> None:
        """StateConfig should accept positive ttl_hours values."""
        from filtarr.config import StateConfig

        config = StateConfig(ttl_hours=24)
        assert config.ttl_hours == 24

        config = StateConfig(ttl_hours=168)  # 1 week
        assert config.ttl_hours == 168

    def test_negative_ttl_hours_raises_error(self) -> None:
        """StateConfig should raise ConfigurationError for negative ttl_hours."""
        from filtarr.config import StateConfig

        with pytest.raises(ConfigurationError, match="Invalid ttl_hours: -1"):
            StateConfig(ttl_hours=-1)

    def test_negative_ttl_hours_error_message(self) -> None:
        """Error message should indicate value must be 0 or greater."""
        from filtarr.config import StateConfig

        with pytest.raises(ConfigurationError, match="must be 0 or greater"):
            StateConfig(ttl_hours=-24)

    def test_default_ttl_hours_is_valid(self) -> None:
        """Default StateConfig should have valid ttl_hours."""
        from filtarr.config import StateConfig

        config = StateConfig()
        assert config.ttl_hours == 24


class TestStateConfigTtlHoursFromEnv:
    """Tests for FILTARR_STATE_TTL_HOURS environment variable parsing."""

    def test_valid_ttl_hours_from_env(self, tmp_path: Path) -> None:
        """Should parse valid integer from FILTARR_STATE_TTL_HOURS."""
        with (
            patch.object(Path, "home", return_value=tmp_path),
            patch.dict(
                os.environ,
                {"FILTARR_STATE_TTL_HOURS": "48"},
                clear=True,
            ),
        ):
            config = Config.load()

        assert config.state.ttl_hours == 48

    def test_zero_ttl_hours_from_env(self, tmp_path: Path) -> None:
        """Should parse zero from FILTARR_STATE_TTL_HOURS."""
        with (
            patch.object(Path, "home", return_value=tmp_path),
            patch.dict(
                os.environ,
                {"FILTARR_STATE_TTL_HOURS": "0"},
                clear=True,
            ),
        ):
            config = Config.load()

        assert config.state.ttl_hours == 0

    def test_invalid_ttl_hours_from_env_raises_error(self, tmp_path: Path) -> None:
        """Should raise ConfigurationError for non-integer FILTARR_STATE_TTL_HOURS."""
        with (
            patch.object(Path, "home", return_value=tmp_path),
            patch.dict(
                os.environ,
                {"FILTARR_STATE_TTL_HOURS": "not-a-number"},
                clear=True,
            ),
            pytest.raises(ConfigurationError, match="Invalid FILTARR_STATE_TTL_HOURS"),
        ):
            Config.load()

    def test_invalid_ttl_hours_error_includes_value(self, tmp_path: Path) -> None:
        """Error message should include the invalid value."""
        with (
            patch.object(Path, "home", return_value=tmp_path),
            patch.dict(
                os.environ,
                {"FILTARR_STATE_TTL_HOURS": "abc123"},
                clear=True,
            ),
            pytest.raises(ConfigurationError, match="'abc123'"),
        ):
            Config.load()

    def test_invalid_ttl_hours_error_mentions_integer(self, tmp_path: Path) -> None:
        """Error message should mention value must be a valid integer."""
        with (
            patch.object(Path, "home", return_value=tmp_path),
            patch.dict(
                os.environ,
                {"FILTARR_STATE_TTL_HOURS": "12.5"},
                clear=True,
            ),
            pytest.raises(ConfigurationError, match="must be a valid integer"),
        ):
            Config.load()

    def test_negative_ttl_hours_from_env_raises_error(self, tmp_path: Path) -> None:
        """Should raise ConfigurationError for negative FILTARR_STATE_TTL_HOURS."""
        with (
            patch.object(Path, "home", return_value=tmp_path),
            patch.dict(
                os.environ,
                {"FILTARR_STATE_TTL_HOURS": "-5"},
                clear=True,
            ),
            pytest.raises(ConfigurationError, match="Invalid ttl_hours: -5"),
        ):
            Config.load()

    def test_ttl_hours_env_overrides_file(self, tmp_path: Path) -> None:
        """FILTARR_STATE_TTL_HOURS should override file config."""
        config_dir = tmp_path / ".config" / "filtarr"
        config_dir.mkdir(parents=True)
        config_file = config_dir / "config.toml"
        config_file.write_text("""
[state]
ttl_hours = 24
""")

        with (
            patch.object(Path, "home", return_value=tmp_path),
            patch.dict(
                os.environ,
                {"FILTARR_STATE_TTL_HOURS": "72"},
                clear=True,
            ),
        ):
            config = Config.load()

        assert config.state.ttl_hours == 72


class TestConfigDirectoryDetection:
    """Tests for configuration directory detection including Docker paths."""

    def test_docker_config_path_detection_via_get_config_base_path(self, tmp_path: Path) -> None:
        """Should use _get_config_base_path for Docker config directory detection."""
        # Create a fake config directory to simulate Docker environment
        docker_config_dir = tmp_path / "docker_config"
        docker_config_dir.mkdir(parents=True)
        config_file = docker_config_dir / "config.toml"
        config_file.write_text("""
[radarr]
url = "http://localhost:7878"
api_key = "docker-key"
""")

        # Mock the _get_config_base_path function to return our test directory
        with (
            patch("filtarr.config._get_config_base_path", return_value=docker_config_dir),
            patch.dict(os.environ, {}, clear=True),
        ):
            config = Config.load()

        assert config.radarr is not None
        assert config.radarr.api_key == "docker-key"

    def test_filtarr_config_dir_env_var_override(self, tmp_path: Path) -> None:
        """FILTARR_CONFIG_DIR should override default config directory."""
        custom_config_dir = tmp_path / "custom_config"
        custom_config_dir.mkdir(parents=True)
        config_file = custom_config_dir / "config.toml"
        config_file.write_text("""
[radarr]
url = "http://localhost:7878"
api_key = "custom-config-dir-key"
""")

        with (
            patch.object(Path, "home", return_value=tmp_path / "wrong_home"),
            patch.dict(
                os.environ,
                {"FILTARR_CONFIG_DIR": str(custom_config_dir)},
                clear=True,
            ),
        ):
            config = Config.load()

        assert config.radarr is not None
        assert config.radarr.api_key == "custom-config-dir-key"

    def test_filtarr_config_dir_takes_priority_via_env(self, tmp_path: Path) -> None:
        """FILTARR_CONFIG_DIR env var takes priority over all other config paths."""
        # Create a home config
        home_config_dir = tmp_path / ".config" / "filtarr"
        home_config_dir.mkdir(parents=True)
        home_config_file = home_config_dir / "config.toml"
        home_config_file.write_text("""
[radarr]
url = "http://localhost:7878"
api_key = "home-key"
""")

        # Create custom config dir
        custom_config_dir = tmp_path / "custom_config"
        custom_config_dir.mkdir(parents=True)
        custom_config_file = custom_config_dir / "config.toml"
        custom_config_file.write_text("""
[radarr]
url = "http://localhost:7878"
api_key = "custom-key"
""")

        # FILTARR_CONFIG_DIR should win over home config
        with (
            patch.object(Path, "home", return_value=tmp_path),
            patch.dict(
                os.environ,
                {"FILTARR_CONFIG_DIR": str(custom_config_dir)},
                clear=True,
            ),
        ):
            config = Config.load()

        assert config.radarr is not None
        assert config.radarr.api_key == "custom-key"

    def test_filtarr_config_dir_with_nonexistent_path(self, tmp_path: Path) -> None:
        """FILTARR_CONFIG_DIR pointing to nonexistent path should fallback gracefully."""
        with (
            patch.object(Path, "home", return_value=tmp_path),
            patch.dict(
                os.environ,
                {"FILTARR_CONFIG_DIR": "/nonexistent/config/path"},
                clear=True,
            ),
        ):
            # Should not raise, just use defaults
            config = Config.load()

        # Should have no Radarr/Sonarr configured since no config file exists
        assert config.radarr is None
        assert config.sonarr is None

    def test_default_home_config_path_used(self, tmp_path: Path) -> None:
        """Default ~/.config/filtarr path should be used when no overrides."""
        config_dir = tmp_path / ".config" / "filtarr"
        config_dir.mkdir(parents=True)
        config_file = config_dir / "config.toml"
        config_file.write_text("""
[radarr]
url = "http://localhost:7878"
api_key = "home-config-key"
""")

        with (
            patch.object(Path, "home", return_value=tmp_path),
            patch.dict(os.environ, {}, clear=True),
        ):
            config = Config.load()

        assert config.radarr is not None
        assert config.radarr.api_key == "home-config-key"


class TestLoggingConfigFields:
    """Tests for LoggingConfig timestamps and output_format fields."""

    def test_logging_config_has_timestamps_field(self) -> None:
        """LoggingConfig should have timestamps field defaulting to True."""
        config = LoggingConfig()
        assert config.timestamps is True

    def test_logging_config_has_output_format_field(self) -> None:
        """LoggingConfig should have output_format field defaulting to 'text'."""
        config = LoggingConfig()
        assert config.output_format == "text"

    def test_logging_config_output_format_validation(self) -> None:
        """LoggingConfig should validate output_format values."""
        # Valid values
        LoggingConfig(output_format="text")
        LoggingConfig(output_format="json")

        # Invalid value
        with pytest.raises(ConfigurationError):
            LoggingConfig(output_format="xml")

    def test_logging_config_output_format_case_insensitive(self) -> None:
        """output_format should be case insensitive."""
        config = LoggingConfig(output_format="JSON")
        assert config.output_format == "json"

    def test_logging_config_timestamps_can_be_set_false(self) -> None:
        """LoggingConfig should allow timestamps to be set to False."""
        config = LoggingConfig(timestamps=False)
        assert config.timestamps is False

    def test_logging_config_output_format_text_normalized(self) -> None:
        """output_format 'TEXT' should be normalized to 'text'."""
        config = LoggingConfig(output_format="TEXT")
        assert config.output_format == "text"

    def test_logging_config_invalid_output_format_error_message(self) -> None:
        """Error message should include valid output format options."""
        with pytest.raises(ConfigurationError) as exc_info:
            LoggingConfig(output_format="yaml")
        assert "json" in str(exc_info.value)
        assert "text" in str(exc_info.value)

    def test_logging_config_from_toml_with_timestamps(self, tmp_path: Path) -> None:
        """Should load timestamps from TOML file."""
        config_dir = tmp_path / ".config" / "filtarr"
        config_dir.mkdir(parents=True)
        config_file = config_dir / "config.toml"
        config_file.write_text("""
[logging]
level = "INFO"
timestamps = false
""")

        with (
            patch.object(Path, "home", return_value=tmp_path),
            patch.dict(os.environ, {}, clear=True),
        ):
            config = Config.load()

        assert config.logging.timestamps is False

    def test_logging_config_from_toml_with_output_format(self, tmp_path: Path) -> None:
        """Should load output_format from TOML file."""
        config_dir = tmp_path / ".config" / "filtarr"
        config_dir.mkdir(parents=True)
        config_file = config_dir / "config.toml"
        config_file.write_text("""
[logging]
level = "INFO"
output_format = "json"
""")

        with (
            patch.object(Path, "home", return_value=tmp_path),
            patch.dict(os.environ, {}, clear=True),
        ):
            config = Config.load()

        assert config.logging.output_format == "json"

    def test_logging_config_from_env_timestamps(self, tmp_path: Path) -> None:
        """Should load timestamps from FILTARR_LOG_TIMESTAMPS env var."""
        with (
            patch.object(Path, "home", return_value=tmp_path),
            patch.dict(
                os.environ,
                {"FILTARR_LOG_TIMESTAMPS": "false"},
                clear=True,
            ),
        ):
            config = Config.load()

        assert config.logging.timestamps is False

    def test_logging_config_from_env_output_format(self, tmp_path: Path) -> None:
        """Should load output_format from FILTARR_LOG_OUTPUT_FORMAT env var."""
        with (
            patch.object(Path, "home", return_value=tmp_path),
            patch.dict(
                os.environ,
                {"FILTARR_LOG_OUTPUT_FORMAT": "json"},
                clear=True,
            ),
        ):
            config = Config.load()

        assert config.logging.output_format == "json"

    def test_logging_config_env_overrides_file_timestamps(self, tmp_path: Path) -> None:
        """FILTARR_LOG_TIMESTAMPS should override file config."""
        config_dir = tmp_path / ".config" / "filtarr"
        config_dir.mkdir(parents=True)
        config_file = config_dir / "config.toml"
        config_file.write_text("""
[logging]
timestamps = true
""")

        with (
            patch.object(Path, "home", return_value=tmp_path),
            patch.dict(
                os.environ,
                {"FILTARR_LOG_TIMESTAMPS": "false"},
                clear=True,
            ),
        ):
            config = Config.load()

        assert config.logging.timestamps is False

    def test_logging_config_env_overrides_file_output_format(self, tmp_path: Path) -> None:
        """FILTARR_LOG_OUTPUT_FORMAT should override file config."""
        config_dir = tmp_path / ".config" / "filtarr"
        config_dir.mkdir(parents=True)
        config_file = config_dir / "config.toml"
        config_file.write_text("""
[logging]
output_format = "text"
""")

        with (
            patch.object(Path, "home", return_value=tmp_path),
            patch.dict(
                os.environ,
                {"FILTARR_LOG_OUTPUT_FORMAT": "json"},
                clear=True,
            ),
        ):
            config = Config.load()

        assert config.logging.output_format == "json"
