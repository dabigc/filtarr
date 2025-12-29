"""Webhook server for receiving Radarr/Sonarr notifications."""

from __future__ import annotations

import asyncio
import json as json_module
import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import httpx
from pydantic import ValidationError

from filtarr.checker import ReleaseChecker
from filtarr.config import Config, ConfigurationError
from filtarr.models.webhook import (
    RadarrWebhookPayload,
    SonarrWebhookPayload,
    WebhookResponse,
)

if TYPE_CHECKING:
    from filtarr.scheduler import SchedulerManager
    from filtarr.state import StateManager
    from filtarr.tagger import TagResult

logger = logging.getLogger(__name__)

# Global reference to scheduler manager for status endpoint
_scheduler_manager: SchedulerManager | None = None
# Global reference to state manager for TTL checks
_state_manager: StateManager | None = None
# Global reference to output format for JSON mode
_output_format: str = "text"


def _output_json_event(event_type: str, **data: object) -> None:
    """Output a JSON event line to stdout.

    Args:
        event_type: Type of event (e.g., 'webhook_received', 'check_complete').
        **data: Event data to include.
    """
    event = {
        "event": event_type,
        "timestamp": datetime.now(UTC).isoformat(),
        **data,
    }
    print(json_module.dumps(event), flush=True)


def _validate_api_key(api_key: str | None, config: Config) -> str | None:
    """Validate the API key against configured keys.

    Args:
        api_key: The API key from the X-Api-Key header.
        config: Application configuration.

    Returns:
        The service name ('radarr' or 'sonarr') if valid, None otherwise.
    """
    if not api_key:
        return None

    # Check against Radarr API key
    if config.radarr and api_key == config.radarr.api_key:
        return "radarr"

    # Check against Sonarr API key
    if config.sonarr and api_key == config.sonarr.api_key:
        return "sonarr"

    return None


def _format_network_error(error: httpx.ConnectError | httpx.TimeoutException) -> str:
    """Format a network error for clean logging.

    Args:
        error: The network error (connect or timeout).

    Returns:
        A concise error description.
    """
    if isinstance(error, httpx.TimeoutException):
        return "connection timed out"
    # ConnectError - extract just the core message
    return "connection failed"


def _format_check_outcome(
    has_match: bool,
    tag_result: TagResult | None,
) -> str:
    """Format the check outcome for logging.

    Args:
        has_match: Whether 4K releases were found.
        tag_result: The TagResult from the check, or None.

    Returns:
        A human-readable outcome string.
    """
    if has_match:
        if tag_result is None:
            return "4K available"
        if tag_result.dry_run:
            return f"4K available (dry-run, would apply: {tag_result.tag_applied})"
        if tag_result.tag_already_present:
            return f"4K available, tag already present ({tag_result.tag_applied})"
        if tag_result.tag_applied:
            return f"4K available, tag applied ({tag_result.tag_applied})"
        return "4K available (tagging disabled)"
    else:
        if tag_result is None:
            return "4K not available"
        if tag_result.dry_run:
            return f"4K not available (dry-run, would apply: {tag_result.tag_applied})"
        if tag_result.tag_already_present:
            return f"4K not available, tag already present ({tag_result.tag_applied})"
        if tag_result.tag_applied:
            return f"4K not available, tag applied ({tag_result.tag_applied})"
        return "4K not available (tagging disabled)"


