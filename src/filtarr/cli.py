"""Command-line interface for filtarr."""

from __future__ import annotations

import asyncio
import json
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path  # noqa: TC003 - needed at runtime for typer
from typing import TYPE_CHECKING, Annotated, Literal

import httpx
import typer
from rich.console import Console
from rich.progress import BarColumn, Progress, TaskProgressColumn, TextColumn, TimeElapsedColumn
from rich.table import Table

from filtarr import __version__
from filtarr.checker import ReleaseChecker, SamplingStrategy, SearchResult
from filtarr.clients.radarr import RadarrClient
from filtarr.clients.sonarr import SonarrClient
from filtarr.config import VALID_LOG_LEVELS, Config, ConfigurationError
from filtarr.criteria import MOVIE_ONLY_CRITERIA, SearchCriteria
from filtarr.logging import configure_logging
from filtarr.output import OutputFormatter
from filtarr.state import BatchProgress, CheckRecord, StateManager

# Map CLI criteria names to SearchCriteria enum values
CRITERIA_MAP: dict[str, SearchCriteria] = {
    "4k": SearchCriteria.FOUR_K,
    "hdr": SearchCriteria.HDR,
    "dolby-vision": SearchCriteria.DOLBY_VISION,
    "directors-cut": SearchCriteria.DIRECTORS_CUT,
    "extended": SearchCriteria.EXTENDED,
    "remaster": SearchCriteria.REMASTER,
    "imax": SearchCriteria.IMAX,
    "special-edition": SearchCriteria.SPECIAL_EDITION,
}

VALID_CRITERIA_NAMES = list(CRITERIA_MAP.keys())

if TYPE_CHECKING:
    from filtarr.models.radarr import Movie
    from filtarr.models.sonarr import Series
    from filtarr.scheduler import SchedulerManager

app = typer.Typer(
    name="filtarr",
    help="Check release availability for movies and TV shows via Radarr/Sonarr.",
    no_args_is_help=True,
)
check_app = typer.Typer(help="Check release availability for movies and TV shows.")
app.add_typer(check_app, name="check")

schedule_app = typer.Typer(help="Manage scheduled batch operations.")
app.add_typer(schedule_app, name="schedule")

console = Console()
error_console = Console(stderr=True)


@app.callback()
def main(
    ctx: typer.Context,
    log_level: Annotated[
        str | None,
        typer.Option(
            "--log-level",
            "-l",
            help="Logging level (debug, info, warning, error, critical).",
        ),
    ] = None,
    timestamps: Annotated[
        bool,
        typer.Option(
            "--timestamps/--no-timestamps",
            help="Show timestamps in output (default: enabled).",
        ),
    ] = True,
    output_format: Annotated[
        str | None,
        typer.Option(
            "--output-format",
            help="Output format: text or json (default: text).",
        ),
    ] = None,
) -> None:
    """filtarr - Check release availability for movies and TV shows via Radarr/Sonarr."""
    import os

    # Priority: CLI > env var > config.toml > default
    if log_level:
        effective_level = log_level
    elif os.environ.get("FILTARR_LOG_LEVEL"):
        effective_level = os.environ["FILTARR_LOG_LEVEL"]
    else:
        try:
            config = Config.load()
            effective_level = config.logging.level
        except ConfigurationError:
            effective_level = "INFO"

    # Validate
    if effective_level.upper() not in VALID_LOG_LEVELS:
        error_console.print(
            f"[red]Invalid log level: {effective_level}[/red]\n"
            f"Valid options: {', '.join(sorted(VALID_LOG_LEVELS))}"
        )
        raise typer.Exit(1)

    # Configure logging
    configure_logging(level=effective_level)

    # Store in context for commands that need it
    ctx.ensure_object(dict)
    ctx.obj["log_level"] = effective_level.upper()
    ctx.obj["timestamps"] = timestamps
    ctx.obj["output_format"] = output_format or "text"


class OutputFormat(str, Enum):
    """Output format options."""

    JSON = "json"
    TABLE = "table"
    SIMPLE = "simple"


def format_result_json(result: SearchResult) -> str:
    """Format result as JSON."""
    data: dict[str, object] = {
        "item_id": result.item_id,
        "item_type": result.item_type,
        "item_name": result.item_name,
        "has_match": result.has_match,
        "result_type": result.result_type.value,
        "releases_count": len(result.releases),
        "matched_releases_count": len(result.matched_releases),
    }
    if result.episodes_checked:
        data["episodes_checked"] = result.episodes_checked
    if result.seasons_checked:
        data["seasons_checked"] = result.seasons_checked
    if result.strategy_used:
        data["strategy_used"] = result.strategy_used.value
    if result.tag_result:
        data["tag"] = {
            "applied": result.tag_result.tag_applied,
            "removed": result.tag_result.tag_removed,
            "created": result.tag_result.tag_created,
            "error": result.tag_result.tag_error,
            "dry_run": result.tag_result.dry_run,
        }

    return json.dumps(data, indent=2)


def _get_effective_format(
    typer_ctx: typer.Context | None,
    explicit_format: OutputFormat | None,
    default: OutputFormat,
) -> OutputFormat:
    """Get effective output format respecting global flag.

    Priority: explicit --format > global --output-format > command default.

    Args:
        typer_ctx: Typer context with global options.
        explicit_format: Explicitly passed --format value (None if not specified).
        default: Command's default format.

    Returns:
        The effective OutputFormat to use.
    """
    # Explicit --format always wins
    if explicit_format is not None:
        return explicit_format

    # Check global --output-format
    if typer_ctx and typer_ctx.obj:
        global_format = typer_ctx.obj.get("output_format", "text")
        if global_format == "json":
            return OutputFormat.JSON

    # Fall back to command's default
    return default


def format_result_table(result: SearchResult) -> Table:
    """Format result as a rich table."""
    if result.item_name:
        title = f"Release Check: {result.item_name} ({result.item_id})"
    else:
        title = f"Release Check: {result.item_type.title()} {result.item_id}"
    table = Table(title=title)

    table.add_column("Property", style="cyan")
    table.add_column("Value", style="green" if result.has_match else "red")

    table.add_row("Match Found", "Yes" if result.has_match else "No")
    table.add_row("Search Type", _format_result_type(result.result_type.value))
    table.add_row("Total Releases", str(len(result.releases)))
    table.add_row("Matched Releases", str(len(result.matched_releases)))

    if result.seasons_checked:
        table.add_row("Seasons Checked", ", ".join(map(str, result.seasons_checked)))
    if result.strategy_used:
        table.add_row("Strategy", result.strategy_used.value)

    if result.tag_result:
        if result.tag_result.dry_run:
            tag_status = f"Would apply: {result.tag_result.tag_applied}"
        elif result.tag_result.tag_error:
            tag_status = f"Error: {result.tag_result.tag_error}"
        else:
            tag_status = result.tag_result.tag_applied or "None"
        table.add_row("Tag Applied", tag_status)

    return table


def _format_result_type(result_type_value: str) -> str:
    """Format result type for user-friendly display.

    Converts enum values to user-friendly display strings.
    E.g., "4k" -> "4K", "directors_cut" -> "Director's Cut"
    """
    display_names = {
        "4k": "4K",
        "hdr": "HDR",
        "dolby_vision": "Dolby Vision",
        "directors_cut": "Director's Cut",
        "extended": "Extended",
        "remaster": "Remaster",
        "imax": "IMAX",
        "special_edition": "Special Edition",
        "custom": "Custom",
    }
    return display_names.get(result_type_value, result_type_value)


def format_result_simple(result: SearchResult) -> str:
    """Format result as simple text."""
    display_type = _format_result_type(result.result_type.value)
    status = f"{display_type} available" if result.has_match else f"No {display_type}"
    tag_info = ""
    if result.tag_result:
        if result.tag_result.dry_run:
            tag_info = f" [would tag: {result.tag_result.tag_applied}]"
        elif result.tag_result.tag_error:
            tag_info = f" [tag error: {result.tag_result.tag_error}]"
        elif result.tag_result.tag_applied:
            tag_info = f" [tagged: {result.tag_result.tag_applied}]"
    if result.item_name:
        return f"{result.item_name} ({result.item_id}): {status}{tag_info}"
    return f"{result.item_type}:{result.item_id}: {status}{tag_info}"


