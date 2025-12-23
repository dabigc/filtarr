"""Tests for CLI commands."""

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from typer.testing import CliRunner

from findarr.checker import FourKResult, SamplingStrategy
from findarr.cli import app, format_result_json, format_result_simple
from findarr.config import Config, RadarrConfig, SonarrConfig

runner = CliRunner()


def _create_mock_state_manager() -> MagicMock:
    """Create a mock StateManager for testing."""
    mock = MagicMock()
    mock.record_check = MagicMock()
    mock.get_stale_unavailable_items = MagicMock(return_value=[])
    return mock


class TestOutputFormatters:
    """Tests for output formatting functions."""

    def test_format_result_json(self) -> None:
        """Should format result as valid JSON."""
        result = FourKResult(
            item_id=123,
            item_type="movie",
            has_4k=True,
            releases=[],
            episodes_checked=[1, 2],
            seasons_checked=[1, 2],
            strategy_used=SamplingStrategy.RECENT,
        )

        json_str = format_result_json(result)
        data = json.loads(json_str)

        assert data["item_id"] == 123
        assert data["item_type"] == "movie"
        assert data["has_4k"] is True
        assert data["episodes_checked"] == [1, 2]
        assert data["seasons_checked"] == [1, 2]
        assert data["strategy_used"] == "recent"

    def test_format_result_simple_with_4k(self) -> None:
        """Should format as '<type>:<id>: 4K available'."""
        result = FourKResult(item_id=456, item_type="series", has_4k=True)
        assert format_result_simple(result) == "series:456: 4K available"

    def test_format_result_simple_no_4k(self) -> None:
        """Should format as '<type>:<id>: No 4K'."""
        result = FourKResult(item_id=789, item_type="movie", has_4k=False)
        assert format_result_simple(result) == "movie:789: No 4K"


class TestCheckMovieCommand:
    """Tests for 'findarr check movie' command."""

    def test_check_movie_with_4k(self) -> None:
        """Should exit 0 when 4K is available."""
        mock_result = FourKResult(item_id=123, item_type="movie", has_4k=True)
        mock_config = Config(radarr=RadarrConfig(url="http://test", api_key="key"))

        async def mock_check_movie(_movie_id: int, **_kwargs: object) -> FourKResult:
            return mock_result

        mock_checker = MagicMock()
        mock_checker.check_movie = mock_check_movie
        mock_state_manager = _create_mock_state_manager()

        with (
            patch("findarr.cli.Config.load", return_value=mock_config),
            patch("findarr.cli.get_checker", return_value=mock_checker),
            patch("findarr.cli.get_state_manager", return_value=mock_state_manager),
        ):
            result = runner.invoke(app, ["check", "movie", "123", "--format", "simple"])

        assert result.exit_code == 0
        assert "4K available" in result.output

    def test_check_movie_no_4k(self) -> None:
        """Should exit 1 when no 4K available."""
        mock_result = FourKResult(item_id=123, item_type="movie", has_4k=False)
        mock_config = Config(radarr=RadarrConfig(url="http://test", api_key="key"))

        async def mock_check_movie(_movie_id: int, **_kwargs: object) -> FourKResult:
            return mock_result

        mock_checker = MagicMock()
        mock_checker.check_movie = mock_check_movie
        mock_state_manager = _create_mock_state_manager()

        with (
            patch("findarr.cli.Config.load", return_value=mock_config),
            patch("findarr.cli.get_checker", return_value=mock_checker),
            patch("findarr.cli.get_state_manager", return_value=mock_state_manager),
        ):
            result = runner.invoke(app, ["check", "movie", "123", "--format", "simple"])

        assert result.exit_code == 1
        assert "No 4K" in result.output

    def test_check_movie_not_configured(self) -> None:
        """Should exit 2 when Radarr not configured."""
        mock_config = Config()  # No Radarr

        with patch("findarr.cli.Config.load", return_value=mock_config):
            result = runner.invoke(app, ["check", "movie", "123"])

        assert result.exit_code == 2


