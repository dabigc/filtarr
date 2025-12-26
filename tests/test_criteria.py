"""Tests for criteria matching functions."""

from filtarr.criteria import _contains_edition_phrase, _match_special_edition
from filtarr.models.common import Quality, Release


def _make_release(title: str) -> Release:
    """Create a Release with the given title for testing."""
    return Release(
        guid="test",
        title=title,
        indexer="Test",
        size=1000,
        quality=Quality(id=1, name="test"),
    )


class TestContainsEditionPhrase:
    """Tests for the _contains_edition_phrase helper function."""

    def test_matches_at_start_of_string(self) -> None:
        """Should match phrase at start of string."""
        assert _contains_edition_phrase("special edition release", "special edition")

    def test_matches_at_end_of_string(self) -> None:
        """Should match phrase at end of string."""
        assert _contains_edition_phrase("movie special edition", "special edition")

    def test_matches_exact_string(self) -> None:
        """Should match when phrase is entire string."""
        assert _contains_edition_phrase("special edition", "special edition")

    def test_matches_with_dot_separator(self) -> None:
        """Should match phrase with dot separators."""
        assert _contains_edition_phrase("movie.special edition.2160p", "special edition")

    def test_matches_with_dash_separator(self) -> None:
        """Should match phrase with dash separators."""
        assert _contains_edition_phrase("movie-special edition-2160p", "special edition")

    def test_matches_with_underscore_separator(self) -> None:
        """Should match phrase with underscore separators."""
        assert _contains_edition_phrase("movie_special edition_2160p", "special edition")

    def test_rejects_embedded_in_word(self) -> None:
        """Should reject phrase embedded in larger word."""
        # "aspecial" is not "special"
        assert not _contains_edition_phrase("aspecial edition", "special edition")

    def test_rejects_word_continuation_after(self) -> None:
        """Should reject when phrase continues into another word."""
        # "editions" is not "edition"
        assert not _contains_edition_phrase("special editions", "special edition")

    def test_rejects_partial_match(self) -> None:
        """Should reject when only part of phrase matches."""
        assert not _contains_edition_phrase("special day", "special edition")

    def test_handles_multiple_occurrences(self) -> None:
        """Should find valid match even with invalid occurrence first."""
        # First occurrence is invalid (aspecial), second is valid
        assert _contains_edition_phrase(
            "aspecial edition but also special edition here", "special edition"
        )


class TestMatchSpecialEdition:
    """Tests for the _match_special_edition matcher function."""

    def test_matches_special_edition_with_spaces(self) -> None:
        """Should match 'special edition' with spaces."""
        release = _make_release("Movie.2024.Special Edition.2160p.BluRay")
        assert _match_special_edition(release)

    def test_matches_special_edition_with_dots(self) -> None:
        """Should match 'special.edition' with dots."""
        release = _make_release("Movie.2024.special.edition.2160p.BluRay")
        assert _match_special_edition(release)

    def test_matches_collectors_edition(self) -> None:
        """Should match collector's edition variations."""
        for variant in ["Collector's Edition", "collectors edition", "Collector Edition"]:
            release = _make_release(f"Movie.2024.{variant}.2160p")
            assert _match_special_edition(release), f"Failed for: {variant}"

    def test_matches_anniversary_edition(self) -> None:
        """Should match anniversary edition."""
        release = _make_release("Movie.25th.Anniversary Edition.2160p")
        assert _match_special_edition(release)

    def test_matches_ultimate_edition(self) -> None:
        """Should match ultimate edition."""
        release = _make_release("Movie.2024.Ultimate Edition.2160p")
        assert _match_special_edition(release)

    def test_matches_definitive_edition(self) -> None:
        """Should match definitive edition."""
        release = _make_release("Game.Definitive Edition.2024.2160p")
        assert _match_special_edition(release)

    def test_rejects_non_special_edition(self) -> None:
        """Should reject regular releases without special edition markers."""
        release = _make_release("Movie.2024.2160p.BluRay.x265")
        assert not _match_special_edition(release)

    def test_rejects_false_positive_embedded(self) -> None:
        """Should reject false positives from embedded words."""
        # "aspecial.edition" should not match
        release = _make_release("Movie.aspecial.edition.2160p")
        assert not _match_special_edition(release)

    def test_rejects_false_positive_plural(self) -> None:
        """Should reject false positives from plural forms."""
        # "collectors editions" (plural) should not match "collectors edition"
        release = _make_release("Movie.collectors editions.2160p")
        assert not _match_special_edition(release)

    def test_case_insensitive(self) -> None:
        """Should match case-insensitively."""
        release = _make_release("Movie.SPECIAL EDITION.2160p")
        assert _match_special_edition(release)
