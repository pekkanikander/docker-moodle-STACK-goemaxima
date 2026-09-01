#!/bin/sh
set -eu

# Update an installed Hetzner server to the currently checked-out commit.
# Encodes the update sequence from infra/hetzner/DEPLOY.md; run as admin
# (docker group), with sudo only for the backup and bootstrap steps.
#
# Deliberately never runs moodle-init.sh (destroys config.php on an installed
# site) and never `down -v` (destroys the generated DB credentials in the
# secrets volume).

REPO_DIR=${REPO_DIR:-/opt/moodle-stack}
cd "$REPO_DIR"
PATH="$PATH:/snap/bin"   # snap yq is not on PATH in non-interactive SSH shells
export PATH

[ -f .env ] || { echo "ERROR: no .env; not an installed server. See DEPLOY.md." >&2; exit 1; }

echo "Backing up database..."
sudo systemctl start moodle-db-backup.service   # oneshot: blocks and propagates failure

# Idempotent host convergence: Caddyfile, backup units, .env.versions,
# image build + pulls. Does not touch an existing .env, does not `up -d`.
sudo ./infra/hetzner/scripts/server-bootstrap.sh

dc="docker compose --env-file .env.versions --env-file .env"
$dc up -d
$dc exec -T -u www-data moodle php /var/www/html/admin/cli/upgrade.php --non-interactive

# The same idempotent, .env-driven convergence tools/start.sh runs locally, so
# a server whose install predates a setting picks it up. Not running them is
# how the stack/ directories TASK-04 added came to be missing here, silently
# dropping every CAS-generated plot. moodle-init.sh stays out: see above.
./init/scripts/lang-init.sh
./init/scripts/mail-init.sh
./init/scripts/stack-init.sh
./init/scripts/auth-init.sh
./init/scripts/appearance-init.sh

echo "Running smoke tests..."
./init/scripts/smoke-tests.sh

# The smoke tests exercise the container's published port; a broken
# Caddy/TLS front is invisible to them. Check the public URL too.
site_url=$(sed -n 's/^MOODLE_SITE_URL=//p' .env)
curl -fsS "$site_url/login/index.php" > /dev/null
echo "External check OK: $site_url"
echo "Update complete: now at $(git rev-parse HEAD)"