class TestCheckSeriesCommand:
    """Tests for 'findarr check series' command."""

    def test_check_series_with_4k(self) -> None:
        """Should exit 0 when 4K is available."""
        mock_result = FourKResult(
            item_id=456,
            item_type="series",
            has_4k=True,
            strategy_used=SamplingStrategy.RECENT,
        )
        mock_config = Config(sonarr=SonarrConfig(url="http://test", api_key="key"))

        with (
            patch("findarr.cli.Config.load", return_value=mock_config),
            patch("findarr.cli.asyncio.run", return_value=mock_result),
        ):
            result = runner.invoke(app, ["check", "series", "456", "--format", "simple"])

        assert result.exit_code == 0
        assert "4K available" in result.stdout

    def test_check_series_with_strategy_option(self) -> None:
        """Should accept --strategy option."""
        mock_result = FourKResult(
            item_id=456,
            item_type="series",
            has_4k=False,
            strategy_used=SamplingStrategy.DISTRIBUTED,
        )
        mock_config = Config(sonarr=SonarrConfig(url="http://test", api_key="key"))

        with (
            patch("findarr.cli.Config.load", return_value=mock_config),
            patch("findarr.cli.asyncio.run", return_value=mock_result),
        ):
            result = runner.invoke(
                app,
                ["check", "series", "456", "--strategy", "distributed", "--format", "simple"],
            )

        assert result.exit_code == 1

    def test_check_series_invalid_strategy(self) -> None:
        """Should exit 2 for invalid strategy."""
        mock_config = Config(sonarr=SonarrConfig(url="http://test", api_key="key"))

        with patch("findarr.cli.Config.load", return_value=mock_config):
            result = runner.invoke(app, ["check", "series", "456", "--strategy", "invalid"])

        assert result.exit_code == 2


class TestBatchCommand:
    """Tests for 'findarr check batch' command."""

    def test_batch_file_not_found(self) -> None:
        """Should exit 2 when file doesn't exist."""
        result = runner.invoke(app, ["check", "batch", "--file", "/nonexistent/file.txt"])
        assert result.exit_code == 2

    def test_batch_with_valid_file(self, tmp_path: Path) -> None:
        """Should process items from file."""
        batch_file = tmp_path / "items.txt"
        batch_file.write_text("movie:123\nseries:456\n")

        mock_movie_result = FourKResult(item_id=123, item_type="movie", has_4k=True)
        mock_series_result = FourKResult(
            item_id=456,
            item_type="series",
            has_4k=True,
            strategy_used=SamplingStrategy.RECENT,
        )
        mock_config = Config(
            radarr=RadarrConfig(url="http://radarr", api_key="key"),
            sonarr=SonarrConfig(url="http://sonarr", api_key="key"),
        )

        with (
            patch("findarr.cli.Config.load", return_value=mock_config),
            patch("findarr.cli.get_checker") as mock_get_checker,
        ):
            mock_checker = AsyncMock()
            mock_checker.check_movie.return_value = mock_movie_result
            mock_checker.check_series.return_value = mock_series_result
            mock_get_checker.return_value = mock_checker

            result = runner.invoke(
                app,
                ["check", "batch", "--file", str(batch_file), "--format", "simple"],
            )

        assert "Summary:" in result.stdout

    def test_batch_with_comments_and_empty_lines(self, tmp_path: Path) -> None:
        """Should skip comments and empty lines."""
        batch_file = tmp_path / "items.txt"
        batch_file.write_text("# This is a comment\n\nmovie:123\n")

        mock_result = FourKResult(item_id=123, item_type="movie", has_4k=True)
        mock_config = Config(radarr=RadarrConfig(url="http://test", api_key="key"))

        with (
            patch("findarr.cli.Config.load", return_value=mock_config),
            patch("findarr.cli.get_checker") as mock_get_checker,
        ):
            mock_checker = AsyncMock()
            mock_checker.check_movie.return_value = mock_result
            mock_get_checker.return_value = mock_checker

            result = runner.invoke(
                app,
                ["check", "batch", "--file", str(batch_file), "--format", "simple"],
            )

        assert "movie:123: 4K available" in result.stdout


class TestVersionCommand:
    """Tests for version command."""

    def test_version_shows_version(self) -> None:
        """Should show version information."""
        result = runner.invoke(app, ["version"])
        assert result.exit_code == 0
        assert "findarr version" in result.stdout


