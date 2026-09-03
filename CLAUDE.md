# CLAUDE.md

Purpose: guide LLM/coding agents working in this repo.

## Project goal
Build an OSS Docker Compose setup for Moodle + MariaDB + goemaxima (STACK), with pinned versions, CI validation, and safe updates.
The setup serves exam drilling and question-interpretation training for a homeschooled learner (Finnish peruskoulu physics/chemistry, later maths); see `ROADMAP.md`.

## Core rules
- Prefer pinned tags (optionally digests); avoid `latest`.
- Keep `docker compose up -d` reproducible.
- No secrets in the repo; use `.env.example` and GitHub Actions secrets.
  The Anthropic API key and SMTP credentials are set only via the Moodle admin UI, never in code or env.
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
- `docker/moodle/Dockerfile` for the custom Moodle build (Moodle + STACK +
  `aiprovider_claude` + `qtype_aitext_rubric` + `local_aitextflags`, all
  pinned in `versions.yml`).
- `qbank/` for the question-bank machinery: `compiler/` (YAML → Moodle XML),
  `cli/` (import and quiz build, run inside the `moodle` container),
  `fixtures/` (test content), `tests/` (compiler tests, run in the
  `qbank-tools` container), and `README.md` for the source format and the
  provenance the compiler stamps on every question.
- `tools/qbank.sh` as the entry point; `docker/qbank-tools/` builds the compiler
  image. Question content lives in a separate repo, found via `QBANK_CONTENT_DIR`.
- Sibling repos, checked out next to this one: `oivus-questions` (question
  content), `moodle-qtype_aitext_rubric` (our qtype, forked from
  marcusgreen/moodle-qtype_aitext) and `moodle-local_aitextflags` (companion
  plugin), the latter two for the AI essay-drilling extension.
- `.github/workflows/ci.yml` for end-to-end CI.
- `README.md` for quickstart and update policy.
- `ROADMAP.md` for milestones and current priorities.
- `tools/act-ci.sh` for local CI via `act`.
- `notes/` for `LESSONS-LEARNED.md` (decisions with their rejected
  alternatives, and platform facts verified against the pinned tuple), the
  surveys behind deferred decisions, and the AI-grading walkthrough. Task
  briefs live here while their work is in flight and are retired into
  `LESSONS-LEARNED.md` at release; see `notes/README.md`.
- `infra/hetzner/` for VM provisioning (cloud-init, hcloud helper); runbook in `infra/hetzner/DEPLOY.md`.
- `infra/BACKUP.md` for the backup/restore architecture; `infra/mbp/` holds the
  master copies deployed to `~/Sites/oivus.pnr.iki.fi` by `infra/mbp/deploy.sh`.

## Workflow guidance
- We are in a pre-alpha stage. Prefer regenerating everything from scratch. There are no precious data, yet.
- When bumping versions, update `versions.yml` and `compatibility.yml` together.
- When changing Moodle/STACK versions, also update the Dockerfile inputs and checksums.
- Keep init scripts usable both locally and in CI.
- Document any manual steps in `README.md` if automation is not feasible.

## CI expectations
- CI must run the full flow: compose up, `moodle-init.sh`, `stack-init.sh`, smoke tests, then cleanup.
- Always capture logs on failure.
