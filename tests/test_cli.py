"""Tests for CLI commands."""

import json
from datetime import UTC, datetime, timedelta
from io import StringIO
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from rich.console import Console
from typer.testing import CliRunner

from filtarr.checker import SamplingStrategy, SearchResult
from filtarr.cli import (
    OutputFormat,
    _format_cached_time,
    _get_effective_format,
    _is_transient_error,
    _parse_batch_file,
    _print_cached_result,
    app,
    format_result_json,
    format_result_simple,
    print_result,
)
from filtarr.config import Config, ConfigurationError, RadarrConfig, SonarrConfig
from filtarr.state import CheckRecord
from filtarr.tagger import TagResult
from tests.test_utils import create_asyncio_run_mock

runner = CliRunner()


def _create_mock_state_manager() -> MagicMock:
    """Create a mock StateManager for testing."""
    mock = MagicMock()
    mock.record_check = MagicMock()
    mock.get_stale_unavailable_items = MagicMock(return_value=[])
    # TTL-related methods (Task 5)
    mock.is_recently_checked = MagicMock(return_value=False)
    mock.get_cached_result = MagicMock(return_value=None)
    return mock


class TestOutputFormatters:
    """Tests for output formatting functions."""

    def test_format_result_json(self) -> None:
        """Should format result as valid JSON."""
        result = SearchResult(
            item_id=123,
            item_type="movie",
            has_match=True,
            releases=[],
            episodes_checked=[1, 2],
            seasons_checked=[1, 2],
            strategy_used=SamplingStrategy.RECENT,
        )

        json_str = format_result_json(result)
        data = json.loads(json_str)

        assert data["item_id"] == 123
        assert data["item_type"] == "movie"
        assert data["has_match"] is True
        assert data["episodes_checked"] == [1, 2]
        assert data["seasons_checked"] == [1, 2]
        assert data["strategy_used"] == "recent"

    def test_format_result_json_with_tag_result(self) -> None:
        """Should include tag information in JSON when tag_result is present (L88-94)."""
        result = SearchResult(
            item_id=123,
            item_type="movie",
            has_match=True,
            releases=[],
            tag_result=TagResult(
                tag_applied="4k-available",
                tag_removed="4k-unavailable",
                tag_created=True,
                tag_error=None,
                dry_run=False,
            ),
        )

        json_str = format_result_json(result)
        data = json.loads(json_str)

        assert "tag" in data
        assert data["tag"]["applied"] == "4k-available"
        assert data["tag"]["removed"] == "4k-unavailable"
        assert data["tag"]["created"] is True
        assert data["tag"]["error"] is None
        assert data["tag"]["dry_run"] is False

    def test_format_result_json_with_tag_error(self) -> None:
        """Should include tag error in JSON output."""
        result = SearchResult(
            item_id=123,
            item_type="movie",
            has_match=True,
            releases=[],
            tag_result=TagResult(tag_error="Connection refused"),
        )

        json_str = format_result_json(result)
        data = json.loads(json_str)

        assert "tag" in data
        assert data["tag"]["error"] == "Connection refused"
        assert data["tag"]["applied"] is None

    def test_format_result_json_with_dry_run(self) -> None:
        """Should indicate dry_run in JSON output."""
        result = SearchResult(
            item_id=123,
            item_type="movie",
            has_match=True,
            releases=[],
            tag_result=TagResult(tag_applied="4k-available", dry_run=True),
        )

        json_str = format_result_json(result)
        data = json.loads(json_str)

        assert "tag" in data
        assert data["tag"]["dry_run"] is True

    def test_format_result_simple_with_4k(self) -> None:
        """Should format as '<type>:<id>: 4K available'."""
        result = SearchResult(item_id=456, item_type="series", has_match=True)
        assert format_result_simple(result) == "series:456: 4K available"

    def test_format_result_simple_no_4k(self) -> None:
        """Should format as '<type>:<id>: No 4K'."""
        result = SearchResult(item_id=789, item_type="movie", has_match=False)
        assert format_result_simple(result) == "movie:789: No 4K"

    def test_format_result_simple_with_item_name(self) -> None:
        """Should include item name when available (L165)."""
        result = SearchResult(
            item_id=123,
            item_type="movie",
            item_name="The Matrix",
            has_match=True,
        )
        assert format_result_simple(result) == "The Matrix (123): 4K available"

    def test_format_result_simple_with_dry_run_tag(self) -> None:
        """Should show 'would tag' for dry_run mode (L158-159)."""
        result = SearchResult(
            item_id=123,
            item_type="movie",
            has_match=True,
            tag_result=TagResult(tag_applied="4k-available", dry_run=True),
        )
        output = format_result_simple(result)
        assert "[would tag: 4k-available]" in output
        assert "4K available" in output

    def test_format_result_simple_with_tag_error(self) -> None:
        """Should show tag error message (L160-161)."""
        result = SearchResult(
            item_id=123,
            item_type="movie",
            has_match=True,
            tag_result=TagResult(tag_error="Connection refused"),
        )
        output = format_result_simple(result)
        assert "[tag error: Connection refused]" in output
        assert "4K available" in output

    def test_format_result_simple_with_tag_applied(self) -> None:
        """Should show tagged message when tag is applied (L162-163)."""
        result = SearchResult(
            item_id=123,
            item_type="movie",
            has_match=True,
            tag_result=TagResult(tag_applied="4k-available"),
        )
        output = format_result_simple(result)
        assert "[tagged: 4k-available]" in output
        assert "4K available" in output

    def test_format_result_simple_with_item_name_and_tag(self) -> None:
        """Should include both item name and tag info (L165 + tag_info)."""
        result = SearchResult(
            item_id=123,
            item_type="movie",
            item_name="The Matrix",
            has_match=True,
            tag_result=TagResult(tag_applied="4k-available"),
        )
        output = format_result_simple(result)
        assert output == "The Matrix (123): 4K available [tagged: 4k-available]"


class TestPrintResult:
    """Tests for print_result function (L171-174)."""

    def test_print_result_json_format(self) -> None:
        """Should use JSON format when OutputFormat.JSON is specified (L171-172)."""
        result = SearchResult(
            item_id=123,
            item_type="movie",
            has_match=True,
            releases=[],
        )

        output = StringIO()
        test_console = Console(file=output, force_terminal=False)

        with patch("filtarr.cli.console", test_console):
            print_result(result, OutputFormat.JSON)

        output_str = output.getvalue()
        # Should be valid JSON
        data = json.loads(output_str)
        assert data["item_id"] == 123
        assert data["has_match"] is True

    def test_print_result_table_format(self) -> None:
        """Should use TABLE format when OutputFormat.TABLE is specified (L173-174)."""
        result = SearchResult(
            item_id=123,
            item_type="movie",
            has_match=True,
            releases=[],
        )

        output = StringIO()
        test_console = Console(file=output, force_terminal=False)

        with patch("filtarr.cli.console", test_console):
            print_result(result, OutputFormat.TABLE)

        output_str = output.getvalue()
        # Table output should contain the release check title
        assert "Release Check" in output_str
        assert "Movie 123" in output_str

    def test_print_result_simple_format(self) -> None:
        """Should use SIMPLE format when OutputFormat.SIMPLE is specified."""
        result = SearchResult(
            item_id=123,
            item_type="movie",
            has_match=True,
        )

        output = StringIO()
        test_console = Console(file=output, force_terminal=False)

        with patch("filtarr.cli.console", test_console):
            print_result(result, OutputFormat.SIMPLE)

        output_str = output.getvalue()
        assert "movie:123: 4K available" in output_str


class TestGetChecker:
    """Tests for get_checker function (L190-191)."""

    def test_get_checker_with_radarr(self) -> None:
        """Should extract Radarr config when need_radarr=True (L190-191)."""
        from filtarr.cli import get_checker

        mock_config = Config(radarr=RadarrConfig(url="http://localhost:7878", api_key="test-key"))

        checker = get_checker(mock_config, need_radarr=True)

        # Verify the checker was created with Radarr config as a tuple (url, api_key)
        assert checker._radarr_config is not None
        assert checker._radarr_config[0] == "http://localhost:7878"
        assert checker._radarr_config[1] == "test-key"

    def test_get_checker_with_sonarr(self) -> None:
        """Should extract Sonarr config when need_sonarr=True."""
        from filtarr.cli import get_checker

        mock_config = Config(sonarr=SonarrConfig(url="http://localhost:8989", api_key="sonarr-key"))

        checker = get_checker(mock_config, need_sonarr=True)

        # Verify the checker was created with Sonarr config as a tuple (url, api_key)
        assert checker._sonarr_config is not None
        assert checker._sonarr_config[0] == "http://localhost:8989"
        assert checker._sonarr_config[1] == "sonarr-key"

    def test_get_checker_with_both(self) -> None:
        """Should extract both Radarr and Sonarr configs when both are needed."""
        from filtarr.cli import get_checker

        mock_config = Config(
            radarr=RadarrConfig(url="http://localhost:7878", api_key="radarr-key"),
            sonarr=SonarrConfig(url="http://localhost:8989", api_key="sonarr-key"),
        )

        checker = get_checker(mock_config, need_radarr=True, need_sonarr=True)

        assert checker._radarr_config is not None
        assert checker._radarr_config[0] == "http://localhost:7878"
        assert checker._sonarr_config is not None
        assert checker._sonarr_config[0] == "http://localhost:8989"


