# docker-moodle-STACK-goemaxima

Minimal Docker Compose for Moodle + MariaDB + STACK (goemaxima),
with pinned versions and a custom Moodle image.

## Quickstart
0) Install `yq` if you don't have it installed
1) Run `./tools/update-versions.sh` to update/generate `.env.versions`
2) Run `cp .env.example .env` to set up the default environment.
   Do not copy `.env.versions` content into `.env`: the tooling layers both files
   (`.env` after `.env.versions`), so stale pins in `.env` would silently override
   freshly generated versions.
3) Set in `.env` at least:
   - `MOODLE_ADMIN_EMAIL`
   - `MOODLE_ADMIN_PASSWORD`
   - (optional) `MOODLE_SITE_FULLNAME`, `MOODLE_SITE_SHORTNAME`, `MOODLE_SITE_URL`
   - (optional) `MOODLE_PERSISTENT_ROOT` (set a local path if you don't have `/srv/moodle-persistent`)
   - For local dev, set `MOODLE_SITE_URL` to `http://localhost:${MOODLE_HTTP_PORT}`
4) `docker compose --env-file .env.versions --env-file .env build`
5) `docker compose --env-file .env.versions --env-file .env up -d`
6) Run the automated installer:
   - `./init/scripts/moodle-init.sh`
7) Configure STACK (optional but recommended):
   - `./init/scripts/stack-init.sh`
8) Open `http://localhost:${MOODLE_HTTP_PORT}` and log in with your admin credentials.

## Configuration

The local `.env` (or `.env.ci` for CI, see below) override defaults generated from `versions.yml` and
those in `docker-compose.yml` and in the scripts, if needed.
Common overrides:
- `MOODLE_ADMIN_PASSWORD`
- `MOODLE_NOREPLY_EMAIL`
- `MOODLE_HTTP_PORT`
- `MOODLE_SITE_URL`, `MOODLE_SITE_FULLNAME`, `MOODLE_SITE_SHORTNAME`
- `MOODLE_ADMIN_EMAIL`
- `MOODLE_ADMIN_USER`
- `MOODLE_PERSISTENT_ROOT` (bind-mount root for moodledata and mariadb)
Less common overrides:
- `DOCKER_COMPOSE_ARGS` (extra arguments passed to `docker compose` by init scripts)
- `MARIADB_UID`, `MARIADB_GID` (override mysql UID/GID inside the image for bind mounts)
- `MOODLE_STACK_MAXIMAVERSION`, `MOODLE_STACK_MAXIMACOMMAND`, `MOODLE_STACK_MAXIMACOMMANDOPT`
- `MOODLE_STACK_MAXIMACOMMANDSERVER`, `MOODLE_STACK_MAXIMALIBRARIES`
- `MOODLE_STACK_PLATFORM`
Version overrides, if you want to set something else than in `versions.yml` and `.env.versions`:
- `MOODLE_PHP_BASE_IMAGE`, `MOODLE_RELEASE_URL`, `MOODLE_RELEASE_SHA256`
- `MOODLE_STACK_PLUGIN_URL`, `MOODLE_STACK_PLUGIN_SHA256`
- `MOODLE_STACK_BEHAVIOUR_*_URL`, `MOODLE_STACK_BEHAVIOUR_*_SHA256`
- `MOODLE_STACK_QBANK_IMPORTASVERSION_URL`, `MOODLE_STACK_QBANK_IMPORTASVERSION_SHA256`
- `GOEMAXIMA_IMAGE`

Site name notes:
- `MOODLE_SITE_FULLNAME` shows in the site header and admin pages.
- `MOODLE_SITE_SHORTNAME` is used in navigation and course listings.

Database passwords are generated at startup by the `secrets-init` service
and stored in the `secrets` named volume. They are removed when you run
`docker compose down -v`.

If you change database charset/collation settings, recreate the DB volume:
`docker compose down -v` then `docker compose up -d`.

