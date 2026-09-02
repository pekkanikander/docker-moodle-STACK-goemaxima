# docker-moodle-STACK-goemaxima

Minimal Docker Compose for Moodle + MariaDB + STACK (goemaxima),
with pinned versions and a custom Moodle image.

## Quickstart (no terminal needed)

1. Install this repository
   1.1. Download [GitHub Desktop](https://desktop.github.com/) and start it.
      If you don't have and don't want a GitHub account,
      select "Skip this step" on the registration pane.
   1.2. In GitHub Desktop choose `File → Clone repository → URL`,
      paste https://github.com/pekkanikander/docker-moodle-STACK-goemaxima,
      and click Clone.
      The clone lands in `~/Documents/GitHub/docker-moodle-STACK-goemaxima` by default.

      Do **not** download the repository as a ZIP: macOS quarantines the
      unpacked files and refuses to run the setup app.

2. Install [Docker Desktop](https://www.docker.com/products/docker-desktop/)
   (or OrbStack) and start it.

3. In the cloned folder, double-click **Setup Moodle**. The first run
   downloads and builds everything and takes several minutes; a progress
   window shows the current phase. When done, the browser opens the Moodle
   login page. Log in with username `admin` and an empty password: the local
   instance listens on localhost only and is configured for passwordless
   login.

Running **Setup Moodle** again is safe: it restarts the stack and skips the
installation. It logs to `.generated/setup.log`.

## Quickstart (command line)

0) Install Docker (with compose) if you don't have it installed.
1) Optional: `cp .env.example .env` and adjust. Without a `.env`,
   the next step generates one with local-use defaults and a temporary
   admin password (see `tools/start.sh`).
   Do not copy `.env.versions` content into `.env`: the tooling layers both
   files (`.env` after `.env.versions`), so stale pins in `.env` would
   silently override the committed versions.
2) `./tools/start.sh` — builds, starts, installs (first run only, incl.
   STACK configuration), and opens `http://localhost:${MOODLE_HTTP_PORT}`.

Or run the steps yourself:

1) `docker compose --env-file .env.versions --env-file .env build`
2) `docker compose --env-file .env.versions --env-file .env up -d`
3) Run the automated installer:
   - `./init/scripts/moodle-init.sh`
4) Install language packs and set the default language:
   - `./init/scripts/lang-init.sh`
5) Configure outgoing mail (noreply address, SMTP target):
   - `./init/scripts/mail-init.sh`
6) Configure STACK (optional but recommended):
   - `./init/scripts/stack-init.sh`
7) Configure authentication (passwordless login on a localhost site URL,
   password login otherwise; converges the Google SSO issuer when the
   `MOODLE_GOOGLE_OAUTH_CLIENT_*` variables are set in `.env`):
   - `./init/scripts/auth-init.sh`
8) Mark the environment (page tint and corner badge, optional):
   - `./init/scripts/appearance-init.sh`
9) Open `http://localhost:${MOODLE_HTTP_PORT}` and log in as your admin user
   (empty password on a localhost site URL).

`.env.versions` is committed and generated from `versions.yml`; after editing
`versions.yml`, maintainers regenerate it with `./tools/update-versions.sh`
(requires `yq`). CI fails if the two drift apart.

## Configuration

The local `.env` (or `.env.ci` for CI, see below) overrides defaults generated from `versions.yml` and
those in `docker-compose.yml` and in the scripts, if needed.
Common overrides:
- `MOODLE_ADMIN_PASSWORD`
- `MOODLE_NOREPLY_EMAIL`
- `MOODLE_HTTP_PORT`
- `MOODLE_SITE_URL`, `MOODLE_SITE_FULLNAME`, `MOODLE_SITE_SHORTNAME`
- `MOODLE_ADMIN_EMAIL`
- `MOODLE_ADMIN_USER`
- `MOODLE_ADMIN_FORCE_PASSWORD_CHANGE` (`1` forces an admin password change at
  first login; moot on a localhost instance, where `auth-init.sh` switches
  accounts to passwordless login)