def print_result(result: SearchResult, output_format: OutputFormat) -> None:
    """Print result in the specified format."""
    if output_format == OutputFormat.JSON:
        console.print(format_result_json(result))
    elif output_format == OutputFormat.TABLE:
        console.print(format_result_table(result))
    else:
        console.print(format_result_simple(result))


def get_checker(
    config: Config, need_radarr: bool = False, need_sonarr: bool = False
) -> ReleaseChecker:
    """Create a ReleaseChecker from config."""
    radarr_url = None
    radarr_key = None
    sonarr_url = None
    sonarr_key = None

    if need_radarr:
        radarr = config.require_radarr()
        radarr_url = radarr.url
        radarr_key = radarr.api_key

    if need_sonarr:
        sonarr = config.require_sonarr()
        sonarr_url = sonarr.url
        sonarr_key = sonarr.api_key

    return ReleaseChecker(
        radarr_url=radarr_url,
        radarr_api_key=radarr_key,
        sonarr_url=sonarr_url,
        sonarr_api_key=sonarr_key,
        timeout=config.timeout,
        tag_config=config.tags,
    )


def get_state_manager(config: Config) -> StateManager:
    """Create a StateManager from config."""
    return StateManager(config.state.path)


def display_movie_choices(matches: list[tuple[int, str, int]]) -> None:
    """Display multiple movie matches for user selection."""
    error_console.print("[yellow]Multiple movies found:[/yellow]")
    for movie_id, title, year in matches:
        error_console.print(f"  {movie_id}: {title} ({year})")
    error_console.print("\n[yellow]Please use the numeric ID to select a specific movie.[/yellow]")


def display_series_choices(matches: list[tuple[int, str, int]]) -> None:
    """Display multiple series matches for user selection."""
    error_console.print("[yellow]Multiple series found:[/yellow]")
    for series_id, title, year in matches:
        error_console.print(f"  {series_id}: {title} ({year})")
    error_console.print("\n[yellow]Please use the numeric ID to select a specific series.[/yellow]")


def _format_cached_time(cached: CheckRecord) -> str:
    """Format the cached check time for display."""
    # Handle timezone-naive datetimes
    last_checked = cached.last_checked
    if last_checked.tzinfo is None:
        last_checked = last_checked.replace(tzinfo=UTC)

    now = datetime.now(UTC)
    elapsed = now - last_checked
    total_seconds = elapsed.total_seconds()

    if total_seconds < 3600:
        minutes = int(total_seconds / 60)
        return f"{minutes} minute{'s' if minutes != 1 else ''} ago"
    elif total_seconds < 86400:
        hours = int(total_seconds / 3600)
        return f"{hours} hour{'s' if hours != 1 else ''} ago"
    else:
        days = int(total_seconds / 86400)
        return f"{days} day{'s' if days != 1 else ''} ago"


def _print_cached_result(
    item_type: str, item_id: int, cached: CheckRecord, output_format: OutputFormat
) -> None:
    """Print cached result message."""
    result_status = "available" if cached.result == "available" else "unavailable"
    time_ago = _format_cached_time(cached)

    if output_format == OutputFormat.JSON:
        data = {
            "item_id": item_id,
            "item_type": item_type,
            "has_match": cached.result == "available",
            "cached": True,
            "cached_at": cached.last_checked.isoformat(),
            "tag_applied": cached.tag_applied,
        }
        console.print(json.dumps(data, indent=2))
    else:
        console.print(f"[dim]Using cached result from {time_ago}: {result_status}[/dim]")
        if cached.tag_applied:
            console.print(f"[dim]Tag: {cached.tag_applied}[/dim]")


@check_app.command("movie")
def check_movie(
    typer_ctx: typer.Context,
    movie: Annotated[str, typer.Argument(help="Movie ID or name to check")],
    criteria: Annotated[
        str,
        typer.Option(
            "--criteria",
            "-c",
            help="Search criteria: 4k, hdr, dolby-vision, directors-cut, extended, remaster, imax, special-edition",
        ),
    ] = "4k",
    output_format: Annotated[
        OutputFormat | None, typer.Option("--format", "-f", help="Output format")
    ] = None,
    no_tag: Annotated[bool, typer.Option("--no-tag", help="Disable automatic tagging")] = False,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Show what tags would be applied without applying them"),
    ] = False,
    force: Annotated[
        bool,
        typer.Option("--force", help="Bypass TTL cache and force a fresh check"),
    ] = False,
) -> None:
    """Check if a movie has releases matching criteria.

    You can specify either a numeric Radarr movie ID or a movie name.
    If a name matches multiple movies, you'll be shown the options.

    By default, recently checked items (within TTL period) will use cached
    results. Use --force to bypass the cache and perform a fresh check.

    Criteria options:
      4k             - 4K/2160p resolution
      hdr            - HDR content
      dolby-vision   - Dolby Vision content
      directors-cut  - Director's Cut editions
      extended       - Extended editions
      remaster       - Remastered editions
      imax           - IMAX editions
      special-edition - Special/Collector's/Anniversary editions

    Examples:
        filtarr check movie 123
        filtarr check movie "The Matrix" --criteria directors-cut
        filtarr check movie 123 --criteria imax --no-tag
        filtarr check movie 123 --dry-run
        filtarr check movie 123 --force
    """
    effective_format = _get_effective_format(typer_ctx, output_format, OutputFormat.TABLE)

    try:
        # Validate criteria
        criteria_lower = criteria.lower()
        if criteria_lower not in CRITERIA_MAP:
            error_console.print(
                f"[red]Invalid criteria:[/red] {criteria}. "
                f"Valid options: {', '.join(VALID_CRITERIA_NAMES)}"
            )
            raise typer.Exit(2)
        search_criteria = CRITERIA_MAP[criteria_lower]

        config = Config.load()
        state_manager = get_state_manager(config)

        # Resolve movie ID if a name was provided
        movie_id: int
        if movie.isdigit():
            movie_id = int(movie)
        else:
            # Search by name first to get the ID
            checker = get_checker(config, need_radarr=True)
            matches = asyncio.run(checker.search_movies(movie))
            if not matches:
                error_console.print(f"[red]Movie not found:[/red] {movie}")
                raise typer.Exit(2)
            if len(matches) > 1:
                display_movie_choices(matches)
                raise typer.Exit(2)
            movie_id = matches[0][0]
            movie_title = matches[0][1]
            console.print(f"[dim]Found: {movie_title}[/dim]")

        # Check TTL cache unless force is specified
        if not force and not dry_run:
            cached = state_manager.get_cached_result("movie", movie_id, config.state.ttl_hours)
            if cached is not None:
                _print_cached_result("movie", movie_id, cached, effective_format)
                raise typer.Exit(0 if cached.result == "available" else 1)

        # Perform the actual check
        checker = get_checker(config, need_radarr=True)
        apply_tags = not no_tag

        result = asyncio.run(
            checker.check_movie(
                movie_id, criteria=search_criteria, apply_tags=apply_tags, dry_run=dry_run
            )
        )

        # Record check in state file (unless dry run)
        if not dry_run and apply_tags and result.tag_result:
            state_manager.record_check(
                "movie",
                result.item_id,
                result.has_match,
                result.tag_result.tag_applied,
            )

        print_result(result, effective_format)
        raise typer.Exit(0 if result.has_match else 1)
    except typer.Exit:
        raise
    except ConfigurationError as e:
        error_console.print(f"[red]Configuration error:[/red] {e}")
        raise typer.Exit(2) from e
    except Exception as e:
        error_console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(2) from e


