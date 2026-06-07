# PR Preview Docker Image Builds — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an opt-in GitHub Actions workflow that builds Docker images from PRs with `pr-{number}` tags and cleans up on close.

**Architecture:** Single workflow file (`.github/workflows/pr-preview.yml`) with two jobs: `build` (triggered by label or dispatch) and `cleanup` (triggered by PR close). Uses the same Docker toolchain as `release.yml` but amd64-only.

**Tech Stack:** GitHub Actions, Docker Buildx, GHCR, GitHub Packages REST API, `peter-evans/create-or-update-comment` for sticky PR comments.

**Spec:** `docs/superpowers/specs/2026-05-15-pr-preview-docker-builds-design.md`

---

### Task 1: Create workflow file with build job

**Files:**
- Create: `.github/workflows/pr-preview.yml`

This task creates the complete workflow file with triggers, the build job, and a PR comment. The cleanup job is added in Task 2.

- [ ] **Step 1: Create the workflow file**

Create `.github/workflows/pr-preview.yml` with the following content:

```yaml
name: PR Preview Build

on:
  pull_request:
    types: [labeled, synchronize, closed]
    branches: [main]
  workflow_dispatch:
    inputs:
      pr_number:
        description: "PR number to build a preview image for"
        required: true
        type: number

concurrency:
  group: pr-preview-${{ github.event.pull_request.number || inputs.pr_number }}
  cancel-in-progress: true

permissions:
  contents: read
  packages: write
  pull-requests: write

env:
  REGISTRY: ghcr.io
  IMAGE_NAME: ${{ github.repository }}

jobs:
  build:
    name: Build Preview Image
    if: >-
      (github.event.action == 'labeled' && github.event.label.name == 'deploy-preview') ||
      (github.event.action == 'synchronize' && contains(github.event.pull_request.labels.*.name, 'deploy-preview')) ||
      github.event_name == 'workflow_dispatch'
    runs-on: ubuntu-latest
    timeout-minutes: 15
    steps:
      - name: Resolve PR number
        id: pr
        run: |
          if [ "${{ github.event_name }}" = "workflow_dispatch" ]; then
            echo "number=${{ inputs.pr_number }}" >> "$GITHUB_OUTPUT"
          else
            echo "number=${{ github.event.pull_request.number }}" >> "$GITHUB_OUTPUT"
          fi

      - name: Checkout repository
        uses: actions/checkout@v6
        with:
          ref: ${{ github.event.pull_request.head.sha || format('refs/pull/{0}/head', inputs.pr_number) }}

      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v4

      - name: Log in to GitHub Container Registry
        uses: docker/login-action@v4
        with:
          registry: ${{ env.REGISTRY }}
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}

      - name: Build and push preview image
        uses: docker/build-push-action@v7
        with:
          context: .
          platforms: linux/amd64
          push: true
          tags: ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}:pr-${{ steps.pr.outputs.number }}
          labels: |
            org.opencontainers.image.source=https://github.com/${{ github.repository }}/pull/${{ steps.pr.outputs.number }}
            org.opencontainers.image.description=PR preview build for #${{ steps.pr.outputs.number }}
            org.opencontainers.image.revision=${{ github.sha }}
          cache-from: type=gha
          cache-to: type=gha,mode=max

      - name: Comment on PR
        uses: peter-evans/create-or-update-comment@v4
        with:
          issue-number: ${{ steps.pr.outputs.number }}
          body: |
            ### Preview image built and pushed

            ```
            docker pull ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}:pr-${{ steps.pr.outputs.number }}
            ```

            Built from ${{ github.sha }}
          comment-tag: pr-preview
```

- [ ] **Step 2: Validate YAML syntax**

Run: `python -c "import yaml; yaml.safe_load(open('.github/workflows/pr-preview.yml'))" && echo "YAML OK"`

Expected: `YAML OK`

If `actionlint` is available, also run:
```bash
actionlint .github/workflows/pr-preview.yml
```

- [ ] **Step 3: Commit the build job**

