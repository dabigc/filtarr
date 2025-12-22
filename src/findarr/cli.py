"""Command-line interface for findarr."""

from __future__ import annotations

import asyncio
import json
from enum import Enum
from pathlib import Path  # noqa: TC003 - needed at runtime for typer
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from findarr.checker import FourKChecker, FourKResult, SamplingStrategy
from findarr.config import Config, ConfigurationError

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
    data = {
        "item_id": result.item_id,
        "item_type": result.item_type,
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

    return json.dumps(data, indent=2)


def format_result_table(result: FourKResult) -> Table:
    """Format result as a rich table."""
    table = Table(title=f"4K Check: {result.item_type.title()} {result.item_id}")

    table.add_column("Property", style="cyan")
    table.add_column("Value", style="green" if result.has_4k else "red")

    table.add_row("4K Available", "Yes" if result.has_4k else "No")
    table.add_row("Total Releases", str(len(result.releases)))
    table.add_row("4K Releases", str(len(result.four_k_releases)))

    if result.seasons_checked:
        table.add_row("Seasons Checked", ", ".join(map(str, result.seasons_checked)))
    if result.strategy_used:
        table.add_row("Strategy", result.strategy_used.value)

    return table


def format_result_simple(result: FourKResult) -> str:
    """Format result as simple text."""
    status = "4K available" if result.has_4k else "No 4K"
    return f"{result.item_type}:{result.item_id}: {status}"


def print_result(result: FourKResult, format: OutputFormat) -> None:
    """Print result in the specified format."""
    if format == OutputFormat.JSON:
        console.print(format_result_json(result))
    elif format == OutputFormat.TABLE:
        console.print(format_result_table(result))
    else:
        console.print(format_result_simple(result))


def get_checker(config: Config, need_radarr: bool = False, need_sonarr: bool = False) -> FourKChecker:
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
    )


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
) -> None:
    """Check if a movie has 4K releases available.

    You can specify either a numeric Radarr movie ID or a movie name.
    If a name matches multiple movies, you'll be shown the options.

    Examples:
        findarr check movie 123
        findarr check movie "The Matrix"
    """
    try:
        config = Config.load()
        checker = get_checker(config, need_radarr=True)

        # Check if argument is numeric (ID) or name
        if movie.isdigit():
            result = asyncio.run(checker.check_movie(int(movie)))
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
            result = asyncio.run(checker.check_movie(movie_id))

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
        int, typer.Option("--seasons", "-s", help="Number of seasons to check (for recent strategy)")
    ] = 3,
    strategy: Annotated[
        str, typer.Option("--strategy", help="Sampling strategy: recent, distributed, or all")
    ] = "recent",
    format: Annotated[
        OutputFormat, typer.Option("--format", "-f", help="Output format")
    ] = OutputFormat.TABLE,
) -> None:
    """Check if a TV series has 4K releases available.

    You can specify either a numeric Sonarr series ID or a series name.
    If a name matches multiple series, you'll be shown the options.

    Examples:
        findarr check series 456
        findarr check series "Breaking Bad"
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
                f"[red]Invalid strategy:[/red] {strategy}. "
                "Use: recent, distributed, or all"
            )
            raise typer.Exit(2)

        sampling_strategy = strategy_map[strategy.lower()]

        config = Config.load()
        checker = get_checker(config, need_sonarr=True)

        # Check if argument is numeric (ID) or name
        if series.isdigit():
            result = asyncio.run(
                checker.check_series(
                    int(series),
                    strategy=sampling_strategy,
                    seasons_to_check=seasons,
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
                )
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


@check_app.command("batch")
def check_batch(
    file: Annotated[
        Path, typer.Option("--file", "-f", help="File with items to check (one per line)")
    ],
    format: Annotated[
        OutputFormat, typer.Option("--format", help="Output format")
    ] = OutputFormat.SIMPLE,
    seasons: Annotated[
        int, typer.Option("--seasons", "-s", help="Seasons to check for series")
    ] = 3,
    strategy: Annotated[
        str, typer.Option("--strategy", help="Strategy for series: recent, distributed, all")
    ] = "recent",
) -> None:
    """Check multiple items from a file.

    File format: one item per line as 'movie:<id_or_name>' or 'series:<id_or_name>'.

    Example file:
        movie:123
        movie:The Matrix
        series:Breaking Bad
        series:789
    """
    if not file.exists():
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

    # Parse items from file - now supports both IDs and names
    items: list[tuple[str, str]] = []  # (type, id_or_name)
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
            items.append((item_type, item_value.strip()))

    if not items:
        error_console.print("[red]No valid items found in file[/red]")
        raise typer.Exit(2)

    # Check items
    results: list[FourKResult] = []
    has_4k_count = 0

    async def run_checks() -> None:
        nonlocal has_4k_count
        for item_type, item_value in items:
            try:
                if item_type == "movie":
                    checker = get_checker(config, need_radarr=True)
                    if item_value.isdigit():
                        result = await checker.check_movie(int(item_value))
                    else:
                        # Search by name
                        matches = await checker.search_movies(item_value)
                        if not matches:
                            error_console.print(f"[yellow]Movie not found:[/yellow] {item_value}")
                            continue
                        if len(matches) > 1:
                            error_console.print(
                                f"[yellow]Multiple movies match '{item_value}':[/yellow] "
                                f"{', '.join(f'{t} ({y})' for _, t, y in matches[:3])}"
                                f"{'...' if len(matches) > 3 else ''}"
                            )
                            continue
                        movie_id, movie_title, _ = matches[0]
                        console.print(f"[dim]Found: {movie_title}[/dim]")
                        result = await checker.check_movie(movie_id)
                else:
                    checker = get_checker(config, need_sonarr=True)
                    if item_value.isdigit():
                        result = await checker.check_series(
                            int(item_value),
                            strategy=sampling_strategy,
                            seasons_to_check=seasons,
                        )
                    else:
                        # Search by name
                        matches = await checker.search_series(item_value)
                        if not matches:
                            error_console.print(f"[yellow]Series not found:[/yellow] {item_value}")
                            continue
                        if len(matches) > 1:
                            error_console.print(
                                f"[yellow]Multiple series match '{item_value}':[/yellow] "
                                f"{', '.join(f'{t} ({y})' for _, t, y in matches[:3])}"
                                f"{'...' if len(matches) > 3 else ''}"
                            )
                            continue
                        series_id, series_title, _ = matches[0]
                        console.print(f"[dim]Found: {series_title}[/dim]")
                        result = await checker.check_series(
                            series_id,
                            strategy=sampling_strategy,
                            seasons_to_check=seasons,
                        )
                results.append(result)
                if result.has_4k:
                    has_4k_count += 1
                print_result(result, format)
            except ConfigurationError as e:
                error_console.print(f"[red]Config error for {item_type}:{item_value}:[/red] {e}")
            except Exception as e:
                error_console.print(f"[red]Error checking {item_type}:{item_value}:[/red] {e}")

    asyncio.run(run_checks())

    # Print summary
    console.print()
    console.print(f"[bold]Summary:[/bold] {has_4k_count}/{len(results)} items have 4K available")

    raise typer.Exit(0 if has_4k_count == len(results) else 1)


@app.command()
def version() -> None:
    """Show version information."""
    from findarr import __version__
    console.print(f"findarr version {__version__}")


if __name__ == "__main__":
    app()
