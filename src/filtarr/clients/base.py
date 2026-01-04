"""Base client for Radarr/Sonarr API interactions."""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import logging
import time
from typing import TYPE_CHECKING, Any, Protocol, Self, runtime_checkable

import httpx
from cachetools import TTLCache
from tenacity import (
    RetryCallState,
    retry,
    retry_base,
    stop_after_attempt,
    wait_exponential,
)

# Status codes that should trigger a retry
RETRYABLE_STATUS_CODES = frozenset({429, 500, 502, 503, 504})


class RetryableHTTPError(Exception):
    """Exception for HTTP errors that should trigger a retry.

    This exception wraps HTTPStatusError for cases where we want to retry
    (429, 5xx responses) and carries the retry delay from Retry-After header.
    """

    def __init__(
        self,
        message: str,
        response: httpx.Response,
        retry_after: float | None = None,
    ) -> None:
        """Initialize RetryableHTTPError.

        Args:
            message: Error message
            response: The HTTP response that triggered the error
            retry_after: Optional delay in seconds from Retry-After header
        """
        super().__init__(message)
        self.response = response
        self.retry_after = retry_after

    @property
    def status_code(self) -> int:
        """Get the HTTP status code."""
        return self.response.status_code


class RetryPredicate(retry_base):
    """Custom retry predicate that retries on connection errors and retryable HTTP errors."""

    def __call__(self, retry_state: RetryCallState) -> bool:
        """Check if the exception should trigger a retry.

        Args:
            retry_state: The current retry state

        Returns:
            True if the exception should trigger a retry
        """
        if retry_state.outcome is None:
            return False

        exception = retry_state.outcome.exception()
        if exception is None:
            return False

        # Retry on connection errors
        if isinstance(exception, (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout)):
            return True

        # Retry on our custom retryable HTTP error
        return isinstance(exception, RetryableHTTPError)


class RetryAfterWait(wait_exponential):
    """Custom wait strategy that respects Retry-After header when present."""

    def __call__(self, retry_state: RetryCallState) -> float:
        """Calculate the wait time, respecting Retry-After if available.

        Args:
            retry_state: The current retry state

        Returns:
            Wait time in seconds
        """
        # Check if the exception has a retry_after value
        if retry_state.outcome is not None:
            exception = retry_state.outcome.exception()
            if isinstance(exception, RetryableHTTPError) and exception.retry_after is not None:
                return exception.retry_after

        # Fall back to exponential backoff
        return super().__call__(retry_state)


if TYPE_CHECKING:
    from filtarr.models.common import Release, Tag

logger = logging.getLogger(__name__)


@runtime_checkable
class ReleaseProvider(Protocol):
    """Protocol for clients that can fetch releases for media items.

    This protocol defines the interface for clients that can search for and
    return releases from indexers. Both RadarrClient and SonarrClient implement
    this protocol, allowing them to be used polymorphically in release-checking
    operations.

    Example:
        async def check_releases(provider: ReleaseProvider, item_id: int) -> bool:
            releases = await provider.get_releases_for_item(item_id)
            return any(r.is_4k() for r in releases)
    """

    async def get_releases_for_item(self, item_id: int) -> list[Release]:
        """Fetch releases for a specific media item.

        Args:
            item_id: The ID of the media item (movie ID for Radarr,
                     series ID for Sonarr)

        Returns:
            List of Release models found by indexers
        """
        ...


