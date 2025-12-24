# syntax=docker/dockerfile:1

# Build stage - install dependencies
FROM python:3.14-alpine AS builder

# Install build dependencies and uv
RUN apk add --no-cache gcc musl-dev libffi-dev
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Copy dependency files first for better layer caching
COPY pyproject.toml uv.lock README.md ./

# Create virtual environment and install dependencies
# Install webhook, cli, and scheduler extras (not dev dependencies)
# Scheduler is included to enable scheduled batch operations out of the box
RUN uv sync --frozen --no-dev --extra webhook --extra cli --extra scheduler

# Copy source code and install the package itself
# Combined into single layer since source changes always require reinstall
COPY src/ ./src/
RUN uv pip install --no-deps -e .


# Runtime stage - minimal image
FROM python:3.14-alpine AS runtime

# Install runtime dependencies, create non-root user, and set up directories
# Combined into single layer to minimize image size
RUN apk add --no-cache libffi curl && \
    addgroup -g 1000 filtarr && \
    adduser -u 1000 -G filtarr -D -h /app filtarr && \
    mkdir -p /config && \
    chown filtarr:filtarr /config

WORKDIR /app

# Copy virtual environment and source from builder
COPY --from=builder --chown=filtarr:filtarr /app/.venv /app/.venv
COPY --from=builder --chown=filtarr:filtarr /app/src /app/src

# Set environment variables
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    FILTARR_WEBHOOK_HOST="0.0.0.0" \
    FILTARR_WEBHOOK_PORT="8080"

# Switch to non-root user
USER filtarr

# Expose webhook port
EXPOSE 8080

# Health check using the /health endpoint
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

# Default command: run the webhook server
CMD ["filtarr", "serve", "--host", "0.0.0.0", "--port", "8080"]
