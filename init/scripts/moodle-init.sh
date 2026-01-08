#!/bin/sh
set -eu

. ./init/scripts/init-env.sh

MOODLE_HTTP_PORT="${MOODLE_HTTP_PORT:-8080}"
MOODLE_SITE_URL="${MOODLE_SITE_URL:-http://localhost:${MOODLE_HTTP_PORT}}"
MOODLE_SITE_FULLNAME="${MOODLE_SITE_FULLNAME:-Moodle Site}"
MOODLE_SITE_SHORTNAME="${MOODLE_SITE_SHORTNAME:-Moodle}"
MOODLE_ADMIN_USER="${MOODLE_ADMIN_USER:-admin}"

require_nonempty "MOODLE_ADMIN_PASSWORD" "${MOODLE_ADMIN_PASSWORD:-}"
require_nonempty "MOODLE_ADMIN_EMAIL" "${MOODLE_ADMIN_EMAIL:-}"
require_nonempty "MOODLE_NOREPLY_EMAIL" "${MOODLE_NOREPLY_EMAIL:-}"

if dc exec -T moodle test -f /var/www/html/config.php; then
  log "Removing existing config.php to force a fresh install."
  dc exec -T moodle rm -f /var/www/html/config.php
fi
if dc exec -T moodle test -f /var/www/moodledata/config.php; then
  dc exec -T moodle rm -f /var/www/moodledata/config.php
fi

log "Reading DB password from secrets volume."
DB_PASS="$(dc exec -T moodle cat /run/secrets/moodle_db_password | tr -d '\r\n')"
if [ -z "$DB_PASS" ]; then
  die "DB password is empty; check secrets-init and the secrets volume."
fi

log "Running Moodle CLI installer."
dc exec -T -u www-data moodle php /var/www/html/admin/cli/install.php \
  --non-interactive \
  --agree-license \
  --wwwroot="${MOODLE_SITE_URL}" \
  --dataroot="/var/www/moodledata" \
  --dbtype="mariadb" \
  --dbhost="mariadb" \
  --dbname="moodle" \
  --dbuser="moodle" \
  --dbpass="${DB_PASS}" \
  --fullname="${MOODLE_SITE_FULLNAME}" \
  --shortname="${MOODLE_SITE_SHORTNAME}" \
  --adminuser="${MOODLE_ADMIN_USER}" \
  --adminpass="${MOODLE_ADMIN_PASSWORD}" \
  --adminemail="${MOODLE_ADMIN_EMAIL}"

log "Fixing config.php permissions."
dc exec -T moodle chown www-data:www-data /var/www/html/config.php
dc exec -T moodle chmod 0640 /var/www/html/config.php
log "Running Moodle CLI upgrade."
dc exec -T -u www-data moodle php /var/www/html/admin/cli/upgrade.php \
  --non-interactive
log "Enabling cron setting."
dc exec -T moodle php /var/www/html/admin/cli/cfg.php \
  --component=core --name=cron_enabled --set=1
log "Setting Moodle noreply address."
dc exec -T moodle php /var/www/html/admin/cli/cfg.php \
  --name=noreplyaddress \
  --set="${MOODLE_NOREPLY_EMAIL}"
log "Purging Moodle caches."
dc exec -T moodle php /var/www/html/admin/cli/purge_caches.php
log "Syncing config.php into moodledata."
dc exec -T -u www-data moodle sh -c \
  'cp /var/www/html/config.php /var/www/moodledata/config.php && chmod 0640 /var/www/moodledata/config.php'
