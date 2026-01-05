# docker-moodle-STACK-goemaxima

Minimal Docker Compose for Moodle + MariaDB + STACK (goemaxima),
with pinned versions and a custom Moodle image.

## Quickstart
1) `docker compose build`
2) `docker compose up -d`
3) Copy `.env.example` to `.env` (see below!) and set at least:
   - `MOODLE_ADMIN_EMAIL`
   - `MOODLE_ADMIN_PASSWORD`
   - (optional) `MOODLE_SITE_FULLNAME`, `MOODLE_SITE_SHORTNAME`, `MOODLE_SITE_URL`
   - (optional) `MOODLE_STACK_BEHAVIOUR_*` URLs once chosen
   - (optional) STACK settings in `.env` if you want to auto-configure STACK
4) Run the automated installer:
   - `./init/scripts/moodle-init.sh`
5) Configure STACK + noreply email (optional but recommended):
   - `./init/scripts/stack-init.sh`
6) Open `http://localhost:8080` and log in with your admin credentials.

## Configuration

In the local `.env` override defaults in `docker-compose.yml`, if needed.
Common overrides:
- `MARIADB_DATABASE`, `MARIADB_USER`
- `MOODLE_HTTP_PORT`
- `MOODLE_PHP_BASE_IMAGE`, `MOODLE_RELEASE_URL`, `MOODLE_RELEASE_SHA256`
- `MOODLE_SITE_URL`, `MOODLE_SITE_FULLNAME`, `MOODLE_SITE_SHORTNAME`
- `MOODLE_ADMIN_USER`, `MOODLE_ADMIN_EMAIL`, `MOODLE_ADMIN_PASSWORD`
- `MOODLE_NOREPLY_EMAIL`
- `MOODLE_STACK_PLUGIN_URL`, `MOODLE_STACK_PLUGIN_SHA256`
- `MOODLE_STACK_BEHAVIOUR_*_URL`, `MOODLE_STACK_BEHAVIOUR_*_SHA256`
- `MOODLE_STACK_MAXIMAVERSION`, `MOODLE_STACK_MAXIMACOMMAND`, `MOODLE_STACK_MAXIMACOMMANDOPT`
- `MOODLE_STACK_MAXIMACOMMANDSERVER`, `MOODLE_STACK_MAXIMALIBRARIES`
- `GOEMAXIMA_IMAGE`

Site name notes:
- `MOODLE_SITE_FULLNAME` shows in the site header and admin pages.
- `MOODLE_SITE_SHORTNAME` is used in navigation and course listings.

Database passwords are generated at startup by the `secrets-init` service
and stored in the `secrets` named volume. They are removed when you run
`docker compose down -v`.

If you change database charset/collation settings, recreate the DB volume:
`docker compose down -v` then `docker compose up -d`.

## What runs where
- `moodle` is a custom image built from `php:<version>-apache` + Moodle release tarball.
- `mariadb` uses the official MariaDB image and is internal-only (no host port).
- `maxima` uses the goemaxima image and is internal-only (no host port).
- `STACK` is baked into the Moodle image from a pinned GitHub tag archive.
- `moodle-cron` runs Moodle's CLI cron every minute in a separate container.

In this setup, Apache serves `/var/www/html/public` and Moodle's `$CFG->dirroot` resolves
to `/var/www/html/public`. When installing plugins manually, place them under the
`/var/www/html/public` tree.

## Supported versions (initial proposal)
- Moodle 5.1.1 (tarball + SHA256 from Moodle packaging site)
- PHP base `php:8.3-apache`
- MariaDB `mariadb:11.4`
- STACK 4.11.0 (plugin version 2025102100)
- goemaxima `mathinstitut/goemaxima:2025102100-1.2.0`

STACK plugin source is pinned to a GitHub tag archive with a recorded checksum; companion behaviour
plugin checksums are still pending confirmation.

## STACK/goemaxima setup notes
- STACK is installed at build time from `MOODLE_STACK_PLUGIN_URL` (GitHub tag archive).
- Companion behaviour plugins are installed by default from GitHub tag archives:
  `qbehaviour_dfexplicitvaildate`, `qbehaviour_dfcbmexplicitvaildate`, `qbehaviour_adaptivemultipart`.
- Companion behaviour plugin checksums are intentionally left blank for now; fill them once you fetch the archives.
- After installation, configure STACK to use goemaxima at `http://maxima:8080/goemaxima`
  (fallback `http://maxima:8080/maxima`) in the Moodle admin UI.
- To automate STACK settings + the noreply email, run `./init/scripts/stack-init.sh`
  after filling the `MOODLE_STACK_MAXIMA*` and `MOODLE_NOREPLY_EMAIL` values in `.env`.

**NOTE! The following are Work in Progress, not there yet**

## Local CI with `act`

Use `tools/act-ci.sh` to run the GitHub Actions workflow locally; tested only with macOS 15.7.
This repo assumes `ghcr.io/catthehacker/ubuntu:act-latest` is available on your hardware.

## Clean rebuild
If you need a pristine rebuild (wipe containers, volumes, and image cache), run:
```
./tools/clean-rebuild.sh
```

## Updates
- Versions are pinned in `versions.yml`.
- `compatibility.yml` captures supported tuples and upgrade notes.
- Renovate (planned) will open update PRs and group related changes.

## Backups
- Back up the MariaDB volume and `moodledata` volume.
- Test restores by bringing up fresh containers and verifying Moodle starts and data is present.

## Troubleshooting
- First start can take time; check `docker compose logs` for progress.
- If `moodle-cron` logs "config.php not found", re-run `./init/scripts/moodle-init.sh`.

## Read-only goal
The Moodle code tree should be read-only at runtime, but this is just a goal until validated.
