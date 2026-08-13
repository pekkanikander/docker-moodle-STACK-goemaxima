# CLAUDE.md

Purpose: guide LLM/coding agents working in this repo.

## Project goal
Build an OSS Docker Compose setup for Moodle + MariaDB + goemaxima (STACK), with pinned versions, CI validation, and safe updates.

## Core rules
- Prefer pinned tags (optionally digests); avoid `latest`.
- Keep `docker compose up -d` reproducible.
- No secrets in the repo; use `.env.example` and GitHub Actions secrets.
- Fail fast; do not mask errors in scripts or CI.
- Build a custom Moodle image from a pinned PHP base + Moodle release tarball checksum.
- Keep the Moodle code tree read-only at runtime as a goal until validated.
- Keep goemaxima internal-only (no host port exposure).
- Keep MariaDB internal-only (no host port exposure).
- Generate DB credentials at startup into a named secrets volume; use `*_FILE` env vars.

## Key files (may change, please update if you detect deviations)
- `docker-compose.yml` for services, volumes, ports, healthchecks.
- `versions.yml` as the single source of truth for versions.
- `compatibility.yml` for supported tuples and notes.
- `init/scripts/*.sh` for bootstrap, install, config, and smoke tests.
- `docker/moodle/Dockerfile` for the custom Moodle build (Moodle + STACK).
- `.github/workflows/ci.yml` for end-to-end CI.
- `README.md` for quickstart and update policy.
- `tools/act-ci.sh` for local CI via `act`.

## Workflow guidance
- We are in an early pre-alpha stage. Prefer regenerating everything from scratch. There are no precious data, yet.
- When bumping versions, update `versions.yml` and `compatibility.yml` together.
- When changing Moodle/STACK versions, also update the Dockerfile inputs and checksums.
- Keep init scripts usable both locally and in CI.
- Document any manual steps in `README.md` if automation is not feasible.

## CI expectations
- CI must run the full flow: compose up, `moodle-init.sh`, `stack-init.sh`, smoke tests, then cleanup.
- Always capture logs on failure.