- `MOODLE_GOOGLE_OAUTH_CLIENT_ID` and `MOODLE_GOOGLE_OAUTH_CLIENT_SECRET`
  (optional Google SSO; `auth-init.sh` creates/updates the Google issuer
  from them — see `.env.example` and `infra/hetzner/DEPLOY.md` §8)
- `MOODLE_LANGPACKS` (language packs to install, comma- or space-separated
  Moodle language codes, e.g. `fi`; English needs no pack)
- `MOODLE_LANG` (fallback site language, default `en`; must be `en` or one of
  `MOODLE_LANGPACKS`)
- `MOODLE_PERSISTENT_ROOT` (bind-mount root for moodledata and mariadb)
- `MOODLE_SMTPHOSTS` (outgoing mail target as `host:port`; `mailpit:1025`
  sends to the bundled Mailpit capture, browsable at
  `http://localhost:${MAILPIT_HTTP_PORT}` — for real delivery use a relay
  and set its credentials in the Moodle admin UI; `mail-init.sh` is safe to
  rerun and applies changed mail settings to an installed site)
- `MOODLE_SMTPSECURE` (SMTP transport security: empty, `tls` or `ssl`)
- `COMPOSE_PROFILES` (`mail-capture` runs the bundled Mailpit; empty on
  servers relaying to a real SMTP host)
- `MAILPIT_HTTP_PORT` (host-local port for the Mailpit web UI, default `8025`)
- `MOODLE_ENV_LABEL`, `MOODLE_ENV_COLOUR` (per-environment marking applied by
  `appearance-init.sh`, safe to rerun: every page gets a tint of the colour
  and a corner badge with the label, so it is obvious whether you are looking
  at local, staging or production. An empty label leaves the site unmarked;
  the colour is a hex value or a CSS colour name)
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

Language notes:
- The browser wins. `lang-init.sh` enables Moodle's `autolang`, so a visitor is
  served whichever of the installed languages their browser asks for;
  `MOODLE_LANG` applies only when the browser asks for something else.
- A language a user has explicitly chosen in their profile overrides both.
- Unlike the other init scripts' settings, `MOODLE_LANGPACKS` is not read only
  at install time: `lang-init.sh` is safe to rerun, and adding a code and
  rerunning it installs the new pack on a live site.

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
- If it is an absolute path, set `PURGE_PERSISTENT=1` to empty `mariadb/` and
  `moodledata/` in place; the directories themselves (with their ownership)
  and `backups/` are kept.

## What runs where
- `moodle` is a custom image built from `php:<version>-apache` + Moodle release tarball.
- `mariadb` is a custom image derived from the official MariaDB image and is internal-only (no host port).
- `maxima` uses the goemaxima image and is internal-only (no host port).
- `STACK` is baked into the Moodle image from a pinned GitHub tag archive.
- `moodle-cron` runs Moodle's CLI cron every minute in a separate container.
  It is the one internal service also attached to the `frontend` network:
  Moodle's scheduled `update_langpacks_task` has to reach `download.moodle.org`.
- Language packs live in `moodledata/lang`, not in the code tree, so they
  survive image rebuilds. `lang-init.sh` downloads only the packs that are
  missing, so re-running it (as `tools/start.sh` does) needs no network.
- `config.php` lives in the container's writable layer, so it does not survive a
  container recreate. `moodle-init.sh` keeps the durable copy in `moodledata`,
  and the container entrypoint restores it on start; rebuilding the image is
  therefore safe, and `moodle-init.sh` is only for a first install.
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

## AI provider (Anthropic Claude)

- The `aiprovider_claude` plugin is baked into the Moodle image from a pinned
  GitHub tag archive (see `versions.yml`), like the STACK plugins. It backs the
  Moodle core AI subsystem with the Anthropic Messages API
  (actions: generate text, summarise text, explain text).
- The API key is never stored in this repo. To activate the provider, go to
  Site administration → AI → AI providers, add a "Claude API Provider"
  instance, and paste an Anthropic API key. Set an explicit `max_tokens` per
  action there; the plugin's default is the model maximum. The key is stored
  in the Moodle database only.
- For a local testing environment, use a separate, spend-limited key, not the
  production one. It lives in the local database, so it disappears with the
  persistent root on a full from-scratch rebuild and must then be re-entered.
- Survey and selection rationale: `notes/aiprovider-survey.md`.

