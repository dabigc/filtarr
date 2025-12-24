"""Command-line interface for filtarr."""

from __future__ import annotations

import asyncio
import json
import uuid
from enum import Enum
from pathlib import Path  # noqa: TC003 - needed at runtime for typer
from typing import TYPE_CHECKING, Annotated, Literal

import typer
from rich.console import Console
from rich.progress import BarColumn, Progress, TaskProgressColumn, TextColumn, TimeRemainingColumn
from rich.table import Table

from filtarr.checker import ReleaseChecker, SamplingStrategy, SearchResult
from filtarr.clients.radarr import RadarrClient
from filtarr.clients.sonarr import SonarrClient
from filtarr.config import Config, ConfigurationError
from filtarr.state import BatchProgress, StateManager

if TYPE_CHECKING:
    from filtarr.models.radarr import Movie
    from filtarr.models.sonarr import Series
    from filtarr.scheduler import SchedulerManager

app = typer.Typer(
    name="filtarr",
    help="Check release availability for movies and TV shows via Radarr/Sonarr.",
    no_args_is_help=True,
)
check_app = typer.Typer(help="Check 4K availability for media items.")
app.add_typer(check_app, name="check")

schedule_app = typer.Typer(help="Manage scheduled batch operations.")
app.add_typer(schedule_app, name="schedule")

console = Console()
error_console = Console(stderr=True)


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


