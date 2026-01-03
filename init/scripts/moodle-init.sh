#!/bin/sh
set -eu

if [ ! -f ./.env ]; then
  echo "Missing .env. Copy .env.example to .env and fill required values." >&2
  exit 1
fi

# Load .env for admin/site settings and optional overrides.
set -a
. ./.env
set +a

MOODLE_HTTP_PORT="${MOODLE_HTTP_PORT:-8080}"
MOODLE_SITE_URL="${MOODLE_SITE_URL:-http://localhost:${MOODLE_HTTP_PORT}}"
MOODLE_SITE_FULLNAME="${MOODLE_SITE_FULLNAME:-Moodle Site}"
MOODLE_SITE_SHORTNAME="${MOODLE_SITE_SHORTNAME:-Moodle}"
MOODLE_ADMIN_USER="${MOODLE_ADMIN_USER:-admin}"

: "${MOODLE_ADMIN_PASSWORD:?Set MOODLE_ADMIN_PASSWORD in .env}"
: "${MOODLE_ADMIN_EMAIL:?Set MOODLE_ADMIN_EMAIL in .env}"

MARIADB_DATABASE="${MARIADB_DATABASE:-moodle}"
MARIADB_USER="${MARIADB_USER:-moodle}"

if docker compose exec -T moodle test -f /var/www/html/config.php; then
  if docker compose exec -T -u www-data moodle test -r /var/www/html/config.php; then
    echo "Moodle already configured (config.php exists)."
    exit 0
  fi
  echo "Fixing config.php ownership for www-data."
  docker compose exec -T moodle chown www-data:www-data /var/www/html/config.php
  docker compose exec -T moodle chmod 0640 /var/www/html/config.php
  exit 0
fi

DB_PASS="$(docker compose exec -T moodle cat /run/secrets/moodle_db_password | tr -d '\r\n')"

docker compose exec -T -u www-data moodle php /var/www/html/admin/cli/install.php \
  --non-interactive \
  --agree-license \
  --wwwroot="${MOODLE_SITE_URL}" \
  --dataroot="/var/www/moodledata" \
  --dbtype="mariadb" \
  --dbhost="mariadb" \
  --dbname="${MARIADB_DATABASE}" \
  --dbuser="${MARIADB_USER}" \
  --dbpass="${DB_PASS}" \
  --fullname="${MOODLE_SITE_FULLNAME}" \
  --shortname="${MOODLE_SITE_SHORTNAME}" \
  --adminuser="${MOODLE_ADMIN_USER}" \
  --adminpass="${MOODLE_ADMIN_PASSWORD}" \
  --adminemail="${MOODLE_ADMIN_EMAIL}"