async def _process_movie_check(movie_id: int, movie_title: str, config: Config) -> None:
    """Background task to check 4K availability for a movie."""
    if _output_format == "json":
        _output_json_event("webhook_received", source="radarr", title=movie_title)
    else:
        logger.info("Webhook: Radarr check - %s", movie_title)

    try:
        # Check TTL cache first
        if _state_manager is not None and config.state.ttl_hours > 0:
            cached = _state_manager.get_cached_result("movie", movie_id, config.state.ttl_hours)
            if cached is not None:
                cached_outcome = (
                    "4K available" if cached.result == "available" else "4K not available"
                )
                logger.info(
                    "Check result: skipped (recently checked), %s",
                    cached_outcome,
                )
                return

        radarr_config = config.require_radarr()
        logger.debug("Checking releases against criteria: 4K")
        checker = ReleaseChecker(
            radarr_url=radarr_config.url,
            radarr_api_key=radarr_config.api_key,
            timeout=config.timeout,
            tag_config=config.tags,
        )

        result = await checker.check_movie(movie_id, apply_tags=True)
        matching_count = len(result.matched_releases)
        logger.debug(
            "Found %d matching releases out of %d total",
            matching_count,
            len(result.releases),
        )

        # Build completion message with clear outcome
        outcome = _format_check_outcome(result.has_match, result.tag_result)

        # Determine tag_applied for JSON output
        tag_applied: str | None = None
        if result.tag_result and result.tag_result.tag_applied:
            tag_applied = result.tag_result.tag_applied

        if _output_format == "json":
            _output_json_event(
                "check_complete",
                title=movie_title,
                available=result.has_match,
                tag_applied=tag_applied,
            )
        else:
            logger.info("Check result: %s", outcome)

        # Record result in state file (even if no tag was applied)
        if _state_manager is not None:
            _state_manager.record_check(
                "movie",
                movie_id,
                result.has_match,
                result.tag_result.tag_applied if result.tag_result else None,
            )
    except ConfigurationError as e:
        logger.error("Webhook error: %s - configuration error: %s", movie_title, e)
    except httpx.HTTPStatusError as e:
        logger.error(
            "Webhook error: %s - HTTP %d %s",
            movie_title,
            e.response.status_code,
            e.response.reason_phrase,
        )
    except (httpx.ConnectError, httpx.TimeoutException) as e:
        logger.error("Webhook error: %s - %s", movie_title, _format_network_error(e))
    except ValidationError:
        logger.error("Webhook error: %s - invalid response data", movie_title)
    except Exception:
        # Catch-all for unexpected errors - use exception() for full traceback
        logger.exception("Webhook error: %s - unexpected error", movie_title)


async def _process_series_check(series_id: int, series_title: str, config: Config) -> None:
    """Background task to check 4K availability for a series."""
    if _output_format == "json":
        _output_json_event("webhook_received", source="sonarr", title=series_title)
    else:
        logger.info("Webhook: Sonarr check - %s", series_title)

    try:
        # Check TTL cache first
        if _state_manager is not None and config.state.ttl_hours > 0:
            cached = _state_manager.get_cached_result("series", series_id, config.state.ttl_hours)
            if cached is not None:
                cached_outcome = (
                    "4K available" if cached.result == "available" else "4K not available"
                )
                logger.info(
                    "Check result: skipped (recently checked), %s",
                    cached_outcome,
                )
                return

        sonarr_config = config.require_sonarr()
        logger.debug("Checking releases against criteria: 4K")
        checker = ReleaseChecker(
            sonarr_url=sonarr_config.url,
            sonarr_api_key=sonarr_config.api_key,
            timeout=config.timeout,
            tag_config=config.tags,
        )

        result = await checker.check_series(series_id, apply_tags=True)
        matching_count = len(result.matched_releases)
        logger.debug(
            "Found %d matching releases out of %d total",
            matching_count,
            len(result.releases),
        )

        # Build completion message with clear outcome
        outcome = _format_check_outcome(result.has_match, result.tag_result)

        # Determine tag_applied for JSON output
        tag_applied: str | None = None
        if result.tag_result and result.tag_result.tag_applied:
            tag_applied = result.tag_result.tag_applied

        if _output_format == "json":
            _output_json_event(
                "check_complete",
                title=series_title,
                available=result.has_match,
                tag_applied=tag_applied,
            )
        else:
            logger.info("Check result: %s", outcome)

        # Record result in state file (even if no tag was applied)
        if _state_manager is not None:
            _state_manager.record_check(
                "series",
                series_id,
                result.has_match,
                result.tag_result.tag_applied if result.tag_result else None,
            )
    except ConfigurationError as e:
        logger.error("Webhook error: %s - configuration error: %s", series_title, e)
    except httpx.HTTPStatusError as e:
        logger.error(
            "Webhook error: %s - HTTP %d %s",
            series_title,
            e.response.status_code,
            e.response.reason_phrase,
        )
    except (httpx.ConnectError, httpx.TimeoutException) as e:
        logger.error("Webhook error: %s - %s", series_title, _format_network_error(e))
    except ValidationError:
        logger.error("Webhook error: %s - invalid response data", series_title)
    except Exception:
        # Catch-all for unexpected errors - use exception() for full traceback
        logger.exception("Webhook error: %s - unexpected error", series_title)


