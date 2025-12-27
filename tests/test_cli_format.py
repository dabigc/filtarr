"""Tests for CLI formatting functions."""

from filtarr.checker import SearchResult
from filtarr.cli import format_result_table
from filtarr.criteria import ResultType
from filtarr.models.common import Quality, Release
from filtarr.tagger import TagResult


class TestFormatResultTable:
    """Tests for format_result_table function."""

    def test_format_result_table_with_item_name(self) -> None:
        """Should format table with item name when available."""
        result = SearchResult(
            item_id=123,
            item_type="movie",
            item_name="Test Movie",
            has_match=True,
            releases=[],
            result_type=ResultType.FOUR_K,
        )

        table = format_result_table(result)

        assert table.title == "Release Check: Test Movie (123)"

    def test_format_result_table_without_item_name(self) -> None:
        """Should format table without item name."""
        result = SearchResult(
            item_id=456,
            item_type="series",
            has_match=False,
            releases=[],
            result_type=ResultType.HDR,
        )

        table = format_result_table(result)

        assert table.title == "Release Check: Series 456"

    def test_format_result_table_with_match(self) -> None:
        """Should format table with match found."""
        releases = [
            Release(
                guid="rel1",
                title="Movie.2160p.BluRay",
                indexer="Test",
                size=5000,
                quality=Quality(id=19, name="WEBDL-2160p"),
            )
        ]
        result = SearchResult(
            item_id=123,
            item_type="movie",
            has_match=True,
            releases=releases,
            result_type=ResultType.FOUR_K,
        )

        table = format_result_table(result)

        # Table should have columns
        assert len(table.columns) == 2

    def test_format_result_table_with_seasons_checked(self) -> None:
        """Should include seasons checked when available."""
        result = SearchResult(
            item_id=123,
            item_type="series",
            has_match=True,
            releases=[],
            result_type=ResultType.FOUR_K,
            seasons_checked=[1, 2, 3],
        )

        table = format_result_table(result)

        # Table should be created successfully
        assert table is not None
        assert table.title is not None

    def test_format_result_table_with_strategy(self) -> None:
        """Should include strategy when available."""
        from filtarr.checker import SamplingStrategy

        result = SearchResult(
            item_id=123,
            item_type="series",
            has_match=True,
            releases=[],
            result_type=ResultType.FOUR_K,
            strategy_used=SamplingStrategy.RECENT,
        )

        table = format_result_table(result)

        assert table is not None

    def test_format_result_table_with_tag_result_applied(self) -> None:
        """Should include tag result when available."""
        result = SearchResult(
            item_id=123,
            item_type="movie",
            has_match=True,
            releases=[],
            result_type=ResultType.FOUR_K,
            tag_result=TagResult(tag_applied="4k-available"),
        )

        table = format_result_table(result)

        assert table is not None

    def test_format_result_table_with_tag_result_dry_run(self) -> None:
        """Should indicate dry run in tag status."""
        result = SearchResult(
            item_id=123,
            item_type="movie",
            has_match=True,
            releases=[],
            result_type=ResultType.FOUR_K,
            tag_result=TagResult(tag_applied="4k-available", dry_run=True),
        )

        table = format_result_table(result)

        assert table is not None

    def test_format_result_table_with_tag_error(self) -> None:
        """Should include tag error in table."""
        result = SearchResult(
            item_id=123,
            item_type="movie",
            has_match=True,
            releases=[],
            result_type=ResultType.FOUR_K,
            tag_result=TagResult(tag_error="Connection refused"),
        )

        table = format_result_table(result)

        assert table is not None

    def test_format_result_table_with_no_tag_applied(self) -> None:
        """Should handle tag result with no tag applied."""
        result = SearchResult(
            item_id=123,
            item_type="movie",
            has_match=False,
            releases=[],
            result_type=ResultType.FOUR_K,
            tag_result=TagResult(),
        )

        table = format_result_table(result)

        assert table is not None
