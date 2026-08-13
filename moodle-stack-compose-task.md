# Project: moodle-stack-compose

Audience: LLM within Cursor (e.g. OpenAI Codex ChatGPT running as a Cursor/VSCode extension)

Goal: Create an OSS GitHub project that provides an **as-simple-as-possible**
Docker Compose setup for **Moodle + MariaDB + goemaxima**,
with **strong CI** and **semi-automated, safe version updates** to reduce compatibility churn.

The exact, modern versions of the modules shall be selected to follow the best community practices of 2026.

Prototype on macOS using OrbStack.

Focus on reproducible pinned versions and CI-validated update PRs.

Non-goals (for this phase):
- “always-latest” auto-updates without CI gating
- TLS (will be implemented separately, probably as a Caddy-based solution)

Research decisions (2026-01-02):
- There is no Docker Official Image for Moodle; prefer a custom Moodle runtime image.
- Build Moodle from a pinned `php:<version>-apache` base (optionally with digest) plus a Moodle release tarball with checksum.
- Keep the Moodle code tree read-only at runtime as a goal; only enforce after validation.
- Install STACK at image build time from pinned downloads with checksums; run Moodle CLI upgrade at first start.
- goemaxima endpoint default: `http://maxima:8080/goemaxima` (fallback `/maxima`).
- goemaxima must be internal-only (no host port exposure).
- MariaDB must be internal-only (no host port exposure).
- Target the latest supported Moodle line (not LTS).
- Initial proposed tuple:
  - Moodle 5.1.1 tarball + SHA256 from `https://packaging.moodle.org/stable501/moodle-5.1.1.tgz`
  - PHP base `php:8.3-apache`
  - MariaDB `mariadb:11.4`
  - STACK 4.11.0 (plugin version 2025102100) + companion behaviours (pinned tags)
  - goemaxima `mathinstitut/goemaxima:2025102100-1.2.0`
- STACK plugin ZIP downloads may be blocked; prefer a pinned Git commit/archive with a recorded SHA256 if needed.

---

## 0) General constraints / operating rules

1. Prefer **pinned versions** over `latest`. Use **tags** and optionally **image digests**.
2. All changes must keep `docker compose up -d` reproducible.
3. CI must validate the whole integration: Moodle starts, DB works, goemaxima is reachable, and STACK is installed/configured.
4. No secrets committed. Use `.env.example` and GitHub Actions secrets only where required.
5. Keep the repo minimal, documented, and easy to maintain.
6. Prefer fail fast to attempts of recovering from errors.
7. If you want to search the Internet, e.g. to determine the best current community practise,
   but your configuration does not allow that, you can create questions (as separate .md files)
   that the user can ask a separate LLM agent, with Internet access, to answer.
8. Prefer a custom Moodle image built from pinned base image + Moodle release tarball with checksum.
9. Keep the Moodle code tree read-only at runtime as a goal until validated.
10. Expose goemaxima only on an internal Docker network (no host port).
11. Expose MariaDB only on an internal Docker network (no host port).
12. Generate DB credentials at startup into a named secrets volume; use `*_FILE` env vars.
13. Target the latest supported Moodle line (currently 5.1.x), pinned to a specific point release.

---

## 1) Repository skeleton

Create, for example, the following structure:
```
.github/
└── workflows/
│   └── ci.yml
|   └── update-versions.yml
docker/
└── moodle/
    └── Dockerfile
init/
│   └── scripts/
│       └── moodle-init.sh
│       └── stack-install.sh
│       └── stack-configure.sh
│       └── smoke-tests.sh
│       └── wait-for-http.sh
tools/
└── act-ci.sh
.env.example
LICENSE
README.md
docker-compose.yml
compatibility.yml
versions.yml
```
Notes:
- `versions.yml` = pinned component versions.
- `compatibility.yml` = explicit mapping/rules for “what combinations are supported”.
- `init/scripts/*` = one-shot bootstrap and verification scripts called in CI and optionally by users.
- `docker/moodle/Dockerfile` = pinned, reproducible Moodle image build (Moodle + STACK).
- `tools/act-ci.sh` = helper to run CI locally via `act`.

If reasonable, simplify the repo structure, leaving out files that turn out
unnecessary or whose overall benefit is tiny.

## 2) Define the version model (versions.yml, compatibility.yml)

### 2.1 versions.yml (single source of truth)