class TestCheckMovieByName:
    """Tests for 'findarr check movie' with name lookup."""

    def test_check_movie_by_name_single_match(self) -> None:
        """Should use single match when searching by name."""
        mock_result = FourKResult(item_id=123, item_type="movie", has_4k=True)
        mock_config = Config(radarr=RadarrConfig(url="http://test", api_key="key"))

        async def mock_search_movies(_term: str) -> list[tuple[int, str, int]]:
            return [(123, "The Matrix", 1999)]

        async def mock_check_movie(_movie_id: int, **_kwargs: object) -> FourKResult:
            return mock_result

        mock_checker = MagicMock()
        mock_checker.search_movies = mock_search_movies
        mock_checker.check_movie = mock_check_movie
        mock_state_manager = _create_mock_state_manager()

        with (
            patch("findarr.cli.Config.load", return_value=mock_config),
            patch("findarr.cli.get_checker", return_value=mock_checker),
            patch("findarr.cli.get_state_manager", return_value=mock_state_manager),
        ):
            result = runner.invoke(app, ["check", "movie", "The Matrix", "--format", "simple"])

        assert result.exit_code == 0
        assert "4K available" in result.output
        assert "Found: The Matrix" in result.output

    def test_check_movie_by_name_multiple_matches(self) -> None:
        """Should display choices when multiple matches found."""
        mock_config = Config(radarr=RadarrConfig(url="http://test", api_key="key"))

        async def mock_search_movies(_term: str) -> list[tuple[int, str, int]]:
            return [(1, "The Matrix", 1999), (2, "The Matrix Reloaded", 2003)]

        mock_checker = MagicMock()
        mock_checker.search_movies = mock_search_movies
        mock_state_manager = _create_mock_state_manager()

        with (
            patch("findarr.cli.Config.load", return_value=mock_config),
            patch("findarr.cli.get_checker", return_value=mock_checker),
            patch("findarr.cli.get_state_manager", return_value=mock_state_manager),
        ):
            result = runner.invoke(app, ["check", "movie", "Matrix", "--format", "simple"])

        assert result.exit_code == 2
        assert "Multiple movies found" in result.output
        assert "1: The Matrix (1999)" in result.output
        assert "2: The Matrix Reloaded (2003)" in result.output

    def test_check_movie_by_name_not_found(self) -> None:
        """Should exit 2 when movie not found by name."""
        mock_config = Config(radarr=RadarrConfig(url="http://test", api_key="key"))

        async def mock_search_movies(_term: str) -> list[tuple[int, str, int]]:
            return []

        mock_checker = MagicMock()
        mock_checker.search_movies = mock_search_movies
        mock_state_manager = _create_mock_state_manager()

        with (
            patch("findarr.cli.Config.load", return_value=mock_config),
            patch("findarr.cli.get_checker", return_value=mock_checker),
            patch("findarr.cli.get_state_manager", return_value=mock_state_manager),
        ):
            result = runner.invoke(app, ["check", "movie", "Nonexistent", "--format", "simple"])

        assert result.exit_code == 2
        assert "Movie not found" in result.output


class TestCheckSeriesByName:
    """Tests for 'findarr check series' with name lookup."""

    def test_check_series_by_name_single_match(self) -> None:
        """Should use single match when searching by name."""
        mock_result = FourKResult(
            item_id=456,
            item_type="series",
            has_4k=True,
            strategy_used=SamplingStrategy.RECENT,
        )
        mock_config = Config(sonarr=SonarrConfig(url="http://test", api_key="key"))

        async def mock_search_series(_term: str) -> list[tuple[int, str, int]]:
            return [(456, "Breaking Bad", 2008)]

        async def mock_check_series(_series_id: int, **_kwargs: object) -> FourKResult:
            return mock_result

        mock_checker = MagicMock()
        mock_checker.search_series = mock_search_series
        mock_checker.check_series = mock_check_series

        with (
            patch("findarr.cli.Config.load", return_value=mock_config),
            patch("findarr.cli.get_checker", return_value=mock_checker),
        ):
            result = runner.invoke(app, ["check", "series", "Breaking Bad", "--format", "simple"])

        assert result.exit_code == 0
        assert "4K available" in result.output
        assert "Found: Breaking Bad" in result.output

    def test_check_series_by_name_multiple_matches(self) -> None:
        """Should display choices when multiple matches found."""
        mock_config = Config(sonarr=SonarrConfig(url="http://test", api_key="key"))

        async def mock_search_series(_term: str) -> list[tuple[int, str, int]]:
            return [(1, "Breaking Bad", 2008), (2, "Breaking Bad: El Camino", 2019)]

        mock_checker = MagicMock()
        mock_checker.search_series = mock_search_series

        with (
            patch("findarr.cli.Config.load", return_value=mock_config),
            patch("findarr.cli.get_checker", return_value=mock_checker),
        ):
            result = runner.invoke(app, ["check", "series", "Breaking", "--format", "simple"])

        assert result.exit_code == 2
        assert "Multiple series found" in result.output
        assert "1: Breaking Bad (2008)" in result.output

    def test_check_series_by_name_not_found(self) -> None:
        """Should exit 2 when series not found by name."""
        mock_config = Config(sonarr=SonarrConfig(url="http://test", api_key="key"))

        async def mock_search_series(_term: str) -> list[tuple[int, str, int]]:
            return []

        mock_checker = MagicMock()
        mock_checker.search_series = mock_search_series

        with (
            patch("findarr.cli.Config.load", return_value=mock_config),
            patch("findarr.cli.get_checker", return_value=mock_checker),
        ):
            result = runner.invoke(app, ["check", "series", "Nonexistent", "--format", "simple"])

        assert result.exit_code == 2
        assert "Series not found" in result.output


