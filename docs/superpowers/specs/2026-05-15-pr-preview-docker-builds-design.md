# PR Preview Docker Image Builds

## Summary

Add an opt-in GitHub Actions workflow that builds Docker images from pull requests and pushes them to GHCR with PR-specific tags, enabling real-world integration testing before merging.

## Motivation

Currently, Docker images are only published on tagged releases. To test a PR in a production-like environment, you'd need to manually build the image locally and transfer it. This workflow automates that — label a PR, get a pullable image.

## Design

### Workflow File

New file: `.github/workflows/pr-preview.yml`

Separate from `ci.yml` (quality gates) and `release.yml` (production images). Owns the entire PR preview lifecycle: build, push, and cleanup.

### Triggers

| Trigger | Event | Purpose |
|---------|-------|---------|
| `pull_request: [labeled]` | Label added to PR | Build when `deploy-preview` label is applied |
| `pull_request: [synchronize]` | Push to labeled PR | Rebuild on new commits if label is present |
| `pull_request: [closed]` | PR merged or closed | Clean up the preview image |
| `workflow_dispatch` | Manual from Actions UI | One-off build by entering a PR number |

### Jobs

#### `build` — Build and Push Preview Image

**Runs when** (any of):
- `labeled` event AND the label is `deploy-preview`
- `synchronize` event AND PR currently has `deploy-preview` label
- `workflow_dispatch` event

**Steps:**
1. Checkout code — PR events use `github.event.pull_request.head.sha`; dispatch uses `refs/pull/{input.pr_number}/head`
2. Set up Docker Buildx (no QEMU — amd64 only)
3. Login to GHCR with `GITHUB_TOKEN`
4. Resolve PR number from event context or dispatch input
5. Build and push: `ghcr.io/dabigc/filtarr:pr-{number}` — single platform `linux/amd64`
6. Comment on PR with the pull command

**Image tag:** `pr-{number}` (e.g., `pr-123`). Overwrites on each push — always points to the latest build for that PR.

#### `cleanup` — Delete Preview Image on PR Close

**Runs when:** `closed` event AND PR has `deploy-preview` label

**Steps:**
1. Find the package version tagged `pr-{number}` via GitHub REST API (`GET /users/{owner}/packages/container/{name}/versions`)
2. Delete the version (`DELETE /users/{owner}/packages/container/{name}/versions/{id}`)
3. Comment on PR confirming image was cleaned up

### Concurrency

```yaml
concurrency:
  group: pr-preview-${{ github.event.pull_request.number || github.event.inputs.pr_number }}
  cancel-in-progress: true
```

Prevents parallel builds for the same PR when commits are pushed in rapid succession.

### Permissions

```yaml
permissions:
  contents: read
  packages: write
  pull-requests: write
```

- `contents: read` — checkout code
- `packages: write` — push/delete container images
- `pull-requests: write` — post comments on the PR

### Security Model

- **No fork PR risk:** This repo does not accept fork PRs. The `pull_request` event (not `pull_request_target`) is safe and has access to `GITHUB_TOKEN` with the permissions above.
- **Label gating:** Only users with **write** access to the repo can add labels, providing natural access control.
- **workflow_dispatch gating:** Only users with **write** access can trigger manual workflows.
- **No additional secrets:** Only `GITHUB_TOKEN` is used — no external registry credentials needed.
- **If fork PRs are ever accepted in the future:** This workflow should be revisited. The `pull_request` event from forks has limited `GITHUB_TOKEN` permissions and cannot push to GHCR. A `workflow_run` or `pull_request_target` pattern would be needed.

### Tag Hygiene

- PR images use `pr-{number}` prefix — clearly distinct from semver tags (`3.0.1`, `3.0`, `3`, `latest`)
- No `latest` or version tags are applied to preview images
- OCI labels include source metadata pointing to the PR
- Automatic cleanup on PR close prevents tag accumulation

### PR Comments

The workflow posts comments to the PR at two points:

**On successful build:**
> Preview image built and pushed.
> ```
> docker pull ghcr.io/dabigc/filtarr:pr-123
> ```

**On cleanup (PR close):**
> Preview image `pr-123` has been cleaned up.

### Build Configuration

- **Platform:** `linux/amd64` only (no arm64 — not needed for test environment)
- **Cache:** GitHub Actions cache (`type=gha`) for Docker layer caching
- **Timeout:** 15 minutes
- **Base image:** Same Dockerfile as production (multi-stage, `python:3.14-alpine`)

### Usage

```bash
# Option 1: Add label to PR
# Go to PR → Labels → add "deploy-preview"
# Image builds automatically on each push

# Option 2: Manual trigger
# Go to Actions → "PR Preview Build" → Run workflow → enter PR number

# Pull the image on your server
docker pull ghcr.io/dabigc/filtarr:pr-123

# Run it
docker run -d \
  -p 8080:8080 \
  -e FILTARR_RADARR_URL="http://radarr:7878" \
  -e FILTARR_RADARR_API_KEY="your-key" \
  ghcr.io/dabigc/filtarr:pr-123
```

## Out of Scope

- Multi-arch builds (arm64) — not needed for the test environment
- Build gating on CI status — preview builds are independent of quality checks
- Deployment automation — the user manually pulls and runs the image
- Image signing or attestation — not needed for preview images