## Persistent data (bind mounts)
The database and moodledata live under `MOODLE_PERSISTENT_ROOT` as bind mounts:
```
${MOODLE_PERSISTENT_ROOT}/
  mariadb/
  moodledata/
  backups/db/
```
This data persists across `docker compose down -v` (only the `secrets` volume is removed).
To wipe local data, delete the directory or use `./tools/clean-rebuild.sh`:
- If `MOODLE_PERSISTENT_ROOT` is a relative path, `clean-rebuild` will wipe it.
- If it is an absolute path, set `PURGE_PERSISTENT=1` to wipe it.

## What runs where
- `moodle` is a custom image built from `php:<version>-apache` + Moodle release tarball.
- `mariadb` is a custom image derived from the official MariaDB image and is internal-only (no host port).
- `maxima` uses the goemaxima image and is internal-only (no host port).
- `STACK` is baked into the Moodle image from a pinned GitHub tag archive.
- `moodle-cron` runs Moodle's CLI cron every minute in a separate container.
- `moodle` HTTP is bound to `127.0.0.1:${MOODLE_HTTP_PORT}` for use behind a host reverse proxy.

In this setup, Apache serves `/var/www/html/public` and Moodle's `$CFG->dirroot` resolves
to `/var/www/html/public`. When installing plugins manually, place them under the
`/var/www/html/public` tree.  Please note that this is the expected configuration as of Moodle 5.1

## Supported versions

Pinned versions live in `versions.yml` (single source of truth).

STACK plugin source is pinned to a GitHub tag archive with a recorded checksum,
as are the companion behaviour plugins.

## STACK/goemaxima setup notes

- STACK is installed at build time from `MOODLE_STACK_PLUGIN_URL` (GitHub tag archive).
- Companion plugins are installed from GitHub tag archives with recorded checksums:
  `qbehaviour_dfexplicitvaildate`, `qbehaviour_dfcbmexplicitvaildate`, `qbehaviour_adaptivemultipart`,
  and `qbank_importasversion` (required by STACK >= 4.13).
- After installation, configure STACK to use goemaxima at `http://maxima:8080/goemaxima`
  (fallback `http://maxima:8080/maxima`) in the Moodle admin UI.
- To automate STACK settings, run `./init/scripts/stack-init.sh`
  after filling the `MOODLE_STACK_MAXIMA*` and `MOODLE_STACK_PLATFORM` values in `.env`.

## Question banks

Questions are authored as YAML in a separate content repo, compiled to Moodle
XML, and imported by CLI. The git tree is the source of truth: nothing is
authored in the Moodle web UI, and anything edited there is overwritten by the
next import. `qbank/README.md` documents the source format and what happens
when an already-imported question changes.

All commands below assume `QBANK_CONTENT_DIR` points at your content repo:

```sh
export QBANK_CONTENT_DIR=~/src/oivus-questions
```

With `QBANK_CONTENT_DIR` unset, the fixtures in `qbank/fixtures/` are used;
those are what CI runs.

### 0. Start the local test environment and log in

```sh
docker compose --env-file .env.versions --env-file .env up -d
docker compose --env-file .env.versions --env-file .env ps
```

Open `http://localhost:${MOODLE_HTTP_PORT}` once `moodle` reports healthy, and
log in as `MOODLE_ADMIN_USER` with `MOODLE_ADMIN_PASSWORD` from `.env`. Those
values are read at install time only, so a site installed from a different
`.env` keeps the password it was installed with; see Troubleshooting below.

For a pristine site, `./tools/clean-rebuild.sh` reinstalls from scratch and
wipes local data.

### 1. Edit the question bank

Edit or add YAML files under `$QBANK_CONTENT_DIR/questions/` (one question per
file) and `$QBANK_CONTENT_DIR/quizzes/`. `id:` is the permanent identity of a
question and must never be renamed. Review the change as a git diff before
importing it anywhere.

### 2. Compile

```sh
./tools/qbank.sh compile
```

YAML becomes Moodle XML under `.generated/qbank`, in the `qbank-tools`
container. Errors name the offending file and stop the run; nothing reaches
Moodle. Each question is also put through STACK's own validation before import,
because STACK otherwise saves an invalid question silently as broken and hidden.

### 3. Load it into the local site

```sh
./tools/qbank.sh import     # questions into the question bank
./tools/qbank.sh quizzes    # quiz activities
./tools/qbank.sh test       # each question's own tests, through Maxima
```

or all four steps in order:

```sh
./tools/qbank.sh all
```

