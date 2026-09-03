# Roadmap

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

## Done

### M0–M4 — platform, hosting, question banks as code (2026-08)

Versions pinned and current (Moodle 5.1.6, STACK 4.13.0, goemaxima
2026062900-1.2.0; `versions.yml` is the source of truth). Hosted go-live on a
Hetzner VM behind Caddy TLS at `oivus.pnr.iki.fi` (staging), provisioned
repeatably via hcloud + cloud-init, with a CI-gated deploy workflow. Server-side
daily DB dumps with rotation, macOS rsync pulls, and a documented restore drill.
Question banks as code: YAML sources compiled to Moodle XML, imported via CLI,
with the interpretation-scaffolding ladder (`stated` / `choice` / `none`) and a
CI-run fixture exam exercising every supported feature. Content authoring (the
old M4) lives in the separate `oivus-questions` repo and continues there.

### M5 — AI feedback pipeline (2026-09-01)

Formative essay drilling beyond STACK's numeric/CAS grading, with the Moodle
core AI subsystem as the provider-agnostic abstraction. The contributed
`aiprovider_claude` was surveyed and adopted rather than written
(`notes/aiprovider-survey.md`); it supports Moodle 5.0–5.2, so it puts no
pressure on the 5.2 migration. On top of it, `qtype_aitext_rubric` 0.1.1 (our
component, derived from `qtype_aitext`) plus the two behaviour forks and the
`local_aitextflags` companion give criterion-referenced structured feedback,
scaffold-then-fade levels, honest grading progression and flag-for-teacher —
all pinned in `versions.yml`, baked into the image, and smoke-tested. The
compiler emits aitext Moodle XML and `tools/qbank.sh aitest` exercises real
grading against golden fixtures. Verified end to end on staging 2026-09-01: a
student attempt was really AI-graded (3.0/5 on a deliberately partial answer),
the flag produced its notification row, and SMTP delivery succeeded. Design
rationale and the fork/companion split in `notes/LESSONS-LEARNED.md`.

### Question-bank capability (2026-08)

What a question can be made of, beyond the interpretation ladder M4 left in
place.

- **Drilling mode** (2026-08-31) as a property of the quiz rather than of the
  question, so one source serves both uses. `hints:` is an ordered ladder of
  prose blocks; only the `interactive` behaviour reads hints, so a hinted
  question renders byte-identically everywhere else, and under `interactive`
  the hint count is the try count. Quiz `grade: 0` makes a drill ungraded — no
  gradebook item, and no `marks` in the review lists, so a wrong answer is
  feedback rather than a score.
- **Figures** (2026-08-29): `figure.plot` for a graph STACK draws from the
  question's own variables, `figure.svg` for a static schematic embedded as
  base64 and served through `@@PLUGINFILE@@`. Alt text is mandatory and in
  Finnish; writing a figure into the prose instead is refused.
  `qbank/cli/figure-test.php` renders every figure question at every deployed
  seed. Prerequisite bug fixed on the way: STACK's `$CFG->dataroot/stack`
  directories are never created in server mode, so every CAS-generated plot
  was silently dropped on arrival.
- **Multiple choice** (2026-08-31) as `type: mcq` — a STACK `radio` over named
  options, one PRT node per option, so the attempt data records which
  distractor was chosen rather than just "wrong", and each option's `why:`
  names the misunderstanding back to the student. `shuffle:` and `show: k`
  randomise per variant. Quizzes take `grade:` and may draw random slots from
  the bank by `tags:` and/or `category:`.

Authoring reference in `qbank/README.md`; the platform facts behind these
choices in `notes/LESSONS-LEARNED.md`.

### M6 — Operational trust (2026-09-02)

- **Outgoing email** (2026-08-29): Mailpit capture for local/CI, `mail-init.sh`
  for idempotent mail configuration, staging relaying via smtp.iki.fi with no
  MTA on the VM. Real delivery verified; sender `pnr+noreply@iki.fi`.
- **Content provenance** (2026-08-29): the compiler stamps a `src-<sha>` tag
  per question and writes a build manifest (both commits, dirty flags, build
  time, source path and hash per question); the importer refuses a build made
  from a dirty tree unless the target is a throwaway site, and records each
  import run in `{config_plugins}`. The tag is excluded from the
  change-detection hash, so a new commit alone creates no question versions.
- **Backup security** (2026-09-01): repos are the source of truth and Moodle
  state is expendable, so the response to suspected compromise is
  rebuild-from-scratch, not forensics. MBP weeklies retained ~1 year; the API
  key confined to a dedicated Claude Platform workspace capped at 10 USD/month.
  Stance in `infra/BACKUP.md`.
- **Server hardening** (2026-09-02): HSTS (max-age 180 d, no
  includeSubDomains/preload, so the later domain move stays unconstrained);
  sshd tightened via a repo-held drop-in (`infra/hetzner/sshd/`) installed by
  `server-bootstrap.sh`, so the running VM converges through the normal deploy
  path. Monitoring: a daily dead-man check (`moodle-health.timer`, 07:00 UTC —
  disk usage, DB-dump freshness, the public login page through Caddy/TLS) pings
  healthchecks.io only when healthy; a missed ping emails. Daily granularity is
  the accepted detection bound. Runbook in `infra/hetzner/DEPLOY.md` §11.
