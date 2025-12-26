"""Tests for individual criteria matcher functions."""

from __future__ import annotations

from filtarr.criteria import (
    _match_directors_cut,
    _match_dolby_vision,
    _match_extended,
    _match_hdr,
    _match_imax,
    _match_remaster,
)
from filtarr.models.common import Quality, Release


def create_release(title: str, quality_name: str = "WEBDL-1080p") -> Release:
    """Create a Release object with the given title and quality."""
    return Release(
        guid="test-guid",
        title=title,
        indexer="TestIndexer",
        size=1000000,
        quality=Quality(id=1, name=quality_name),
    )


class TestMatchHdr:
    """Tests for _match_hdr() function."""

    def test_match_hdr_lowercase(self) -> None:
        """Test matching 'hdr' in lowercase."""
        release = create_release("Movie.2024.2160p.hdr.BluRay")
        assert _match_hdr(release) is True

    def test_match_hdr_uppercase(self) -> None:
        """Test matching 'HDR' in uppercase."""
        release = create_release("Movie.2024.2160p.HDR.BluRay")
        assert _match_hdr(release) is True

    def test_match_hdr_mixed_case(self) -> None:
        """Test matching 'Hdr' in mixed case."""
        release = create_release("Movie.2024.2160p.Hdr.BluRay")
        assert _match_hdr(release) is True

    def test_match_hdr10(self) -> None:
        """Test matching 'hdr10'."""
        release = create_release("Movie.2024.2160p.HDR10.BluRay")
        assert _match_hdr(release) is True

    def test_match_hdr10_lowercase(self) -> None:
        """Test matching 'hdr10' in lowercase."""
        release = create_release("Movie.2024.2160p.hdr10.BluRay")
        assert _match_hdr(release) is True

    def test_match_hdr10_plus(self) -> None:
        """Test matching 'hdr10+'."""
        release = create_release("Movie.2024.2160p.HDR10+.BluRay")
        assert _match_hdr(release) is True

    def test_match_hdr10_plus_lowercase(self) -> None:
        """Test matching 'hdr10+' in lowercase."""
        release = create_release("Movie.2024.2160p.hdr10+.BluRay")
        assert _match_hdr(release) is True

    def test_no_match_without_hdr(self) -> None:
        """Test non-matching title without HDR."""
        release = create_release("Movie.2024.2160p.BluRay")
        assert _match_hdr(release) is False

    def test_no_match_sdr(self) -> None:
        """Test non-matching title with SDR."""
        release = create_release("Movie.2024.2160p.SDR.BluRay")
        assert _match_hdr(release) is False

    def test_match_hdr_in_middle(self) -> None:
        """Test matching HDR in the middle of the title."""
        release = create_release("Some.Movie.HDR.2160p.BluRay.x265")
        assert _match_hdr(release) is True


class TestMatchDolbyVision:
    """Tests for _match_dolby_vision() function."""

    def test_match_dv_uppercase(self) -> None:
        """Test matching 'DV' (Dolby Vision abbreviation)."""
        release = create_release("Movie.2024.2160p.DV.BluRay")
        assert _match_dolby_vision(release) is True

    def test_match_dv_lowercase(self) -> None:
        """Test matching 'dv' in lowercase."""
        release = create_release("Movie.2024.2160p.dv.BluRay")
        assert _match_dolby_vision(release) is True

    def test_match_dolby_vision_full(self) -> None:
        """Test matching 'dolby vision' full phrase."""
        release = create_release("Movie.2024.2160p.Dolby Vision.BluRay")
        assert _match_dolby_vision(release) is True

    def test_match_dolby_vision_lowercase(self) -> None:
        """Test matching 'dolby vision' in lowercase."""
        release = create_release("Movie.2024.2160p.dolby vision.BluRay")
        assert _match_dolby_vision(release) is True

    def test_match_dolbyvision_no_space(self) -> None:
        """Test matching 'dolbyvision' without space."""
        release = create_release("Movie.2024.2160p.DolbyVision.BluRay")
        assert _match_dolby_vision(release) is True

    def test_match_dolbyvision_lowercase_no_space(self) -> None:
        """Test matching 'dolbyvision' in lowercase without space."""
        release = create_release("Movie.2024.2160p.dolbyvision.BluRay")
        assert _match_dolby_vision(release) is True

    def test_no_match_without_dolby_vision(self) -> None:
        """Test non-matching title without Dolby Vision."""
        release = create_release("Movie.2024.2160p.BluRay")
        assert _match_dolby_vision(release) is False

    def test_no_match_dolby_atmos(self) -> None:
        """Test that 'Dolby Atmos' (audio) doesn't match."""
        release = create_release("Movie.2024.2160p.Dolby.Atmos.BluRay")
        assert _match_dolby_vision(release) is False

    def test_match_dv_hdr_combo(self) -> None:
        """Test matching when both DV and HDR are in title."""
        release = create_release("Movie.2024.2160p.DV.HDR.BluRay")
        assert _match_dolby_vision(release) is True