class TestCheckMovieCommand:
    """Tests for 'filtarr check movie' command."""

    def test_check_movie_with_4k(self) -> None:
        """Should exit 0 when 4K is available."""
        mock_result = SearchResult(item_id=123, item_type="movie", has_match=True)
        mock_config = Config(radarr=RadarrConfig(url="http://localhost:7878", api_key="key"))

        async def mock_check_movie(_movie_id: int, **_kwargs: object) -> SearchResult:
            return mock_result

        mock_checker = MagicMock()
        mock_checker.check_movie = mock_check_movie
        mock_state_manager = _create_mock_state_manager()

        with (
            patch("filtarr.cli.Config.load", return_value=mock_config),
            patch("filtarr.cli.get_checker", return_value=mock_checker),
            patch("filtarr.cli.get_state_manager", return_value=mock_state_manager),
        ):
            result = runner.invoke(app, ["check", "movie", "123", "--format", "simple"])

        assert result.exit_code == 0
        assert "4K available" in result.output

    def test_check_movie_no_4k(self) -> None:
        """Should exit 1 when no 4K available."""
        mock_result = SearchResult(item_id=123, item_type="movie", has_match=False)
        mock_config = Config(radarr=RadarrConfig(url="http://localhost:7878", api_key="key"))

        async def mock_check_movie(_movie_id: int, **_kwargs: object) -> SearchResult:
            return mock_result

        mock_checker = MagicMock()
        mock_checker.check_movie = mock_check_movie
        mock_state_manager = _create_mock_state_manager()

        with (
            patch("filtarr.cli.Config.load", return_value=mock_config),
            patch("filtarr.cli.get_checker", return_value=mock_checker),
            patch("filtarr.cli.get_state_manager", return_value=mock_state_manager),
        ):
            result = runner.invoke(app, ["check", "movie", "123", "--format", "simple"])

        assert result.exit_code == 1
        assert "No 4K" in result.output

    def test_check_movie_not_configured(self) -> None:
        """Should exit 2 when Radarr not configured."""
        mock_config = Config()  # No Radarr

        with patch("filtarr.cli.Config.load", return_value=mock_config):
            result = runner.invoke(app, ["check", "movie", "123"])

        assert result.exit_code == 2


class TestCheckSeriesCommand:
    """Tests for 'filtarr check series' command."""

    def test_check_series_with_4k(self) -> None:
        """Should exit 0 when 4K is available."""
        mock_result = SearchResult(
            item_id=456,
            item_type="series",
            has_match=True,
            strategy_used=SamplingStrategy.RECENT,
        )
        mock_config = Config(sonarr=SonarrConfig(url="http://localhost:8989", api_key="key"))

        with (
            patch("filtarr.cli.Config.load", return_value=mock_config),
            patch("filtarr.cli.asyncio.run", create_asyncio_run_mock(mock_result)),
        ):
            result = runner.invoke(app, ["check", "series", "456", "--format", "simple"])

        assert result.exit_code == 0
        assert "4K available" in result.stdout

    def test_check_series_with_strategy_option(self) -> None:
        """Should accept --strategy option."""
        mock_result = SearchResult(
            item_id=456,
            item_type="series",
            has_match=False,
            strategy_used=SamplingStrategy.DISTRIBUTED,
        )
        mock_config = Config(sonarr=SonarrConfig(url="http://localhost:8989", api_key="key"))

        with (
            patch("filtarr.cli.Config.load", return_value=mock_config),
            patch("filtarr.cli.asyncio.run", create_asyncio_run_mock(mock_result)),
        ):
            result = runner.invoke(
                app,
                ["check", "series", "456", "--strategy", "distributed", "--format", "simple"],
            )

        assert result.exit_code == 1

    def test_check_series_invalid_strategy(self) -> None:
        """Should exit 2 for invalid strategy."""
        mock_config = Config(sonarr=SonarrConfig(url="http://localhost:8989", api_key="key"))

        with patch("filtarr.cli.Config.load", return_value=mock_config):
            result = runner.invoke(app, ["check", "series", "456", "--strategy", "invalid"])

        assert result.exit_code == 2

    def test_check_series_records_state_with_tags(self) -> None:
        """Should record check in state file when apply_tags=True (L520-525)."""
        mock_result = SearchResult(
            item_id=456,
            item_type="series",
            has_match=True,
            strategy_used=SamplingStrategy.RECENT,
            tag_result=TagResult(tag_applied="4k-available"),
        )
        mock_config = Config(sonarr=SonarrConfig(url="http://localhost:8989", api_key="key"))
        mock_state_manager = _create_mock_state_manager()
        mock_state_manager.get_cached_result.return_value = None

        with (
            patch("filtarr.cli.Config.load", return_value=mock_config),
            patch("filtarr.cli.get_state_manager", return_value=mock_state_manager),
            patch("filtarr.cli.asyncio.run", create_asyncio_run_mock(mock_result)),
        ):
            result = runner.invoke(app, ["check", "series", "456", "--format", "simple"])

        assert result.exit_code == 0
        # Should have recorded the check
        mock_state_manager.record_check.assert_called_once_with("series", 456, True, "4k-available")

    def test_check_series_configuration_error(self) -> None:
        """Should exit 2 and show error for ConfigurationError (L531-533)."""
        mock_config = Config()  # No Sonarr configured

        with patch("filtarr.cli.Config.load", return_value=mock_config):
            result = runner.invoke(app, ["check", "series", "456", "--format", "simple"])

        assert result.exit_code == 2
        assert "Configuration error" in result.output

    def test_check_series_general_exception(self) -> None:
        """Should exit 2 and show error for general exceptions (L534-536)."""
        mock_config = Config(sonarr=SonarrConfig(url="http://localhost:8989", api_key="key"))
        mock_state_manager = _create_mock_state_manager()
        mock_state_manager.get_cached_result.return_value = None

        def mock_run_raises(coro: object) -> None:
            if hasattr(coro, "close"):
                coro.close()
            raise RuntimeError("Unexpected server error")

        with (
            patch("filtarr.cli.Config.load", return_value=mock_config),
            patch("filtarr.cli.get_state_manager", return_value=mock_state_manager),
            patch("filtarr.cli.asyncio.run", side_effect=mock_run_raises),
        ):
            result = runner.invoke(app, ["check", "series", "456", "--format", "simple"])

        assert result.exit_code == 2
        assert "Error" in result.output
        assert "Unexpected server error" in result.output


