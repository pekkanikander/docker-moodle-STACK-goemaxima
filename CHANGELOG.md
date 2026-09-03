# Changelog

Notable changes per release. Versioning follows [SemVer](https://semver.org/);
pre-1.0, minor versions may break anything.

## [0.2.0] — 2026-09-02

From proof of concept to a system running a real (staging) site.

### Local setup
- Zero-input install: `tools/start.sh`, wrapped by the double-clickable
  **Setup Moodle** app (macOS) with a progress window.
- Persistent data as bind mounts under `MOODLE_PERSISTENT_ROOT`;
  HTTP bound to loopback only (v4 and v6);
  custom MariaDB image with fixed UID/GID.
- Passwordless login on loopback-only instances;
  smoke tests assert the posture and refuse it anywhere else.
- Automatic language packs (`MOODLE_LANGPACKS`), browser language wins.
- Mailpit mail capture for local and CI runs.

### Hosting (Hetzner staging, `oivus.pnr.iki.fi`)
- Repeatable provisioning: hcloud + cloud-init, Caddy TLS, runbook in
  `infra/hetzner/DEPLOY.md`.
- CI-gated deploy workflow; server updates + site config, not just code.
- Daily DB dumps with rotation, offsite pulls to a Mac, restore runbooks
  (`infra/BACKUP.md`), and a recorded compromise-response stance.
- Hardening and monitoring: sshd tightening, HSTS, daily dead-man health
  check pinging healthchecks.io.
- Google SSO via core `auth_oauth2`, issuer converged from `.env`;
  SSO-only accounts carry no password.
- Outgoing mail via a real SMTP relay; per-environment page tint and badge.

### Questions as code (`qbank/`)
- YAML → Moodle XML compiler, CLI import and quiz build, per-question tests
  through Maxima, all run via `tools/qbank.sh` (one run at a time, locked).
- Question features:
  - interpretation-scaffold ladder,
  - hint ladders for drilling (quiz-level, not question-level),
  - figures (STACK-drawn plots and static SVG, alt text mandatory),
  - MCQ with per-distractor tracking,
  - ungraded quizzes,
  - random slots by tag/category.
- Provenance:
  - every question version is bound to the content-repo commit that produced it;
  - imports from a dirty tree are refused outside throwaway sites.
- Golden-test harness for AI-graded questions (`tools/qbank.sh aitest`).

### AI grading
- `aiprovider_claude` 1.0.4 baked into the image (Moodle core AI subsystem;
  API key only ever in the Moodle admin UI).
- `qtype_aitext_rubric` 0.1.1 — criterion-referenced essay feedback with
  fading scaffolds and flag-for-teacher — plus its behaviour adapters and
  the `local_aitextflags` companion, all pinned.

### Versions
- Moodle 5.1.6, STACK 4.13.0, goemaxima 2026062900-1.2.0, MariaDB 11.4
  (tuple `moodle51-stack4130-maxima2026062900-1.2.0`).

## [0.1] — 2026-01-08

Proof of concept: Docker Compose for Moodle + MariaDB + goemaxima; custom
Moodle image with STACK and its behaviour plugins installed from pinned,
checksummed archives; generated DB secrets; install and STACK init scripts;
smoke tests; CI running the full flow.

[0.2.0]: https://github.com/pekkanikander/docker-moodle-STACK-goemaxima/compare/v0.1...v0.2.0
[0.1]: https://github.com/pekkanikander/docker-moodle-STACK-goemaxima/releases/tag/v0.1
