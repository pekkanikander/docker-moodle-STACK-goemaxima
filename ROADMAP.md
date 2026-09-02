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
in `notes/`. Done 2026-09-01: both tasks are implemented, pinned, deployed to
staging and verified there.

- [x] TASK-01 (`notes/TASK-01-anthropic-aiprovider.md`): done 2026-08-26.
      Survey (`notes/aiprovider-survey.md`) found the contributed
      `aiprovider_claude` 1.0.4 usable; adopted, baked into the image like the
      STACK plugins, deployed to staging. It supports Moodle 5.0–5.2, so it
      puts no pressure on the 5.2 migration. API key added and provider
      enabled on staging via the admin UI 2026-08-26; fully done.
- [x] TASK-02 (`notes/TASK-02-aitext-drilling-extension.md`): done 2026-09-01.
      Essay-drilling extension on qtype_aitext — criterion-referenced
      structured feedback, scaffold-then-fade levels, honest grading
      progression, flag-for-teacher.
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
      (`pekkanikander/moodle-qtype_aitext_rubric`); it requires the two
      behaviour forks
      `pekkanikander/moodle-qbehaviour_{immediate,deferred}_for_aitext`,
      which drop upstream's `is_compatible_question()` pin to `qtype_aitext`
      (PRs open upstream). Deferred by decision (recorded in the task note):
      scaffold level 0, `double_run`/`fuzz`, dynamic scaffold level.
      Operationalised 2026-08-28: `versions.yml` pins the qtype release, the
      behaviour forks and the companion (the latter three by commit SHA, none
      tagged yet); all four are baked into the image and smoke-tested, and the
      dev overlay is no longer needed to run the extension. Released 0.1.1 on
      2026-09-01, rebased onto upstream main — which loosens the behaviour
      dependencies to `ANY_VERSION`, so the forks no longer have to track a
      qtype release number — and pinned here the same day. Bell-icon
      notification re-tested locally 2026-08-28: the flag-for-teacher
      notification and its email both work (email verified via the Mailpit
      capture). The student flag flow has Behat coverage in the companion's
      `tests/behat/flag.feature`; the fork's own student rendering (rubric
      checklist, scaffold levels) has none, which is accepted for now.
      Verified end to end on staging 2026-09-01, with the fixtures imported
      there: a student attempt was really AI-graded (3.0/5 on a deliberately
      partial answer), the flag produced its notification row, and SMTP
      delivery to `smtp.iki.fi` succeeded. The notification goes to the admin
      account, whose address is still the `admin@example.com` placeholder and
      only reaches a mailbox because `divertallemailsto` catches it — fix that
      together with M7's removal of the divert.

## Question-bank capability

What a question can be made of, beyond the interpretation ladder that M4 left
in place. Briefs in `notes/`.

- [x] TASK-03 (`notes/TASK-03-drilling-mode.md`): done 2026-08-31. Drilling
      mode, as a property of the quiz rather than of the question, so one
      source serves both uses and no question is forked into an exam copy and
      a drill copy that drift apart. `hints:` on a question source is an
      ordered ladder of prose blocks; only the `interactive` behaviour reads
      hints, so a hinted question renders byte-identically everywhere else,
      and under `interactive` the hint count is the try count. Quiz `grade: 0`
      (from TASK-06) makes a drill ungraded — no gradebook item, and no
      `marks` in the review lists, so a wrong answer is feedback rather than a
      score. Deliberately not done: STACK's `[[hint]]` reveal blocks and the
      twin-question `drill:` route (Feature 3 in the brief), pending evidence
      from use on whether `interactive`'s fixed try count reads as structure
      or as pressure; genuine spaced repetition (Leitner, SM-2), which is not
      in Moodle core and is out of scope.
- [x] TASK-04 (`notes/TASK-04-figures.md`): done 2026-08-29. Questions can
      carry a figure: `figure.plot` for a graph STACK draws from the
      question's own variables (no constant may be repeated from
      `variables:`, and axis ticks get a decimal comma via `PLOT_TERM_OPT`),
      `figure.svg` for a static schematic embedded into the question XML as
      base64 and served through `@@PLUGINFILE@@`. Alt text is mandatory and
      in Finnish; writing a figure into the prose instead is refused.
      `qbank/cli/figure-test.php` renders every figure question at every
      deployed seed and checks the images exist, wired into
      `tools/qbank.sh test`. Prerequisite bug fixed on the way: STACK's
      `$CFG->dataroot/stack` directories are never created in server mode, so
      every CAS-generated plot was silently dropped on arrival;
      `stack-init.sh` creates them and clears the CAS cache, and
      `smoke-tests.sh` asserts they are writable.
- [x] TASK-06 (`notes/TASK-06-mcq.md`): done 2026-08-31. Multiple-choice
      questions as `type: mcq` — a STACK `radio` over named options, one PRT
      node per option, so the attempt data records which distractor was
      chosen rather than just "wrong", and each option's `why:` names the
      misunderstanding back to the student. `shuffle:` (default true) and
      `show: k` (draw k−1 distractors, correct one always shown) randomise
      per variant; both require deployed seeds, and the question note records
      the shown keys in shown order so a variant is recoverable from its
      seed. Quizzes take `grade:` (0 = ungraded, no gradebook item) and may
      draw random slots from the bank by `tags:` and/or `category:`, with the
      pool checked against both the compiled tree and the actual bank.

## M6 — Operational trust

