#!/bin/sh
set -eu

# Dump the Moodle database to $MOODLE_PERSISTENT_ROOT/backups/db and rotate.
# One dump per calendar day (rerunning overwrites the same file); Sunday's
# dump is also kept in weekly/. Run from the repo root; on the server this is
# driven by the moodle-db-backup.timer systemd unit.

. ./init/scripts/init-env.sh

backup_root="${MOODLE_PERSISTENT_ROOT}/backups/db"
daily_keep=${DAILY_KEEP:-14}
weekly_keep=${WEEKLY_KEEP:-160}

day=$(date +%Y%m%d)
mkdir -p "$backup_root/daily" "$backup_root/weekly"

dump="$backup_root/daily/moodle-$day.sql.gz"
tmp="$dump.part"

# --databases + --add-drop-database make the dump self-contained: restoring
# is a plain import, no manual drop/create (see restore-db.sh).
dc exec -T mariadb sh -c \
  'exec mariadb-dump -u root -p"$(cat /run/secrets/mariadb_root_password)" \
     --single-transaction --routines --events \
     --databases moodle --add-drop-database' \
  | gzip > "$tmp"

# The pipe above swallows a mid-dump failure (plain sh, no pipefail): refuse
# any dump that is corrupt, trivially small, or lacks the completion marker.
gzip -t "$tmp"
[ "$(wc -c < "$tmp")" -gt 10000 ] || die "dump suspiciously small: $tmp"
gzip -dc "$tmp" | tail -n 1 | grep -q '^-- Dump completed' \
  || die "dump has no completion marker: $tmp"

mv "$tmp" "$dump"

if [ "$(date +%u)" = 7 ]; then
  cp "$dump" "$backup_root/weekly/moodle-$day.sql.gz"
fi

prune() {
  dir="$1"
  keep="$2"
  ls -1 "$dir" | sort -r | tail -n +"$((keep + 1))" | while read -r f; do
    rm -- "$dir/$f"
  done
}
prune "$backup_root/daily" "$daily_keep"
prune "$backup_root/weekly" "$weekly_keep"

log "Backup complete: $dump"
