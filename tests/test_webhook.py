"""Tests for webhook server functionality."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from findarr.config import Config, RadarrConfig, SonarrConfig, TagConfig, WebhookConfig
from findarr.models.webhook import (
    RadarrWebhookPayload,
    SonarrWebhookPayload,
    WebhookResponse,
)
from findarr.webhook import create_app


@pytest.fixture
def radarr_config() -> RadarrConfig:
    """Create a test Radarr configuration."""
    return RadarrConfig(url="http://radarr:7878", api_key="radarr-api-key")


@pytest.fixture
def sonarr_config() -> SonarrConfig:
    """Create a test Sonarr configuration."""
    return SonarrConfig(url="http://sonarr:8989", api_key="sonarr-api-key")


@pytest.fixture
def full_config(radarr_config: RadarrConfig, sonarr_config: SonarrConfig) -> Config:
    """Create a full test configuration."""
    return Config(
        radarr=radarr_config,
        sonarr=sonarr_config,
        tags=TagConfig(),
        webhook=WebhookConfig(host="0.0.0.0", port=8080),
    )


@pytest.fixture
def radarr_only_config(radarr_config: RadarrConfig) -> Config:
    """Create a config with only Radarr configured."""
    return Config(radarr=radarr_config, webhook=WebhookConfig())


@pytest.fixture
def sonarr_only_config(sonarr_config: SonarrConfig) -> Config:
    """Create a config with only Sonarr configured."""
    return Config(sonarr=sonarr_config, webhook=WebhookConfig())


@pytest.fixture
def test_client(full_config: Config) -> TestClient:
    """Create a test client for the webhook app."""
    app = create_app(full_config)
    return TestClient(app)


class TestWebhookModels:
    """Tests for webhook Pydantic models."""

    def test_radarr_webhook_payload_parsing(self) -> None:
        """Should parse Radarr webhook payload correctly."""
        data = {
            "eventType": "MovieAdded",
            "movie": {
                "id": 123,
                "title": "The Matrix",
                "year": 1999,
                "tmdbId": 603,
                "imdbId": "tt0133093",
            },
        }
        payload = RadarrWebhookPayload.model_validate(data)

        assert payload.event_type == "MovieAdded"
        assert payload.movie.id == 123
        assert payload.movie.title == "The Matrix"
        assert payload.movie.year == 1999
        assert payload.movie.tmdb_id == 603
        assert payload.movie.imdb_id == "tt0133093"
        assert payload.is_movie_added() is True

    def test_radarr_webhook_non_added_event(self) -> None:
        """Should correctly identify non-MovieAdded events."""
        data = {
            "eventType": "Download",
            "movie": {"id": 123, "title": "Test Movie"},
        }
        payload = RadarrWebhookPayload.model_validate(data)

        assert payload.event_type == "Download"
        assert payload.is_movie_added() is False

    def test_sonarr_webhook_payload_parsing(self) -> None:
        """Should parse Sonarr webhook payload correctly."""
        data = {
            "eventType": "SeriesAdd",
            "series": {
                "id": 456,
                "title": "Breaking Bad",
                "year": 2008,
                "tvdbId": 81189,
                "imdbId": "tt0903747",
            },
        }
        payload = SonarrWebhookPayload.model_validate(data)

        assert payload.event_type == "SeriesAdd"
        assert payload.series.id == 456
        assert payload.series.title == "Breaking Bad"
        assert payload.series.year == 2008
        assert payload.series.tvdb_id == 81189
        assert payload.series.imdb_id == "tt0903747"
        assert payload.is_series_add() is True

    def test_sonarr_webhook_non_add_event(self) -> None:
        """Should correctly identify non-SeriesAdd events."""
        data = {
            "eventType": "Download",
            "series": {"id": 456, "title": "Test Series"},
        }
        payload = SonarrWebhookPayload.model_validate(data)

        assert payload.event_type == "Download"
        assert payload.is_series_add() is False

    def test_webhook_response_model(self) -> None:
        """Should create webhook response correctly."""
        response = WebhookResponse(
            status="accepted",
            message="4K availability check queued",
            media_id=123,
            media_title="The Matrix",
        )

        assert response.status == "accepted"
        assert response.message == "4K availability check queued"
        assert response.media_id == 123
        assert response.media_title == "The Matrix"


class TestHealthEndpoint:
    """Tests for the health check endpoint."""

    def test_health_check_returns_healthy(self, test_client: TestClient) -> None:
        """Should return healthy status."""
        response = test_client.get("/health")

        assert response.status_code == 200
        assert response.json() == {"status": "healthy"}


class TestRadarrWebhook:
    """Tests for the Radarr webhook endpoint."""

    def test_radarr_webhook_requires_api_key(self, test_client: TestClient) -> None:
        """Should reject requests without API key."""
        response = test_client.post(
            "/webhook/radarr",
            json={
                "eventType": "MovieAdded",
                "movie": {"id": 123, "title": "Test Movie"},
            },
        )

        assert response.status_code == 401
        assert "X-Api-Key" in response.json()["detail"]

    def test_radarr_webhook_rejects_invalid_api_key(self, test_client: TestClient) -> None:
        """Should reject requests with invalid API key."""
        response = test_client.post(
            "/webhook/radarr",
            json={
                "eventType": "MovieAdded",
                "movie": {"id": 123, "title": "Test Movie"},
            },
            headers={"X-Api-Key": "wrong-key"},
        )

        assert response.status_code == 401

    def test_radarr_webhook_accepts_valid_api_key(self, full_config: Config) -> None:
        """Should accept requests with valid Radarr API key."""
        app = create_app(full_config)
        client = TestClient(app)

        with patch("findarr.webhook.asyncio.create_task"):
            response = client.post(
                "/webhook/radarr",
                json={
                    "eventType": "MovieAdded",
                    "movie": {"id": 123, "title": "Test Movie", "year": 2023},
                },
                headers={"X-Api-Key": "radarr-api-key"},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "accepted"
        assert data["media_id"] == 123
        assert data["media_title"] == "Test Movie"

    def test_radarr_webhook_ignores_non_movie_added_events(self, full_config: Config) -> None:
        """Should ignore events that are not MovieAdded."""
        app = create_app(full_config)
        client = TestClient(app)

        response = client.post(
            "/webhook/radarr",
            json={
                "eventType": "Download",
                "movie": {"id": 123, "title": "Test Movie"},
            },
            headers={"X-Api-Key": "radarr-api-key"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ignored"
        assert "Download" in data["message"]

    def test_radarr_webhook_not_configured(self, sonarr_only_config: Config) -> None:
        """Should return 503 when Radarr is not configured."""
        app = create_app(sonarr_only_config)
        client = TestClient(app)

        response = client.post(
            "/webhook/radarr",
            json={
                "eventType": "MovieAdded",
                "movie": {"id": 123, "title": "Test Movie"},
            },
            headers={"X-Api-Key": "sonarr-api-key"},
        )

        assert response.status_code == 503
        assert "Radarr is not configured" in response.json()["detail"]


class TestSonarrWebhook:
    """Tests for the Sonarr webhook endpoint."""

    def test_sonarr_webhook_requires_api_key(self, test_client: TestClient) -> None:
        """Should reject requests without API key."""
        response = test_client.post(
            "/webhook/sonarr",
            json={
                "eventType": "SeriesAdd",
                "series": {"id": 456, "title": "Test Series"},
            },
        )

        assert response.status_code == 401
        assert "X-Api-Key" in response.json()["detail"]

    def test_sonarr_webhook_rejects_invalid_api_key(self, test_client: TestClient) -> None:
        """Should reject requests with invalid API key."""
        response = test_client.post(
            "/webhook/sonarr",
            json={
                "eventType": "SeriesAdd",
                "series": {"id": 456, "title": "Test Series"},
            },
            headers={"X-Api-Key": "wrong-key"},
        )

        assert response.status_code == 401

    def test_sonarr_webhook_accepts_valid_api_key(self, full_config: Config) -> None:
        """Should accept requests with valid Sonarr API key."""
        app = create_app(full_config)
        client = TestClient(app)

        with patch("findarr.webhook.asyncio.create_task"):
            response = client.post(
                "/webhook/sonarr",
                json={
                    "eventType": "SeriesAdd",
                    "series": {"id": 456, "title": "Breaking Bad", "year": 2008},
                },
                headers={"X-Api-Key": "sonarr-api-key"},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "accepted"
        assert data["media_id"] == 456
        assert data["media_title"] == "Breaking Bad"

    def test_sonarr_webhook_ignores_non_series_add_events(self, full_config: Config) -> None:
        """Should ignore events that are not SeriesAdd."""
        app = create_app(full_config)
        client = TestClient(app)

        response = client.post(
            "/webhook/sonarr",
            json={
                "eventType": "Download",
                "series": {"id": 456, "title": "Test Series"},
            },
            headers={"X-Api-Key": "sonarr-api-key"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ignored"
        assert "Download" in data["message"]

    def test_sonarr_webhook_not_configured(self, radarr_only_config: Config) -> None:
        """Should return 503 when Sonarr is not configured."""
        app = create_app(radarr_only_config)
        client = TestClient(app)

        response = client.post(
            "/webhook/sonarr",
            json={
                "eventType": "SeriesAdd",
                "series": {"id": 456, "title": "Test Series"},
            },
            headers={"X-Api-Key": "radarr-api-key"},
        )

        assert response.status_code == 503
        assert "Sonarr is not configured" in response.json()["detail"]


class TestBackgroundProcessing:
    """Tests for background task processing."""

    @pytest.mark.asyncio
    async def test_movie_check_background_task_created(self, full_config: Config) -> None:
        """Should create background task for movie check on MovieAdded event."""
        app = create_app(full_config)
        client = TestClient(app)

        with patch("findarr.webhook.asyncio.create_task") as mock_create_task:
            response = client.post(
                "/webhook/radarr",
                json={
                    "eventType": "MovieAdded",
                    "movie": {"id": 123, "title": "Test Movie", "year": 2023},
                },
                headers={"X-Api-Key": "radarr-api-key"},
            )

            assert response.status_code == 200
            mock_create_task.assert_called_once()

    @pytest.mark.asyncio
    async def test_series_check_background_task_created(self, full_config: Config) -> None:
        """Should create background task for series check on SeriesAdd event."""
        app = create_app(full_config)
        client = TestClient(app)

        with patch("findarr.webhook.asyncio.create_task") as mock_create_task:
            response = client.post(
                "/webhook/sonarr",
                json={
                    "eventType": "SeriesAdd",
                    "series": {"id": 456, "title": "Test Series", "year": 2020},
                },
                headers={"X-Api-Key": "sonarr-api-key"},
            )

            assert response.status_code == 200
            mock_create_task.assert_called_once()


class TestWebhookConfig:
    """Tests for WebhookConfig in the Config class."""

    def test_default_webhook_config(self) -> None:
        """Should have default webhook configuration."""
        config = Config()

        assert config.webhook.host == "0.0.0.0"
        assert config.webhook.port == 8080

    def test_custom_webhook_config(self) -> None:
        """Should accept custom webhook configuration."""
        config = Config(webhook=WebhookConfig(host="127.0.0.1", port=9000))

        assert config.webhook.host == "127.0.0.1"
        assert config.webhook.port == 9000