@runtime_checkable
class TaggableClient(Protocol):
    """Protocol for clients that support tag operations.

    This protocol defines the interface for clients that can manage tags
    on media items. Both RadarrClient and SonarrClient implement this protocol.
    """

    async def get_tags(self) -> list[Tag]:
        """Fetch all tags.

        Returns:
            List of Tag models
        """
        ...

    async def create_tag(self, label: str) -> Tag:
        """Create a new tag.

        Args:
            label: The tag label

        Returns:
            The created Tag model
        """
        ...

    async def add_tag_to_item(self, item_id: int, tag_id: int) -> Any:
        """Add a tag to an item (movie or series).

        Args:
            item_id: The item ID
            tag_id: The tag ID to add

        Returns:
            The updated item model
        """
        ...

    async def remove_tag_from_item(self, item_id: int, tag_id: int) -> Any:
        """Remove a tag from an item (movie or series).

        Args:
            item_id: The item ID
            tag_id: The tag ID to remove

        Returns:
            The updated item model
        """
        ...


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
        max_connections: int = 20,
        max_keepalive_connections: int = 10,
    ) -> None:
        """Initialize the client.

        Args:
            base_url: The base URL of the arr instance (e.g., http://localhost:7878)
            api_key: The API key for authentication
            timeout: Request timeout in seconds (default 120.0)
            cache_ttl: Cache time-to-live in seconds (default 300)
            max_retries: Maximum number of retry attempts (default 3)
            max_connections: Maximum number of concurrent connections in the pool
                (default 20). This limits the total number of simultaneous
                connections to the server.
            max_keepalive_connections: Maximum number of idle keep-alive connections
                to maintain in the pool (default 10). Keep-alive connections are
                reused for subsequent requests to avoid connection overhead.
        """
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self.cache_ttl = cache_ttl
        self.max_retries = max_retries
        self.max_connections = max_connections
        self.max_keepalive_connections = max_keepalive_connections

        self._client: httpx.AsyncClient | None = None
        self._cache: TTLCache[str, Any] = TTLCache(maxsize=1000, ttl=cache_ttl)
        self._cache_lock = asyncio.Lock()
        # Pending requests for stampede protection (thundering herd prevention)
        # Maps cache_key -> (Event, result_holder)
        # result_holder is a dict with 'data' or 'error' key once completed
        self._pending_requests: dict[str, tuple[asyncio.Event, dict[str, Any]]] = {}

    async def __aenter__(self) -> Self:
        """Enter async context manager."""
        limits = httpx.Limits(
            max_connections=self.max_connections,
            max_keepalive_connections=self.max_keepalive_connections,
        )
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            headers={"X-Api-Key": self.api_key},
            timeout=self.timeout,
            limits=limits,
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

    async def _get(self, endpoint: str, params: dict[str, Any] | None = None) -> Any:
        """Make a cached GET request with stampede protection.

        Checks the cache first. If not found, makes the request and caches
        the result. Includes stampede protection to prevent thundering herd
        when multiple concurrent requests hit the same uncached key.

        Args:
            endpoint: The API endpoint path (e.g., "/api/v3/release")
            params: Optional query parameters

        Returns:
            The JSON response data

        Raises:
            httpx.HTTPStatusError: On HTTP errors (after retries exhausted)
        """
        cache_key = self._make_cache_key(endpoint, params)

        # Variables to track if we're the leader or a waiter
        is_leader = False
        event: asyncio.Event | None = None
        result_holder: dict[str, Any] | None = None

        async with self._cache_lock:
            # Check cache first
            if cache_key in self._cache:
                logger.debug("Cache hit for %s", endpoint)
                return self._cache[cache_key]

            # Check if there's already a pending request for this key
            if cache_key in self._pending_requests:
                # Another request is already fetching this data - we'll wait for it
                event, result_holder = self._pending_requests[cache_key]
                logger.debug("Waiting for pending request for %s", endpoint)
            else:
                # We'll be the "leader" - create the pending request entry
                is_leader = True
                event = asyncio.Event()
                result_holder = {}
                self._pending_requests[cache_key] = (event, result_holder)
                logger.debug("Cache miss for %s, fetching from API", endpoint)

        # If we're a waiter (not the leader), wait for the leader to complete
        if not is_leader:
            assert event is not None and result_holder is not None
            await event.wait()

            # Return the result or re-raise the error
            if "error" in result_holder:
                raise result_holder["error"]
            return result_holder["data"]

        # We're the leader - fetch the data
        assert event is not None and result_holder is not None
        try:
            data = await self._get_uncached(endpoint, params)

            # Store in cache and set result for waiters
            async with self._cache_lock:
                self._cache[cache_key] = data
                result_holder["data"] = data
                # Clean up pending request entry
                self._pending_requests.pop(cache_key, None)

            # Signal waiters that data is ready (outside lock to avoid deadlock)
            event.set()

            return data

        except Exception as e:
            # Store error for waiters
            async with self._cache_lock:
                result_holder["error"] = e
                # Clean up pending request entry
                self._pending_requests.pop(cache_key, None)

            # Signal waiters that we're done (with error)
            event.set()
            raise

    async def _get_uncached(self, endpoint: str, params: dict[str, Any] | None = None) -> Any:
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
        # Track timing for performance diagnostics
        start_time = time.monotonic()

        @retry(
            stop=stop_after_attempt(self.max_retries),
            wait=RetryAfterWait(multiplier=1, min=1, max=10),
            retry=RetryPredicate(),
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

            # Retry on 429 or 5xx - raise RetryableHTTPError
            if response.status_code in RETRYABLE_STATUS_CODES:
                logger.warning("Retryable HTTP error %d for %s", response.status_code, endpoint)

                # Parse Retry-After header if present (for 429 responses)
                retry_after: float | None = None
                if response.status_code == 429:
                    retry_after_header = response.headers.get("Retry-After")
                    if retry_after_header:
                        # Retry-After can also be an HTTP date, but we only parse numeric values
                        with contextlib.suppress(ValueError):
                            retry_after = float(retry_after_header)

                raise RetryableHTTPError(
                    f"Retryable HTTP error {response.status_code} for {endpoint}",
                    response=response,
                    retry_after=retry_after,
                )

            # Other errors - raise without retry
            response.raise_for_status()

            return response.json()

        try:
            result = await _do_request()
            elapsed = time.monotonic() - start_time
            # Log slow requests (>5s) for performance diagnostics
            if elapsed > 5.0:
                logger.warning(
                    "Slow request (%.2fs) to %s - may indicate proxy timeout risk",
                    elapsed,
                    endpoint,
                )
            elif elapsed > 2.0:
                logger.debug("Request to %s took %.2fs", endpoint, elapsed)
            return result
        except RetryableHTTPError as e:
            # Re-raise as HTTPStatusError to maintain backward compatibility
            elapsed = time.monotonic() - start_time
            logger.warning(
                "Request to %s failed after %.2fs",
                endpoint,
                elapsed,
            )
            e.response.raise_for_status()
            raise  # pragma: no cover  # Unreachable: raise_for_status always raises
        except Exception:
            elapsed = time.monotonic() - start_time
            logger.warning(
                "Request to %s failed after %.2fs",
                endpoint,
                elapsed,
            )
            raise

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

    async def _post(self, endpoint: str, json: dict[str, Any] | None = None) -> Any:
        """Make a POST request.

        Args:
            endpoint: The API endpoint path
            json: Optional JSON body

        Returns:
            The JSON response data

        Raises:
            httpx.HTTPStatusError: On HTTP errors (after retries exhausted)
        """
        return await self._request_with_retry("POST", endpoint, json=json)

    async def _put(self, endpoint: str, json: dict[str, Any] | None = None) -> Any:
        """Make a PUT request.

        Args:
            endpoint: The API endpoint path
            json: Optional JSON body

        Returns:
            The JSON response data

        Raises:
            httpx.HTTPStatusError: On HTTP errors (after retries exhausted)
        """
        return await self._request_with_retry("PUT", endpoint, json=json)

    @staticmethod
    def _parse_release(item: dict[str, Any]) -> Release:
        """Parse a release from API response.

        Args:
            item: A single release item from the API response

        Returns:
            A Release model instance
        """
        from filtarr.models.common import Quality, Release

        quality_data = item.get("quality", {}).get("quality", {})
        return Release(
            guid=item["guid"],
            title=item["title"],
            indexer=item.get("indexer", "Unknown"),
            size=item.get("size", 0),
            quality=Quality(
                id=quality_data.get("id", 0),
                name=quality_data.get("name", "Unknown"),
            ),
        )
