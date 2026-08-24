# Roadmap (provisional, 2026-08)

## Purpose

Run a low-cost, hosted Moodle + STACK + Maxima instance for **exam drilling and
question-interpretation training** for a homeschooled learner following the Finnish
peruskoulu curriculum (physics and chemistry first, mathematics later).
Teaching content per se comes from elsewhere; this system provides randomised,
automatically assessed practice and exam simulation.
Public access for other Finnish homeschoolers is a possible later extension.

Question-design principle: exam questions often require inferring the *intended*
neurotypical reading (e.g. "distance" = straight line or along a route?). Question
banks should train this explicitly, e.g. multipart questions whose first step is an
interpretation choice, with the scaffolding faded over time.

## M0 — Versions and repo hygiene (done 2026-08)

- [x] Bump to Moodle 5.1.6 (Aug 2026 security release), STACK 4.13.0,
      goemaxima 2026062900-1.2.0; refresh behaviour-plugin tags and fill the
      missing checksums in `versions.yml`. (STACK 4.13.1 needs stackmaxima
      2026080600, for which no goemaxima release exists yet; see `versions.yml`.)
- Policy: stay on the Moodle 5.1 line for now; evaluate 5.2 later as a separate
  update PR. MariaDB 11.4 (LTS to 2029) and PHP 8.3 stay.

## M1 — Hosted go-live

- [x] Fix provisioning defects: `hcloud-create.sh` missing `--image`/`--type`,
      firewall never created, `docker-compose-plugin` not in Ubuntu repos.
- [x] Caddyfile and on-VM runtime layout (`/opt/moodle-stack`), documented
      (`infra/hetzner/caddy/Caddyfile`, `infra/hetzner/DEPLOY.md`).
- [x] Provision VM (hcloud + cloud-init, repeatable via `RECREATE=1`), DNS
      A+AAAA for `oivus.pnr.iki.fi` (zone `pnr.iki.fi` at easyDNS), TLS via
      Caddy. (done 2026-08-14)
- [x] Documented deploy: cloud-init bootstraps repo clone, Caddy vhost and
      image build; manual steps are `.env` secrets + init scripts (DEPLOY.md).
      Phase 6 (release-artefact automation, deploy user, forced-command key) is
      **deferred** until an update cadence justifies it.
- [x] Site posture at go-live: guest login hidden (set by `moodle-init.sh`),
      self-registration at Moodle's default (off), accounts created manually,
      minimal plugin surface. Outbound email remains out of scope while there
      is a single learner (admin resets passwords by hand).

## M2 — Backups and restore drill (Phase 5)

Before real attempt history accumulates:
- [x] Server-side daily DB dumps with rotation. (2026-08-14)
- [x] macOS rsync pull of moodledata + dumps. (2026-08-14)
- [x] One successful, documented restore drill. (2026-08-14: server-side
      `restore-db.sh` + smoke tests green; full from-MBP disaster drill
      deferred until worth destroying the server for.)

## M3 — Question banks as code

- [x] Keep question banks in git and import them via Moodle CLI. Questions are
      authored as YAML and compiled to Moodle XML rather than hand-written as
      XML; see `qbank/README.md`.
- [x] LLM-assisted authoring reviewed as diffs: the content lives in a separate
      repo, located by `QBANK_CONTENT_DIR`, never by an assumed path.
- [x] Interpretation-scaffolded question templates (see purpose above), as a
      `stated` / `choice` / `none` ladder.
- [x] A fixture exam (`qbank/fixtures/`) exercising every supported feature,
      run end to end by CI.
With questions in git, the DB stays near-disposable until attempt history matters.

## M4 — Content, in their own repo (or repos)

- [ ] Peruskoulu physics drilling sets (national exam level).
- [ ] Peruskoulu chemistry drilling sets (national exam level).
- [ ] Later: mathematics, incl. geometry via JSXGraph if feasible.

## M5 — Possible extensions (not planned yet)

- Access for other homeschool families: outbound email, GDPR/privacy notice,
  account provisioning policy.
- Windows support for the no-terminal local setup (`tools/start.sh` stays
  POSIX; a Windows launcher is needed).
- Release-based deploy automation: GitHub release artefact with checksums,
  `deploy` user with a forced-command SSH key, root-owned update script with
  tight sudoers, rollback to last-known-good. Deferred until the update
  cadence justifies it; until then, `infra/hetzner/DEPLOY.md` documents the
  manual deploy.
- Server hardening leftovers: fail2ban (or equivalent), HSTS once stable,
  minimal monitoring (disk-usage threshold, external uptime check).
- Real production at `oivus.fi` (or similar; domain not yet registered) —
  `oivus.pnr.iki.fi` is the staging environment. Before production go-live:
  set `display_errors=0` in the Moodle image (deliberately 1 for now, to
  surface errors while staging).
- Moodle 5.2 line migration.
- Renovate (or similar) update PRs, grouped and CI-gated.

## Planned: backup security session

A dedicated planning session on backups after a server compromise: a
compromised server can poison the dumps the MBP pulls, and a restored dump
faithfully restores attacker state (admin accounts, web-service tokens,
altered settings, uploaded files). Topics: making the MBP copies
append-only against the server, baselining/diffing security-relevant
tables between dumps, and a post-restore audit checklist. Interim stance
in `infra/BACKUP.md` (prefer an older weekly, audit users and tokens).

## Related documents

- `infra/hetzner/DEPLOY.md` — hosting runbook (provisioning, DNS, TLS, deploy).
- `infra/BACKUP.md` — backup/restore architecture and runbooks.
- `notes/` — research notes behind version and design decisions.
