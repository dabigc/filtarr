#!/usr/bin/env bash
# Docker runtime testing for filtarr
#
# This script builds and tests the Docker image to verify:
# - The image builds successfully
# - The server starts correctly (catches issues like PR #54's uvicorn log level bug)
# - All endpoints respond as expected
#
# Usage:
#   ./scripts/test-docker.sh [--skip-build] [--pre-commit] [--image IMAGE_NAME]
#
# Options:
#   --skip-build      Skip the Docker build step (use existing image)
#   --pre-commit      Return exit code 0 (with warning) if Docker unavailable
#                     (for pre-commit hook compatibility)
#   --image NAME      Use specified image name instead of building 'filtarr-test'
#
# Exit codes:
#   0 - All tests passed (or Docker unavailable with --pre-commit)
#   1 - Tests failed
#   2 - Docker not available (only without --pre-commit flag)

set -euo pipefail

# Configuration
DEFAULT_IMAGE_NAME="filtarr-test"
IMAGE_NAME="$DEFAULT_IMAGE_NAME"
readonly CONTAINER_NAME="filtarr-test-$$"
PORT="$(python3 - <<'PY'
import socket

with socket.socket() as s:
    s.bind(("", 0))
    print(s.getsockname()[1])
PY
)"
readonly PORT
readonly HEALTH_TIMEOUT=30
readonly HEALTH_INTERVAL=1

# Colors for output
readonly RED='\033[0;31m'
readonly GREEN='\033[0;32m'
readonly YELLOW='\033[1;33m'
readonly NC='\033[0m' # No Color

# Track if we need cleanup
CONTAINER_STARTED=false

# Mode flags
PRE_COMMIT_MODE=false

#######################################
# Print colored message
#######################################
log_info() {
    echo -e "${GREEN}[INFO]${NC} $*"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $*"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $*"
}

#######################################
# Cleanup on exit
#######################################
cleanup() {
    if [[ "$CONTAINER_STARTED" == "true" ]]; then
        log_info "Cleaning up container..."
        docker stop "$CONTAINER_NAME" >/dev/null 2>&1 || true
        docker rm "$CONTAINER_NAME" >/dev/null 2>&1 || true
    fi
}
trap cleanup EXIT

#######################################
# Check if Docker is available
#######################################
check_docker() {
    if ! command -v docker &>/dev/null; then
        log_warn "Docker command not found. Skipping Docker tests."
        if [[ "$PRE_COMMIT_MODE" == "true" ]]; then
            exit 0
        fi
        exit 2
    fi

    if ! docker info &>/dev/null; then
        log_warn "Docker daemon not running. Skipping Docker tests."
        if [[ "$PRE_COMMIT_MODE" == "true" ]]; then
            exit 0
        fi
        exit 2
    fi

    log_info "Docker is available"
}

#######################################
# Check if curl is available
#######################################
check_curl() {
    if ! command -v curl &>/dev/null; then
        log_error "curl command not found. Please install curl to run Docker tests."
        if [[ "$PRE_COMMIT_MODE" == "true" ]]; then
            exit 0
        fi
        exit 2
    fi

    log_info "curl is available"
}

#######################################
# Build the Docker image
#######################################
build_image() {
    log_info "Building Docker image: $IMAGE_NAME"
    if ! docker build -t "$IMAGE_NAME" .; then
        log_error "Docker build failed"
        exit 1
    fi
    log_info "Docker image built successfully"
}

#######################################
# Start the container
#######################################
start_container() {
    log_info "Starting container: $CONTAINER_NAME on port $PORT"

    # Use minimal mock configuration
    # - allow_insecure=true to bypass HTTPS requirement for mock URLs
    # - scheduler disabled to avoid unnecessary background tasks
    # The container will start but return errors for actual API calls
    local docker_output
    if ! docker_output="$(
        docker run -d \
            --name "$CONTAINER_NAME" \
            -p "$PORT:8080" \
            -e FILTARR_RADARR_URL="http://mock-radarr:7878" \
            -e FILTARR_RADARR_API_KEY="mock-radarr-key-for-testing" \
            -e FILTARR_RADARR_ALLOW_INSECURE="true" \
            -e FILTARR_SONARR_URL="http://mock-sonarr:8989" \
            -e FILTARR_SONARR_API_KEY="mock-sonarr-key-for-testing" \
            -e FILTARR_SONARR_ALLOW_INSECURE="true" \
            -e FILTARR_SCHEDULER_ENABLED="false" \
            "$IMAGE_NAME" 2>&1
    )"; then
        log_error "Failed to start container:"
        echo "$docker_output"
        exit 1
    fi

    CONTAINER_STARTED=true
    log_info "Container started"
}

