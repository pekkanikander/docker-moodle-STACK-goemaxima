#!/bin/sh
set -eu

# App-level bootstrap of the Hetzner VM. Run as root by cloud-init after the
# repo clone; idempotent, so also safe to re-run manually after a git pull.

REPO_DIR=${REPO_DIR:-/opt/moodle-stack}
cd "$REPO_DIR"

install -o root -g root -m 0644 infra/hetzner/caddy/Caddyfile /etc/caddy/Caddyfile
systemctl reload caddy

install -o root -g root -m 0644 infra/hetzner/systemd/moodle-db-backup.service \
  infra/hetzner/systemd/moodle-db-backup.timer /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now moodle-db-backup.timer

./tools/update-versions.sh

if [ ! -f .env ]; then
  # Site URL is fixed; the remaining values are secrets/preferences the admin
  # must set before running the init scripts.
  sed 's|^MOODLE_SITE_URL=.*|MOODLE_SITE_URL=https://oivus.pnr.iki.fi|' .env.example > .env
  chmod 600 .env
fi

docker compose --env-file .env.versions --env-file .env build
# moodle and mariadb are built locally, not pullable.
docker compose --env-file .env.versions --env-file .env pull --ignore-buildable

chown -R admin:admin "$REPO_DIR"
