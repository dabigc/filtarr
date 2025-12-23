"""Command-line interface for findarr."""

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

from findarr.checker import FourKChecker, FourKResult, SamplingStrategy
from findarr.clients.radarr import RadarrClient
from findarr.clients.sonarr import SonarrClient
from findarr.config import Config, ConfigurationError
from findarr.state import BatchProgress, StateManager

if TYPE_CHECKING:
    from findarr.models.radarr import Movie
    from findarr.models.sonarr import Series

app = typer.Typer(
    name="findarr",
    help="Check 4K availability for movies and TV shows via Radarr/Sonarr.",
    no_args_is_help=True,
)
check_app = typer.Typer(help="Check 4K availability for media items.")
app.add_typer(check_app, name="check")

console = Console()
error_console = Console(stderr=True)


class OutputFormat(str, Enum):
    """Output format options."""

    JSON = "json"
    TABLE = "table"
    SIMPLE = "simple"


def format_result_json(result: FourKResult) -> str:
    """Format result as JSON."""
    data: dict[str, object] = {
        "item_id": result.item_id,
        "item_type": result.item_type,
        "item_name": result.item_name,
        "has_4k": result.has_4k,
        "releases_count": len(result.releases),
        "four_k_releases_count": len(result.four_k_releases),
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


def format_result_table(result: FourKResult) -> Table:
    """Format result as a rich table."""
    if result.item_name:
        title = f"4K Check: {result.item_name} ({result.item_id})"
    else:
        title = f"4K Check: {result.item_type.title()} {result.item_id}"
    table = Table(title=title)

    table.add_column("Property", style="cyan")
    table.add_column("Value", style="green" if result.has_4k else "red")

    table.add_row("4K Available", "Yes" if result.has_4k else "No")
    table.add_row("Total Releases", str(len(result.releases)))
    table.add_row("4K Releases", str(len(result.four_k_releases)))

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


def format_result_simple(result: FourKResult) -> str:
    """Format result as simple text."""
    status = "4K available" if result.has_4k else "No 4K"
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


def print_result(result: FourKResult, format: OutputFormat) -> None:
    """Print result in the specified format."""
    if format == OutputFormat.JSON:
        console.print(format_result_json(result))
    elif format == OutputFormat.TABLE:
        console.print(format_result_table(result))
    else:
        console.print(format_result_simple(result))


def get_checker(
    config: Config, need_radarr: bool = False, need_sonarr: bool = False
) -> FourKChecker:
    """Create a FourKChecker from config."""
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

    return FourKChecker(
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
    format: Annotated[
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
        findarr check movie 123
        findarr check movie "The Matrix"
        findarr check movie 123 --no-tag
        findarr check movie 123 --dry-run
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
                result.has_4k,
                result.tag_result.tag_applied,
            )

        print_result(result, format)
        raise typer.Exit(0 if result.has_4k else 1)
    except typer.Exit:
        raise
    except ConfigurationError as e:
        error_console.print(f"[red]Configuration error:[/red] {e}")
        raise typer.Exit(2) from e
    except Exception as e:
        error_console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(2) from e


@check_app.command("series")
def check_series(
    series: Annotated[str, typer.Argument(help="Series ID or name to check")],
    seasons: Annotated[
        int,
        typer.Option("--seasons", "-s", help="Number of seasons to check (for recent strategy)"),
    ] = 3,
    strategy: Annotated[
        str, typer.Option("--strategy", help="Sampling strategy: recent, distributed, or all")
    ] = "recent",
    format: Annotated[
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
        findarr check series 456
        findarr check series "Breaking Bad"
        findarr check series 456 --no-tag
        findarr check series 456 --dry-run
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
                result.has_4k,
                result.tag_result.tag_applied,
            )

        print_result(result, format)
        raise typer.Exit(0 if result.has_4k else 1)
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
        findarr check batch --file items.txt
        findarr check batch --all-movies
        findarr check batch --all-movies --batch-size 100
        findarr check batch --all-series --delay 1.0
        findarr check batch --all-movies --all-series
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
    results: list[FourKResult] = []
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
                    result: FourKResult | None = None

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
                        if result.has_4k:
                            has_4k_count += 1

                        # Record in state file (unless dry run)
                        if not dry_run and apply_tags and result.tag_result:
                            state_manager.record_check(
                                result.item_type,  # type: ignore[arg-type]
                                result.item_id,
                                result.has_4k,
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


@app.command()
def version() -> None:
    """Show version information."""
    from findarr import __version__

    console.print(f"findarr version {__version__}")


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
) -> None:
    """Start the webhook server to receive Radarr/Sonarr notifications.

    The server listens for webhook events from Radarr and Sonarr when new
    movies or series are added. When a webhook is received, findarr will
    automatically check 4K availability and apply tags based on your config.

    Configure webhooks in Radarr/Sonarr:
    - URL: http://<host>:<port>/webhook/radarr (or /webhook/sonarr)
    - Method: POST
    - Events: On Movie Added (Radarr) or On Series Add (Sonarr)
    - Add header: X-Api-Key with your Radarr/Sonarr API key

    Example:
        findarr serve --port 8080
        findarr serve --host 0.0.0.0 --port 9000 --log-level debug
    """
    try:
        from findarr.webhook import run_server
    except ImportError:
        error_console.print(
            "[red]Error:[/red] Webhook server requires additional dependencies.\n"
            "Install with: [bold]pip install findarr[webhook][/bold]"
        )
        raise typer.Exit(1) from None

    config = Config.load()

    # Use CLI args or fall back to config
    server_host = host or config.webhook.host
    server_port = port or config.webhook.port

    console.print("[bold green]Starting findarr webhook server[/bold green]")
    console.print(f"  Host: {server_host}")
    console.print(f"  Port: {server_port}")
    console.print(f"  Radarr configured: {'Yes' if config.radarr else 'No'}")
    console.print(f"  Sonarr configured: {'Yes' if config.sonarr else 'No'}")
    console.print()
    console.print("[dim]Configure webhooks in Radarr/Sonarr to POST to:[/dim]")
    if config.radarr:
        console.print(f"  Radarr: http://{server_host}:{server_port}/webhook/radarr")
    if config.sonarr:
        console.print(f"  Sonarr: http://{server_host}:{server_port}/webhook/sonarr")
    console.print()

    run_server(
        host=server_host,
        port=server_port,
        config=config,
        log_level=log_level,
    )


if __name__ == "__main__":
    app()
