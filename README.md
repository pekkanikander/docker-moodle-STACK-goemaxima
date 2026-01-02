# docker-moodle-STACK-goemaxima

Minimal Docker Compose for Moodle + MariaDB + STACK (goemaxima), with pinned versions and CI-validated updates.
Custom Moodle image is built from a pinned PHP base plus a Moodle release tarball and baked-in STACK plugin.

## Quickstart
1) `cp .env.example .env`
2) Edit `.env` (see categories below).
3) `docker compose build`
4) `docker compose up -d`
5) Run the init scripts in this order:
   - `./init/scripts/moodle-init.sh`
   - `./init/scripts/stack-install.sh`
   - `./init/scripts/stack-configure.sh`
   - `./init/scripts/smoke-tests.sh`

## Configuration

Exact variable names live in `.env.example`. Expect categories:
- Moodle admin credentials and email
- Moodle site URL (for reverse proxy later)
- Database name/user/password
- Optional STACK config overrides (if needed)

No secrets are committed to the repo.

## What runs where
- `moodle` is a custom image built from `php:<version>-apache` + Moodle release tarball.
- `mariadb` uses the official MariaDB image and is internal-only (no host port).
- `maxima` uses `mathinstitut/goemaxima` and is internal-only (no host port).
- Moodle reaches goemaxima at `http://maxima:8080/goemaxima`.

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
- If STACK does not appear, confirm `stack-install.sh` ran successfully.
- If CAS tests fail, verify the goemaxima URL and container health.

## Read-only goal
The Moodle code tree should be read-only at runtime, but this is just a goal until validated.