class TestBatchWithNames:
    """Tests for batch command with name-based lookups."""

    def test_batch_with_movie_names(self, tmp_path: Path) -> None:
        """Should process movies by name in batch."""
        batch_file = tmp_path / "items.txt"
        batch_file.write_text("movie:The Matrix\n")

        mock_result = FourKResult(item_id=123, item_type="movie", has_4k=True)
        mock_config = Config(radarr=RadarrConfig(url="http://test", api_key="key"))

        with (
            patch("findarr.cli.Config.load", return_value=mock_config),
            patch("findarr.cli.get_checker") as mock_get_checker,
        ):
            mock_checker = AsyncMock()
            mock_checker.search_movies.return_value = [(123, "The Matrix", 1999)]
            mock_checker.check_movie.return_value = mock_result
            mock_get_checker.return_value = mock_checker

            result = runner.invoke(
                app,
                ["check", "batch", "--file", str(batch_file), "--format", "simple"],
            )

        assert "Found: The Matrix" in result.stdout
        assert "movie:123: 4K available" in result.stdout

    def test_batch_skips_multiple_matches(self, tmp_path: Path) -> None:
        """Should skip items with multiple matches in batch mode."""
        batch_file = tmp_path / "items.txt"
        batch_file.write_text("movie:Matrix\n")

        mock_config = Config(radarr=RadarrConfig(url="http://test", api_key="key"))

        with (
            patch("findarr.cli.Config.load", return_value=mock_config),
            patch("findarr.cli.get_checker") as mock_get_checker,
        ):
            mock_checker = AsyncMock()
            mock_checker.search_movies.return_value = [
                (1, "The Matrix", 1999),
                (2, "The Matrix Reloaded", 2003),
            ]
            mock_get_checker.return_value = mock_checker

            result = runner.invoke(
                app,
                ["check", "batch", "--file", str(batch_file), "--format", "simple"],
                catch_exceptions=False,
            )

        # Warning goes to stderr, check in combined output
        assert "Multiple movies match" in result.output
        # Should show the summary with 0/0
        assert "Summary:" in result.stdout

    def test_batch_skips_not_found(self, tmp_path: Path) -> None:
        """Should skip items that are not found in batch mode."""
        batch_file = tmp_path / "items.txt"
        batch_file.write_text("movie:Nonexistent\n")

        mock_config = Config(radarr=RadarrConfig(url="http://test", api_key="key"))

        with (
            patch("findarr.cli.Config.load", return_value=mock_config),
            patch("findarr.cli.get_checker") as mock_get_checker,
        ):
            mock_checker = AsyncMock()
            mock_checker.search_movies.return_value = []
            mock_get_checker.return_value = mock_checker

            result = runner.invoke(
                app,
                ["check", "batch", "--file", str(batch_file), "--format", "simple"],
                catch_exceptions=False,
            )

        # Warning goes to stderr, check in combined output
        assert "Movie not found" in result.output


class TestHelpOutput:
    """Tests for help output."""

    def test_main_help(self) -> None:
        """Should show main help."""
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "Check 4K availability" in result.stdout

    def test_check_help(self) -> None:
        """Should show check subcommand help."""
        result = runner.invoke(app, ["check", "--help"])
        assert result.exit_code == 0
        assert "movie" in result.stdout
        assert "series" in result.stdout
        assert "batch" in result.stdout