@check_app.command("movie")
def check_movie(
    movie: Annotated[str, typer.Argument(help="Movie ID or name to check")],
    output_format: Annotated[
        OutputFormat, typer.Option("--format", "-f", help="Output format")
    ] = OutputFormat.TABLE,
    no_tag: Annotated[bool, typer.Option("--no-tag", help="Disable automatic tagging")] = False,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Show what tags would be applied without applying them"),
    ] = False,
) -> None:
    """Check if a movie has 4K releases available.

    You can specify either a numeric Radarr movie ID or a movie name.
    If a name matches multiple movies, you'll be shown the options.

    Examples:
        filtarr check movie 123
        filtarr check movie "The Matrix"
        filtarr check movie 123 --no-tag
        filtarr check movie 123 --dry-run
    """
    try:
        config = Config.load()
        checker = get_checker(config, need_radarr=True)
        state_manager = get_state_manager(config)

        apply_tags = not no_tag

        # Check if argument is numeric (ID) or name
        if movie.isdigit():
            result = asyncio.run(
                checker.check_movie(int(movie), apply_tags=apply_tags, dry_run=dry_run)
            )
        else:
            # Search by name
            matches = asyncio.run(checker.search_movies(movie))
            if not matches:
                error_console.print(f"[red]Movie not found:[/red] {movie}")
                raise typer.Exit(2)
            if len(matches) > 1:
                display_movie_choices(matches)
                raise typer.Exit(2)
            # Single match - use it
            movie_id = matches[0][0]
            movie_title = matches[0][1]
            console.print(f"[dim]Found: {movie_title}[/dim]")
            result = asyncio.run(
                checker.check_movie(movie_id, apply_tags=apply_tags, dry_run=dry_run)
            )

        # Record check in state file (unless dry run)
        if not dry_run and apply_tags and result.tag_result:
            state_manager.record_check(
                "movie",
                result.item_id,
                result.has_match,
                result.tag_result.tag_applied,
            )

        print_result(result, output_format)
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
    series: Annotated[str, typer.Argument(help="Series ID or name to check")],
    seasons: Annotated[
        int,
        typer.Option("--seasons", "-s", help="Number of seasons to check (for recent strategy)"),
    ] = 3,
    strategy: Annotated[
        str, typer.Option("--strategy", help="Sampling strategy: recent, distributed, or all")
    ] = "recent",
    output_format: Annotated[
        OutputFormat, typer.Option("--format", "-f", help="Output format")
    ] = OutputFormat.TABLE,
    no_tag: Annotated[bool, typer.Option("--no-tag", help="Disable automatic tagging")] = False,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Show what tags would be applied without applying them"),
    ] = False,
) -> None:
    """Check if a TV series has 4K releases available.

    You can specify either a numeric Sonarr series ID or a series name.
    If a name matches multiple series, you'll be shown the options.

    Examples:
        filtarr check series 456
        filtarr check series "Breaking Bad"
        filtarr check series 456 --no-tag
        filtarr check series 456 --dry-run
    """
    try:
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
        checker = get_checker(config, need_sonarr=True)
        state_manager = get_state_manager(config)

        apply_tags = not no_tag

        # Check if argument is numeric (ID) or name
        if series.isdigit():
            result = asyncio.run(
                checker.check_series(
                    int(series),
                    strategy=sampling_strategy,
                    seasons_to_check=seasons,
                    apply_tags=apply_tags,
                    dry_run=dry_run,
                )
            )
        else:
            # Search by name
            matches = asyncio.run(checker.search_series(series))
            if not matches:
                error_console.print(f"[red]Series not found:[/red] {series}")
                raise typer.Exit(2)
            if len(matches) > 1:
                display_series_choices(matches)
                raise typer.Exit(2)
            # Single match - use it
            series_id = matches[0][0]
            series_title = matches[0][1]
            console.print(f"[dim]Found: {series_title}[/dim]")
            result = asyncio.run(
                checker.check_series(
                    series_id,
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

        print_result(result, output_format)
        raise typer.Exit(0 if result.has_match else 1)
    except ConfigurationError as e:
        error_console.print(f"[red]Configuration error:[/red] {e}")
        raise typer.Exit(2) from e
    except typer.Exit:
        raise
    except Exception as e:
        error_console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(2) from e


def _filter_movies_by_tags(movies: list[Movie], skip_tag_ids: set[int]) -> list[Movie]:
    """Filter movies that already have skip tags."""
    return [m for m in movies if not any(tag in skip_tag_ids for tag in m.tags)]


def _filter_series_by_tags(series: list[Series], skip_tag_ids: set[int]) -> list[Series]:
    """Filter series that already have skip tags."""
    return [s for s in series if not any(tag in skip_tag_ids for tag in s.tags)]


@check_app.command("batch")
def check_batch(
    file: Annotated[
        Path | None, typer.Option("--file", "-f", help="File with items to check (one per line)")
    ] = None,
    all_movies: Annotated[
        bool, typer.Option("--all-movies", "-am", help="Process all movies from Radarr")
    ] = False,
    all_series: Annotated[
        bool, typer.Option("--all-series", "-as", help="Process all series from Sonarr")
    ] = False,
    format: Annotated[
        OutputFormat, typer.Option("--format", help="Output format")
    ] = OutputFormat.SIMPLE,
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
        typer.Option("--skip-tagged/--no-skip-tagged", help="Skip items with existing 4k tags"),
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

    Examples:
        filtarr check batch --file items.txt
        filtarr check batch --all-movies
        filtarr check batch --all-movies --batch-size 100
        filtarr check batch --all-series --delay 1.0
        filtarr check batch --all-movies --all-series
    """
    # Validate: need either file or --all-* flags
    if not file and not all_movies and not all_series:
        error_console.print("[red]Error:[/red] Must specify --file, --all-movies, or --all-series")
        raise typer.Exit(2)

    if file and not file.exists():
        error_console.print(f"[red]File not found:[/red] {file}")
        raise typer.Exit(2)

    strategy_map = {
        "recent": SamplingStrategy.RECENT,
        "distributed": SamplingStrategy.DISTRIBUTED,
        "all": SamplingStrategy.ALL,
    }
    if strategy.lower() not in strategy_map:
        error_console.print(f"[red]Invalid strategy:[/red] {strategy}")
        raise typer.Exit(2)
    sampling_strategy = strategy_map[strategy.lower()]

    try:
        config = Config.load()
    except ConfigurationError as e:
        error_console.print(f"[red]Configuration error:[/red] {e}")
        raise typer.Exit(2) from e

    state_manager = get_state_manager(config)
    apply_tags = not no_tag

    # Determine batch type for state tracking
    batch_type: Literal["movie", "series", "mixed"]
    if all_movies and all_series:
        batch_type = "mixed"
    elif all_movies:
        batch_type = "movie"
    elif all_series:
        batch_type = "series"
    else:
        # File-only mode or no items specified - treat as mixed
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

    # Parse items from file - now supports both IDs and names
    file_items: list[tuple[str, str]] = []  # (type, id_or_name)
    file_item_keys: set[str] = set()  # Track items from file to avoid duplicates
    if file:
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

    # Include stale unavailable items for rechecking
    recheck_count = 0
    if include_rechecks:
        stale_items = state_manager.get_stale_unavailable_items(config.tags.recheck_days)
        for item_type, item_id in stale_items:
            key = f"{item_type}:{item_id}"
            if key not in file_item_keys:
                file_items.append((item_type, str(item_id)))
                recheck_count += 1

        if recheck_count > 0:
            console.print(
                f"[dim]Including {recheck_count} stale items for re-checking "
                f"(>{config.tags.recheck_days} days old)[/dim]"
            )

    # Check items
    results: list[SearchResult] = []
    has_4k_count = 0
    skipped_count = 0
    processed_this_run = 0
    batch_limit_reached = False

    async def run_checks() -> None:
        nonlocal has_4k_count, skipped_count, processed_this_run, batch_limit_reached

        # Create clients for --all-* processing
        movies_to_check: list[Movie] = []
        series_to_check: list[Series] = []

        # Get tag IDs to skip and fetch all items using context managers
        movie_skip_tags: set[int] = set()
        series_skip_tags: set[int] = set()

        if all_movies:
            radarr = config.require_radarr()
            async with RadarrClient(radarr.url, radarr.api_key, timeout=config.timeout) as client:
                # Get tags to skip
                if skip_tagged:
                    tag_names = {config.tags.available, config.tags.unavailable}
                    all_tags = await client.get_tags()
                    for tag in all_tags:
                        if tag.label in tag_names:
                            movie_skip_tags.add(tag.id)

                # Fetch all movies
                console.print("[dim]Fetching all movies from Radarr...[/dim]")
                all_movies_list = await client.get_all_movies()
                if skip_tagged:
                    movies_to_check = _filter_movies_by_tags(all_movies_list, movie_skip_tags)
                    skipped = len(all_movies_list) - len(movies_to_check)
                    if skipped > 0:
                        console.print(f"[dim]Skipping {skipped} already-tagged movies[/dim]")
                else:
                    movies_to_check = all_movies_list
                console.print(f"[dim]Found {len(movies_to_check)} movies to check[/dim]")

        if all_series:
            sonarr = config.require_sonarr()
            async with SonarrClient(sonarr.url, sonarr.api_key, timeout=config.timeout) as client:
                # Get tags to skip
                if skip_tagged:
                    tag_names = {config.tags.available, config.tags.unavailable}
                    all_tags = await client.get_tags()
                    for tag in all_tags:
                        if tag.label in tag_names:
                            series_skip_tags.add(tag.id)

                # Fetch all series
                console.print("[dim]Fetching all series from Sonarr...[/dim]")
                all_series_list = await client.get_all_series()
                if skip_tagged:
                    series_to_check = _filter_series_by_tags(all_series_list, series_skip_tags)
                    skipped = len(all_series_list) - len(series_to_check)
                    if skipped > 0:
                        console.print(f"[dim]Skipping {skipped} already-tagged series[/dim]")
                else:
                    series_to_check = all_series_list
                console.print(f"[dim]Found {len(series_to_check)} series to check[/dim]")

        # Build combined item list: (type, id, title)
        all_items: list[tuple[str, int, str]] = []

        # Add movies
        for movie in movies_to_check:
            all_items.append(("movie", movie.id, movie.title))

        # Add series
        for series in series_to_check:
            all_items.append(("series", series.id, series.title))

        # Add file items (resolve names to IDs)
        for item_type, item_value in file_items:
            if item_value.isdigit():
                all_items.append((item_type, int(item_value), f"ID:{item_value}"))
            else:
                # Will resolve during processing
                all_items.append((item_type, -1, item_value))

        if not all_items:
            error_console.print("[red]No items to check[/red]")
            return

        # Start or resume batch progress tracking
        nonlocal existing_progress
        batch_progress: BatchProgress | None = None
        if all_movies or all_series:
            if existing_progress:
                batch_progress = existing_progress
            else:
                batch_id = str(uuid.uuid4())[:8]
                batch_progress = state_manager.start_batch(
                    batch_id,
                    batch_type,
                    len(all_items),
                )

        # Process items with progress bar
        with Progress(
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            TimeRemainingColumn(),
            console=console,
            disable=len(all_items) < 3,  # Don't show progress for small batches
        ) as progress:
            task = progress.add_task("Checking items...", total=len(all_items))

            for item_type, item_id, item_name in all_items:
                # Skip if already processed (resume mode)
                if batch_progress and item_id > 0 and batch_progress.is_processed(item_id):
                    progress.advance(task)
                    skipped_count += 1
                    continue

                try:
                    result: SearchResult | None = None

                    if item_type == "movie":
                        checker = get_checker(config, need_radarr=True)
                        if item_id > 0:
                            result = await checker.check_movie(
                                item_id, apply_tags=apply_tags, dry_run=dry_run
                            )
                        else:
                            # Search by name
                            matches = await checker.search_movies(item_name)
                            if not matches:
                                error_console.print(
                                    f"[yellow]Movie not found:[/yellow] {item_name}"
                                )
                            elif len(matches) > 1:
                                error_console.print(
                                    f"[yellow]Multiple movies match '{item_name}':[/yellow] "
                                    f"{', '.join(f'{t} ({y})' for _, t, y in matches[:3])}"
                                    f"{'...' if len(matches) > 3 else ''}"
                                )
                            else:
                                movie_id, movie_title, _ = matches[0]
                                console.print(f"[dim]Found: {movie_title}[/dim]")
                                result = await checker.check_movie(
                                    movie_id, apply_tags=apply_tags, dry_run=dry_run
                                )
                    else:
                        checker = get_checker(config, need_sonarr=True)
                        if item_id > 0:
                            result = await checker.check_series(
                                item_id,
                                strategy=sampling_strategy,
                                seasons_to_check=seasons,
                                apply_tags=apply_tags,
                                dry_run=dry_run,
                            )
                        else:
                            # Search by name
                            matches = await checker.search_series(item_name)
                            if not matches:
                                error_console.print(
                                    f"[yellow]Series not found:[/yellow] {item_name}"
                                )
                            elif len(matches) > 1:
                                error_console.print(
                                    f"[yellow]Multiple series match '{item_name}':[/yellow] "
                                    f"{', '.join(f'{t} ({y})' for _, t, y in matches[:3])}"
                                    f"{'...' if len(matches) > 3 else ''}"
                                )
                            else:
                                series_id, series_title, _ = matches[0]
                                console.print(f"[dim]Found: {series_title}[/dim]")
                                result = await checker.check_series(
                                    series_id,
                                    strategy=sampling_strategy,
                                    seasons_to_check=seasons,
                                    apply_tags=apply_tags,
                                    dry_run=dry_run,
                                )

                    if result:
                        results.append(result)
                        if result.has_match:
                            has_4k_count += 1

                        # Record in state file (unless dry run)
                        if not dry_run and apply_tags and result.tag_result:
                            state_manager.record_check(
                                result.item_type,  # type: ignore[arg-type]
                                result.item_id,
                                result.has_match,
                                result.tag_result.tag_applied,
                            )

                        # Update batch progress
                        if batch_progress and item_id > 0:
                            state_manager.update_batch_progress(item_id)

                        print_result(result, format)
                        processed_this_run += 1

                        # Check if batch size limit reached
                        if batch_size > 0 and processed_this_run >= batch_size:
                            batch_limit_reached = True
                            break

                except ConfigurationError as e:
                    error_console.print(f"[red]Config error for {item_type}:{item_name}:[/red] {e}")
                    # Track failed items to avoid infinite retries on resume
                    if batch_progress and item_id > 0:
                        state_manager.update_batch_progress(item_id)
                except Exception as e:
                    error_console.print(f"[red]Error checking {item_type}:{item_name}:[/red] {e}")
                    # Track failed items to avoid infinite retries on resume
                    if batch_progress and item_id > 0:
                        state_manager.update_batch_progress(item_id)

                progress.advance(task)

                # Apply delay between checks
                if delay > 0:
                    await asyncio.sleep(delay)

        # Clear batch progress on successful completion (not if stopped by batch size limit)
        if batch_progress and not batch_limit_reached:
            state_manager.clear_batch_progress()

    asyncio.run(run_checks())

    # Print summary
    console.print()
    summary_parts = [f"{has_4k_count}/{len(results)} items have 4K available"]
    if skipped_count > 0:
        summary_parts.append(f"{skipped_count} resumed/skipped")
    if batch_limit_reached:
        summary_parts.append(f"batch limit ({batch_size}) reached - run again to continue")
    console.print(f"[bold]Summary:[/bold] {', '.join(summary_parts)}")

    raise typer.Exit(0 if has_4k_count == len(results) else 1)


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
    enabled_only: Annotated[
        bool, typer.Option("--enabled-only", help="Show only enabled schedules")
    ] = False,
    output_format: Annotated[
        OutputFormat, typer.Option("--format", "-f", help="Output format")
    ] = OutputFormat.TABLE,
) -> None:
    """List all configured schedules."""
    from filtarr.scheduler import format_trigger_description, get_next_run_time

    manager = _get_scheduler_manager()
    schedules = manager.get_all_schedules()

    if enabled_only:
        schedules = [s for s in schedules if s.enabled]

    if not schedules:
        console.print("[dim]No schedules configured[/dim]")
        raise typer.Exit(0)

    if output_format == OutputFormat.JSON:
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
    name: Annotated[
        str | None, typer.Option("--name", "-n", help="Filter by schedule name")
    ] = None,
    limit: Annotated[int, typer.Option("--limit", "-l", help="Maximum records to show")] = 20,
    output_format: Annotated[
        OutputFormat, typer.Option("--format", "-f", help="Output format")
    ] = OutputFormat.TABLE,
) -> None:
    """Show schedule run history."""
    manager = _get_scheduler_manager()
    history = manager.get_history(schedule_name=name, limit=limit)

    if not history:
        console.print("[dim]No history found[/dim]")
        raise typer.Exit(0)

    if output_format == OutputFormat.JSON:
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
        filtarr schedule export --format cron > /etc/cron.d/findarr
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
    log_level: Annotated[
        str,
        typer.Option(
            "--log-level",
            "-l",
            help="Logging level (debug, info, warning, error).",
        ),
    ] = "info",
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
    movies or series are added. When a webhook is received, findarr will
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
        filtarr serve --host 0.0.0.0 --port 9000 --log-level debug
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

    console.print("[bold green]Starting filtarr server[/bold green]")
    console.print(f"  Host: {server_host}")
    console.print(f"  Port: {server_port}")
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
        log_level=log_level,
        scheduler_enabled=scheduler_enabled,
    )


if __name__ == "__main__":
    app()