Unchanged files are skipped. An edited file keeping the same `id:` is added as a
new Moodle *version* of the existing question, so earlier attempts stay intact.
`./tools/qbank.sh import -n` dry-runs; `--force` re-imports unchanged files.

`import` and `quizzes` print the course, bank and quiz they touched, with the
Moodle course-module ids.

### 4. See it in the browser

Reload the page; there is nothing to clear or republish. Using the cmids printed
in step 3:

- question bank — `http://localhost:${MOODLE_HTTP_PORT}/mod/qbank/view.php?id=<cmid>`
- quiz — `http://localhost:${MOODLE_HTTP_PORT}/mod/quiz/view.php?id=<cmid>`

Preview a single question from the question bank, or use *Preview quiz* to work
through the whole thing as a student would. A question already open in a browser
tab keeps showing the version it was loaded with, so reload after an import.

## Local CI with `act`

Use `tools/act-ci.sh` to run the GitHub Actions workflow locally; tested only with macOS 15.7.
This repo assumes `ghcr.io/catthehacker/ubuntu:act-latest` is available on your hardware.
CI runs on PRs, tags, releases, and manual dispatch; `act-ci.sh` uses amd64 emulation.
`act-ci.sh` uses `--bind` so bind-mounted persistent paths work.

The CI run creates `.env` by concatenating `.env.versions`, `.env.example` and `.env.ci`.
If there is no `.env.ci`, CI generates a minimal one (relative `MOODLE_PERSISTENT_ROOT`,
throwaway admin password).  For a local build, you don't need `.env.ci`.

**`act-ci.sh` overwrites your local `.env`.**  `act --bind` mounts the working tree
into the runner, so the CI step that writes `.env` writes *your* `.env`.  Back it up
before running, and keep `MOODLE_PERSISTENT_ROOT` pointed somewhere other than
`.ci-persistent`, which the CI run wipes.

If you want to mimic the CI behaviour exactly, you can create a `.env.ci` and do
```
cat .env.example .env.versions .env.ci > .env
```

## Smoke tests
Run the current verification suite after install/config:
```
./init/scripts/smoke-tests.sh
```

## Clean rebuild
If you need a pristine rebuild (rebuilds without cache and prunes dangling images), run:
```
./tools/clean-rebuild.sh
```
`clean-rebuild` also resets bind-mounted data for relative `MOODLE_PERSISTENT_ROOT` values,
so CI and local runs don't reuse stale DB data with new secrets. For absolute paths, set
`PURGE_PERSISTENT=1` to wipe the persistent root.

## Hosting
Production hosting (Hetzner VM, Caddy TLS, `oivus.pnr.iki.fi`) is documented in
`infra/hetzner/DEPLOY.md`; the underlying plan is `hetzner-hosting-task.md`.
Backups and restore procedures are documented in `infra/BACKUP.md`.

## Updates
- Versions are pinned in `versions.yml`.
- `compatibility.yml` captures supported tuples and upgrade notes.
- Renovate (planned) will open update PRs and group related changes.

**NOTE! The following are Work in Progress, not there yet**

## Backups
- Back up the MariaDB and `moodledata` directories under `MOODLE_PERSISTENT_ROOT`.
- Test restores by bringing up fresh containers and verifying Moodle starts and data is present.

## Troubleshooting
- First start can take time; check `docker compose logs` for progress.
- If `moodle-cron` logs "config.php not found", re-run `./init/scripts/moodle-init.sh`.
- If the admin password in `.env` is refused, the site was installed from a different
  `.env`.  Reset it to the current value rather than guessing:
  ```sh
  set -a; . ./.env; set +a
  docker compose --env-file .env.versions --env-file .env exec -T -u www-data \
    -e NEWUSER="$MOODLE_ADMIN_USER" -e NEWPASS="$MOODLE_ADMIN_PASSWORD" moodle php -r \
    'define("CLI_SCRIPT", true); require("/var/www/html/config.php");
     $u = $DB->get_record("user", ["username" => getenv("NEWUSER")]);
     update_internal_user_password($u, getenv("NEWPASS"));'
  ```

## Read-only goal
The Moodle code tree should be read-only at runtime, but this is just a goal until validated.