class TestMatchDirectorsCut:
    """Tests for _match_directors_cut() function."""

    def test_match_directors_cut_apostrophe(self) -> None:
        """Test matching 'Director's Cut'."""
        release = create_release("Movie.2024.Director's.Cut.BluRay")
        assert _match_directors_cut(release) is True

    def test_match_directors_cut_no_apostrophe(self) -> None:
        """Test matching 'Directors Cut' without apostrophe."""
        release = create_release("Movie.2024.Directors.Cut.BluRay")
        assert _match_directors_cut(release) is True

    def test_match_director_cut_lowercase(self) -> None:
        """Test matching 'director cut' in lowercase."""
        release = create_release("Movie.2024.director.cut.BluRay")
        assert _match_directors_cut(release) is True

    def test_match_director_cut_mixed_case(self) -> None:
        """Test matching with mixed case."""
        release = create_release("Movie.2024.Director.CUT.BluRay")
        assert _match_directors_cut(release) is True

    def test_match_director_and_cut_separated(self) -> None:
        """Test matching when 'director' and 'cut' are separated."""
        release = create_release("Movie.2024.Director.Extended.Cut.BluRay")
        assert _match_directors_cut(release) is True

    def test_no_match_only_director(self) -> None:
        """Test non-matching when only 'director' is present."""
        release = create_release("Movie.2024.by.Director.John.BluRay")
        assert _match_directors_cut(release) is False

    def test_no_match_only_cut(self) -> None:
        """Test non-matching when only 'cut' is present."""
        release = create_release("Movie.2024.Final.Cut.BluRay")
        assert _match_directors_cut(release) is False

    def test_no_match_neither(self) -> None:
        """Test non-matching when neither word is present."""
        release = create_release("Movie.2024.2160p.BluRay")
        assert _match_directors_cut(release) is False


class TestMatchExtended:
    """Tests for _match_extended() function."""

    def test_match_extended_lowercase(self) -> None:
        """Test matching 'extended' in lowercase."""
        release = create_release("Movie.2024.extended.BluRay")
        assert _match_extended(release) is True

    def test_match_extended_uppercase(self) -> None:
        """Test matching 'EXTENDED' in uppercase."""
        release = create_release("Movie.2024.EXTENDED.BluRay")
        assert _match_extended(release) is True

    def test_match_extended_mixed_case(self) -> None:
        """Test matching 'Extended' in mixed case."""
        release = create_release("Movie.2024.Extended.BluRay")
        assert _match_extended(release) is True

    def test_match_extended_edition(self) -> None:
        """Test matching 'Extended Edition'."""
        release = create_release("Movie.2024.Extended.Edition.BluRay")
        assert _match_extended(release) is True

    def test_match_extended_cut(self) -> None:
        """Test matching 'Extended Cut'."""
        release = create_release("Movie.2024.Extended.Cut.BluRay")
        assert _match_extended(release) is True

    def test_no_match_without_extended(self) -> None:
        """Test non-matching title without 'extended'."""
        release = create_release("Movie.2024.2160p.BluRay")
        assert _match_extended(release) is False

    def test_no_match_extend(self) -> None:
        """Test that partial word 'extend' doesn't match."""
        release = create_release("Movie.2024.We.Extend.Our.Thanks.BluRay")
        # 'extend' doesn't match 'extended'
        assert _match_extended(release) is False