Add keys like:

- `moodle_base_image`: `php:<version>-apache` (optionally pinned with a digest)
- `moodle_release_url`: `<moodle release tarball URL>`
- `moodle_release_sha256`: `<sha256>`
- `mariadb_image`: `<tbd>/mariadb:<tag>`
- `goemaxima_image`: `mathinstitut/goemaxima:<tag>`
- `stack_plugin_source`: `url` or `git`
- `stack_plugin_url`: `<STACK plugin zip URL>` (if source is `url`)
- `stack_plugin_git`: `<repo>@<commit>` (if source is `git`)
- `stack_plugin_sha256`: `<sha256>`
- `stack_plugin_version`: `<version>`
- `stack_behaviour_plugins`: (if needed)
- `stack_deps_versions`: (if needed)
- `compose_stack_id`: e.g. `moodle45-stackX-maximaY`

### 2.1a Initial pinned tuple (proposed)
- Moodle 5.1.1 tarball: `https://packaging.moodle.org/stable501/moodle-5.1.1.tgz`
- Moodle SHA256: `https://packaging.moodle.org/stable501/moodle-5.1.1.tgz.sha256`
- PHP base: `php:8.3-apache`
- MariaDB: `mariadb:11.4`
- STACK: 4.11.0 (plugin version 2025102100) + companion behaviours (pinned tags)
- goemaxima: `mathinstitut/goemaxima:2025102100-1.2.0`

### 2.2 compatibility.yml (rules + supported tuples)
Define at least one supported tuple initially:

- Moodle major/minor line (latest supported line, not LTS)
- STACK version expected to work with that Moodle line
- goemaxima tag expected to match STACK/Maxima expectations
- MariaDB version known compatible with the chosen Moodle/PHP line

Include comments explaining:
- why tags are pinned
- how to bump safely
- known breaking edges (Moodle major bump, PHP compatibility, STACK/goemaxima alignment)

---

## 3) Docker Compose baseline + custom Moodle image

### 3.0 Moodle image build (docker/moodle/Dockerfile)
- Build from a pinned `php:<version>-apache` base image (optionally with digest).
- Download Moodle release tarball using `moodle_release_url`, verify `moodle_release_sha256`, then extract into the web root.
- Install required PHP extensions per Moodle requirements (ensure `mbstring` for STACK).
- Download STACK plugin from a pinned source (prefer GitHub commit/archive if plugin ZIP is blocked), verify SHA256, and unpack into `question/type/stack`.
- Install companion behaviour plugins required by STACK (confirm exact plugin names/paths).
- Keep Moodle code tree read-only at runtime as a goal; only enforce after validation.

### 3.1 Services
- `mariadb` using official MariaDB image
- `moodle` built from the local Dockerfile
- `maxima` using mathinstitut/goemaxima image

### 3.2 Compose requirements
- Persistent volumes for DB and Moodle data
- Secrets volume with generated DB credentials (`MARIADB_ROOT_PASSWORD_FILE`, `MARIADB_PASSWORD_FILE`)
- Explicit ports for Moodle (HTTP) [and optionally HTTPS, later]
- Enable Moodle cron (env var?) if supported.
  - Note: cron may appear silent; if admin warning persists, run `php admin/cli/cron.php` once manually.
- Before release, ensure PHP `display_errors=0` for production safety.
- Healthchecks where feasible:
  - `mariadb`: simple TCP check
  - `moodle`: HTTP check to `/login/index.php`
  - `maxima`: HTTP check to `http://maxima:8080/goemaxima` (fallback `/maxima`)
- `maxima` must be internal-only (no host ports; use an internal Docker network).
- `mariadb` must be internal-only (no host ports; use an internal Docker network).

### 3.3 .env
Provide `.env.example` containing:
- admin credentials placeholders
- DB name/user placeholders (passwords are generated)
- site URL (for reverse proxy use)
- optional `STACK_*` vars for configuration scripts

No secrets in repo.

---

## 4) Init & automation scripts (init/scripts)

Goal: Allow both local usage and CI usage with the same scripts.

### 4.1 moodle-init.sh
- Runs after `docker compose up -d`
- Performs first-run install and upgrade
- Ensures config/volumes are ready
- Purges caches after upgrade

### 4.2 stack-init.sh
- Configures STACK settings (Maxima version, server URL, optional libraries).
- Sets the Moodle noreply address.
- Purges caches after configuration.