#######################################
# Wait for container to be healthy
#######################################
wait_for_healthy() {
    log_info "Waiting for container to be healthy (timeout: ${HEALTH_TIMEOUT}s)..."

    local elapsed=0
    while [[ $elapsed -lt $HEALTH_TIMEOUT ]]; do
        if curl -sf "http://localhost:$PORT/health" >/dev/null 2>&1; then
            log_info "Container is healthy after ${elapsed}s"
            return 0
        fi
        sleep "$HEALTH_INTERVAL"
        elapsed=$((elapsed + HEALTH_INTERVAL))
    done

    log_error "Container failed to become healthy within ${HEALTH_TIMEOUT}s"

    # Show container logs for debugging
    log_error "Container logs:"
    docker logs "$CONTAINER_NAME" 2>&1 | tail -50

    exit 1
}

#######################################
# Test an endpoint
# Arguments:
#   $1 - endpoint path
#   $2 - expected HTTP status code
#   $3 - description
#######################################
test_endpoint() {
    local endpoint="$1"
    local expected_status="$2"
    local description="$3"

    local actual_status
    # Use -s (silent) but not -f (fail) so we can capture non-2xx status codes
    actual_status=$(curl -s -o /dev/null -w "%{http_code}" "http://localhost:$PORT$endpoint" 2>/dev/null) || actual_status="000"

    if [[ "$actual_status" == "$expected_status" ]]; then
        log_info "PASS: $description (${endpoint} -> $actual_status)"
        return 0
    else
        log_error "FAIL: $description (${endpoint} -> expected $expected_status, got $actual_status)"
        return 1
    fi
}

#######################################
# Test POST endpoint with expected status
# Arguments:
#   $1 - endpoint path
#   $2 - expected HTTP status code
#   $3 - description
#######################################
test_post_endpoint() {
    local endpoint="$1"
    local expected_status="$2"
    local description="$3"

    local actual_status
    # Use -s (silent) but not -f (fail) so we can capture non-2xx status codes
    actual_status=$(curl -s -o /dev/null -w "%{http_code}" -X POST \
        -H "Content-Type: application/json" \
        -d '{}' \
        "http://localhost:$PORT$endpoint" 2>/dev/null) || actual_status="000"

    if [[ "$actual_status" == "$expected_status" ]]; then
        log_info "PASS: $description (POST ${endpoint} -> $actual_status)"
        return 0
    else
        log_error "FAIL: $description (POST ${endpoint} -> expected $expected_status, got $actual_status)"
        return 1
    fi
}

#######################################
# Run all endpoint tests
#######################################
run_tests() {
    log_info "Running endpoint tests..."

    local failed=0

    # Health endpoint - should always return 200
    test_endpoint "/health" "200" "Health endpoint responds" || ((failed++))

    # Status endpoint - should return 200 with scheduler info
    test_endpoint "/status" "200" "Status endpoint responds" || ((failed++))

    # Webhook endpoints with empty body - should return 422 Unprocessable Entity
    # FastAPI validates request body before auth, so 422 proves:
    # - The endpoint exists
    # - FastAPI routing is working
    # - Pydantic validation is active
    test_post_endpoint "/webhook/radarr" "422" "Radarr webhook validates payload" || ((failed++))
    test_post_endpoint "/webhook/sonarr" "422" "Sonarr webhook validates payload" || ((failed++))

    return $failed
}

#######################################
# Main
#######################################
main() {
    local skip_build=false

    # Parse arguments
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --skip-build)
                skip_build=true
                shift
                ;;
            --pre-commit)
                PRE_COMMIT_MODE=true
                shift
                ;;
            --image)
                if [[ -z "${2:-}" ]]; then
                    log_error "--image requires an argument"
                    exit 1
                fi
                IMAGE_NAME="$2"
                shift 2
                ;;
            *)
                log_error "Unknown option: $1"
                exit 1
                ;;
        esac
    done

    log_info "Starting Docker runtime tests for filtarr"

    check_docker
    check_curl

    if [[ "$skip_build" == "true" ]]; then
        if ! docker image inspect "$IMAGE_NAME" &>/dev/null; then
            log_error "Image '$IMAGE_NAME' not found. Either build it first or specify an existing image with --image."
            exit 1
        fi
        log_info "Using existing image: $IMAGE_NAME"
    else
        build_image
    fi

    start_container
    wait_for_healthy

    if run_tests; then
        log_info "All Docker tests passed!"
        exit 0
    else
        log_error "Some Docker tests failed"
        exit 1
    fi
}

main "$@"
