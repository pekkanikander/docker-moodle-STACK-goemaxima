#!/bin/sh
set -eu

# Restore the server's Moodle database from a dump held on this Mac.
#
# Usage: mbp-restore-db.sh [dump.sql.gz]
# Default: the newest local daily dump.
#
# Uploads the dump into the server's backup tree, then runs the server-side
# restore (stops Moodle, imports, restarts, purges caches). REPLACES the
# whole database; attempt history after the dump's date is lost.
# Needs only ssh access to the server, not a repo clone.

HOST=${BACKUP_SSH_HOST:-moodle-hetzner}
SRC=${BACKUP_DEST:-$HOME/Sites/oivus.pnr.iki.fi}

dump="${1:-$(ls -1 "$SRC"/db/daily/*.sql.gz 2>/dev/null | sort | tail -n 1 || true)}"
[ -n "$dump" ] || { echo "no dump found under $SRC/db/daily" >&2; exit 1; }
[ -f "$dump" ] || { echo "no such dump: $dump" >&2; exit 1; }
gzip -t "$dump"

name=$(basename "$dump")
# backups/ is root-owned on the server; the admin login needs sudo rsync
# to write there.
rsync -az --rsync-path="sudo rsync" "$dump" \
  "$HOST":/srv/moodle-persistent/backups/db/daily/"$name"
ssh "$HOST" "cd /opt/moodle-stack && \
  ./init/scripts/restore-db.sh /srv/moodle-persistent/backups/db/daily/$name"