- **SSO and localhost auth** (2026-09-02): Google SSO on staging via core
  `auth_oauth2`, converged by `auth-init.sh` from `.env`
  (`infra/hetzner/DEPLOY.md` §8; the Google Cloud side and account linking stay
  manual). Localhost is passwordless: on a loopback-only wwwroot `auth-init.sh`
  switches local accounts to `auth_none` and blanks their passwords;
  off-loopback it asserts the opposite posture, and `smoke-tests.sh` fails the
  deploy if any active account accepts an empty password. Apple SSO surveyed
  (`notes/sso-apple-survey.md`) and deferred: Moodle 5.1 core cannot complete
  an Apple login.
- **Content deploy** (2026-09-03): question content reaches staging by the same
  shape as the stack — a workflow in `oivus-questions` SSHes a content SHA to a
  second restricted key, forced to `deploy-content-cmd.sh`, which checks that
  SHA out in `/opt/oivus-questions` and runs `qbank.sh all` from
  `/opt/moodle-stack`. The question and figure tests are the gate, so the
  content repo needs no CI; the clean detached checkout means provenance is
  always exact. Both forced commands now share `~/.moodle-deploy.lock`, since a
  stack update and a content import drive the same running Moodle.
  `infra/hetzner/DEPLOY.md` §"Deploying question content".

## Open

- Full from-MBP disaster restore drill, when worth destroying the server.
- No figure question exists in real content yet — only fixtures.

## Deferred by decision

Recorded so they are not rediscovered as fresh ideas. Reasoning in
`notes/LESSONS-LEARNED.md` where it is not obvious.

- **aitext:** scaffold level 0 (labelled boxes), `double_run` and `fuzz`
  grading modes, dynamic per-student scaffold level, AI-assisted skeleton
  authoring. All wait on evidence from use.
- **aitext test coverage:** no Behat for the plugin's own student rendering
  (rubric checklist, scaffold levels); the student flag flow *is* covered by
  the companion's `tests/behat/flag.feature`. Prompt text lives in the rubric
  class rather than standalone template files — accepted, revisit if prompts
  start churning.
- **Drilling:** STACK's `[[hint]]` reveal blocks and the twin-question `drill:`
  route, pending evidence on whether `interactive`'s fixed try count reads as
  structure or as pressure. Genuine spaced repetition (Leitner, SM-2) is out of
  scope — not in Moodle core.
- **Figures:** in feedback rather than the stem (likely wanted eventually —
  showing the correct graph beside the student's misreading is exactly the
  pedagogy), interactive or manipulable figures, figures as answers.
- **MCQ:** the "least-wrong" `choice` rung (two independently graded inputs) —
  design it when the content plan asks for it.
- **Seeds:** questions used in drilling want roughly 8–12 deployed seeds rather
  than 3, so *"Try another question like this one"* stops repeating numbers.
  The cost is bulk-test time.

## M7 — Possible extensions (not planned yet)

- Access for other homeschool families: remove the staging
  `divertallemailsto` diversion, GDPR/privacy notice, account provisioning
  policy. **Before removing the divert**, give the admin account a real address
  — it is still the `admin@example.com` placeholder and teacher notifications
  reach a mailbox only because the divert catches them. (`supportemail` is
  already real.)
- Windows support for the no-terminal local setup (`tools/start.sh` stays
  POSIX; a Windows launcher is needed).
- Release-based deploy automation, remaining parts: GitHub release artefact
  with checksums, dedicated `deploy` user, root-owned update script with
  tight sudoers, automated rollback to last-known-good. Already done: the
  CI-gated staging deploy workflow (`deploy-staging.yml`), the content deploy
  workflow in `oivus-questions`, forced-command deploy keys on the admin
  account, and the committed update script
  (`infra/hetzner/scripts/server-update.sh`); see `infra/hetzner/DEPLOY.md`.
- Real production at `oivus.fi` (or similar; domain not yet registered) —
  `oivus.pnr.iki.fi` is the staging environment. Before production go-live:
  set `display_errors=0` in the Moodle image (deliberately 1 for now, to
  surface errors while staging), and parametrise the deploy hostname —
  currently hardcoded in `infra/hetzner/scripts/server-bootstrap.sh`,
  `infra/hetzner/caddy/Caddyfile` and the two `deploy-staging.yml` workflows,
  here and in `oivus-questions` (see `DEPLOY.md` §0) — so staging
  and production deploy from the same scripts, which also unhardcodes it
  for forks.
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
- Sign in with Apple: check MDL-70109 for a fix version at each Moodle bump;
  revisit triggers in `notes/sso-apple-survey.md`.

## Related documents

- `oivus-questions` (sibling repo) — question content; its `NOW.md` tracks
  content work.
- `moodle-qtype_aitext_rubric` and `moodle-local_aitextflags` (sibling
  repos) — the AI-graded question type and its companion plugin.
- `infra/hetzner/DEPLOY.md` — hosting runbook (provisioning, DNS, TLS, deploy).
- `infra/BACKUP.md` — backup/restore architecture and runbooks.
- `qbank/README.md` — question and quiz source format.
- `notes/` — lessons learned, the surveys behind deferred decisions, and the
  AI-grading walkthrough; see `notes/README.md`.