Before real attempt history accumulates (drilling starts after the current
content-creation phase, so this fits in the next few weeks):

- [x] Outgoing email, done 2026-08-29: Mailpit capture for local/CI (pinned
      service, smoke-tested mail round-trip), `mail-init.sh` for idempotent
      mail configuration, staging relaying via smtp.iki.fi (no MTA on the
      VM, no Mailpit there either; runbook in `infra/hetzner/DEPLOY.md`).
      Real delivery verified; sender `pnr+noreply@iki.fi`, and all staging
      mail is diverted to `pnr+oivus@iki.fi` via `divertallemailsto`
      (admin UI) — remove the diversion before opening access to others.
- [x] TASK-05 (`notes/TASK-05-content-provenance.md`): done 2026-08-29.
      Question versions are bound to the content-repo commit that produced
      them: the compiler stamps a `src-<sha>` tag per question and writes a
      build manifest (both commits, dirty flags, build time, source path and
      hash per question); the importer refuses a build made from a dirty tree
      unless the target is a throwaway site, and records each import run in
      `{config_plugins}`. The tag is excluded from the change-detection hash,
      so a new commit alone creates no question versions (tested in
      `qbank/tests/` and end to end in CI).
- [x] Backup security: decided 2026-09-01, no session needed. The GitHub
      repos are the source of truth and Moodle state (attempt history
      included) is expendable, so the response to suspected compromise is
      rebuild-from-scratch plus a weekly dump predating the suspicion, not
      forensics; stance recorded in `infra/BACKUP.md`. Kept: MBP weeklies
      retained ~1 year (53), a post-restore checklist in `infra/BACKUP.md`,
      and the API key confined to a dedicated Claude Platform workspace
      capped at 10 USD/month. Rejected as disproportionate: append-only
      archives beyond that, baselining/diffing dumps.
- [x] Server hardening leftovers: done 2026-09-02. HSTS enabled (max-age
      180 d, no includeSubDomains/preload, so the later domain move stays
      unconstrained). sshd tightened (`MaxAuthTries 3`, `LoginGraceTime 20`);
      the hardening drop-in moved from cloud-init into the repo
      (`infra/hetzner/sshd/`), installed by `server-bootstrap.sh` so the
      running VM converges via the normal deploy path. fail2ban skipped by
      decision: with key-only auth on a firewalled non-default port it is
      log-noise reduction only, at the cost of a daemon plus its own nftables
      machinery on a host with no local firewall; the built-in replacement is
      OpenSSH `PerSourcePenalties` (see Version watch). Monitoring: a daily
      dead-man check (`moodle-health.timer`, 07:00 UTC — disk usage on `/`
      and `/srv/moodle-persistent`, DB-dump freshness, the public login page
      through Caddy/TLS) pings healthchecks.io only when healthy; a missed
      ping emails. Daily granularity is the accepted detection bound;
      minutes-level external uptime monitoring deferred to M7. Runbook in
      `infra/hetzner/DEPLOY.md` §11.
- [x] TASK-07 (`notes/TASK-07-sso-and-localhost-auth.md`): done 2026-09-02.
      Google SSO on staging via core `auth_oauth2`: `auth-init.sh` converges
      the issuer from the `MOODLE_GOOGLE_OAUTH_CLIENT_*` variables in `.env`
      (runbook in `infra/hetzner/DEPLOY.md` §8; the Google Cloud side and
      account linking stay manual), and SSO-only accounts carry no password.
      Localhost is passwordless: on a loopback-only wwwroot `auth-init.sh`
      switches local accounts to `auth_none` and blanks their passwords;
      off-loopback it asserts the opposite posture, and `smoke-tests.sh`
      fails the deploy if any active account accepts an empty password.
      `[::1]` published ports added for `moodle` and `mailpit` so IPv6
      loopback works too. Apple SSO surveyed (`notes/sso-apple-survey.md`)
      and deferred: Moodle 5.1 core cannot complete an Apple login.
- [ ] Full from-MBP disaster restore drill, when worth destroying the server.

## M7 — Possible extensions (not planned yet)

- Access for other homeschool families: remove the staging
  `divertallemailsto` diversion (the admin account and `supportemail` both
  carry real addresses as of 2026-09-01, so teacher notifications survive the
  removal), GDPR/privacy notice, account provisioning policy.
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
- Fine-grained external HTTP uptime monitoring (minutes-level checks, e.g.
  UptimeRobot); the daily dead-man ping only bounds outages to a day.

## Version watch

- STACK 4.13.1 needs stackmaxima 2026080600; bump when goemaxima ships a
  matching release (see `versions.yml`).
- OpenSSH `PerSourcePenalties` (built-in auth-failure throttling, the
  fail2ban replacement) needs OpenSSH ≥ 9.8; Ubuntu 24.04 ships 9.6. Enable
  in `infra/hetzner/sshd/99-hardening.conf` when available.

## Related documents

- `oivus-questions` (sibling repo) — question content; its `NOW.md` tracks
  content work.
- `moodle-qtype_aitext_rubric` and `moodle-local_aitextflags` (sibling
  repos) — the TASK-02 question type and its companion plugin.
- `infra/hetzner/DEPLOY.md` — hosting runbook (provisioning, DNS, TLS, deploy).
- `infra/BACKUP.md` — backup/restore architecture and runbooks.
- `notes/` — task briefs (TASK-01 to TASK-07, all done) and the survey and
  architecture notes behind them.
