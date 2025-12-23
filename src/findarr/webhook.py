"""Webhook server for receiving Radarr/Sonarr notifications."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from findarr.checker import FourKChecker
from findarr.config import Config, TagConfig
from findarr.models.webhook import (
    RadarrWebhookPayload,
    SonarrWebhookPayload,
    WebhookResponse,
)

if TYPE_CHECKING:
    from findarr.scheduler import SchedulerManager

logger = logging.getLogger(__name__)

# Global reference to scheduler manager for status endpoint
_scheduler_manager: SchedulerManager | None = None


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


async def _process_movie_check(movie_id: int, movie_title: str, config: Config) -> None:
    """Background task to check 4K availability for a movie."""
    logger.info(f"Processing 4K check for movie: {movie_title} (id={movie_id})")

    try:
        radarr_config = config.require_radarr()
        tag_config = TagConfig(
            available=config.tags.available,
            unavailable=config.tags.unavailable,
            create_if_missing=config.tags.create_if_missing,
            recheck_days=config.tags.recheck_days,
        )
        checker = FourKChecker(
            radarr_url=radarr_config.url,
            radarr_api_key=radarr_config.api_key,
            timeout=config.timeout,
            tag_config=tag_config,
        )

        result = await checker.check_movie(movie_id, apply_tags=True)
        logger.info(
            f"4K check complete for '{movie_title}': "
            f"has_4k={result.has_4k}, releases={len(result.releases)}"
        )
    except Exception:
        logger.exception(f"Failed to check 4K availability for movie {movie_id}")


async def _process_series_check(series_id: int, series_title: str, config: Config) -> None:
    """Background task to check 4K availability for a series."""
    logger.info(f"Processing 4K check for series: {series_title} (id={series_id})")

    try:
        sonarr_config = config.require_sonarr()
        tag_config = TagConfig(
            available=config.tags.available,
            unavailable=config.tags.unavailable,
            create_if_missing=config.tags.create_if_missing,
            recheck_days=config.tags.recheck_days,
        )
        checker = FourKChecker(
            sonarr_url=sonarr_config.url,
            sonarr_api_key=sonarr_config.api_key,
            timeout=config.timeout,
            tag_config=tag_config,
        )

        result = await checker.check_series(series_id, apply_tags=True)
        logger.info(
            f"4K check complete for '{series_title}': "
            f"has_4k={result.has_4k}, releases={len(result.releases)}"
        )
    except Exception:
        logger.exception(f"Failed to check 4K availability for series {series_id}")


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
            "FastAPI is required for webhook server. Install with: pip install findarr[webhook]"
        ) from e

    if config is None:
        config = Config.load()

    app = FastAPI(
        title="findarr Webhook Server",
        description="Receive Radarr/Sonarr webhooks and check 4K availability",
        version="0.0.2",
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
            logger.debug(f"Ignoring Radarr event: {payload.event_type}")
            return WebhookResponse(
                status="ignored",
                message=f"Event type '{payload.event_type}' is not handled",
                media_id=payload.movie.id,
                media_title=payload.movie.title,
            )

        # Schedule background task for 4K check
        logger.info(
            f"Received MovieAdded webhook for: {payload.movie.title} (id={payload.movie.id})"
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
            logger.debug(f"Ignoring Sonarr event: {payload.event_type}")
            return WebhookResponse(
                status="ignored",
                message=f"Event type '{payload.event_type}' is not handled",
                media_id=payload.series.id,
                media_title=payload.series.title,
            )

        # Schedule background task for 4K check
        logger.info(
            f"Received SeriesAdd webhook for: {payload.series.title} (id={payload.series.id})"
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
) -> None:
    """Run the webhook server with optional scheduler.

    Args:
        host: Host to bind to.
        port: Port to listen on.
        config: Application configuration.
        log_level: Logging level for uvicorn.
        scheduler_enabled: Whether to start the scheduler.
    """
    global _scheduler_manager

    try:
        import uvicorn
    except ImportError as e:
        raise ImportError(
            "uvicorn is required for webhook server. Install with: pip install findarr[webhook]"
        ) from e

    if config is None:
        config = Config.load()

    app = create_app(config)

    # Set up scheduler if enabled
    scheduler_manager: SchedulerManager | None = None
    if scheduler_enabled and config.scheduler.enabled:
        try:
            from findarr.scheduler import SchedulerManager
            from findarr.state import StateManager

            state_manager = StateManager(config.state.path)
            scheduler_manager = SchedulerManager(config, state_manager)
            _scheduler_manager = scheduler_manager
            logger.info("Scheduler configured and will start with server")
        except ImportError:
            logger.warning(
                "Scheduler dependencies not installed. Install with: pip install findarr[scheduler]"
            )

    async def run_with_scheduler() -> None:
        """Run uvicorn with scheduler lifecycle management."""
        uvicorn_config = uvicorn.Config(
            app,
            host=host,
            port=port,
            log_level=log_level,
        )
        server = uvicorn.Server(uvicorn_config)

        # Start scheduler before server
        if scheduler_manager is not None:
            try:
                await scheduler_manager.start()
            except Exception as e:
                logger.error("Failed to start scheduler: %s", e)

        try:
            await server.serve()
        finally:
            # Stop scheduler after server
            if scheduler_manager is not None:
                try:
                    await scheduler_manager.stop(wait=True)
                except Exception as e:
                    logger.error("Error stopping scheduler: %s", e)

    if scheduler_manager is not None:
        # Run with asyncio to manage scheduler lifecycle
        asyncio.run(run_with_scheduler())
    else:
        # Simple case - just run uvicorn directly
        uvicorn.run(app, host=host, port=port, log_level=log_level)