## Question banks

Questions are authored as YAML in a separate content directory, compiled to Moodle
XML, and imported by CLI. The git tree is the source of truth: nothing is
authored in the Moodle web UI, and anything edited there is overwritten by the
next import. `qbank/README.md` documents the source format and what happens
when an already-imported question changes.

All commands below assume `QBANK_CONTENT_DIR` points at your content directory:

```sh
export QBANK_CONTENT_DIR=~/path/to/oivus-questions
```

With `QBANK_CONTENT_DIR` unset, the fixtures in `qbank/fixtures/` are used;
those are what CI runs.

### 0. Start the local test environment and log in

```sh
docker compose --env-file .env.versions --env-file .env up -d
docker compose --env-file .env.versions --env-file .env ps
```

Open `http://localhost:${MOODLE_HTTP_PORT}` once `moodle` reports healthy, and
log in as `MOODLE_ADMIN_USER` with an empty password (a localhost instance is
passwordless once `auth-init.sh` has run). On a site that has not been
converged, use `MOODLE_ADMIN_PASSWORD` from `.env`; that value is read at
install time only, so a site installed from a different `.env` keeps the
password it was installed with; see Troubleshooting below.

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

Only one `qbank.sh` run at a time may touch the site; a second one refuses to
start and names the run already in flight. Two at once corrupt each other's
work in ways that look like a broken database rather than like contention.

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
CI runs on pushes to `main`, PRs, tags, releases, and manual dispatch; `act-ci.sh` uses amd64 emulation.
`act-ci.sh` uses `--bind` so bind-mounted persistent paths work.

The CI run creates `.env` by concatenating `.env.versions`, `.env.example` and `.env.ci`.
If there is no `.env.ci`, CI generates a minimal one (relative `MOODLE_PERSISTENT_ROOT`,
throwaway admin password).  For a local build, you don't need `.env.ci`.

**`act-ci.sh` overwrites your local `.env`.**  `act --bind` mounts the working tree
into the runner, so the CI step that writes `.env` writes *your* `.env`.  Back it up
before running, and keep `MOODLE_PERSISTENT_ROOT` pointed somewhere other than
`.ci-persistent`, which the CI run wipes.  The first-run CI step goes further:
it deletes `.env` (replaced by the `tools/start.sh` defaults) and wipes and
reinstalls into `./.persistent`.

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
`PURGE_PERSISTENT=1` to empty `mariadb/` and `moodledata/` in place (the directories and
`backups/` are kept).

## Hosting
Hosted staging (Hetzner VM, Caddy TLS, `oivus.pnr.iki.fi`) is documented in
`infra/hetzner/DEPLOY.md`.
Backups and restore procedures are documented in `infra/BACKUP.md`.

## Updates
- Versions are pinned in `versions.yml`.
- `compatibility.yml` captures supported tuples and upgrade notes.
- Renovate (planned) will open update PRs and group related changes.

## Backups
The hosted instance has automated dumps, offsite pulls and restore runbooks;
see `infra/BACKUP.md`. For a local setup, back up the MariaDB and `moodledata`
directories under `MOODLE_PERSISTENT_ROOT`.

## Troubleshooting
- First start can take time; check `docker compose logs` for progress.
- **Setup Moodle** logs to `.generated/setup.log`; on failure the app opens it.
- If macOS refuses to open **Setup Moodle** ("cannot be opened" /
  "unidentified developer"), the repo was downloaded as a ZIP and quarantined.
  Delete it and clone with GitHub Desktop (or `git clone`) instead.
- On first run, macOS may ask to allow access to your Documents folder;
  this is expected.
- If `moodle-cron` logs "config.php not found", the site has never been installed
  against this `moodledata`; run `./init/scripts/moodle-init.sh`. Do not run it
  on an installed site: it deletes both copies of `config.php` first.
- If the UI is still English for a Finnish browser, check in order: the pack is
  present (`ls "$MOODLE_PERSISTENT_ROOT/moodledata/lang"`), `autolang` is `1`
  (`... exec -T moodle php /var/www/html/admin/cli/cfg.php --name=autolang`),
  and the user has no language set in their own profile preferences.
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