def create_app(config: Config | None = None) -> Any:
    """Create the FastAPI application for webhook handling.

    Args:
        config: Application configuration. If None, loads from default sources.

    Returns:
        Configured FastAPI application.
    """
    try:
        from fastapi import FastAPI, Header, HTTPException, Request
        from fastapi.responses import JSONResponse
    except ImportError as e:
        raise ImportError(
            "FastAPI is required for webhook server. Install with: pip install filtarr[webhook]"
        ) from e

    if config is None:
        config = Config.load()

    app = FastAPI(
        title="Filtarr Webhook Server",
        description="Receive Radarr/Sonarr webhooks and check 4K availability",
        version="2.1.0",  # x-release-please-version
    )

    # Store background tasks to prevent garbage collection
    background_tasks: set[asyncio.Task[None]] = set()

    @app.get("/health")
    async def health_check() -> dict[str, str]:
        """Health check endpoint."""
        return {"status": "healthy"}

    @app.get("/status")
    async def status() -> dict[str, Any]:
        """Status endpoint showing server and scheduler state."""
        result: dict[str, Any] = {
            "status": "healthy",
            "timestamp": datetime.now(UTC).isoformat(),
            "radarr_configured": config.radarr is not None,
            "sonarr_configured": config.sonarr is not None,
            "scheduler": None,
        }

        if _scheduler_manager is not None:
            schedules = _scheduler_manager.get_all_schedules()
            enabled_schedules = [s for s in schedules if s.enabled]
            running = _scheduler_manager.get_running_schedules()
            recent_history = _scheduler_manager.get_history(limit=5)

            result["scheduler"] = {
                "enabled": True,
                "running": _scheduler_manager.is_running,
                "total_schedules": len(schedules),
                "enabled_schedules": len(enabled_schedules),
                "currently_running": list(running),
                "recent_runs": [
                    {
                        "schedule": r.schedule_name,
                        "status": r.status.value,
                        "started_at": r.started_at.isoformat(),
                        "items_processed": r.items_processed,
                        "items_with_4k": r.items_with_4k,
                    }
                    for r in recent_history
                ],
            }
        else:
            result["scheduler"] = {"enabled": False}

        return result

    @app.post("/webhook/radarr", response_model=WebhookResponse)
    async def radarr_webhook(
        payload: RadarrWebhookPayload,
        x_api_key: str | None = Header(default=None, alias="X-Api-Key"),
    ) -> WebhookResponse:
        """Handle Radarr webhook events.

        Expects X-Api-Key header matching the configured Radarr API key.
        Only processes MovieAdded events.
        """
        # Validate API key
        auth_service = _validate_api_key(x_api_key, config)
        if auth_service is None:
            raise HTTPException(
                status_code=401,
                detail="Invalid or missing X-Api-Key header",
            )

        # Check if Radarr is configured
        if config.radarr is None:
            raise HTTPException(
                status_code=503,
                detail="Radarr is not configured",
            )

        # Only process MovieAdded events
        if not payload.is_movie_added():
            logger.debug("Ignoring Radarr event: %s", payload.event_type)
            return WebhookResponse(
                status="ignored",
                message=f"Event type '{payload.event_type}' is not handled",
                media_id=payload.movie.id,
                media_title=payload.movie.title,
            )

        # Schedule background task for 4K check
        logger.debug(
            "Received MovieAdded webhook for: %s (id=%d)",
            payload.movie.title,
            payload.movie.id,
        )
        task = asyncio.create_task(
            _process_movie_check(payload.movie.id, payload.movie.title, config)
        )
        background_tasks.add(task)
        task.add_done_callback(background_tasks.discard)

        return WebhookResponse(
            status="accepted",
            message="4K availability check queued",
            media_id=payload.movie.id,
            media_title=payload.movie.title,
        )

    @app.post("/webhook/sonarr", response_model=WebhookResponse)
    async def sonarr_webhook(
        payload: SonarrWebhookPayload,
        x_api_key: str | None = Header(default=None, alias="X-Api-Key"),
    ) -> WebhookResponse:
        """Handle Sonarr webhook events.

        Expects X-Api-Key header matching the configured Sonarr API key.
        Only processes SeriesAdd events.
        """
        # Validate API key
        auth_service = _validate_api_key(x_api_key, config)
        if auth_service is None:
            raise HTTPException(
                status_code=401,
                detail="Invalid or missing X-Api-Key header",
            )

        # Check if Sonarr is configured
        if config.sonarr is None:
            raise HTTPException(
                status_code=503,
                detail="Sonarr is not configured",
            )

        # Only process SeriesAdd events
        if not payload.is_series_add():
            logger.debug("Ignoring Sonarr event: %s", payload.event_type)
            return WebhookResponse(
                status="ignored",
                message=f"Event type '{payload.event_type}' is not handled",
                media_id=payload.series.id,
                media_title=payload.series.title,
            )

        # Schedule background task for 4K check
        logger.debug(
            "Received SeriesAdd webhook for: %s (id=%d)",
            payload.series.title,
            payload.series.id,
        )
        task = asyncio.create_task(
            _process_series_check(payload.series.id, payload.series.title, config)
        )
        background_tasks.add(task)
        task.add_done_callback(background_tasks.discard)

        return WebhookResponse(
            status="accepted",
            message="4K availability check queued",
            media_id=payload.series.id,
            media_title=payload.series.title,
        )

    @app.exception_handler(Exception)
    async def global_exception_handler(
        request: Request,  # noqa: ARG001
        exc: Exception,  # noqa: ARG001
    ) -> JSONResponse:
        """Handle unexpected exceptions."""
        logger.exception("Unhandled exception in webhook handler")
        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "message": "Internal server error",
                "media_id": None,
                "media_title": None,
            },
        )

    return app