### 4.3 smoke-tests.sh
Run minimal verification:
- Moodle login page reachable
- Confirm STACK + companion behaviours are registered
- Confirm STACK settings and noreply address are configured
- Confirm Maxima service reachable from the Moodle network (prefer `/goemaxima`, fallback `/maxima`)
- If possible: trigger a trivial STACK CAS evaluation or run STACK’s internal health check method (document what is possible)

Output must be CI-friendly (non-zero exit on failure, error messages to stderr, stdout machine readable).

---

## 5) CI pipeline (.github/workflows/ci.yml)

Target: Ubuntu runner.
Optional: Runs also locally on Apple silicon macOS using `act`.

Status: Implemented and verified with `act` locally and GitHub Actions.

Steps:
1. Checkout
2. If needed, install Docker Compose (already present typically)
3. `docker compose build` (ensure custom Moodle image is built)
4. `docker compose up -d`
5. Run `init/scripts/moodle-init.sh`
6. Run `init/scripts/stack-init.sh`
7. Run `init/scripts/smoke-tests.sh`
8. Always `docker compose down -v` (cleanup)

Add log capture on failure:
- `docker compose logs --no-color` for all services
- Artifact upload of logs

Add timeouts to prevent hanging.

If feasible for quick deployment, consider storing the result as a build artefact / Github release.
Provide a local `act` helper script (`tools/act-ci.sh`) to run the same CI steps on macOS.

---

## 6) Automated version updates (Renovate or Dependabot)

### 6.1 Renovate (preferred)
Create `renovate.json`:
- Enable Docker image updates for `docker-compose.yml`, `docker/moodle/Dockerfile`, and `versions.yml`
- Group updates:
  - Group `STACK + goemaxima` together
  - Group `Moodle + MariaDB` together
- Disable automerge for major Moodle updates
- Require CI green to merge
- Optional: schedule updates weekly
Optional: add a regex manager to update Moodle release URLs and STACK plugin URLs in `versions.yml`.

### 6.2 Update policy (document in README)
- Only bump one “axis” at a time.
- If Moodle major changes: add a new supported tuple first, keep old tuple until stable.
- If STACK bumps: bump goemaxima in same PR.

---

## 7) TLS (optional module, later)

Do NOT make TLS mandatory.

Provide documentation for:
- Option A: Reverse proxy (Caddy) in a separate compose override file:
  - `docker-compose.tls.yml`
- Option B: Manual TLS termination externally

If implementing Caddy:
- Document prerequisites for Let’s Encrypt:
  - public DNS points to host
  - inbound 80/443 reachable
- Otherwise, provide a “local dev self-signed” mode only.

---

## 8) README.md (must be practical)

Include:
- Quickstart: `cp .env.example .env`, edit, `docker compose up -d`
- How to build the custom Moodle image and run init scripts locally
- How to run CI locally via `tools/act-ci.sh`
- Supported version tuple(s) (from compatibility.yml)
- How updates work (Renovate PRs + CI gating)
- Backup guidance, including:
  - volumes to back up (DB + moodledata)
  - instructions for testing backup restoration
- Troubleshooting:
  - common failures (first-start time, permissions, goemaxima endpoint mismatch)

---

## 9) Definition of Done (Phase 1)

- Local: On macOS (OrbStack), user can:
  - `docker compose up -d`
  - run a single init command/script
  - reach Moodle in browser
  - create a STACK question type (or at minimum verify plugin installed)
- goemaxima is reachable only from the internal Docker network (no host port).
- MariaDB is reachable only from the internal Docker network (no host port).
- Moodle code tree read-only is validated or explicitly deferred with a note.
- CI: On GitHub Actions:
  - runs end-to-end setup
  - verifies stack + maxima reachability
  - blocks merges on failures
- Local CI via `tools/act-ci.sh` works on macOS.
- Updates: Renovate opens PRs and CI validates them.
- Documentation: enough to reproduce without guessing.

---

## 10) Misc design choices

- Pin image digests after first stable release.

## 11) Open questions to resolve during implementation (do not block initial prototype)

- Confirm STACK plugin source strategy: plugin ZIP URL + checksum vs pinned Git commit/archive + checksum.
- Confirm exact companion behaviour plugin names and their sources (avoid typos and ensure correct paths).

Deliver the initial prototype with one pinned supported tuple and CI green.
