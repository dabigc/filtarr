"""Tests for configuration loading."""

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from filtarr.config import Config, ConfigurationError, RadarrConfig, SonarrConfig, TagConfig


class TestConfigFromEnv:
    """Tests for loading config from environment variables."""

    def test_load_radarr_from_env(self) -> None:
        """Should load Radarr config from environment."""
        with patch.dict(
            os.environ,
            {
                "FILTARR_RADARR_URL": "http://radarr:7878",
                "FILTARR_RADARR_API_KEY": "test-key",
            },
            clear=False,
        ):
            config = Config.load()

        assert config.radarr is not None
        assert config.radarr.url == "http://radarr:7878"
        assert config.radarr.api_key == "test-key"

    def test_load_sonarr_from_env(self) -> None:
        """Should load Sonarr config from environment."""
        with patch.dict(
            os.environ,
            {
                "FILTARR_SONARR_URL": "http://sonarr:8989",
                "FILTARR_SONARR_API_KEY": "sonarr-key",
            },
            clear=False,
        ):
            config = Config.load()

        assert config.sonarr is not None
        assert config.sonarr.url == "http://sonarr:8989"
        assert config.sonarr.api_key == "sonarr-key"

    def test_partial_env_vars_ignored(self, tmp_path: Path) -> None:
        """Should ignore partial config (only URL, no key)."""
        # Use tmp_path for home to avoid loading real config file
        with (
            patch.object(Path, "home", return_value=tmp_path),
            patch.dict(
                os.environ,
                {"FILTARR_RADARR_URL": "http://radarr:7878"},
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
url = "http://radarr:7878"
api_key = "file-radarr-key"

[sonarr]
url = "http://sonarr:8989"
api_key = "file-sonarr-key"
""")

        with (
            patch.object(Path, "home", return_value=tmp_path),
            patch.dict(os.environ, {}, clear=True),
        ):
            config = Config.load()

        assert config.radarr is not None
        assert config.radarr.url == "http://radarr:7878"
        assert config.radarr.api_key == "file-radarr-key"
        assert config.sonarr is not None
        assert config.sonarr.url == "http://sonarr:8989"

    def test_env_overrides_file(self, tmp_path: Path) -> None:
        """Environment variables should override file config."""
        config_dir = tmp_path / ".config" / "filtarr"
        config_dir.mkdir(parents=True)
        config_file = config_dir / "config.toml"
        config_file.write_text("""
[radarr]
url = "http://file-url:7878"
api_key = "file-key"
""")

        with (
            patch.object(Path, "home", return_value=tmp_path),
            patch.dict(
                os.environ,
                {
                    "FILTARR_RADARR_URL": "http://env-url:7878",
                    "FILTARR_RADARR_API_KEY": "env-key",
                },
                clear=True,
            ),
        ):
            config = Config.load()

        assert config.radarr is not None
        assert config.radarr.url == "http://env-url:7878"
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
        config = Config(radarr=RadarrConfig(url="http://test", api_key="key"))
        radarr = config.require_radarr()
        assert radarr.url == "http://test"

    def test_require_radarr_when_not_configured(self) -> None:
        """Should raise ConfigurationError when Radarr not configured."""
        config = Config()
        with pytest.raises(ConfigurationError, match="Radarr is not configured"):
            config.require_radarr()

    def test_require_sonarr_when_configured(self) -> None:
        """Should return SonarrConfig when configured."""
        config = Config(sonarr=SonarrConfig(url="http://test", api_key="key"))
        sonarr = config.require_sonarr()
        assert sonarr.url == "http://test"

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
url = "http://radarr:7878"
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
url = "http://sonarr:8989"
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
url = "http://sonarr:8989"
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