@check_app.command("series")
def check_series_cmd(
    typer_ctx: typer.Context,
    series: Annotated[str, typer.Argument(help="Series ID or name to check")],
    criteria: Annotated[
        str,
        typer.Option(
            "--criteria",
            "-c",
            help="Search criteria: 4k, hdr, dolby-vision (movie-only criteria not allowed)",
        ),
    ] = "4k",
    seasons: Annotated[
        int,
        typer.Option("--seasons", "-s", help="Number of seasons to check (for recent strategy)"),
    ] = 3,
    strategy: Annotated[
        str, typer.Option("--strategy", help="Sampling strategy: recent, distributed, or all")
    ] = "recent",
    output_format: Annotated[
        OutputFormat | None, typer.Option("--format", "-f", help="Output format")
    ] = None,
    no_tag: Annotated[bool, typer.Option("--no-tag", help="Disable automatic tagging")] = False,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Show what tags would be applied without applying them"),
    ] = False,
    force: Annotated[
        bool,
        typer.Option("--force", help="Bypass TTL cache and force a fresh check"),
    ] = False,
) -> None:
    """Check if a TV series has releases matching criteria.

    You can specify either a numeric Sonarr series ID or a series name.
    If a name matches multiple series, you'll be shown the options.

    By default, recently checked items (within TTL period) will use cached
    results. Use --force to bypass the cache and perform a fresh check.

    Note: Movie-only criteria (directors-cut, extended, remaster, imax,
    special-edition) cannot be used for TV series.

    Examples:
        filtarr check series 456
        filtarr check series "Breaking Bad" --criteria hdr
        filtarr check series 456 --no-tag
        filtarr check series 456 --dry-run
        filtarr check series 456 --force
    """
    effective_format = _get_effective_format(typer_ctx, output_format, OutputFormat.TABLE)

    try:
        # Validate criteria
        criteria_lower = criteria.lower()
        if criteria_lower not in CRITERIA_MAP:
            error_console.print(
                f"[red]Invalid criteria:[/red] {criteria}. "
                f"Valid options: {', '.join(VALID_CRITERIA_NAMES)}"
            )
            raise typer.Exit(2)
        search_criteria = CRITERIA_MAP[criteria_lower]

        # Check for movie-only criteria
        if search_criteria in MOVIE_ONLY_CRITERIA:
            error_console.print(
                f"[red]Error:[/red] {criteria} criteria is only applicable to movies, not TV series. "
                f"Valid options for series: 4k, hdr, dolby-vision"
            )
            raise typer.Exit(2)

        # Parse strategy
        strategy_map = {
            "recent": SamplingStrategy.RECENT,
            "distributed": SamplingStrategy.DISTRIBUTED,
            "all": SamplingStrategy.ALL,
        }
        if strategy.lower() not in strategy_map:
            error_console.print(
                f"[red]Invalid strategy:[/red] {strategy}. Use: recent, distributed, or all"
            )
            raise typer.Exit(2)

        sampling_strategy = strategy_map[strategy.lower()]

        config = Config.load()
        state_manager = get_state_manager(config)

        # Resolve series ID if a name was provided
        series_id: int
        if series.isdigit():
            series_id = int(series)
        else:
            # Search by name first to get the ID
            checker = get_checker(config, need_sonarr=True)
            matches = asyncio.run(checker.search_series(series))
            if not matches:
                error_console.print(f"[red]Series not found:[/red] {series}")
                raise typer.Exit(2)
            if len(matches) > 1:
                display_series_choices(matches)
                raise typer.Exit(2)
            series_id = matches[0][0]
            series_title = matches[0][1]
            console.print(f"[dim]Found: {series_title}[/dim]")

        # Check TTL cache unless force is specified
        if not force and not dry_run:
            cached = state_manager.get_cached_result("series", series_id, config.state.ttl_hours)
            if cached is not None:
                _print_cached_result("series", series_id, cached, effective_format)
                raise typer.Exit(0 if cached.result == "available" else 1)

        # Perform the actual check
        checker = get_checker(config, need_sonarr=True)
        apply_tags = not no_tag

        result = asyncio.run(
            checker.check_series(
                series_id,
                criteria=search_criteria,
                strategy=sampling_strategy,
                seasons_to_check=seasons,
                apply_tags=apply_tags,
                dry_run=dry_run,
            )
        )

        # Record check in state file (unless dry run)
        if not dry_run and apply_tags and result.tag_result:
            state_manager.record_check(
                "series",
                result.item_id,
                result.has_match,
                result.tag_result.tag_applied,
            )

        print_result(result, effective_format)
        raise typer.Exit(0 if result.has_match else 1)
    except typer.Exit:
        raise
    except ConfigurationError as e:
        error_console.print(f"[red]Configuration error:[/red] {e}")
        raise typer.Exit(2) from e
    except Exception as e:
        error_console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(2) from e


def _filter_movies_by_tags(movies: list[Movie], skip_tag_ids: set[int]) -> list[Movie]:
    """Filter movies that already have skip tags."""
    return [m for m in movies if not any(tag in skip_tag_ids for tag in m.tags)]


def _filter_series_by_tags(series: list[Series], skip_tag_ids: set[int]) -> list[Series]:
    """Filter series that already have skip tags."""
    return [s for s in series if not any(tag in skip_tag_ids for tag in s.tags)]


# =============================================================================
# Batch Processing Helper Functions
# =============================================================================


@dataclass
class BatchContext:
    """Context for batch processing operations."""

    config: Config
    state_manager: StateManager
    search_criteria: SearchCriteria
    criteria_str: str
    sampling_strategy: SamplingStrategy
    seasons: int
    apply_tags: bool
    dry_run: bool
    batch_size: int
    delay: float
    output_format: OutputFormat
    console: Console
    error_console: Console
    timestamps: bool = True

    # Counters (mutable)
    results: list[SearchResult] = field(default_factory=list)
    has_match_count: int = 0
    skipped_count: int = 0
    processed_this_run: int = 0
    batch_limit_reached: bool = False

    # Output formatting for error/warning collection (initialized in __post_init__)
    formatter: OutputFormatter = field(default_factory=OutputFormatter)

    def __post_init__(self) -> None:
        """Initialize formatter with timestamps setting."""
        self.formatter = OutputFormatter(timestamps=self.timestamps)


def _parse_batch_file(file: Path, error_console: Console) -> tuple[list[tuple[str, str]], set[str]]:
    """Parse items from a batch file.

    Args:
        file: Path to the batch file
        error_console: Console for error output

    Returns:
        Tuple of (file_items, file_item_keys) where file_items is list of (type, id_or_name)
        and file_item_keys is set of "type:id" strings for deduplication
    """
    file_items: list[tuple[str, str]] = []
    file_item_keys: set[str] = set()

    with file.open() as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if ":" not in line:
                error_console.print(
                    f"[yellow]Warning:[/yellow] Line {line_num}: "
                    f"Invalid format '{line}', expected 'movie:<id_or_name>' or 'series:<id_or_name>'"
                )
                continue
            item_type, item_value = line.split(":", 1)
            item_type = item_type.lower()
            if item_type not in ("movie", "series"):
                error_console.print(
                    f"[yellow]Warning:[/yellow] Line {line_num}: "
                    f"Invalid type '{item_type}', skipping"
                )
                continue
            file_items.append((item_type, item_value.strip()))
            # Track numeric IDs for deduplication with rechecks
            if item_value.strip().isdigit():
                file_item_keys.add(f"{item_type}:{item_value.strip()}")

    return file_items, file_item_keys