```bash
git add .github/workflows/pr-preview.yml
git commit -m "ci: add PR preview Docker build workflow"
```

---

### Task 2: Add cleanup job

**Files:**
- Modify: `.github/workflows/pr-preview.yml`

Add the `cleanup` job that deletes the preview image when the PR is closed (merged or abandoned). Uses the GitHub Packages REST API to find and delete the tagged version.

- [ ] **Step 1: Add the cleanup job to pr-preview.yml**

Append the following job after the `build` job in `.github/workflows/pr-preview.yml`:

```yaml
  cleanup:
    name: Cleanup Preview Image
    if: >-
      github.event.action == 'closed' &&
      contains(github.event.pull_request.labels.*.name, 'deploy-preview')
    runs-on: ubuntu-latest
    timeout-minutes: 5
    steps:
      - name: Delete preview image from GHCR
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          PR_TAG: pr-${{ github.event.pull_request.number }}
          OWNER: ${{ github.repository_owner }}
          PACKAGE: ${{ github.event.repository.name }}
        run: |
          VERSION_ID=$(gh api --paginate \
            "/users/$OWNER/packages/container/$PACKAGE/versions" \
            --jq ".[] | select(.metadata.container.tags[] == \"$PR_TAG\") | .id")

          if [ -n "$VERSION_ID" ]; then
            gh api --method DELETE \
              "/users/$OWNER/packages/container/$PACKAGE/versions/$VERSION_ID"
            echo "Deleted preview image $PR_TAG (version $VERSION_ID)"
          else
            echo "No preview image found for $PR_TAG — nothing to clean up"
          fi

      - name: Comment on PR
        if: success()
        uses: peter-evans/create-or-update-comment@v4
        with:
          issue-number: ${{ github.event.pull_request.number }}
          body: |
            Preview image `pr-${{ github.event.pull_request.number }}` has been cleaned up.
          comment-tag: pr-preview
```

- [ ] **Step 2: Validate the complete workflow file**

Run: `python -c "import yaml; yaml.safe_load(open('.github/workflows/pr-preview.yml'))" && echo "YAML OK"`

Expected: `YAML OK`

Also verify the complete file has exactly two jobs (`build` and `cleanup`) and the expected triggers:
```bash
python -c "
import yaml
with open('.github/workflows/pr-preview.yml') as f:
    wf = yaml.safe_load(f)
assert set(wf['jobs'].keys()) == {'build', 'cleanup'}, f'Expected build+cleanup jobs, got {set(wf[\"jobs\"].keys())}'
assert 'pull_request' in wf['on'], 'Missing pull_request trigger'
assert 'workflow_dispatch' in wf['on'], 'Missing workflow_dispatch trigger'
assert set(wf['on']['pull_request']['types']) == {'labeled', 'synchronize', 'closed'}, 'Wrong PR event types'
print('All checks passed')
"
```

Expected: `All checks passed`

- [ ] **Step 3: Commit the cleanup job**

```bash
git add .github/workflows/pr-preview.yml
git commit -m "ci: add cleanup job for PR preview images"
```

- [ ] **Step 4: Verify pre-commit hooks pass**

Run the project's pre-commit checks to make sure nothing is broken:

```bash
uv run ruff check src tests
uv run mypy src
uv run pytest --tb=short -q
```

Expected: All pass (this change is YAML-only, no Python changes).

---

## Testing Notes

This is a GitHub Actions workflow — it can only be fully tested by pushing to a branch and triggering the workflow on GitHub. To test end-to-end:

1. Push this branch and create a PR against `main`
2. Add the `deploy-preview` label to the PR
3. Verify the build runs and pushes `ghcr.io/dabigc/filtarr:pr-{number}`
4. Verify the sticky comment appears on the PR
5. Push another commit — verify the build re-runs and the comment updates
6. Close the PR — verify the cleanup job runs and the image is deleted
7. Test `workflow_dispatch` — go to Actions, select the workflow, enter a PR number, verify it builds

## Rollback

Delete the workflow file and force-push, or simply merge without the file. No other files are modified, so rollback is trivial.
