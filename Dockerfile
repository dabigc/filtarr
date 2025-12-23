# syntax=docker/dockerfile:1

# Build stage - install dependencies
FROM python:3.12-alpine AS builder

# Install build dependencies for Alpine
RUN apk add --no-cache gcc musl-dev libffi-dev

# Install uv for fast dependency management
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Copy dependency files first for better layer caching
COPY pyproject.toml uv.lock README.md ./

# Create virtual environment and install dependencies
# Install webhook, cli, and scheduler extras (not dev dependencies)
# Scheduler is included to enable scheduled batch operations out of the box
RUN uv sync --frozen --no-dev --extra webhook --extra cli --extra scheduler

# Copy source code
COPY src/ ./src/

# Install the package itself
RUN uv pip install --no-deps -e .


# Runtime stage - minimal image
FROM python:3.12-alpine AS runtime

# Install runtime dependencies only
RUN apk add --no-cache libffi curl

# Create non-root user for security
RUN addgroup -g 1000 findarr && \
    adduser -u 1000 -G findarr -D -h /app findarr

WORKDIR /app

# Copy virtual environment from builder
COPY --from=builder --chown=findarr:findarr /app/.venv /app/.venv
COPY --from=builder --chown=findarr:findarr /app/src /app/src

# Set environment variables
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    # Default webhook server settings
    FINDARR_WEBHOOK_HOST="0.0.0.0" \
    FINDARR_WEBHOOK_PORT="8080"

# Create config directory
RUN mkdir -p /config && chown findarr:findarr /config

# Switch to non-root user
USER findarr

# Expose webhook port
EXPOSE 8080

# Health check using the /health endpoint
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

# Default command: run the webhook server
CMD ["findarr", "serve", "--host", "0.0.0.0", "--port", "8080"]