async def _fetch_movies_to_check(
    config: Config,
    search_criteria: SearchCriteria,
    skip_tagged: bool,
    console: Console,
) -> tuple[list[Movie], set[int]]:
    """Fetch movies from Radarr and filter by tags if needed.

    Returns:
        Tuple of (movies_to_check, skip_tag_ids)
    """
    radarr = config.require_radarr()
    skip_tags: set[int] = set()
    movies: list[Movie] = []

    async with RadarrClient(radarr.url, radarr.api_key, timeout=config.timeout) as client:
        if skip_tagged:
            available_tag, unavailable_tag = config.tags.get_tag_names(search_criteria.value)
            tag_names = {available_tag, unavailable_tag}
            all_tags = await client.get_tags()
            for tag in all_tags:
                if tag.label in tag_names:
                    skip_tags.add(tag.id)

        console.print("[dim]Fetching all movies from Radarr...[/dim]")
        all_movies_list = await client.get_all_movies()

        if skip_tagged:
            movies = _filter_movies_by_tags(all_movies_list, skip_tags)
            skipped = len(all_movies_list) - len(movies)
            if skipped > 0:
                console.print(f"[dim]Skipping {skipped} already-tagged movies[/dim]")
        else:
            movies = all_movies_list

        console.print(f"[dim]Found {len(movies)} movies to check[/dim]")

    return movies, skip_tags


async def _fetch_series_to_check(
    config: Config,
    search_criteria: SearchCriteria,
    skip_tagged: bool,
    console: Console,
) -> tuple[list[Series], set[int]]:
    """Fetch series from Sonarr and filter by tags if needed.

    Returns:
        Tuple of (series_to_check, skip_tag_ids)
    """
    sonarr = config.require_sonarr()
    skip_tags: set[int] = set()
    series: list[Series] = []

    async with SonarrClient(sonarr.url, sonarr.api_key, timeout=config.timeout) as client:
        if skip_tagged:
            available_tag, unavailable_tag = config.tags.get_tag_names(search_criteria.value)
            tag_names = {available_tag, unavailable_tag}
            all_tags = await client.get_tags()
            for tag in all_tags:
                if tag.label in tag_names:
                    skip_tags.add(tag.id)

        console.print("[dim]Fetching all series from Sonarr...[/dim]")
        all_series_list = await client.get_all_series()

        if skip_tagged:
            series = _filter_series_by_tags(all_series_list, skip_tags)
            skipped = len(all_series_list) - len(series)
            if skipped > 0:
                console.print(f"[dim]Skipping {skipped} already-tagged series[/dim]")
        else:
            series = all_series_list

        console.print(f"[dim]Found {len(series)} series to check[/dim]")

    return series, skip_tags


async def _process_movie_item(
    checker: ReleaseChecker,
    item_id: int,
    item_name: str,
    search_criteria: SearchCriteria,
    apply_tags: bool,
    dry_run: bool,
    console: Console,
    error_console: Console,
) -> SearchResult | None:
    """Process a single movie item (by ID or name lookup).

    Returns:
        SearchResult if successful, None if not found or ambiguous
    """
    if item_id > 0:
        return await checker.check_movie(
            item_id,
            criteria=search_criteria,
            apply_tags=apply_tags,
            dry_run=dry_run,
        )

    # Search by name
    matches = await checker.search_movies(item_name)
    if not matches:
        error_console.print(f"[yellow]Movie not found:[/yellow] {item_name}")
        return None
    if len(matches) > 1:
        error_console.print(
            f"[yellow]Multiple movies match '{item_name}':[/yellow] "
            f"{', '.join(f'{t} ({y})' for _, t, y in matches[:3])}"
            f"{'...' if len(matches) > 3 else ''}"
        )
        return None

    movie_id, movie_title, _ = matches[0]
    console.print(f"[dim]Found: {movie_title}[/dim]")
    return await checker.check_movie(
        movie_id,
        criteria=search_criteria,
        apply_tags=apply_tags,
        dry_run=dry_run,
    )


async def _process_series_item(
    checker: ReleaseChecker,
    item_id: int,
    item_name: str,
    series_criteria: SearchCriteria,
    sampling_strategy: SamplingStrategy,
    seasons: int,
    apply_tags: bool,
    dry_run: bool,
    console: Console,
    error_console: Console,
) -> SearchResult | None:
    """Process a single series item (by ID or name lookup).

    Returns:
        SearchResult if successful, None if not found or ambiguous
    """
    if item_id > 0:
        return await checker.check_series(
            item_id,
            criteria=series_criteria,
            strategy=sampling_strategy,
            seasons_to_check=seasons,
            apply_tags=apply_tags,
            dry_run=dry_run,
        )

    # Search by name
    matches = await checker.search_series(item_name)
    if not matches:
        error_console.print(f"[yellow]Series not found:[/yellow] {item_name}")
        return None
    if len(matches) > 1:
        error_console.print(
            f"[yellow]Multiple series match '{item_name}':[/yellow] "
            f"{', '.join(f'{t} ({y})' for _, t, y in matches[:3])}"
            f"{'...' if len(matches) > 3 else ''}"
        )
        return None

    series_id, series_title, _ = matches[0]
    console.print(f"[dim]Found: {series_title}[/dim]")
    return await checker.check_series(
        series_id,
        criteria=series_criteria,
        strategy=sampling_strategy,
        seasons_to_check=seasons,
        apply_tags=apply_tags,
        dry_run=dry_run,
    )


async def _process_batch_item(
    ctx: BatchContext,
    item_type: str,
    item_id: int,
    item_name: str,
) -> SearchResult | None:
    """Process a single batch item (movie or series).

    Returns:
        SearchResult if successful, None if not found or error
    """
    if item_type == "movie":
        checker = get_checker(ctx.config, need_radarr=True)
        return await _process_movie_item(
            checker,
            item_id,
            item_name,
            ctx.search_criteria,
            ctx.apply_tags,
            ctx.dry_run,
            ctx.console,
            ctx.error_console,
        )

    # For series, use 4K if movie-only criteria was specified
    if ctx.search_criteria in MOVIE_ONLY_CRITERIA:
        ctx.console.print(
            f"[yellow]Warning:[/yellow] {ctx.criteria_str} criteria is movie-only. "
            f"Using 4K for series '{item_name}'"
        )
        series_criteria = SearchCriteria.FOUR_K
    else:
        series_criteria = ctx.search_criteria

    checker = get_checker(ctx.config, need_sonarr=True)
    return await _process_series_item(
        checker,
        item_id,
        item_name,
        series_criteria,
        ctx.sampling_strategy,
        ctx.seasons,
        ctx.apply_tags,
        ctx.dry_run,
        ctx.console,
        ctx.error_console,
    )


def _handle_batch_result(
    ctx: BatchContext,
    result: SearchResult,
    item_id: int,
    batch_progress: BatchProgress | None,
) -> None:
    """Handle a batch result: record state, update progress, print result."""
    # Record in state file (unless dry run)
    if not ctx.dry_run and ctx.apply_tags and result.tag_result:
        ctx.state_manager.record_check(
            result.item_type,  # type: ignore[arg-type]
            result.item_id,
            result.has_match,
            result.tag_result.tag_applied,
        )

    # Update batch progress
    if batch_progress and item_id > 0:
        ctx.state_manager.update_batch_progress(item_id)

    print_result(result, ctx.output_format)


def _build_item_list(
    movies: list[Movie],
    series: list[Series],
    file_items: list[tuple[str, str]],
) -> list[tuple[str, int, str]]:
    """Build combined item list from movies, series, and file items."""
    all_items: list[tuple[str, int, str]] = []

    for movie in movies:
        all_items.append(("movie", movie.id, movie.title))

    for series_item in series:
        all_items.append(("series", series_item.id, series_item.title))

    for item_type, item_value in file_items:
        if item_value.isdigit():
            all_items.append((item_type, int(item_value), f"ID:{item_value}"))
        else:
            all_items.append((item_type, -1, item_value))

    return all_items