class TestBatchCommand:
    """Tests for 'filtarr check batch' command."""

    def test_batch_file_not_found(self) -> None:
        """Should exit 2 when file doesn't exist."""
        result = runner.invoke(app, ["check", "batch", "--file", "/nonexistent/file.txt"])
        assert result.exit_code == 2

    def test_batch_with_valid_file(self, tmp_path: Path) -> None:
        """Should process items from file."""
        batch_file = tmp_path / "items.txt"
        batch_file.write_text("movie:123\nseries:456\n")

        mock_movie_result = SearchResult(item_id=123, item_type="movie", has_match=True)
        mock_series_result = SearchResult(
            item_id=456,
            item_type="series",
            has_match=True,
            strategy_used=SamplingStrategy.RECENT,
        )
        mock_config = Config(
            radarr=RadarrConfig(url="http://localhost:7878", api_key="key"),
            sonarr=SonarrConfig(url="http://127.0.0.1:8989", api_key="key"),
        )

        with (
            patch("filtarr.cli.Config.load", return_value=mock_config),
            patch("filtarr.cli.get_checker") as mock_get_checker,
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

        mock_result = SearchResult(item_id=123, item_type="movie", has_match=True)
        mock_config = Config(radarr=RadarrConfig(url="http://localhost:7878", api_key="key"))

        with (
            patch("filtarr.cli.Config.load", return_value=mock_config),
            patch("filtarr.cli.get_checker") as mock_get_checker,
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
        assert "filtarr version" in result.stdout


class TestCheckMovieByName:
    """Tests for 'filtarr check movie' with name lookup."""

    def test_check_movie_by_name_single_match(self) -> None:
        """Should use single match when searching by name."""
        mock_result = SearchResult(item_id=123, item_type="movie", has_match=True)
        mock_config = Config(radarr=RadarrConfig(url="http://localhost:7878", api_key="key"))

        async def mock_search_movies(_term: str) -> list[tuple[int, str, int]]:
            return [(123, "The Matrix", 1999)]

        async def mock_check_movie(_movie_id: int, **_kwargs: object) -> SearchResult:
            return mock_result

        mock_checker = MagicMock()
        mock_checker.search_movies = mock_search_movies
        mock_checker.check_movie = mock_check_movie
        mock_state_manager = _create_mock_state_manager()

        with (
            patch("filtarr.cli.Config.load", return_value=mock_config),
            patch("filtarr.cli.get_checker", return_value=mock_checker),
            patch("filtarr.cli.get_state_manager", return_value=mock_state_manager),
        ):
            result = runner.invoke(app, ["check", "movie", "The Matrix", "--format", "simple"])

        assert result.exit_code == 0
        assert "4K available" in result.output
        assert "Found: The Matrix" in result.output

    def test_check_movie_by_name_multiple_matches(self) -> None:
        """Should display choices when multiple matches found."""
        mock_config = Config(radarr=RadarrConfig(url="http://localhost:7878", api_key="key"))

        async def mock_search_movies(_term: str) -> list[tuple[int, str, int]]:
            return [(1, "The Matrix", 1999), (2, "The Matrix Reloaded", 2003)]

        mock_checker = MagicMock()
        mock_checker.search_movies = mock_search_movies
        mock_state_manager = _create_mock_state_manager()

        with (
            patch("filtarr.cli.Config.load", return_value=mock_config),
            patch("filtarr.cli.get_checker", return_value=mock_checker),
            patch("filtarr.cli.get_state_manager", return_value=mock_state_manager),
        ):
            result = runner.invoke(app, ["check", "movie", "Matrix", "--format", "simple"])

        assert result.exit_code == 2
        assert "Multiple movies found" in result.output
        assert "1: The Matrix (1999)" in result.output
        assert "2: The Matrix Reloaded (2003)" in result.output

    def test_check_movie_by_name_not_found(self) -> None:
        """Should exit 2 when movie not found by name."""
        mock_config = Config(radarr=RadarrConfig(url="http://localhost:7878", api_key="key"))

        async def mock_search_movies(_term: str) -> list[tuple[int, str, int]]:
            return []

        mock_checker = MagicMock()
        mock_checker.search_movies = mock_search_movies
        mock_state_manager = _create_mock_state_manager()

        with (
            patch("filtarr.cli.Config.load", return_value=mock_config),
            patch("filtarr.cli.get_checker", return_value=mock_checker),
            patch("filtarr.cli.get_state_manager", return_value=mock_state_manager),
        ):
            result = runner.invoke(app, ["check", "movie", "Nonexistent", "--format", "simple"])

        assert result.exit_code == 2
        assert "Movie not found" in result.output


class TestCheckSeriesByName:
    """Tests for 'filtarr check series' with name lookup."""

    def test_check_series_by_name_single_match(self) -> None:
        """Should use single match when searching by name."""
        mock_result = SearchResult(
            item_id=456,
            item_type="series",
            has_match=True,
            strategy_used=SamplingStrategy.RECENT,
        )
        mock_config = Config(sonarr=SonarrConfig(url="http://localhost:8989", api_key="key"))

        async def mock_search_series(_term: str) -> list[tuple[int, str, int]]:
            return [(456, "Breaking Bad", 2008)]

        async def mock_check_series(_series_id: int, **_kwargs: object) -> SearchResult:
            return mock_result

        mock_checker = MagicMock()
        mock_checker.search_series = mock_search_series
        mock_checker.check_series = mock_check_series

        with (
            patch("filtarr.cli.Config.load", return_value=mock_config),
            patch("filtarr.cli.get_checker", return_value=mock_checker),
        ):
            result = runner.invoke(app, ["check", "series", "Breaking Bad", "--format", "simple"])

        assert result.exit_code == 0
        assert "4K available" in result.output
        assert "Found: Breaking Bad" in result.output

    def test_check_series_by_name_multiple_matches(self) -> None:
        """Should display choices when multiple matches found."""
        mock_config = Config(sonarr=SonarrConfig(url="http://localhost:8989", api_key="key"))

        async def mock_search_series(_term: str) -> list[tuple[int, str, int]]:
            return [(1, "Breaking Bad", 2008), (2, "Breaking Bad: El Camino", 2019)]

        mock_checker = MagicMock()
        mock_checker.search_series = mock_search_series

        with (
            patch("filtarr.cli.Config.load", return_value=mock_config),
            patch("filtarr.cli.get_checker", return_value=mock_checker),
        ):
            result = runner.invoke(app, ["check", "series", "Breaking", "--format", "simple"])

        assert result.exit_code == 2
        assert "Multiple series found" in result.output
        assert "1: Breaking Bad (2008)" in result.output

    def test_check_series_by_name_not_found(self) -> None:
        """Should exit 2 when series not found by name."""
        mock_config = Config(sonarr=SonarrConfig(url="http://localhost:8989", api_key="key"))

        async def mock_search_series(_term: str) -> list[tuple[int, str, int]]:
            return []

        mock_checker = MagicMock()
        mock_checker.search_series = mock_search_series

        with (
            patch("filtarr.cli.Config.load", return_value=mock_config),
            patch("filtarr.cli.get_checker", return_value=mock_checker),
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

        mock_result = SearchResult(item_id=123, item_type="movie", has_match=True)
        mock_config = Config(radarr=RadarrConfig(url="http://localhost:7878", api_key="key"))

        with (
            patch("filtarr.cli.Config.load", return_value=mock_config),
            patch("filtarr.cli.get_checker") as mock_get_checker,
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

        mock_config = Config(radarr=RadarrConfig(url="http://localhost:7878", api_key="key"))

        with (
            patch("filtarr.cli.Config.load", return_value=mock_config),
            patch("filtarr.cli.get_checker") as mock_get_checker,
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

        mock_config = Config(radarr=RadarrConfig(url="http://localhost:7878", api_key="key"))

        with (
            patch("filtarr.cli.Config.load", return_value=mock_config),
            patch("filtarr.cli.get_checker") as mock_get_checker,
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
        assert "Check release availability" in result.stdout

    def test_check_help(self) -> None:
        """Should show check subcommand help."""
        result = runner.invoke(app, ["check", "--help"])
        assert result.exit_code == 0
        assert "movie" in result.stdout
        assert "series" in result.stdout
        assert "batch" in result.stdout


class TestParseBatchFile:
    """Tests for _parse_batch_file function."""

    def test_parse_movie_with_numeric_id(self, tmp_path: Path) -> None:
        """Should parse movie with numeric ID."""
        batch_file = tmp_path / "items.txt"
        batch_file.write_text("movie:123\n")

        error_console = Console(stderr=True, force_terminal=False)
        items, keys = _parse_batch_file(batch_file, error_console)

        assert items == [("movie", "123")]
        assert keys == {"movie:123"}

    def test_parse_series_with_numeric_id(self, tmp_path: Path) -> None:
        """Should parse series with numeric ID."""
        batch_file = tmp_path / "items.txt"
        batch_file.write_text("series:456\n")

        error_console = Console(stderr=True, force_terminal=False)
        items, keys = _parse_batch_file(batch_file, error_console)

        assert items == [("series", "456")]
        assert keys == {"series:456"}

    def test_parse_movie_with_name(self, tmp_path: Path) -> None:
        """Should parse movie with name."""
        batch_file = tmp_path / "items.txt"
        batch_file.write_text("movie:The Matrix\n")

        error_console = Console(stderr=True, force_terminal=False)
        items, keys = _parse_batch_file(batch_file, error_console)

        assert items == [("movie", "The Matrix")]
        # Names are not added to keys (only numeric IDs are)
        assert keys == set()

    def test_parse_series_with_name(self, tmp_path: Path) -> None:
        """Should parse series with name."""
        batch_file = tmp_path / "items.txt"
        batch_file.write_text("series:Breaking Bad\n")

        error_console = Console(stderr=True, force_terminal=False)
        items, keys = _parse_batch_file(batch_file, error_console)

        assert items == [("series", "Breaking Bad")]
        # Names are not added to keys (only numeric IDs are)
        assert keys == set()

    def test_invalid_format_missing_colon(self, tmp_path: Path) -> None:
        """Should skip lines with missing colon and warn."""
        batch_file = tmp_path / "items.txt"
        batch_file.write_text("movie_123\n")

        error_console = Console(stderr=True, force_terminal=False)
        items, keys = _parse_batch_file(batch_file, error_console)

        assert items == []
        assert keys == set()

    def test_invalid_type_tv(self, tmp_path: Path) -> None:
        """Should skip lines with invalid type 'tv'."""
        batch_file = tmp_path / "items.txt"
        batch_file.write_text("tv:123\n")

        error_console = Console(stderr=True, force_terminal=False)
        items, keys = _parse_batch_file(batch_file, error_console)

        assert items == []
        assert keys == set()

    def test_invalid_type_tvshow(self, tmp_path: Path) -> None:
        """Should skip lines with invalid type 'tvshow'."""
        batch_file = tmp_path / "items.txt"
        batch_file.write_text("tvshow:456\n")

        error_console = Console(stderr=True, force_terminal=False)
        items, keys = _parse_batch_file(batch_file, error_console)

        assert items == []
        assert keys == set()

    def test_comments_are_skipped(self, tmp_path: Path) -> None:
        """Should skip lines starting with #."""
        batch_file = tmp_path / "items.txt"
        batch_file.write_text("# This is a comment\nmovie:123\n")

        error_console = Console(stderr=True, force_terminal=False)
        items, keys = _parse_batch_file(batch_file, error_console)

        assert items == [("movie", "123")]
        assert keys == {"movie:123"}

    def test_empty_lines_are_skipped(self, tmp_path: Path) -> None:
        """Should skip empty lines."""
        batch_file = tmp_path / "items.txt"
        batch_file.write_text("\n\nmovie:123\n\n")

        error_console = Console(stderr=True, force_terminal=False)
        items, keys = _parse_batch_file(batch_file, error_console)

        assert items == [("movie", "123")]
        assert keys == {"movie:123"}

    def test_whitespace_only_lines_are_skipped(self, tmp_path: Path) -> None:
        """Should skip whitespace-only lines."""
        batch_file = tmp_path / "items.txt"
        batch_file.write_text("   \n\t\nmovie:123\n")

        error_console = Console(stderr=True, force_terminal=False)
        items, keys = _parse_batch_file(batch_file, error_console)

        assert items == [("movie", "123")]
        assert keys == {"movie:123"}

    def test_leading_trailing_whitespace_handling(self, tmp_path: Path) -> None:
        """Should handle leading/trailing whitespace on lines."""
        batch_file = tmp_path / "items.txt"
        batch_file.write_text("  movie:123  \n")

        error_console = Console(stderr=True, force_terminal=False)
        items, keys = _parse_batch_file(batch_file, error_console)

        assert items == [("movie", "123")]
        assert keys == {"movie:123"}

    def test_whitespace_in_value_is_stripped(self, tmp_path: Path) -> None:
        """Should strip whitespace from values."""
        batch_file = tmp_path / "items.txt"
        batch_file.write_text("movie:  The Matrix  \n")

        error_console = Console(stderr=True, force_terminal=False)
        items, keys = _parse_batch_file(batch_file, error_console)

        assert items == [("movie", "The Matrix")]
        assert keys == set()

    def test_multiple_colons_in_name(self, tmp_path: Path) -> None:
        """Should handle names with multiple colons."""
        batch_file = tmp_path / "items.txt"
        batch_file.write_text("movie:Name:With:Colons\n")

        error_console = Console(stderr=True, force_terminal=False)
        items, keys = _parse_batch_file(batch_file, error_console)

        assert items == [("movie", "Name:With:Colons")]
        assert keys == set()

    def test_duplicate_numeric_ids_tracked(self, tmp_path: Path) -> None:
        """Should track duplicate numeric IDs in keys set."""
        batch_file = tmp_path / "items.txt"
        batch_file.write_text("movie:123\nmovie:456\nseries:789\n")

        error_console = Console(stderr=True, force_terminal=False)
        items, keys = _parse_batch_file(batch_file, error_console)

        assert items == [("movie", "123"), ("movie", "456"), ("series", "789")]
        assert keys == {"movie:123", "movie:456", "series:789"}

    def test_same_id_different_types(self, tmp_path: Path) -> None:
        """Should track same ID with different types as separate keys."""
        batch_file = tmp_path / "items.txt"
        batch_file.write_text("movie:123\nseries:123\n")

        error_console = Console(stderr=True, force_terminal=False)
        items, keys = _parse_batch_file(batch_file, error_console)

        assert items == [("movie", "123"), ("series", "123")]
        assert keys == {"movie:123", "series:123"}

    def test_type_case_insensitive(self, tmp_path: Path) -> None:
        """Should handle type case-insensitively."""
        batch_file = tmp_path / "items.txt"
        batch_file.write_text("MOVIE:123\nSeries:456\nMoViE:789\n")

        error_console = Console(stderr=True, force_terminal=False)
        items, keys = _parse_batch_file(batch_file, error_console)

        assert items == [("movie", "123"), ("series", "456"), ("movie", "789")]
        assert keys == {"movie:123", "series:456", "movie:789"}

    def test_mixed_valid_and_invalid_lines(self, tmp_path: Path) -> None:
        """Should parse valid lines and skip invalid ones."""
        batch_file = tmp_path / "items.txt"
        batch_file.write_text(
            "# Comment\nmovie:123\ninvalid_line\ntv:456\nseries:Breaking Bad\n\nmovie:The Matrix\n"
        )

        error_console = Console(stderr=True, force_terminal=False)
        items, keys = _parse_batch_file(batch_file, error_console)

        assert items == [
            ("movie", "123"),
            ("series", "Breaking Bad"),
            ("movie", "The Matrix"),
        ]
        assert keys == {"movie:123"}

    def test_numeric_id_with_leading_zeros(self, tmp_path: Path) -> None:
        """Should handle numeric IDs with leading zeros."""
        batch_file = tmp_path / "items.txt"
        batch_file.write_text("movie:00123\n")

        error_console = Console(stderr=True, force_terminal=False)
        items, keys = _parse_batch_file(batch_file, error_console)

        # "00123" with leading zeros is still considered numeric (isdigit returns True)
        assert items == [("movie", "00123")]
        assert keys == {"movie:00123"}


class TestCheckMovieCriteriaValidation:
    """Tests for criteria validation in check_movie command."""

    def test_check_movie_invalid_criteria(self) -> None:
        """Should exit 2 when invalid criteria is provided."""
        mock_config = Config(radarr=RadarrConfig(url="http://localhost:7878", api_key="key"))

        with patch("filtarr.cli.Config.load", return_value=mock_config):
            result = runner.invoke(app, ["check", "movie", "123", "--criteria", "xyz"])

        assert result.exit_code == 2
        assert "Invalid criteria" in result.output
        assert "xyz" in result.output
        assert "Valid options:" in result.output

    def test_check_movie_invalid_criteria_mixed_case(self) -> None:
        """Should exit 2 when invalid criteria with mixed case is provided."""
        mock_config = Config(radarr=RadarrConfig(url="http://localhost:7878", api_key="key"))

        with patch("filtarr.cli.Config.load", return_value=mock_config):
            result = runner.invoke(app, ["check", "movie", "123", "--criteria", "FooBar"])

        assert result.exit_code == 2
        assert "Invalid criteria" in result.output

    def test_check_movie_valid_criteria_case_insensitive(self) -> None:
        """Should accept valid criteria regardless of case."""
        from filtarr.criteria import ResultType

        mock_result = SearchResult(
            item_id=123, item_type="movie", has_match=True, result_type=ResultType.HDR
        )
        mock_config = Config(radarr=RadarrConfig(url="http://localhost:7878", api_key="key"))

        async def mock_check_movie(_movie_id: int, **_kwargs: object) -> SearchResult:
            return mock_result

        mock_checker = MagicMock()
        mock_checker.check_movie = mock_check_movie
        mock_state_manager = _create_mock_state_manager()

        with (
            patch("filtarr.cli.Config.load", return_value=mock_config),
            patch("filtarr.cli.get_checker", return_value=mock_checker),
            patch("filtarr.cli.get_state_manager", return_value=mock_state_manager),
        ):
            # Test uppercase
            result = runner.invoke(
                app, ["check", "movie", "123", "--criteria", "HDR", "--format", "simple"]
            )

        assert result.exit_code == 0
        assert "HDR available" in result.output


class TestCheckSeriesCriteriaValidation:
    """Tests for criteria validation in check_series command."""

    def test_check_series_invalid_criteria(self) -> None:
        """Should exit 2 when invalid criteria is provided."""
        mock_config = Config(sonarr=SonarrConfig(url="http://localhost:8989", api_key="key"))

        with patch("filtarr.cli.Config.load", return_value=mock_config):
            result = runner.invoke(app, ["check", "series", "456", "--criteria", "xyz"])

        assert result.exit_code == 2
        assert "Invalid criteria" in result.output
        assert "xyz" in result.output

    def test_check_series_directors_cut_error(self) -> None:
        """Should exit 2 when directors-cut criteria is used for series."""
        mock_config = Config(sonarr=SonarrConfig(url="http://localhost:8989", api_key="key"))

        with patch("filtarr.cli.Config.load", return_value=mock_config):
            result = runner.invoke(app, ["check", "series", "456", "--criteria", "directors-cut"])

        assert result.exit_code == 2
        assert "directors-cut" in result.output.lower()
        assert "only applicable to movies" in result.output

    def test_check_series_extended_error(self) -> None:
        """Should exit 2 when extended criteria is used for series."""
        mock_config = Config(sonarr=SonarrConfig(url="http://localhost:8989", api_key="key"))

        with patch("filtarr.cli.Config.load", return_value=mock_config):
            result = runner.invoke(app, ["check", "series", "456", "--criteria", "extended"])

        assert result.exit_code == 2
        assert "extended" in result.output.lower()
        assert "only applicable to movies" in result.output

    def test_check_series_remaster_error(self) -> None:
        """Should exit 2 when remaster criteria is used for series."""
        mock_config = Config(sonarr=SonarrConfig(url="http://localhost:8989", api_key="key"))

        with patch("filtarr.cli.Config.load", return_value=mock_config):
            result = runner.invoke(app, ["check", "series", "456", "--criteria", "remaster"])

        assert result.exit_code == 2
        assert "remaster" in result.output.lower()
        assert "only applicable to movies" in result.output

    def test_check_series_imax_error(self) -> None:
        """Should exit 2 when imax criteria is used for series."""
        mock_config = Config(sonarr=SonarrConfig(url="http://localhost:8989", api_key="key"))

        with patch("filtarr.cli.Config.load", return_value=mock_config):
            result = runner.invoke(app, ["check", "series", "456", "--criteria", "imax"])

        assert result.exit_code == 2
        assert "imax" in result.output.lower()
        assert "only applicable to movies" in result.output

    def test_check_series_special_edition_error(self) -> None:
        """Should exit 2 when special-edition criteria is used for series."""
        mock_config = Config(sonarr=SonarrConfig(url="http://localhost:8989", api_key="key"))

        with patch("filtarr.cli.Config.load", return_value=mock_config):
            result = runner.invoke(app, ["check", "series", "456", "--criteria", "special-edition"])

        assert result.exit_code == 2
        assert "special-edition" in result.output.lower()
        assert "only applicable to movies" in result.output

    def test_check_series_valid_4k_criteria(self) -> None:
        """Should accept 4k criteria for series."""
        mock_result = SearchResult(
            item_id=456,
            item_type="series",
            has_match=True,
            strategy_used=SamplingStrategy.RECENT,
        )
        mock_config = Config(sonarr=SonarrConfig(url="http://localhost:8989", api_key="key"))

        with (
            patch("filtarr.cli.Config.load", return_value=mock_config),
            patch("filtarr.cli.asyncio.run", create_asyncio_run_mock(mock_result)),
        ):
            result = runner.invoke(
                app, ["check", "series", "456", "--criteria", "4k", "--format", "simple"]
            )

        assert result.exit_code == 0
        assert "4K available" in result.stdout

    def test_check_series_valid_hdr_criteria(self) -> None:
        """Should accept hdr criteria for series."""
        from filtarr.criteria import ResultType

        mock_result = SearchResult(
            item_id=456,
            item_type="series",
            has_match=True,
            result_type=ResultType.HDR,
            strategy_used=SamplingStrategy.RECENT,
        )
        mock_config = Config(sonarr=SonarrConfig(url="http://localhost:8989", api_key="key"))

        with (
            patch("filtarr.cli.Config.load", return_value=mock_config),
            patch("filtarr.cli.asyncio.run", create_asyncio_run_mock(mock_result)),
        ):
            result = runner.invoke(
                app, ["check", "series", "456", "--criteria", "hdr", "--format", "simple"]
            )

        assert result.exit_code == 0
        assert "HDR available" in result.stdout

    def test_check_series_valid_dolby_vision_criteria(self) -> None:
        """Should accept dolby-vision criteria for series."""
        from filtarr.criteria import ResultType

        mock_result = SearchResult(
            item_id=456,
            item_type="series",
            has_match=True,
            result_type=ResultType.DOLBY_VISION,
            strategy_used=SamplingStrategy.RECENT,
        )
        mock_config = Config(sonarr=SonarrConfig(url="http://localhost:8989", api_key="key"))

        with (
            patch("filtarr.cli.Config.load", return_value=mock_config),
            patch("filtarr.cli.asyncio.run", create_asyncio_run_mock(mock_result)),
        ):
            result = runner.invoke(
                app,
                ["check", "series", "456", "--criteria", "dolby-vision", "--format", "simple"],
            )

        assert result.exit_code == 0
        assert "Dolby Vision available" in result.stdout


class TestValidateBatchInputs:
    """Tests for _validate_batch_inputs() function."""

    def test_batch_no_file_no_all_flags_error(self) -> None:
        """Should exit 2 when no file and no --all-* flags are provided."""
        result = runner.invoke(app, ["check", "batch"])

        assert result.exit_code == 2
        assert "Must specify --file, --all-movies, or --all-series" in result.output

    def test_batch_file_not_exists_error(self) -> None:
        """Should exit 2 when file path doesn't exist."""
        result = runner.invoke(app, ["check", "batch", "--file", "/nonexistent/path/items.txt"])

        assert result.exit_code == 2
        assert "File not found" in result.output

    def test_batch_invalid_criteria_error(self) -> None:
        """Should exit 2 when invalid criteria is provided."""
        mock_config = Config(radarr=RadarrConfig(url="http://localhost:7878", api_key="key"))

        with patch("filtarr.cli.Config.load", return_value=mock_config):
            result = runner.invoke(
                app, ["check", "batch", "--all-movies", "--criteria", "invalid_criteria"]
            )

        assert result.exit_code == 2
        assert "Invalid criteria" in result.output
        assert "invalid_criteria" in result.output

    def test_batch_movie_only_criteria_with_all_series_error(self) -> None:
        """Should exit 2 when movie-only criteria is used with --all-series."""
        mock_config = Config(sonarr=SonarrConfig(url="http://localhost:8989", api_key="key"))

        with patch("filtarr.cli.Config.load", return_value=mock_config):
            result = runner.invoke(
                app, ["check", "batch", "--all-series", "--criteria", "directors-cut"]
            )

        assert result.exit_code == 2
        assert "only applicable to movies" in result.output
        # Check for key parts of the error message (handles potential line wrapping)
        assert "--all-series" in result.output

    def test_batch_extended_with_all_series_error(self) -> None:
        """Should exit 2 when extended criteria is used with --all-series."""
        mock_config = Config(sonarr=SonarrConfig(url="http://localhost:8989", api_key="key"))

        with patch("filtarr.cli.Config.load", return_value=mock_config):
            result = runner.invoke(
                app, ["check", "batch", "--all-series", "--criteria", "extended"]
            )

        assert result.exit_code == 2
        assert "only applicable to movies" in result.output

    def test_batch_remaster_with_all_series_error(self) -> None:
        """Should exit 2 when remaster criteria is used with --all-series."""
        mock_config = Config(sonarr=SonarrConfig(url="http://localhost:8989", api_key="key"))

        with patch("filtarr.cli.Config.load", return_value=mock_config):
            result = runner.invoke(
                app, ["check", "batch", "--all-series", "--criteria", "remaster"]
            )

        assert result.exit_code == 2
        assert "only applicable to movies" in result.output

    def test_batch_imax_with_all_series_error(self) -> None:
        """Should exit 2 when imax criteria is used with --all-series."""
        mock_config = Config(sonarr=SonarrConfig(url="http://localhost:8989", api_key="key"))

        with patch("filtarr.cli.Config.load", return_value=mock_config):
            result = runner.invoke(app, ["check", "batch", "--all-series", "--criteria", "imax"])

        assert result.exit_code == 2
        assert "only applicable to movies" in result.output

    def test_batch_special_edition_with_all_series_error(self) -> None:
        """Should exit 2 when special-edition criteria is used with --all-series."""
        mock_config = Config(sonarr=SonarrConfig(url="http://localhost:8989", api_key="key"))

        with patch("filtarr.cli.Config.load", return_value=mock_config):
            result = runner.invoke(
                app, ["check", "batch", "--all-series", "--criteria", "special-edition"]
            )

        assert result.exit_code == 2
        assert "only applicable to movies" in result.output

    def test_batch_invalid_strategy_error(self) -> None:
        """Should exit 2 when invalid strategy is provided."""
        mock_config = Config(radarr=RadarrConfig(url="http://localhost:7878", api_key="key"))

        with patch("filtarr.cli.Config.load", return_value=mock_config):
            result = runner.invoke(
                app, ["check", "batch", "--all-movies", "--strategy", "invalid_strategy"]
            )

        assert result.exit_code == 2
        assert "Invalid strategy" in result.output

    def test_batch_valid_criteria_with_all_movies(self) -> None:
        """Should accept movie-only criteria with --all-movies."""
        mock_config = Config(radarr=RadarrConfig(url="http://localhost:7878", api_key="key"))

        with (
            patch("filtarr.cli.Config.load", return_value=mock_config),
            patch("filtarr.cli.get_checker") as mock_get_checker,
            patch("filtarr.cli._fetch_movies_to_check") as mock_fetch,
        ):
            mock_fetch.return_value = ([], set())
            mock_get_checker.return_value = AsyncMock()

            result = runner.invoke(
                app, ["check", "batch", "--all-movies", "--criteria", "directors-cut"]
            )

        # Should not error on criteria validation (may have other issues but not criteria)
        assert "Invalid criteria" not in result.output
        assert "only applicable to movies" not in result.output

    def test_batch_valid_criteria_with_all_series(self) -> None:
        """Should accept valid series criteria with --all-series."""
        mock_config = Config(sonarr=SonarrConfig(url="http://localhost:8989", api_key="key"))

        with (
            patch("filtarr.cli.Config.load", return_value=mock_config),
            patch("filtarr.cli.get_checker") as mock_get_checker,
            patch("filtarr.cli._fetch_series_to_check") as mock_fetch,
        ):
            mock_fetch.return_value = ([], set())
            mock_get_checker.return_value = AsyncMock()

            result = runner.invoke(app, ["check", "batch", "--all-series", "--criteria", "hdr"])

        # Should not error on criteria validation
        assert "Invalid criteria" not in result.output
        assert "only applicable to movies" not in result.output


class TestFormatCachedTime:
    """Tests for _format_cached_time function."""

    def test_format_cached_time_seconds(self) -> None:
        """Should format time in seconds as minutes."""
        # 30 seconds ago should show "0 minutes ago"
        cached = CheckRecord(
            last_checked=datetime.now(UTC) - timedelta(seconds=30),
            result="available",
        )
        result = _format_cached_time(cached)
        assert "minute" in result
        assert "0 minute" in result

    def test_format_cached_time_one_minute(self) -> None:
        """Should show singular 'minute' for 1 minute."""
        cached = CheckRecord(
            last_checked=datetime.now(UTC) - timedelta(minutes=1, seconds=30),
            result="available",
        )
        result = _format_cached_time(cached)
        assert result == "1 minute ago"

    def test_format_cached_time_minutes(self) -> None:
        """Should format time in minutes for elapsed time < 1 hour."""
        cached = CheckRecord(
            last_checked=datetime.now(UTC) - timedelta(minutes=45),
            result="available",
        )
        result = _format_cached_time(cached)
        assert result == "45 minutes ago"

    def test_format_cached_time_one_hour(self) -> None:
        """Should show singular 'hour' for 1 hour."""
        cached = CheckRecord(
            last_checked=datetime.now(UTC) - timedelta(hours=1, minutes=30),
            result="unavailable",
        )
        result = _format_cached_time(cached)
        assert result == "1 hour ago"

    def test_format_cached_time_hours(self) -> None:
        """Should format time in hours for elapsed time < 1 day."""
        cached = CheckRecord(
            last_checked=datetime.now(UTC) - timedelta(hours=5),
            result="unavailable",
        )
        result = _format_cached_time(cached)
        assert result == "5 hours ago"

    def test_format_cached_time_one_day(self) -> None:
        """Should show singular 'day' for 1 day."""
        cached = CheckRecord(
            last_checked=datetime.now(UTC) - timedelta(days=1, hours=12),
            result="available",
        )
        result = _format_cached_time(cached)
        assert result == "1 day ago"

    def test_format_cached_time_days(self) -> None:
        """Should format time in days for elapsed time >= 1 day."""
        cached = CheckRecord(
            last_checked=datetime.now(UTC) - timedelta(days=3),
            result="available",
        )
        result = _format_cached_time(cached)
        assert result == "3 days ago"

    def test_format_cached_time_timezone_naive(self) -> None:
        """Should handle timezone-naive datetimes."""
        # Create a timezone-naive datetime
        cached = CheckRecord(
            last_checked=datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=2),
            result="available",
        )
        result = _format_cached_time(cached)
        assert "hour" in result


class TestPrintCachedResult:
    """Tests for _print_cached_result function."""

    def test_print_cached_result_json_available(self) -> None:
        """Should print JSON format for available cached result."""
        cached = CheckRecord(
            last_checked=datetime.now(UTC) - timedelta(hours=1),
            result="available",
            tag_applied="4k-available",
        )

        # Capture console output
        output = StringIO()
        test_console = Console(file=output, force_terminal=False)

        with patch("filtarr.cli.console", test_console):
            _print_cached_result("movie", 123, cached, OutputFormat.JSON)

        output_str = output.getvalue()
        data = json.loads(output_str)

        assert data["item_id"] == 123
        assert data["item_type"] == "movie"
        assert data["has_match"] is True
        assert data["cached"] is True
        assert data["tag_applied"] == "4k-available"
        assert "cached_at" in data

    def test_print_cached_result_json_unavailable(self) -> None:
        """Should print JSON format for unavailable cached result."""
        cached = CheckRecord(
            last_checked=datetime.now(UTC) - timedelta(hours=2),
            result="unavailable",
            tag_applied="4k-unavailable",
        )

        output = StringIO()
        test_console = Console(file=output, force_terminal=False)

        with patch("filtarr.cli.console", test_console):
            _print_cached_result("series", 456, cached, OutputFormat.JSON)

        output_str = output.getvalue()
        data = json.loads(output_str)

        assert data["item_id"] == 456
        assert data["item_type"] == "series"
        assert data["has_match"] is False
        assert data["cached"] is True

    def test_print_cached_result_table_format(self) -> None:
        """Should print human-readable format for TABLE output."""
        cached = CheckRecord(
            last_checked=datetime.now(UTC) - timedelta(minutes=30),
            result="available",
            tag_applied="4k-available",
        )

        output = StringIO()
        test_console = Console(file=output, force_terminal=False)

        with patch("filtarr.cli.console", test_console):
            _print_cached_result("movie", 123, cached, OutputFormat.TABLE)

        output_str = output.getvalue()
        assert "cached result" in output_str.lower()
        assert "available" in output_str.lower()
        assert "4k-available" in output_str

    def test_print_cached_result_simple_format(self) -> None:
        """Should print human-readable format for SIMPLE output."""
        cached = CheckRecord(
            last_checked=datetime.now(UTC) - timedelta(hours=3),
            result="unavailable",
        )

        output = StringIO()
        test_console = Console(file=output, force_terminal=False)

        with patch("filtarr.cli.console", test_console):
            _print_cached_result("movie", 789, cached, OutputFormat.SIMPLE)

        output_str = output.getvalue()
        assert "cached result" in output_str.lower()
        assert "unavailable" in output_str.lower()

    def test_print_cached_result_no_tag(self) -> None:
        """Should not print tag line when no tag was applied."""
        cached = CheckRecord(
            last_checked=datetime.now(UTC) - timedelta(hours=1),
            result="available",
            tag_applied=None,
        )

        output = StringIO()
        test_console = Console(file=output, force_terminal=False)

        with patch("filtarr.cli.console", test_console):
            _print_cached_result("movie", 123, cached, OutputFormat.TABLE)

        output_str = output.getvalue()
        # Should have the main cached result line
        assert "cached result" in output_str.lower()
        # Should NOT have a Tag: line
        assert "Tag:" not in output_str


class TestTTLCacheHit:
    """Tests for TTL cache hit scenarios."""

    def test_check_movie_uses_cached_result_when_within_ttl(self) -> None:
        """Should use cached result when within TTL period."""
        cached_record = CheckRecord(
            last_checked=datetime.now(UTC) - timedelta(hours=1),
            result="available",
            tag_applied="4k-available",
        )
        mock_config = Config(radarr=RadarrConfig(url="http://localhost:7878", api_key="key"))
        mock_state_manager = _create_mock_state_manager()
        mock_state_manager.get_cached_result.return_value = cached_record

        with (
            patch("filtarr.cli.Config.load", return_value=mock_config),
            patch("filtarr.cli.get_state_manager", return_value=mock_state_manager),
        ):
            result = runner.invoke(app, ["check", "movie", "123", "--format", "simple"])

        # Should exit 0 (available)
        assert result.exit_code == 0
        # Should show cached result message
        assert "cached result" in result.output.lower()
        # get_cached_result should have been called
        mock_state_manager.get_cached_result.assert_called()

    def test_check_movie_cache_hit_unavailable_exits_1(self) -> None:
        """Should exit 1 when cached result is unavailable."""
        cached_record = CheckRecord(
            last_checked=datetime.now(UTC) - timedelta(hours=1),
            result="unavailable",
            tag_applied="4k-unavailable",
        )
        mock_config = Config(radarr=RadarrConfig(url="http://localhost:7878", api_key="key"))
        mock_state_manager = _create_mock_state_manager()
        mock_state_manager.get_cached_result.return_value = cached_record

        with (
            patch("filtarr.cli.Config.load", return_value=mock_config),
            patch("filtarr.cli.get_state_manager", return_value=mock_state_manager),
        ):
            result = runner.invoke(app, ["check", "movie", "123", "--format", "simple"])

        # Should exit 1 (unavailable)
        assert result.exit_code == 1
        # Should show cached result message
        assert "cached result" in result.output.lower()

    def test_check_series_uses_cached_result_when_within_ttl(self) -> None:
        """Should use cached result for series when within TTL period."""
        cached_record = CheckRecord(
            last_checked=datetime.now(UTC) - timedelta(hours=2),
            result="available",
            tag_applied="4k-available",
        )
        mock_config = Config(sonarr=SonarrConfig(url="http://localhost:8989", api_key="key"))
        mock_state_manager = _create_mock_state_manager()
        mock_state_manager.get_cached_result.return_value = cached_record

        with (
            patch("filtarr.cli.Config.load", return_value=mock_config),
            patch("filtarr.cli.get_state_manager", return_value=mock_state_manager),
        ):
            result = runner.invoke(app, ["check", "series", "456", "--format", "simple"])

        # Should exit 0 (available)
        assert result.exit_code == 0
        # Should show cached result message
        assert "cached result" in result.output.lower()


class TestTTLCacheMiss:
    """Tests for TTL cache miss scenarios."""

    def test_check_movie_performs_fresh_check_when_cache_expired(self) -> None:
        """Should perform fresh check when cache is expired."""
        mock_result = SearchResult(item_id=123, item_type="movie", has_match=True)
        mock_config = Config(radarr=RadarrConfig(url="http://localhost:7878", api_key="key"))
        mock_state_manager = _create_mock_state_manager()
        # Cache miss - return None
        mock_state_manager.get_cached_result.return_value = None

        async def mock_check_movie(_movie_id: int, **_kwargs: object) -> SearchResult:
            return mock_result

        mock_checker = MagicMock()
        mock_checker.check_movie = mock_check_movie

        with (
            patch("filtarr.cli.Config.load", return_value=mock_config),
            patch("filtarr.cli.get_checker", return_value=mock_checker),
            patch("filtarr.cli.get_state_manager", return_value=mock_state_manager),
        ):
            result = runner.invoke(app, ["check", "movie", "123", "--format", "simple"])

        # Should exit 0 (fresh check found 4K)
        assert result.exit_code == 0
        # Should NOT show cached result message
        assert "cached result" not in result.output.lower()
        # Should show actual result
        assert "4K available" in result.output

    def test_check_movie_performs_fresh_check_when_no_cache(self) -> None:
        """Should perform fresh check when no cached record exists."""
        mock_result = SearchResult(item_id=123, item_type="movie", has_match=False)
        mock_config = Config(radarr=RadarrConfig(url="http://localhost:7878", api_key="key"))
        mock_state_manager = _create_mock_state_manager()
        # No cached record
        mock_state_manager.get_cached_result.return_value = None

        async def mock_check_movie(_movie_id: int, **_kwargs: object) -> SearchResult:
            return mock_result

        mock_checker = MagicMock()
        mock_checker.check_movie = mock_check_movie

        with (
            patch("filtarr.cli.Config.load", return_value=mock_config),
            patch("filtarr.cli.get_checker", return_value=mock_checker),
            patch("filtarr.cli.get_state_manager", return_value=mock_state_manager),
        ):
            result = runner.invoke(app, ["check", "movie", "123", "--format", "simple"])

        # Should exit 1 (fresh check found no 4K)
        assert result.exit_code == 1
        assert "No 4K" in result.output

    def test_check_series_performs_fresh_check_when_cache_miss(self) -> None:
        """Should perform fresh check for series when cache miss."""
        mock_result = SearchResult(
            item_id=456,
            item_type="series",
            has_match=True,
            strategy_used=SamplingStrategy.RECENT,
        )
        mock_config = Config(sonarr=SonarrConfig(url="http://localhost:8989", api_key="key"))
        mock_state_manager = _create_mock_state_manager()
        mock_state_manager.get_cached_result.return_value = None

        with (
            patch("filtarr.cli.Config.load", return_value=mock_config),
            patch("filtarr.cli.get_state_manager", return_value=mock_state_manager),
            patch("filtarr.cli.asyncio.run", create_asyncio_run_mock(mock_result)),
        ):
            result = runner.invoke(app, ["check", "series", "456", "--format", "simple"])

        # Should exit 0 (fresh check found 4K)
        assert result.exit_code == 0
        assert "4K available" in result.stdout


class TestTTLStateRecording:
    """Tests for state recording after fresh checks."""

    def test_check_movie_records_check_when_tagging_enabled(self) -> None:
        """Should record check in state when tagging is enabled and tag_result exists."""
        mock_result = SearchResult(
            item_id=123,
            item_type="movie",
            has_match=True,
            tag_result=TagResult(tag_applied="4k-available"),
        )
        mock_config = Config(radarr=RadarrConfig(url="http://localhost:7878", api_key="key"))
        mock_state_manager = _create_mock_state_manager()
        mock_state_manager.get_cached_result.return_value = None

        async def mock_check_movie(_movie_id: int, **_kwargs: object) -> SearchResult:
            return mock_result

        mock_checker = MagicMock()
        mock_checker.check_movie = mock_check_movie

        with (
            patch("filtarr.cli.Config.load", return_value=mock_config),
            patch("filtarr.cli.get_checker", return_value=mock_checker),
            patch("filtarr.cli.get_state_manager", return_value=mock_state_manager),
        ):
            result = runner.invoke(app, ["check", "movie", "123", "--format", "simple"])

        assert result.exit_code == 0
        # Should have recorded the check
        mock_state_manager.record_check.assert_called_once_with("movie", 123, True, "4k-available")

    def test_check_movie_error_handling(self) -> None:
        """Should exit 2 and show error when unexpected exception occurs."""
        mock_config = Config(radarr=RadarrConfig(url="http://localhost:7878", api_key="key"))
        mock_state_manager = _create_mock_state_manager()
        mock_state_manager.get_cached_result.return_value = None

        async def mock_check_movie(_movie_id: int, **_kwargs: object) -> SearchResult:
            raise RuntimeError("Connection failed")

        mock_checker = MagicMock()
        mock_checker.check_movie = mock_check_movie

        with (
            patch("filtarr.cli.Config.load", return_value=mock_config),
            patch("filtarr.cli.get_checker", return_value=mock_checker),
            patch("filtarr.cli.get_state_manager", return_value=mock_state_manager),
        ):
            result = runner.invoke(app, ["check", "movie", "123", "--format", "simple"])

        assert result.exit_code == 2
        assert "Error" in result.output
        assert "Connection failed" in result.output


class TestTTLForceFlag:
    """Tests for --force flag bypassing TTL cache."""

    def test_check_movie_force_bypasses_cache(self) -> None:
        """Should bypass cache and perform fresh check with --force."""
        cached_record = CheckRecord(
            last_checked=datetime.now(UTC) - timedelta(minutes=30),
            result="unavailable",
            tag_applied="4k-unavailable",
        )
        # Fresh check returns available
        mock_result = SearchResult(item_id=123, item_type="movie", has_match=True)
        mock_config = Config(radarr=RadarrConfig(url="http://localhost:7878", api_key="key"))

        mock_state_manager = _create_mock_state_manager()
        mock_state_manager.get_cached_result.return_value = cached_record

        async def mock_check_movie(_movie_id: int, **_kwargs: object) -> SearchResult:
            return mock_result

        mock_checker = MagicMock()
        mock_checker.check_movie = mock_check_movie

        with (
            patch("filtarr.cli.Config.load", return_value=mock_config),
            patch("filtarr.cli.get_checker", return_value=mock_checker),
            patch("filtarr.cli.get_state_manager", return_value=mock_state_manager),
        ):
            result = runner.invoke(app, ["check", "movie", "123", "--force", "--format", "simple"])

        # Should exit 0 (fresh check found 4K)
        assert result.exit_code == 0
        # Should NOT show cached result (even though cache would hit)
        assert "cached result" not in result.output.lower()
        # Should show fresh result
        assert "4K available" in result.output
        # get_cached_result should NOT have been called because of --force
        mock_state_manager.get_cached_result.assert_not_called()

    def test_check_series_force_bypasses_cache(self) -> None:
        """Should bypass cache for series with --force."""
        cached_record = CheckRecord(
            last_checked=datetime.now(UTC) - timedelta(minutes=30),
            result="unavailable",
        )
        # Fresh check returns available
        mock_result = SearchResult(
            item_id=456,
            item_type="series",
            has_match=True,
            strategy_used=SamplingStrategy.RECENT,
        )
        mock_config = Config(sonarr=SonarrConfig(url="http://localhost:8989", api_key="key"))

        mock_state_manager = _create_mock_state_manager()
        mock_state_manager.get_cached_result.return_value = cached_record

        with (
            patch("filtarr.cli.Config.load", return_value=mock_config),
            patch("filtarr.cli.get_state_manager", return_value=mock_state_manager),
            patch("filtarr.cli.asyncio.run", create_asyncio_run_mock(mock_result)),
        ):
            result = runner.invoke(app, ["check", "series", "456", "--force", "--format", "simple"])

        # Should exit 0 (fresh check found 4K)
        assert result.exit_code == 0
        assert "4K available" in result.stdout
        # get_cached_result should NOT have been called
        mock_state_manager.get_cached_result.assert_not_called()

    def test_check_movie_dry_run_bypasses_cache(self) -> None:
        """Should bypass cache when --dry-run is specified."""
        cached_record = CheckRecord(
            last_checked=datetime.now(UTC) - timedelta(minutes=30),
            result="unavailable",
        )
        mock_result = SearchResult(item_id=123, item_type="movie", has_match=True)
        mock_config = Config(radarr=RadarrConfig(url="http://localhost:7878", api_key="key"))

        mock_state_manager = _create_mock_state_manager()
        mock_state_manager.get_cached_result.return_value = cached_record

        async def mock_check_movie(_movie_id: int, **_kwargs: object) -> SearchResult:
            return mock_result

        mock_checker = MagicMock()
        mock_checker.check_movie = mock_check_movie

        with (
            patch("filtarr.cli.Config.load", return_value=mock_config),
            patch("filtarr.cli.get_checker", return_value=mock_checker),
            patch("filtarr.cli.get_state_manager", return_value=mock_state_manager),
        ):
            result = runner.invoke(
                app, ["check", "movie", "123", "--dry-run", "--format", "simple"]
            )

        # Should exit 0 (fresh check found 4K)
        assert result.exit_code == 0
        # get_cached_result should NOT have been called because of --dry-run
        mock_state_manager.get_cached_result.assert_not_called()


class TestServeLogLevelValidation:
    """Tests for serve command log level validation via global flag."""

    def test_serve_invalid_log_level_exits_with_error(self) -> None:
        """Should exit with error when an invalid log level is provided."""
        # Global flag is validated before command runs
        result = runner.invoke(app, ["--log-level", "INVALID", "serve"])

        assert result.exit_code == 1
        assert "Invalid log level: INVALID" in result.output
        assert "Valid options:" in result.output

    def test_serve_valid_log_level_accepted(self) -> None:
        """Should accept valid log levels (case-insensitive)."""
        mock_config = Config(
            radarr=RadarrConfig(url="http://localhost:7878", api_key="key"),
        )

        # Mock run_server to avoid actually starting the server
        with (
            patch("filtarr.cli.Config.load", return_value=mock_config),
            patch("filtarr.webhook.run_server"),
            patch("filtarr.cli.configure_logging"),
        ):
            result = runner.invoke(app, ["--log-level", "debug", "serve"])

        # Should not exit with error (log level is valid)
        # The command will either succeed or fail for other reasons (like missing deps)
        # but not due to log level validation
        assert "Invalid log level" not in result.output


class TestIsTransientError:
    """Tests for _is_transient_error function."""

    def test_http_5xx_errors_are_transient(self) -> None:
        """Should classify 5xx HTTP errors as transient."""
        mock_response = MagicMock()
        mock_request = MagicMock()

        # Test 500 Internal Server Error
        mock_response.status_code = 500
        error = httpx.HTTPStatusError("Server error", request=mock_request, response=mock_response)
        assert _is_transient_error(error) is True

        # Test 502 Bad Gateway
        mock_response.status_code = 502
        error = httpx.HTTPStatusError("Bad Gateway", request=mock_request, response=mock_response)
        assert _is_transient_error(error) is True

        # Test 503 Service Unavailable
        mock_response.status_code = 503
        error = httpx.HTTPStatusError(
            "Service Unavailable", request=mock_request, response=mock_response
        )
        assert _is_transient_error(error) is True

        # Test 504 Gateway Timeout
        mock_response.status_code = 504
        error = httpx.HTTPStatusError(
            "Gateway Timeout", request=mock_request, response=mock_response
        )
        assert _is_transient_error(error) is True

    def test_http_429_rate_limit_is_transient(self) -> None:
        """Should classify 429 Too Many Requests as transient."""
        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_request = MagicMock()
        error = httpx.HTTPStatusError(
            "Too Many Requests", request=mock_request, response=mock_response
        )
        assert _is_transient_error(error) is True

    def test_http_4xx_errors_are_not_transient(self) -> None:
        """Should classify 4xx HTTP errors (except 429) as permanent."""
        mock_response = MagicMock()
        mock_request = MagicMock()

        # Test 400 Bad Request
        mock_response.status_code = 400
        error = httpx.HTTPStatusError("Bad Request", request=mock_request, response=mock_response)
        assert _is_transient_error(error) is False

        # Test 401 Unauthorized
        mock_response.status_code = 401
        error = httpx.HTTPStatusError("Unauthorized", request=mock_request, response=mock_response)
        assert _is_transient_error(error) is False

        # Test 403 Forbidden
        mock_response.status_code = 403
        error = httpx.HTTPStatusError("Forbidden", request=mock_request, response=mock_response)
        assert _is_transient_error(error) is False

        # Test 404 Not Found
        mock_response.status_code = 404
        error = httpx.HTTPStatusError("Not Found", request=mock_request, response=mock_response)
        assert _is_transient_error(error) is False

    def test_connect_error_is_transient(self) -> None:
        """Should classify ConnectError as transient."""
        error = httpx.ConnectError("Connection refused")
        assert _is_transient_error(error) is True

    def test_timeout_exception_is_transient(self) -> None:
        """Should classify TimeoutException as transient."""
        error = httpx.TimeoutException("Request timed out")
        assert _is_transient_error(error) is True

    def test_configuration_error_is_not_transient(self) -> None:
        """Should classify ConfigurationError as permanent (not transient)."""
        error = ConfigurationError("Radarr not configured")
        assert _is_transient_error(error) is False

    def test_unknown_error_is_transient(self) -> None:
        """Should classify unknown errors as transient (safer for retry)."""
        error1 = RuntimeError("Unknown error")
        assert _is_transient_error(error1) is True

        error2 = ValueError("Some value error")
        assert _is_transient_error(error2) is True


class TestGlobalOutputFlags:
    """Tests for global --timestamps and --output-format flags."""

    def test_global_timestamps_flag_default(self) -> None:
        """Timestamps should default to True."""
        result = runner.invoke(app, ["version"])
        assert result.exit_code == 0

    def test_global_no_timestamps_flag(self) -> None:
        """--no-timestamps flag should be accepted."""
        result = runner.invoke(app, ["--no-timestamps", "version"])
        assert result.exit_code == 0

    def test_global_output_format_text(self) -> None:
        """--output-format text should be accepted."""
        result = runner.invoke(app, ["--output-format", "text", "version"])
        assert result.exit_code == 0

    def test_global_output_format_json(self) -> None:
        """--output-format json should be accepted."""
        result = runner.invoke(app, ["--output-format", "json", "version"])
        assert result.exit_code == 0


class TestGetEffectiveFormat:
    """Tests for _get_effective_format helper function."""

    def test_explicit_format_wins_over_global(self) -> None:
        """Explicit --format should override global --output-format."""

        # Mock context with global json
        class MockObj:
            def get(self, key: str, default: str) -> str:
                return "json" if key == "output_format" else default

        class MockCtx:
            obj = MockObj()

        result = _get_effective_format(MockCtx(), OutputFormat.TABLE, OutputFormat.SIMPLE)  # type: ignore[arg-type]
        assert result == OutputFormat.TABLE  # Explicit wins

    def test_global_json_when_no_explicit(self) -> None:
        """Global --output-format json should be used when no explicit format."""

        class MockObj:
            def get(self, key: str, default: str) -> str:
                return "json" if key == "output_format" else default

        class MockCtx:
            obj = MockObj()

        result = _get_effective_format(MockCtx(), None, OutputFormat.TABLE)  # type: ignore[arg-type]
        assert result == OutputFormat.JSON

    def test_default_when_global_text(self) -> None:
        """Default should be used when global is text and no explicit format."""

        class MockObj:
            def get(self, key: str, default: str) -> str:
                return "text" if key == "output_format" else default

        class MockCtx:
            obj = MockObj()

        result = _get_effective_format(MockCtx(), None, OutputFormat.TABLE)  # type: ignore[arg-type]
        assert result == OutputFormat.TABLE

    def test_default_when_no_context(self) -> None:
        """Default should be used when context is None."""
        result = _get_effective_format(None, None, OutputFormat.SIMPLE)
        assert result == OutputFormat.SIMPLE

    def test_default_when_context_obj_none(self) -> None:
        """Default should be used when context.obj is None."""

        class MockCtx:
            obj = None

        result = _get_effective_format(MockCtx(), None, OutputFormat.TABLE)  # type: ignore[arg-type]
        assert result == OutputFormat.TABLE


class TestGlobalOutputFormatIntegration:
    """Integration tests for global --output-format affecting commands."""

    def test_global_output_format_json_check_movie(self) -> None:
        """Global --output-format json should produce JSON output for check movie."""
        mock_result = SearchResult(item_id=123, item_type="movie", has_match=True)
        mock_config = Config(radarr=RadarrConfig(url="http://localhost:7878", api_key="key"))

        async def mock_check_movie(_movie_id: int, **_kwargs: object) -> SearchResult:
            return mock_result

        mock_checker = MagicMock()
        mock_checker.check_movie = mock_check_movie
        mock_state_manager = _create_mock_state_manager()

        with (
            patch("filtarr.cli.Config.load", return_value=mock_config),
            patch("filtarr.cli.get_checker", return_value=mock_checker),
            patch("filtarr.cli.get_state_manager", return_value=mock_state_manager),
        ):
            result = runner.invoke(app, ["--output-format", "json", "check", "movie", "123"])

        assert result.exit_code == 0
        # Output should be valid JSON
        data = json.loads(result.output)
        assert data["item_id"] == 123
        assert data["has_match"] is True

    def test_global_output_format_text_uses_table_default(self) -> None:
        """Global --output-format text should use command's default format (TABLE)."""
        mock_result = SearchResult(item_id=123, item_type="movie", has_match=True)
        mock_config = Config(radarr=RadarrConfig(url="http://localhost:7878", api_key="key"))

        async def mock_check_movie(_movie_id: int, **_kwargs: object) -> SearchResult:
            return mock_result

        mock_checker = MagicMock()
        mock_checker.check_movie = mock_check_movie
        mock_state_manager = _create_mock_state_manager()

        with (
            patch("filtarr.cli.Config.load", return_value=mock_config),
            patch("filtarr.cli.get_checker", return_value=mock_checker),
            patch("filtarr.cli.get_state_manager", return_value=mock_state_manager),
        ):
            result = runner.invoke(app, ["--output-format", "text", "check", "movie", "123"])

        assert result.exit_code == 0
        # Should contain TABLE format output (not JSON, not simple)
        assert "Release Check" in result.output
        assert "Movie 123" in result.output

    def test_explicit_format_overrides_global_json(self) -> None:
        """Explicit --format simple should override global --output-format json."""
        mock_result = SearchResult(item_id=123, item_type="movie", has_match=True)
        mock_config = Config(radarr=RadarrConfig(url="http://localhost:7878", api_key="key"))

        async def mock_check_movie(_movie_id: int, **_kwargs: object) -> SearchResult:
            return mock_result

        mock_checker = MagicMock()
        mock_checker.check_movie = mock_check_movie
        mock_state_manager = _create_mock_state_manager()

        with (
            patch("filtarr.cli.Config.load", return_value=mock_config),
            patch("filtarr.cli.get_checker", return_value=mock_checker),
            patch("filtarr.cli.get_state_manager", return_value=mock_state_manager),
        ):
            result = runner.invoke(
                app, ["--output-format", "json", "check", "movie", "123", "--format", "simple"]
            )

        assert result.exit_code == 0
        # Should be SIMPLE format, not JSON
        assert "movie:123: 4K available" in result.output
        # Should NOT be valid JSON (simple format isn't JSON)
        with pytest.raises(json.JSONDecodeError):
            json.loads(result.output)
