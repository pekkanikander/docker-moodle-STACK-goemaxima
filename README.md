# docker-moodle-STACK-goemaxima

Minimal Docker Compose for Moodle + MariaDB, with pinned versions and a custom Moodle image.
STACK (goemaxima) will be added next; this first milestone focuses on Moodle + MariaDB only.

## Quickstart
1) `docker compose build`
2) `docker compose up -d`
3) Copy `.env.example` to `.env` (see below!) and set at least:
   - `MOODLE_ADMIN_EMAIL`
   - `MOODLE_ADMIN_PASSWORD`
   - (optional) `MOODLE_SITE_FULLNAME`, `MOODLE_SITE_SHORTNAME`, `MOODLE_SITE_URL`
4) Run the automated installer:
   - `./init/scripts/moodle-init.sh`
5) Open `http://localhost:8080` and log in with your admin credentials.

## Configuration

In the local `.env` override defaults in `docker-compose.yml`, if needed.
Common overrides:
- `MARIADB_DATABASE`, `MARIADB_USER`
- `MOODLE_HTTP_PORT`
- `MOODLE_PHP_BASE_IMAGE`, `MOODLE_RELEASE_URL`, `MOODLE_RELEASE_SHA256`
- `MOODLE_SITE_URL`, `MOODLE_SITE_FULLNAME`, `MOODLE_SITE_SHORTNAME`
- `MOODLE_ADMIN_USER`, `MOODLE_ADMIN_EMAIL`, `MOODLE_ADMIN_PASSWORD`

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
- `maxima`/STACK are planned but not wired yet in this milestone.

## Supported versions (initial proposal)
- Moodle 5.1.1 (tarball + SHA256 from Moodle packaging site)
- PHP base `php:8.3-apache`
- MariaDB `mariadb:11.4`
- STACK 4.11.0 (plugin version 2025102100)
- goemaxima `mathinstitut/goemaxima:2025102100`

At this point, STACK plugin source is still pending (ZIP URL + checksum vs pinned Git commit/archive + checksum).
Companion behaviour plugins required by STACK still need confirmation.

## Local CI with `act`

Use `tools/act-ci.sh` to run the GitHub Actions workflow locally; tested only with macOS 15.7.
This repo assumes `ghcr.io/catthehacker/ubuntu:act-latest` is available on your hardware.

## Updates
- Versions are pinned in `versions.yml`.
- `compatibility.yml` captures supported tuples and upgrade notes.
- Renovate (planned) will open update PRs and group related changes.

## Backups
- Back up the MariaDB volume and `moodledata` volume.
- Test restores by bringing up fresh containers and verifying Moodle starts and data is present.

## Troubleshooting
- First start can take time; check `docker compose logs` for progress.
- STACK/goemaxima notes will be added when that phase lands.

## Read-only goal
The Moodle code tree should be read-only at runtime, but this is just a goal until validated.
