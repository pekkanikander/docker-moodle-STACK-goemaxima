# Roadmap (2026-08)

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

## Done — M0–M4 (2026-08)

Versions pinned and current (Moodle 5.1.6, STACK 4.13.0, goemaxima
2026062900-1.2.0; `versions.yml` is the source of truth). Hosted go-live on a
Hetzner VM behind Caddy TLS at `oivus.pnr.iki.fi` (staging), provisioned
repeatably via hcloud + cloud-init, with a CI-gated deploy workflow. Server-side
daily DB dumps with rotation, macOS rsync pulls, and a documented restore drill.
Question banks as code: YAML sources compiled to Moodle XML, imported via CLI,
with the interpretation-scaffolding ladder (`stated` / `choice` / `none`) and a
CI-run fixture exam exercising every supported feature. Content authoring (the
old M4) lives in the separate `oivus-questions` repo and continues there — a few
weeks of content creation remain before actual drilling starts; the GUI is
currently being tested with the student.

## M5 — AI feedback pipeline

Extend beyond STACK's numeric/CAS grading to formative essay drilling, using
the Moodle core AI subsystem as the provider-agnostic abstraction. Task briefs
in `notes/`; feature work done locally, operationalisation pending.

- [x] TASK-01 (`notes/TASK-01-anthropic-aiprovider.md`): done 2026-08-26.
      Survey (`notes/aiprovider-survey.md`) found the contributed
      `aiprovider_claude` 1.0.4 usable; adopted, baked into the image like the
      STACK plugins, deployed to staging. It supports Moodle 5.0–5.2, so it
      puts no pressure on the 5.2 migration. API key added and provider
      enabled on staging via the admin UI 2026-08-26; fully done.
- [ ] TASK-02 (`notes/TASK-02-aitext-drilling-extension.md`): essay-drilling
      extension on qtype_aitext — criterion-referenced structured feedback,
      scaffold-then-fade levels, honest grading progression, flag-for-teacher.
      Milestone 1 done 2026-08-26: vanilla qtype_aitext 2.1.0 (+ its two
      behaviour adapter plugins) baked into the image, pinned by commit SHA
      (2.1.0 untagged upstream); architecture note in
      `notes/aitext-extension-architecture.md`. Milestone 2 done 2026-08-27:
      all five features implemented for the agreed scope on the fork and
      companion (`pekkanikander/moodle-local_aitextflags`), running locally
      via the dev overlay (`docker-compose.aitext-dev.yml`); the qbank
      compiler emits aitext Moodle XML and a golden-test harness
      (`tools/qbank.sh aitest`) exercises real grading. Hardening done
      2026-08-28 (PHPUnit both repos, moodle-cs clean, flags-table backup
      decision recorded in the companion README). The fork has since been
      renamed into a separate component, `qtype_aitext_rubric`
      (`pekkanikander/moodle-qtype_aitext_rubric`), released as 0.1.0; it
      requires the two behaviour forks
      `pekkanikander/moodle-qbehaviour_{immediate,deferred}_for_aitext`.
      Deferred by decision (recorded in the task note): scaffold level 0,
      `double_run`/`fuzz`, dynamic scaffold level. Remaining to close:
      operationalisation — repoint `versions.yml` to the 0.1.0 release and
      the behaviour forks, bake the companion into the image, drop the dev
      overlay from the deploy path. Until then CI and the server run the
      upstream `qtype_aitext`, and the compiler's `aitext_rubric` XML will
      not import there.

## M6 — Operational trust

Before real attempt history accumulates (drilling starts after the current
content-creation phase, so this fits in the next few weeks):

- [ ] Backup security session: a compromised server can poison the dumps the
      MBP pulls, and a restored dump faithfully restores attacker state.
      Topics: append-only MBP copies, baselining/diffing security-relevant
      tables between dumps, post-restore audit checklist. Interim stance in
      `infra/BACKUP.md` (prefer an older weekly, audit users and tokens).
- [ ] Server hardening leftovers: fail2ban (or equivalent), minimal monitoring
      (disk-usage threshold, external uptime check), HSTS once stable.
- [ ] Full from-MBP disaster restore drill, when worth destroying the server.

## M7 — Possible extensions (not planned yet)

- Access for other homeschool families: outbound email, GDPR/privacy notice,
  account provisioning policy.
- Windows support for the no-terminal local setup (`tools/start.sh` stays
  POSIX; a Windows launcher is needed).
- Release-based deploy automation, remaining parts: GitHub release artefact
  with checksums, dedicated `deploy` user, root-owned update script with
  tight sudoers, automated rollback to last-known-good. Already done: the
  CI-gated staging deploy workflow (`deploy-staging.yml`), a forced-command
  deploy key on the admin account, and the committed update script
  (`infra/hetzner/scripts/server-update.sh`); see `infra/hetzner/DEPLOY.md`.
- Real production at `oivus.fi` (or similar; domain not yet registered) —
  `oivus.pnr.iki.fi` is the staging environment. Before production go-live:
  set `display_errors=0` in the Moodle image (deliberately 1 for now, to
  surface errors while staging).
- Moodle 5.2 line migration (no pressure from the AI side: the adopted
  provider supports 5.0–5.2).
- Renovate (or similar) update PRs, grouped and CI-gated.

## Version watch

- STACK 4.13.1 needs stackmaxima 2026080600; bump when goemaxima ships a
  matching release (see `versions.yml`).

## Related documents

- `oivus-questions` (sibling repo) — question content; its `NOW.md` tracks
  content work.
- `moodle-qtype_aitext_rubric` and `moodle-local_aitextflags` (sibling
  repos) — the TASK-02 question type and its companion plugin.
- `infra/hetzner/DEPLOY.md` — hosting runbook (provisioning, DNS, TLS, deploy).
- `infra/BACKUP.md` — backup/restore architecture and runbooks.
- `notes/` — task briefs for upcoming work (TASK-01, TASK-02).