def _is_transient_error(error: Exception) -> bool:
    """Check if an error is transient and should be retried on next batch run.

    Transient errors (server issues, network problems) should NOT mark items
    as processed, allowing them to be retried. Permanent errors (client errors,
    config issues) should mark items as processed since retrying won't help.

    Args:
        error: The exception to classify

    Returns:
        True if the error is transient (don't mark as processed),
        False if permanent (mark as processed)
    """
    if isinstance(error, httpx.HTTPStatusError):
        status_code = error.response.status_code
        # 5xx errors are server-side, transient; 429 is rate limiting (transient)
        # 4xx errors (except 429) are client-side, permanent
        return status_code >= 500 or status_code == 429
    if isinstance(error, (httpx.ConnectError, httpx.TimeoutException)):
        # Network errors are transient
        return True
    # Config errors are permanent - won't be fixed by retry
    # Unknown errors - default to transient (safer, allows retry)
    return not isinstance(error, ConfigurationError)


def _format_error_message(error: Exception) -> str:
    """Format an error message for display and collection.

    Args:
        error: The exception to format

    Returns:
        A concise error message string
    """
    if isinstance(error, httpx.HTTPStatusError):
        return f"HTTP {error.response.status_code}"
    if isinstance(error, httpx.ConnectError):
        return "Connection failed"
    if isinstance(error, httpx.TimeoutException):
        return "Request timed out"
    if isinstance(error, ConfigurationError):
        return str(error)
    return str(error)


async def _process_single_item(
    ctx: BatchContext,
    item_type: str,
    item_id: int,
    item_name: str,
    batch_progress: BatchProgress | None,
) -> bool:
    """Process a single item and handle the result.

    Returns:
        True if processing should continue, False if batch limit reached
    """
    # Create display name for error messages
    display_name = (
        item_name if item_name and not item_name.startswith("ID:") else f"{item_type}:{item_id}"
    )

    try:
        result = await _process_batch_item(ctx, item_type, item_id, item_name)

        if result:
            ctx.results.append(result)
            _handle_batch_result(ctx, result, item_id, batch_progress)
            if result.has_match:
                ctx.has_match_count += 1
            ctx.processed_this_run += 1

            # Check if batch size limit reached
            if ctx.batch_size > 0 and ctx.processed_this_run >= ctx.batch_size:
                ctx.batch_limit_reached = True
                return False

    except ConfigurationError as e:
        error_msg = _format_error_message(e)
        ctx.error_console.print(f"[red]Config error for {display_name}:[/red] {error_msg}")
        ctx.formatter.add_error(display_name, error_msg)
        # Config errors are permanent - mark as processed (retry won't help)
        if batch_progress and item_id > 0:
            ctx.state_manager.update_batch_progress(item_id)
    except httpx.HTTPStatusError as e:
        error_msg = _format_error_message(e)
        ctx.error_console.print(f"[red]Error checking {display_name}:[/red] {error_msg}")
        ctx.formatter.add_error(display_name, error_msg)
        # Only mark as processed if NOT a transient error (allows retry for 5xx, 429)
        if not _is_transient_error(e) and batch_progress and item_id > 0:
            ctx.state_manager.update_batch_progress(item_id)
    except (httpx.ConnectError, httpx.TimeoutException) as e:
        error_msg = _format_error_message(e)
        ctx.error_console.print(f"[red]Network error for {display_name}:[/red] {error_msg}")
        ctx.formatter.add_error(display_name, error_msg)
        # Network errors are transient - don't mark as processed (allows retry)
    except Exception as e:
        error_msg = _format_error_message(e)
        ctx.error_console.print(f"[red]Error checking {display_name}:[/red] {error_msg}")
        ctx.formatter.add_error(display_name, error_msg)
        # Unknown errors - don't mark as processed (safer default, allows retry)

    return True


async def _run_batch_checks(
    ctx: BatchContext,
    all_movies: bool,
    all_series: bool,
    skip_tagged: bool,
    file_items: list[tuple[str, str]],
    batch_type: Literal["movie", "series", "mixed"],
    existing_progress: BatchProgress | None,
) -> None:
    """Run batch checks on all items."""
    # Fetch movies and series to check
    movies_to_check: list[Movie] = []
    series_to_check: list[Series] = []

    if all_movies:
        movies_to_check, _ = await _fetch_movies_to_check(
            ctx.config, ctx.search_criteria, skip_tagged, ctx.console
        )

    if all_series:
        series_to_check, _ = await _fetch_series_to_check(
            ctx.config, ctx.search_criteria, skip_tagged, ctx.console
        )

    # Build combined item list
    all_items = _build_item_list(movies_to_check, series_to_check, file_items)

    if not all_items:
        ctx.error_console.print("[red]No items to check[/red]")
        return

    # Start or resume batch progress tracking
    batch_progress: BatchProgress | None = None
    if all_movies or all_series:
        if existing_progress:
            batch_progress = existing_progress
        else:
            batch_id = str(uuid.uuid4())[:8]
            batch_progress = ctx.state_manager.start_batch(batch_id, batch_type, len(all_items))

    # Calculate progress bar total: use batch_size if set, otherwise total items
    # This makes the progress bar show "3/5" instead of "3/100" when batch_size=5
    progress_total = len(all_items)
    if ctx.batch_size > 0:
        progress_total = min(ctx.batch_size, len(all_items))

    # Process items with progress bar
    # Use TimeElapsedColumn instead of TimeRemainingColumn to avoid erratic ETA
    # calculations when errors/retries cause highly variable processing times
    with Progress(
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        TimeElapsedColumn(),
        console=ctx.console,
        disable=progress_total < 3,
    ) as progress:
        task = progress.add_task("Checking items...", total=progress_total)

        for item_type, item_id, item_name in all_items:
            # Skip if already processed (resume mode)
            if batch_progress and item_id > 0 and batch_progress.is_processed(item_id):
                progress.advance(task)
                ctx.skipped_count += 1
                continue

            should_continue = await _process_single_item(
                ctx, item_type, item_id, item_name, batch_progress
            )
            progress.advance(task)

            if not should_continue:
                break

            # Apply delay between checks
            if ctx.delay > 0:
                await asyncio.sleep(ctx.delay)

    # Clear batch progress on successful completion
    if batch_progress and not ctx.batch_limit_reached:
        ctx.state_manager.clear_batch_progress()


def _validate_batch_inputs(
    file: Path | None,
    all_movies: bool,
    all_series: bool,
    criteria: str,
    strategy: str,
) -> tuple[SearchCriteria, SamplingStrategy]:
    """Validate batch command inputs and return parsed criteria/strategy."""
    # Validate: need either file or --all-* flags
    if not file and not all_movies and not all_series:
        error_console.print("[red]Error:[/red] Must specify --file, --all-movies, or --all-series")
        raise typer.Exit(2)

    if file and not file.exists():
        error_console.print(f"[red]File not found:[/red] {file}")
        raise typer.Exit(2)

    # Validate criteria
    criteria_lower = criteria.lower()
    if criteria_lower not in CRITERIA_MAP:
        error_console.print(
            f"[red]Invalid criteria:[/red] {criteria}. "
            f"Valid options: {', '.join(VALID_CRITERIA_NAMES)}"
        )
        raise typer.Exit(2)
    search_criteria = CRITERIA_MAP[criteria_lower]

    # Check for movie-only criteria with series
    if all_series and search_criteria in MOVIE_ONLY_CRITERIA:
        error_console.print(
            f"[red]Error:[/red] {criteria} criteria is only applicable to movies. "
            f"Cannot use with --all-series. Valid options for series: 4k, hdr, dolby-vision"
        )
        raise typer.Exit(2)

    # Validate strategy
    strategy_map = {
        "recent": SamplingStrategy.RECENT,
        "distributed": SamplingStrategy.DISTRIBUTED,
        "all": SamplingStrategy.ALL,
    }
    if strategy.lower() not in strategy_map:
        error_console.print(f"[red]Invalid strategy:[/red] {strategy}")
        raise typer.Exit(2)
    sampling_strategy = strategy_map[strategy.lower()]

    return search_criteria, sampling_strategy


