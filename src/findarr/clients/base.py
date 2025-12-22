"""Base client for Radarr/Sonarr API interactions."""

from __future__ import annotations

import asyncio
import hashlib
import logging
from typing import Any, Self

import httpx
from cachetools import TTLCache
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

logger = logging.getLogger(__name__)


class BaseArrClient:
    """Base client with retry and caching for Radarr/Sonarr APIs.

    This base class provides:
    - HTTP client management with connection pooling
    - Automatic retry with exponential backoff for transient failures
    - Per-client TTL caching for GET requests
    - Context manager protocol for resource cleanup

    Subclasses should implement specific API methods using the provided
    `_get()` method for cached requests or `_get_uncached()` for fresh data.
    """

    def __init__(
        self,
        base_url: str,
        api_key: str,
        *,
        timeout: float = 120.0,
        cache_ttl: int = 300,
        max_retries: int = 3,
    ) -> None:
        """Initialize the client.

        Args:
            base_url: The base URL of the arr instance (e.g., http://localhost:7878)
            api_key: The API key for authentication
            timeout: Request timeout in seconds (default 120.0)
            cache_ttl: Cache time-to-live in seconds (default 300)
            max_retries: Maximum number of retry attempts (default 3)
        """
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self.cache_ttl = cache_ttl
        self.max_retries = max_retries

        self._client: httpx.AsyncClient | None = None
        self._cache: TTLCache[str, Any] = TTLCache(maxsize=1000, ttl=cache_ttl)
        self._cache_lock = asyncio.Lock()

    async def __aenter__(self) -> Self:
        """Enter async context manager."""
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            headers={"X-Api-Key": self.api_key},
            timeout=self.timeout,
        )
        return self

    async def __aexit__(self, *args: Any) -> None:
        """Exit async context manager."""
        if self._client:
            await self._client.aclose()
            self._client = None

    @property
    def client(self) -> httpx.AsyncClient:
        """Get the HTTP client, raising if not in context.

        Returns:
            The httpx async client

        Raises:
            RuntimeError: If called outside of async context manager
        """
        if self._client is None:
            raise RuntimeError("Client must be used within async context manager")
        return self._client

    def _make_cache_key(self, endpoint: str, params: dict[str, Any] | None) -> str:
        """Generate a cache key from endpoint and parameters.

        Args:
            endpoint: The API endpoint path
            params: Query parameters

        Returns:
            A unique cache key string
        """
        params_str = str(sorted((params or {}).items()))
        key_data = f"{endpoint}:{params_str}"
        return hashlib.sha256(key_data.encode()).hexdigest()[:16]

    async def _get(
        self, endpoint: str, params: dict[str, Any] | None = None
    ) -> Any:
        """Make a cached GET request.

        Checks the cache first. If not found, makes the request and caches
        the result.

        Args:
            endpoint: The API endpoint path (e.g., "/api/v3/release")
            params: Optional query parameters

        Returns:
            The JSON response data

        Raises:
            httpx.HTTPStatusError: On HTTP errors (after retries exhausted)
        """
        cache_key = self._make_cache_key(endpoint, params)

        # Check cache first (with lock for async safety)
        async with self._cache_lock:
            if cache_key in self._cache:
                logger.debug("Cache hit for %s", endpoint)
                return self._cache[cache_key]

        # Cache miss - fetch from API
        logger.debug("Cache miss for %s, fetching from API", endpoint)
        data = await self._get_uncached(endpoint, params)

        # Store in cache
        async with self._cache_lock:
            self._cache[cache_key] = data

        return data

    async def _get_uncached(
        self, endpoint: str, params: dict[str, Any] | None = None
    ) -> Any:
        """Make a GET request without caching.

        This method includes retry logic for transient failures.

        Args:
            endpoint: The API endpoint path
            params: Optional query parameters

        Returns:
            The JSON response data

        Raises:
            httpx.HTTPStatusError: On HTTP errors (after retries exhausted)
        """
        return await self._request_with_retry("GET", endpoint, params=params)

    async def _request_with_retry(
        self,
        method: str,
        endpoint: str,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> Any:
        """Make an HTTP request with retry logic.

        Retries on:
        - Connection errors
        - Timeouts
        - 429 (Too Many Requests)
        - 5xx server errors

        Does NOT retry on:
        - 401 (Unauthorized) - fail fast
        - 404 (Not Found) - fail fast
        - Other 4xx client errors

        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: The API endpoint path
            params: Optional query parameters
            json: Optional JSON body

        Returns:
            The JSON response data

        Raises:
            httpx.HTTPStatusError: On non-retryable HTTP errors
            tenacity.RetryError: After all retries exhausted
        """

        @retry(
            stop=stop_after_attempt(self.max_retries),
            wait=wait_exponential(multiplier=1, min=1, max=10),
            retry=retry_if_exception_type(
                (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout)
            ),
            before_sleep=self._log_retry,
            reraise=True,
        )
        async def _do_request() -> Any:
            response = await self.client.request(
                method,
                endpoint,
                params=params,
                json=json,
            )

            # Don't retry on 401/404 - fail immediately
            if response.status_code in (401, 404):
                response.raise_for_status()

            # Retry on 429 or 5xx
            if response.status_code == 429 or response.status_code >= 500:
                logger.warning(
                    "Retryable HTTP error %d for %s", response.status_code, endpoint
                )
                response.raise_for_status()

            # Other errors - raise without retry
            response.raise_for_status()

            return response.json()

        return await _do_request()

    def _log_retry(self, retry_state: Any) -> None:
        """Log retry attempts.

        Args:
            retry_state: Tenacity retry state object
        """
        logger.warning(
            "Retry attempt %d after error: %s",
            retry_state.attempt_number,
            retry_state.outcome.exception() if retry_state.outcome else "unknown",
        )

    async def invalidate_cache(self, endpoint: str, params: dict[str, Any] | None = None) -> bool:
        """Invalidate a specific cache entry.

        Args:
            endpoint: The API endpoint path
            params: Optional query parameters

        Returns:
            True if entry was found and removed, False otherwise
        """
        cache_key = self._make_cache_key(endpoint, params)
        async with self._cache_lock:
            if cache_key in self._cache:
                del self._cache[cache_key]
                return True
            return False

    async def clear_cache(self) -> int:
        """Clear all cached entries.

        Returns:
            The number of entries that were cleared
        """
        async with self._cache_lock:
            count = len(self._cache)
            self._cache.clear()
            return count
