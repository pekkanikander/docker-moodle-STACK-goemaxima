#!/bin/sh
set -eu

# Restore the Moodle database from a dump produced by backup-db.sh.
#
# Usage: ./init/scripts/restore-db.sh [dump.sql.gz]
# Default: the newest daily dump. Run from the repo root.
#
# REPLACES the whole database (the dump carries DROP DATABASE). Attempt
# history after the dump's date is lost.

. ./init/scripts/init-env.sh

backup_root="${MOODLE_PERSISTENT_ROOT}/backups/db"
dump="${1:-$(ls -1 "$backup_root"/daily/*.sql.gz 2>/dev/null | sort | tail -n 1 || true)}"
[ -n "$dump" ] || die "no dump found under $backup_root/daily"
[ -f "$dump" ] || die "no such dump: $dump"
gzip -t "$dump"

log "Restoring from $dump."
log "Stopping Moodle containers."
dc stop moodle moodle-cron

gzip -dc "$dump" | dc exec -T mariadb sh -c \
  'exec mariadb -u root -p"$(cat /run/secrets/mariadb_root_password)"'

log "Starting Moodle containers."
dc start moodle moodle-cron
log "Purging Moodle caches."
dc exec -T moodle php /var/www/html/admin/cli/purge_caches.php
log "Restore complete: $dump"