def _prepare_file_items(
    file: Path | None,
    include_rechecks: bool,
    state_manager: StateManager,
    recheck_days: int,
) -> list[tuple[str, str]]:
    """Prepare file items including rechecks."""
    file_items: list[tuple[str, str]] = []
    file_item_keys: set[str] = set()

    if file:
        file_items, file_item_keys = _parse_batch_file(file, error_console)

    if include_rechecks:
        stale_items = state_manager.get_stale_unavailable_items(recheck_days)
        recheck_count = 0
        for item_type, item_id in stale_items:
            key = f"{item_type}:{item_id}"
            if key not in file_item_keys:
                file_items.append((item_type, str(item_id)))
                recheck_count += 1

        if recheck_count > 0:
            console.print(
                f"[dim]Including {recheck_count} stale items for re-checking "
                f"(>{recheck_days} days old)[/dim]"
            )

    return file_items


def _print_batch_summary(ctx: BatchContext) -> None:
    """Print batch summary including any collected errors."""
    console.print()
    display_criteria = _format_result_type(ctx.search_criteria.value)
    summary_parts = [
        f"{ctx.has_match_count}/{len(ctx.results)} items have {display_criteria} available"
    ]
    if ctx.skipped_count > 0:
        summary_parts.append(f"{ctx.skipped_count} resumed/skipped")
    if ctx.batch_limit_reached:
        summary_parts.append(f"batch limit ({ctx.batch_size}) reached - run again to continue")
    console.print(f"[bold]Summary:[/bold] {', '.join(summary_parts)}")

    # Print warnings and errors summary from formatter
    summary_lines = ctx.formatter.format_summary()
    for line in summary_lines:
        if line.startswith("Warnings"):
            console.print(f"[yellow]{line}[/yellow]")
        elif line.startswith("Errors"):
            console.print(f"[red]{line}[/red]")
        elif line.startswith("  -"):
            console.print(f"[dim]{line}[/dim]")
        else:
            console.print(line)


@check_app.command("batch")
def check_batch(
    typer_ctx: typer.Context,
    file: Annotated[
        Path | None, typer.Option("--file", "-f", help="File with items to check (one per line)")
    ] = None,
    all_movies: Annotated[
        bool, typer.Option("--all-movies", "-am", help="Process all movies from Radarr")
    ] = False,
    all_series: Annotated[
        bool, typer.Option("--all-series", "-as", help="Process all series from Sonarr")
    ] = False,
    criteria: Annotated[
        str,
        typer.Option(
            "--criteria",
            "-c",
            help="Search criteria (movie-only criteria not allowed with --all-series)",
        ),
    ] = "4k",
    format: Annotated[OutputFormat | None, typer.Option("--format", help="Output format")] = None,
    seasons: Annotated[
        int, typer.Option("--seasons", "-s", help="Seasons to check for series")
    ] = 3,
    strategy: Annotated[
        str, typer.Option("--strategy", help="Strategy for series: recent, distributed, all")
    ] = "recent",
    delay: Annotated[
        float, typer.Option("--delay", "-d", help="Delay between checks in seconds")
    ] = 0.5,
    batch_size: Annotated[
        int, typer.Option("--batch-size", "-b", help="Max items to process per run (0=unlimited)")
    ] = 0,
    skip_tagged: Annotated[
        bool,
        typer.Option("--skip-tagged/--no-skip-tagged", help="Skip items with existing tags"),
    ] = True,
    resume: Annotated[
        bool, typer.Option("--resume/--no-resume", help="Resume interrupted batch run")
    ] = True,
    no_tag: Annotated[bool, typer.Option("--no-tag", help="Disable automatic tagging")] = False,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Show what tags would be applied without applying them"),
    ] = False,
    include_rechecks: Annotated[
        bool,
        typer.Option("--include-rechecks", help="Include stale unavailable items for re-checking"),
    ] = True,
) -> None:
    """Check multiple items from a file or process all items from Radarr/Sonarr.

    Use --file for file-based processing (format: 'movie:<id_or_name>' or 'series:<id_or_name>').
    Use --all-movies and/or --all-series to process entire libraries.
    Use --batch-size to limit items per run (avoids overloading indexers).

    Criteria options: 4k, hdr, dolby-vision, directors-cut, extended, remaster, imax, special-edition

    Note: Movie-only criteria (directors-cut, extended, remaster, imax, special-edition)
    cannot be used with --all-series.

    Examples:
        filtarr check batch --file items.txt
        filtarr check batch --all-movies
        filtarr check batch --all-movies --criteria imax
        filtarr check batch --all-movies --batch-size 100
        filtarr check batch --all-series --delay 1.0
        filtarr check batch --all-movies --all-series
    """
    # Validate inputs
    search_criteria, sampling_strategy = _validate_batch_inputs(
        file, all_movies, all_series, criteria, strategy
    )

    # Load configuration
    try:
        config = Config.load()
    except ConfigurationError as e:
        error_console.print(f"[red]Configuration error:[/red] {e}")
        raise typer.Exit(2) from e

    state_manager = get_state_manager(config)

    # Determine batch type
    batch_type: Literal["movie", "series", "mixed"]
    if all_movies and all_series:
        batch_type = "mixed"
    elif all_movies:
        batch_type = "movie"
    elif all_series:
        batch_type = "series"
    else:
        batch_type = "mixed"

    # Check for existing batch progress
    existing_progress: BatchProgress | None = None
    if resume and (all_movies or all_series):
        existing_progress = state_manager.get_batch_progress()
        if existing_progress:
            console.print(
                f"[yellow]Resuming batch:[/yellow] {existing_progress.processed_count}/"
                f"{existing_progress.total_items} already processed"
            )

    # Prepare file items
    file_items = _prepare_file_items(
        file, include_rechecks, state_manager, config.tags.recheck_days
    )

    # Get timestamps flag from global context (defaults to True if not set)
    timestamps = typer_ctx.obj.get("timestamps", True) if typer_ctx.obj else True

    # Get effective output format respecting global flag
    effective_format = _get_effective_format(typer_ctx, format, OutputFormat.SIMPLE)

    # Create batch context
    ctx = BatchContext(
        config=config,
        state_manager=state_manager,
        search_criteria=search_criteria,
        criteria_str=criteria,
        sampling_strategy=sampling_strategy,
        seasons=seasons,
        apply_tags=not no_tag,
        dry_run=dry_run,
        batch_size=batch_size,
        delay=delay,
        output_format=effective_format,
        console=console,
        error_console=error_console,
        timestamps=timestamps,
    )

    # Run batch checks
    asyncio.run(
        _run_batch_checks(
            ctx, all_movies, all_series, skip_tagged, file_items, batch_type, existing_progress
        )
    )

    # Print summary
    _print_batch_summary(ctx)

    raise typer.Exit(0 if ctx.has_match_count == len(ctx.results) else 1)


# =============================================================================
# Schedule Commands
# =============================================================================


def _get_scheduler_manager() -> SchedulerManager:
    """Get a SchedulerManager instance."""
    from filtarr.scheduler import SchedulerManager

    config = Config.load()
    state_manager = get_state_manager(config)
    return SchedulerManager(config, state_manager)


@schedule_app.command("list")
def schedule_list(
    typer_ctx: typer.Context,
    enabled_only: Annotated[
        bool, typer.Option("--enabled-only", help="Show only enabled schedules")
    ] = False,
    output_format: Annotated[
        OutputFormat | None, typer.Option("--format", "-f", help="Output format")
    ] = None,
) -> None:
    """List all configured schedules."""
    effective_format = _get_effective_format(typer_ctx, output_format, OutputFormat.TABLE)

    from filtarr.scheduler import format_trigger_description, get_next_run_time

    manager = _get_scheduler_manager()
    schedules = manager.get_all_schedules()

    if enabled_only:
        schedules = [s for s in schedules if s.enabled]

    if not schedules:
        console.print("[dim]No schedules configured[/dim]")
        raise typer.Exit(0)

    if effective_format == OutputFormat.JSON:
        data = [s.model_dump(mode="json") for s in schedules]
        console.print(json.dumps(data, indent=2, default=str))
    else:
        table = Table(title="Configured Schedules")
        table.add_column("Name", style="cyan")
        table.add_column("Target", style="yellow")
        table.add_column("Trigger", style="green")
        table.add_column("Enabled", style="blue")
        table.add_column("Source", style="dim")
        table.add_column("Next Run", style="magenta")

        for schedule in schedules:
            next_run = get_next_run_time(schedule.trigger)
            table.add_row(
                schedule.name,
                schedule.target.value,
                format_trigger_description(schedule.trigger),
                "Yes" if schedule.enabled else "No",
                schedule.source,
                next_run.strftime("%Y-%m-%d %H:%M") if schedule.enabled else "-",
            )

        console.print(table)


