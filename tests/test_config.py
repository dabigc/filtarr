"""Tests for configuration loading."""

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from findarr.config import Config, ConfigurationError, RadarrConfig, SonarrConfig


class TestConfigFromEnv:
    """Tests for loading config from environment variables."""

    def test_load_radarr_from_env(self) -> None:
        """Should load Radarr config from environment."""
        with patch.dict(
            os.environ,
            {
                "FINDARR_RADARR_URL": "http://radarr:7878",
                "FINDARR_RADARR_API_KEY": "test-key",
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
                "FINDARR_SONARR_URL": "http://sonarr:8989",
                "FINDARR_SONARR_API_KEY": "sonarr-key",
            },
            clear=False,
        ):
            config = Config.load()

        assert config.sonarr is not None
        assert config.sonarr.url == "http://sonarr:8989"
        assert config.sonarr.api_key == "sonarr-key"

    def test_partial_env_vars_ignored(self) -> None:
        """Should ignore partial config (only URL, no key)."""
        with patch.dict(
            os.environ,
            {"FINDARR_RADARR_URL": "http://radarr:7878"},
            clear=False,
        ):
            # Remove API key if it exists
            env = os.environ.copy()
            env.pop("FINDARR_RADARR_API_KEY", None)
            with patch.dict(os.environ, env, clear=True):
                config = Config.load()

        assert config.radarr is None


class TestConfigFromFile:
    """Tests for loading config from TOML file."""

    def test_load_from_toml_file(self, tmp_path: Path) -> None:
        """Should load config from TOML file."""
        config_dir = tmp_path / ".config" / "findarr"
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
        config_dir = tmp_path / ".config" / "findarr"
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
                    "FINDARR_RADARR_URL": "http://env-url:7878",
                    "FINDARR_RADARR_API_KEY": "env-key",
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
        config_dir = tmp_path / ".config" / "findarr"
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
