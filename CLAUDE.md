# CLAUDE.md

Purpose: guide LLM/coding agents working in this repo.

## Project goal
Build an OSS Docker Compose setup for Moodle + MariaDB + goemaxima (STACK), with pinned versions, CI validation, and safe updates.
The setup serves exam drilling and question-interpretation training for a homeschooled learner (Finnish peruskoulu physics/chemistry, later maths); see `ROADMAP.md`.

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
- `tools/start.sh` for one-shot local setup/start; `Setup Moodle.app` (built
  from `tools/launcher/setup-moodle.applescript`) is its double-click launcher.
- `docker/moodle/Dockerfile` for the custom Moodle build (Moodle + STACK).
- `qbank/` for the question-bank machinery: `compiler/` (YAML → Moodle XML),
  `cli/` (import and quiz build, run inside the `moodle` container),
  `fixtures/` (test content), and `README.md` for the source format.
- `tools/qbank.sh` as the entry point; `docker/qbank-tools/` builds the compiler
  image. Question content lives in a separate repo, found via `QBANK_CONTENT_DIR`.
- `.github/workflows/ci.yml` for end-to-end CI.
- `README.md` for quickstart and update policy.
- `ROADMAP.md` for milestones and current priorities.
- `tools/act-ci.sh` for local CI via `act`.
- `notes/` for research notes behind version and design decisions.
- `infra/hetzner/` for VM provisioning (cloud-init, hcloud helper); runbook in `infra/hetzner/DEPLOY.md`.
- `infra/BACKUP.md` for the backup/restore architecture; `infra/mbp/` holds the
  master copies deployed to `~/Sites/oivus.pnr.iki.fi` by `infra/mbp/deploy.sh`.

## Workflow guidance
- We are in an early pre-alpha stage. Prefer regenerating everything from scratch. There are no precious data, yet.
- When bumping versions, update `versions.yml` and `compatibility.yml` together.
- When changing Moodle/STACK versions, also update the Dockerfile inputs and checksums.
- Keep init scripts usable both locally and in CI.
- Document any manual steps in `README.md` if automation is not feasible.

## CI expectations
- CI must run the full flow: compose up, `moodle-init.sh`, `stack-init.sh`, smoke tests, then cleanup.
- Always capture logs on failure.
