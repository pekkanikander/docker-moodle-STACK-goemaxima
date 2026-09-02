#!/bin/sh
set -eu

# App-level bootstrap of the Hetzner VM. Run as root by cloud-init after the
# repo clone; idempotent, so also safe to re-run manually after a git pull.

REPO_DIR=${REPO_DIR:-/opt/moodle-stack}
cd "$REPO_DIR"

# Under cloud-init snap yq resolved via the inherited root PATH; under sudo
# from server-update.sh that depends on sudoers secure_path. Be deterministic.
PATH="$PATH:/snap/bin"
export PATH

install -o root -g root -m 0644 infra/hetzner/caddy/Caddyfile /etc/caddy/Caddyfile
systemctl reload caddy

install -o root -g root -m 0644 infra/hetzner/sshd/99-hardening.conf \
  /etc/ssh/sshd_config.d/99-hardening.conf
sshd -t
systemctl reload ssh || true  # socket-activated; sshd may not be running

install -o root -g root -m 0644 \
  infra/hetzner/systemd/moodle-db-backup.service \
  infra/hetzner/systemd/moodle-db-backup.timer \
  infra/hetzner/systemd/moodle-health.service \
  infra/hetzner/systemd/moodle-health.timer /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now moodle-db-backup.timer moodle-health.timer

./tools/update-versions.sh

if [ ! -f .env ]; then
  # Site URL is fixed; the remaining values are secrets/preferences the admin
  # must set before running the init scripts.
  sed 's|^MOODLE_SITE_URL=.*|MOODLE_SITE_URL=https://oivus.pnr.iki.fi|' .env.example > .env
  chmod 600 .env
fi

docker compose --env-file .env.versions --env-file .env build
# Only these two services use registry images; the rest are built locally
# (--ignore-buildable does not help: moodle-cron reuses a built image
# without a build stanza and compose would still try to pull it).
docker compose --env-file .env.versions --env-file .env pull secrets-init maxima

chown -R admin:admin "$REPO_DIR"