@schedule_app.command("add")
def schedule_add(
    name: Annotated[str, typer.Argument(help="Unique schedule name")],
    target: Annotated[
        str, typer.Option("--target", "-t", help="What to check: movies, series, or both")
    ] = "both",
    cron: Annotated[
        str | None, typer.Option("--cron", "-c", help="Cron expression (e.g., '0 3 * * *')")
    ] = None,
    interval: Annotated[
        str | None, typer.Option("--interval", "-i", help="Interval (e.g., '6h', '1d', '30m')")
    ] = None,
    batch_size: Annotated[
        int, typer.Option("--batch-size", "-b", help="Max items per run (0=unlimited)")
    ] = 0,
    delay: Annotated[
        float, typer.Option("--delay", "-d", help="Delay between checks in seconds")
    ] = 0.5,
    skip_tagged: Annotated[
        bool, typer.Option("--skip-tagged/--no-skip-tagged", help="Skip items with existing tags")
    ] = True,
    strategy: Annotated[
        str, typer.Option("--strategy", "-s", help="Series strategy: recent, distributed, all")
    ] = "recent",
    seasons: Annotated[int, typer.Option("--seasons", help="Seasons to check for series")] = 3,
    enabled: Annotated[
        bool, typer.Option("--enabled/--disabled", help="Whether schedule is active")
    ] = True,
) -> None:
    """Add a new dynamic schedule.

    Examples:
        filtarr schedule add daily-movies --target movies --cron "0 3 * * *"
        filtarr schedule add hourly-check --target both --interval 6h
        filtarr schedule add weekly-series --target series --interval 1w --strategy recent
    """
    from filtarr.scheduler import (
        ScheduleDefinition,
        ScheduleTarget,
        SeriesStrategy,
        parse_interval_string,
    )
    from filtarr.scheduler.models import CronTrigger, IntervalTrigger

    # Validate trigger
    if not cron and not interval:
        error_console.print("[red]Error:[/red] Must specify --cron or --interval")
        raise typer.Exit(2)

    if cron and interval:
        error_console.print("[red]Error:[/red] Cannot specify both --cron and --interval")
        raise typer.Exit(2)

    # Parse trigger
    trigger: IntervalTrigger | CronTrigger
    if cron:
        try:
            trigger = CronTrigger(expression=cron)
        except ValueError as e:
            error_console.print(f"[red]Invalid cron expression:[/red] {e}")
            raise typer.Exit(2) from e
    else:
        assert interval is not None
        try:
            trigger = parse_interval_string(interval)
        except ValueError as e:
            error_console.print(f"[red]Invalid interval:[/red] {e}")
            raise typer.Exit(2) from e

    # Validate target
    try:
        target_enum = ScheduleTarget(target.lower())
    except ValueError:
        error_console.print(
            f"[red]Invalid target:[/red] {target}. Must be: movies, series, or both"
        )
        raise typer.Exit(2) from None

    # Validate strategy
    try:
        strategy_enum = SeriesStrategy(strategy.lower())
    except ValueError:
        error_console.print(
            f"[red]Invalid strategy:[/red] {strategy}. Must be: recent, distributed, or all"
        )
        raise typer.Exit(2) from None

    # Create schedule
    try:
        schedule = ScheduleDefinition(
            name=name,
            enabled=enabled,
            target=target_enum,
            trigger=trigger,
            batch_size=batch_size,
            delay=delay,
            skip_tagged=skip_tagged,
            strategy=strategy_enum,
            seasons=seasons,
            source="dynamic",
        )
    except ValueError as e:
        error_console.print(f"[red]Invalid schedule:[/red] {e}")
        raise typer.Exit(2) from e

    # Add schedule
    manager = _get_scheduler_manager()
    try:
        manager.add_schedule(schedule)
    except ValueError as e:
        error_console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(2) from e

    console.print(f"[green]Schedule '{schedule.name}' added successfully[/green]")
    console.print("[dim]Note: Restart 'filtarr serve' to activate new schedule[/dim]")


@schedule_app.command("remove")
def schedule_remove(
    name: Annotated[str, typer.Argument(help="Schedule name to remove")],
) -> None:
    """Remove a dynamic schedule."""
    manager = _get_scheduler_manager()

    try:
        removed = manager.remove_schedule(name)
    except ValueError as e:
        error_console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(2) from e

    if removed:
        console.print(f"[green]Schedule '{name}' removed[/green]")
    else:
        error_console.print(f"[red]Schedule not found:[/red] {name}")
        raise typer.Exit(1)


@schedule_app.command("enable")
def schedule_enable(
    name: Annotated[str, typer.Argument(help="Schedule name to enable")],
) -> None:
    """Enable a schedule."""
    manager = _get_scheduler_manager()

    try:
        updated = manager.enable_schedule(name)
    except ValueError as e:
        error_console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(2) from e

    if updated:
        console.print(f"[green]Schedule '{name}' enabled[/green]")
        console.print("[dim]Note: Restart 'filtarr serve' to apply changes[/dim]")
    else:
        error_console.print(f"[red]Schedule not found:[/red] {name}")
        raise typer.Exit(1)


@schedule_app.command("disable")
def schedule_disable(
    name: Annotated[str, typer.Argument(help="Schedule name to disable")],
) -> None:
    """Disable a schedule."""
    manager = _get_scheduler_manager()

    try:
        updated = manager.disable_schedule(name)
    except ValueError as e:
        error_console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(2) from e

    if updated:
        console.print(f"[green]Schedule '{name}' disabled[/green]")
        console.print("[dim]Note: Restart 'filtarr serve' to apply changes[/dim]")
    else:
        error_console.print(f"[red]Schedule not found:[/red] {name}")
        raise typer.Exit(1)


@schedule_app.command("run")
def schedule_run(
    name: Annotated[str, typer.Argument(help="Schedule name to run")],
) -> None:
    """Run a schedule immediately."""
    manager = _get_scheduler_manager()

    schedule = manager.get_schedule(name)
    if schedule is None:
        error_console.print(f"[red]Schedule not found:[/red] {name}")
        raise typer.Exit(1)

    console.print(f"[bold]Running schedule: {name}[/bold]")
    console.print(f"  Target: {schedule.target.value}")
    console.print(f"  Batch size: {schedule.batch_size or 'unlimited'}")
    console.print()

    async def run() -> None:
        result = await manager.run_schedule(name)
        console.print()
        console.print(f"[bold]Result:[/bold] {result.status.value}")
        console.print(f"  Items processed: {result.items_processed}")
        console.print(f"  Items with 4K: {result.items_with_4k}")
        if result.errors:
            console.print(f"  Errors: {len(result.errors)}")
            for error in result.errors[:5]:
                error_console.print(f"    [red]- {error}[/red]")
            if len(result.errors) > 5:
                error_console.print(f"    [dim]... and {len(result.errors) - 5} more[/dim]")

    asyncio.run(run())