def run_server(
    host: str = "0.0.0.0",
    port: int = 8080,
    config: Config | None = None,
    log_level: str = "info",
    scheduler_enabled: bool = True,
    output_format: str = "text",
) -> None:
    """Run the webhook server with optional scheduler.

    Args:
        host: Host to bind to.
        port: Port to listen on.
        config: Application configuration.
        log_level: Logging level for uvicorn.
        scheduler_enabled: Whether to start the scheduler.
        output_format: Output format ('text' or 'json').
    """
    global _scheduler_manager, _state_manager, _output_format

    try:
        import uvicorn
    except ImportError as e:
        raise ImportError(
            "uvicorn is required for webhook server. Install with: pip install filtarr[webhook]"
        ) from e

    if config is None:
        config = Config.load()

    # Set the global output format
    _output_format = output_format

    app = create_app(config)

    # Initialize state manager for TTL checks and ensure state file exists
    from filtarr.state import StateManager

    state_manager = StateManager(config.state.path)
    state_manager.ensure_initialized()
    _state_manager = state_manager
    logger.info("State file initialized at: %s", config.state.path)
    if config.state.ttl_hours > 0:
        logger.info("State TTL: %d hours", config.state.ttl_hours)
    else:
        logger.info("State TTL: disabled")

    # Set up scheduler if enabled
    scheduler_manager: SchedulerManager | None = None
    if scheduler_enabled and config.scheduler.enabled:
        try:
            from filtarr.scheduler import SchedulerManager

            scheduler_manager = SchedulerManager(config, state_manager)
            _scheduler_manager = scheduler_manager
            logger.info("Scheduler configured and will start with server")
        except ImportError:
            logger.warning(
                "Scheduler dependencies not installed. Install with: pip install filtarr[scheduler]"
            )

    # Output server_started event in JSON mode
    if output_format == "json":
        _output_json_event(
            "server_started",
            host=host,
            port=port,
            radarr_configured=bool(config.radarr),
            sonarr_configured=bool(config.sonarr),
            scheduler_enabled=scheduler_enabled and config.scheduler.enabled,
        )

    async def run_with_scheduler() -> None:
        """Run uvicorn with scheduler lifecycle management."""
        uvicorn_config = uvicorn.Config(
            app,
            host=host,
            port=port,
            log_level=log_level.lower(),
        )
        server = uvicorn.Server(uvicorn_config)

        # Start scheduler before server
        if scheduler_manager is not None:
            try:
                await scheduler_manager.start()
            except (ImportError, ValueError) as e:
                # ImportError: APScheduler not installed
                # ValueError: Invalid schedule configuration
                logger.error("Failed to start scheduler: %s", e)
            except RuntimeError as e:
                # RuntimeError: Scheduler already running or other state issues
                logger.error("Scheduler runtime error: %s", e)

        try:
            await server.serve()
        finally:
            # Stop scheduler after server
            if scheduler_manager is not None:
                try:
                    await scheduler_manager.stop(wait=True)
                except asyncio.CancelledError:
                    # Expected during shutdown
                    logger.debug("Scheduler stop cancelled during shutdown")
                except RuntimeError as e:
                    # RuntimeError: Scheduler state issues during shutdown
                    logger.warning("Error during scheduler shutdown: %s", e)

    if scheduler_manager is not None:
        # Run with asyncio to manage scheduler lifecycle
        asyncio.run(run_with_scheduler())
    else:
        # Simple case - just run uvicorn directly
        uvicorn.run(app, host=host, port=port, log_level=log_level.lower())
