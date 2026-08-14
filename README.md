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

## Local CI with `act`

Use `tools/act-ci.sh` to run the GitHub Actions workflow locally; tested only with macOS 15.7.
This repo assumes `ghcr.io/catthehacker/ubuntu:act-latest` is available on your hardware.
CI runs on PRs, tags, releases, and manual dispatch; `act-ci.sh` uses amd64 emulation.
`act-ci.sh` uses `--bind` so bind-mounted persistent paths work.

The CI run creates `.env` by concatenating `.env.versions`, `.env.example` and `.env.ci`.
If there is no `.env.ci`, CI generates a minimal one (relative `MOODLE_PERSISTENT_ROOT`,
throwaway admin password).  That `.env` is used only by the CI run; it doesn't change your
local `.env` if you have one.  For a local build, you don't need `.env.ci`.

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

## Read-only goal
The Moodle code tree should be read-only at runtime, but this is just a goal until validated.