@schedule_app.command("history")
def schedule_history(
    typer_ctx: typer.Context,
    name: Annotated[
        str | None, typer.Option("--name", "-n", help="Filter by schedule name")
    ] = None,
    limit: Annotated[int, typer.Option("--limit", "-l", help="Maximum records to show")] = 20,
    output_format: Annotated[
        OutputFormat | None, typer.Option("--format", "-f", help="Output format")
    ] = None,
) -> None:
    """Show schedule run history."""
    effective_format = _get_effective_format(typer_ctx, output_format, OutputFormat.TABLE)

    manager = _get_scheduler_manager()
    history = manager.get_history(schedule_name=name, limit=limit)

    if not history:
        console.print("[dim]No history found[/dim]")
        raise typer.Exit(0)

    if effective_format == OutputFormat.JSON:
        data = [r.model_dump(mode="json") for r in history]
        console.print(json.dumps(data, indent=2, default=str))
    else:
        table = Table(title="Schedule Run History")
        table.add_column("Schedule", style="cyan")
        table.add_column("Started", style="blue")
        table.add_column("Status", style="green")
        table.add_column("Items", style="yellow")
        table.add_column("4K", style="magenta")
        table.add_column("Duration", style="dim")

        for record in history:
            status_style = {
                "completed": "green",
                "failed": "red",
                "running": "yellow",
                "skipped": "dim",
            }.get(record.status.value, "white")

            duration = ""
            if record.duration_seconds() is not None:
                secs = int(record.duration_seconds() or 0)
                if secs < 60:
                    duration = f"{secs}s"
                elif secs < 3600:
                    duration = f"{secs // 60}m {secs % 60}s"
                else:
                    duration = f"{secs // 3600}h {(secs % 3600) // 60}m"

            table.add_row(
                record.schedule_name,
                record.started_at.strftime("%Y-%m-%d %H:%M"),
                f"[{status_style}]{record.status.value}[/{status_style}]",
                str(record.items_processed),
                str(record.items_with_4k),
                duration,
            )

        console.print(table)


@schedule_app.command("export")
def schedule_export(
    format_type: Annotated[
        str, typer.Option("--format", "-f", help="Export format: cron or systemd")
    ] = "cron",
    output: Annotated[
        Path | None,
        typer.Option("--output", "-o", help="Output file or directory (default: stdout)"),
    ] = None,
) -> None:
    """Export schedules to external scheduler format.

    Generates configuration for cron or systemd timers that run
    'filtarr check batch' commands equivalent to the configured schedules.

    Examples:
        filtarr schedule export --format cron
        filtarr schedule export --format cron > /etc/cron.d/filtarr
        filtarr schedule export --format systemd --output /etc/systemd/system/
    """
    from filtarr.scheduler import export_cron, export_systemd

    manager = _get_scheduler_manager()
    schedules = manager.get_all_schedules()
    enabled_schedules = [s for s in schedules if s.enabled]

    if not enabled_schedules:
        error_console.print("[yellow]No enabled schedules to export[/yellow]")
        raise typer.Exit(0)

    format_type = format_type.lower()
    if format_type not in ("cron", "systemd"):
        error_console.print(
            f"[red]Invalid format:[/red] {format_type}. Must be 'cron' or 'systemd'"
        )
        raise typer.Exit(2)

    if format_type == "cron":
        content = export_cron(enabled_schedules)
        if output:
            output.write_text(content)
            console.print(f"[green]Cron config written to:[/green] {output}")
        else:
            console.print(content)

    else:  # systemd
        if output:
            results = export_systemd(enabled_schedules, output_dir=output)
            console.print(f"[green]Generated {len(results)} systemd timer/service pairs:[/green]")
            for name, _, _ in results:
                console.print(f"  - filtarr-{name}.timer")
                console.print(f"  - filtarr-{name}.service")
            console.print()
            console.print("[dim]To install:[/dim]")
            console.print(f"  sudo cp {output}/filtarr-*.{{timer,service}} /etc/systemd/system/")
            console.print("  sudo systemctl daemon-reload")
            for name, _, _ in results:
                console.print(f"  sudo systemctl enable --now filtarr-{name}.timer")
        else:
            results = export_systemd(enabled_schedules)
            for name, timer_content, service_content in results:
                console.print(f"[bold cyan]# filtarr-{name}.timer[/bold cyan]")
                console.print(timer_content)
                console.print(f"[bold cyan]# filtarr-{name}.service[/bold cyan]")
                console.print(service_content)
                console.print()


@app.command()
def version() -> None:
    """Show version information."""
    from filtarr import __version__

    console.print(f"filtarr version {__version__}")


@app.command()
def serve(
    ctx: typer.Context,
    host: Annotated[
        str | None,
        typer.Option(
            "--host",
            "-h",
            help="Host to bind the webhook server to.",
        ),
    ] = None,
    port: Annotated[
        int | None,
        typer.Option(
            "--port",
            "-p",
            help="Port to listen on.",
        ),
    ] = None,
    scheduler: Annotated[
        bool,
        typer.Option(
            "--scheduler/--no-scheduler",
            help="Enable or disable the batch scheduler.",
        ),
    ] = True,
) -> None:
    """Start the webhook server to receive Radarr/Sonarr notifications.

    The server listens for webhook events from Radarr and Sonarr when new
    movies or series are added. When a webhook is received, filtarr will
    automatically check 4K availability and apply tags based on your config.

    The scheduler runs batch operations on configured schedules. Use
    'filtarr schedule list' to see configured schedules. Disable with
    --no-scheduler if you only want webhook functionality.

    Configure webhooks in Radarr/Sonarr:
    - URL: http://<host>:<port>/webhook/radarr (or /webhook/sonarr)
    - Method: POST
    - Events: On Movie Added (Radarr) or On Series Add (Sonarr)
    - Add header: X-Api-Key with your Radarr/Sonarr API key

    Example:
        filtarr serve --port 8080
        filtarr --log-level debug serve --host 0.0.0.0 --port 9000
        filtarr serve --no-scheduler  # Webhooks only, no scheduled batches
    """
    try:
        from filtarr.webhook import run_server
    except ImportError:
        error_console.print(
            "[red]Error:[/red] Webhook server requires additional dependencies.\n"
            "Install with: [bold]pip install filtarr[webhook][/bold]"
        )
        raise typer.Exit(1) from None

    config = Config.load()

    # Use CLI args or fall back to config
    server_host = host or config.webhook.host
    server_port = port or config.webhook.port
    scheduler_enabled = scheduler and config.scheduler.enabled

    # Get log level from global context (set by app callback)
    effective_log_level = ctx.obj.get("log_level", "INFO") if ctx.obj else "INFO"

    # Get output format from global context (set by app callback)
    output_format = ctx.obj.get("output_format", "text") if ctx.obj else "text"

    console.print(
        f"[bold green]filtarr v{__version__} - Starting webhook server on {server_host}:{server_port}[/bold green]"
    )
    console.print(f"  Host: {server_host}")
    console.print(f"  Port: {server_port}")
    console.print(f"  Log level: {effective_log_level.upper()}")
    console.print(f"  Radarr configured: {'Yes' if config.radarr else 'No'}")
    console.print(f"  Sonarr configured: {'Yes' if config.sonarr else 'No'}")
    console.print(f"  Scheduler: {'Enabled' if scheduler_enabled else 'Disabled'}")

    if scheduler_enabled:
        from filtarr.scheduler import SchedulerManager

        state_manager = get_state_manager(config)
        manager = SchedulerManager(config, state_manager)
        schedules = manager.get_all_schedules()
        enabled_count = len([s for s in schedules if s.enabled])
        console.print(f"  Schedules: {enabled_count} enabled")

    console.print()
    console.print("[dim]Webhook endpoints:[/dim]")
    if config.radarr:
        console.print(f"  Radarr: http://{server_host}:{server_port}/webhook/radarr")
    if config.sonarr:
        console.print(f"  Sonarr: http://{server_host}:{server_port}/webhook/sonarr")
    console.print(f"  Status: http://{server_host}:{server_port}/status")
    console.print()

    run_server(
        host=server_host,
        port=server_port,
        config=config,
        log_level=effective_log_level,
        scheduler_enabled=scheduler_enabled,
        output_format=output_format,
    )


if __name__ == "__main__":
    app()