class TestMatchRemaster:
    """Tests for _match_remaster() function."""

    def test_match_remaster_lowercase(self) -> None:
        """Test matching 'remaster' in lowercase."""
        release = create_release("Movie.2024.remaster.BluRay")
        assert _match_remaster(release) is True

    def test_match_remaster_uppercase(self) -> None:
        """Test matching 'REMASTER' in uppercase."""
        release = create_release("Movie.2024.REMASTER.BluRay")
        assert _match_remaster(release) is True

    def test_match_remastered(self) -> None:
        """Test matching 'Remastered'."""
        release = create_release("Movie.2024.Remastered.BluRay")
        assert _match_remaster(release) is True

    def test_match_remastered_lowercase(self) -> None:
        """Test matching 'remastered' in lowercase."""
        release = create_release("Movie.2024.remastered.BluRay")
        assert _match_remaster(release) is True

    def test_match_4k_remaster(self) -> None:
        """Test matching '4K Remaster'."""
        release = create_release("Movie.2024.4K.Remaster.BluRay")
        assert _match_remaster(release) is True

    def test_no_match_without_remaster(self) -> None:
        """Test non-matching title without 'remaster'."""
        release = create_release("Movie.2024.2160p.BluRay")
        assert _match_remaster(release) is False

    def test_no_match_master(self) -> None:
        """Test that 'master' alone doesn't match."""
        release = create_release("Movie.2024.Master.BluRay")
        assert _match_remaster(release) is False


class TestMatchImax:
    """Tests for _match_imax() function."""

    def test_match_imax_uppercase(self) -> None:
        """Test matching 'IMAX' in uppercase."""
        release = create_release("Movie.2024.IMAX.BluRay")
        assert _match_imax(release) is True

    def test_match_imax_lowercase(self) -> None:
        """Test matching 'imax' in lowercase."""
        release = create_release("Movie.2024.imax.BluRay")
        assert _match_imax(release) is True

    def test_match_imax_mixed_case(self) -> None:
        """Test matching 'Imax' in mixed case."""
        release = create_release("Movie.2024.Imax.BluRay")
        assert _match_imax(release) is True

    def test_match_imax_edition(self) -> None:
        """Test matching 'IMAX Edition'."""
        release = create_release("Movie.2024.IMAX.Edition.BluRay")
        assert _match_imax(release) is True

    def test_match_imax_enhanced(self) -> None:
        """Test matching 'IMAX Enhanced'."""
        release = create_release("Movie.2024.IMAX.Enhanced.BluRay")
        assert _match_imax(release) is True

    def test_no_match_without_imax(self) -> None:
        """Test non-matching title without 'imax'."""
        release = create_release("Movie.2024.2160p.BluRay")
        assert _match_imax(release) is False

    def test_no_match_max(self) -> None:
        """Test that 'max' alone doesn't match."""
        release = create_release("Movie.2024.Max.BluRay")
        assert _match_imax(release) is False


class TestMatchersNegativeCases:
    """Additional negative test cases for all matchers."""

    def test_hdr_not_in_unrelated_word(self) -> None:
        """Test that HDR doesn't match inside unrelated words."""
        # 'hdr' inside another word - but since we check with 'in', this would match
        # This documents current behavior
        release = create_release("Movie.2024.Cathedral.BluRay")
        # 'cathedral' doesn't contain 'hdr' as standalone
        assert _match_hdr(release) is False

    def test_empty_title(self) -> None:
        """Test matchers with empty title."""
        release = create_release("")
        assert _match_hdr(release) is False
        assert _match_dolby_vision(release) is False
        assert _match_directors_cut(release) is False
        assert _match_extended(release) is False
        assert _match_remaster(release) is False
        assert _match_imax(release) is False

    def test_only_dots_title(self) -> None:
        """Test matchers with title containing only dots."""
        release = create_release("...")
        assert _match_hdr(release) is False
        assert _match_dolby_vision(release) is False
        assert _match_directors_cut(release) is False
        assert _match_extended(release) is False
        assert _match_remaster(release) is False
        assert _match_imax(release) is False

    def test_whitespace_title(self) -> None:
        """Test matchers with whitespace-only title."""
        release = create_release("   ")
        assert _match_hdr(release) is False
        assert _match_dolby_vision(release) is False
        assert _match_directors_cut(release) is False
        assert _match_extended(release) is False
        assert _match_remaster(release) is False
        assert _match_imax(release) is False

    def test_standard_release_no_special_features(self) -> None:
        """Test a standard release with no special edition features."""
        release = create_release("Generic.Movie.2024.1080p.BluRay.x264-GROUP")
        assert _match_hdr(release) is False
        assert _match_dolby_vision(release) is False
        assert _match_directors_cut(release) is False
        assert _match_extended(release) is False
        assert _match_remaster(release) is False
        assert _match_imax(release) is False
