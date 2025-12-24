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
