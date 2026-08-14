#!/bin/sh
set -eu

# Best-effort pull of the server's backups to this Mac. Deployed to
# ~/Sites/oivus.pnr.iki.fi/bin by infra/mbp/deploy.sh and fired hourly by
# launchd: syncs at most once per $MIN_AGE_H hours, and exits quietly when
# the server is unreachable, so an offline laptop simply catches up at the
# next opportunity. Needs only ssh access to the server, not a repo clone.

HOST=${BACKUP_SSH_HOST:-moodle-hetzner}
DEST=${BACKUP_DEST:-$HOME/Sites/oivus.pnr.iki.fi}
MIN_AGE_H=${MIN_AGE_H:-20}
DAILY_KEEP=${DAILY_KEEP:-7}
WEEKLY_KEEP=${WEEKLY_KEEP:-4}

stamp="$DEST/.last-sync"
mkdir -p "$DEST/db/daily" "$DEST/db/weekly" "$DEST/moodledata"

if [ -f "$stamp" ] && [ -n "$(find "$stamp" -mtime -"${MIN_AGE_H}"h 2>/dev/null)" ]; then
  exit 0
fi

ssh -o BatchMode=yes -o ConnectTimeout=5 "$HOST" true 2>/dev/null || exit 0

# sudo on the remote side: backups/ is root-owned and moodledata/ is
# www-data-only; the admin login can read neither directly.
rsync -az --rsync-path="sudo rsync" \
  "$HOST":/srv/moodle-persistent/backups/db/ "$DEST/db/"

rsync -az --delete --rsync-path="sudo rsync" \
  --exclude=cache/ --exclude=localcache/ --exclude=sessions/ \
  --exclude=temp/ --exclude=trashdir/ --exclude=lock/ \
  "$HOST":/srv/moodle-persistent/moodledata/ "$DEST/moodledata/"

prune() {
  dir="$1"
  keep="$2"
  ls -1 "$dir" | sort -r | tail -n +"$((keep + 1))" | while read -r f; do
    rm -- "$dir/$f"
  done
}
prune "$DEST/db/daily" "$DAILY_KEEP"
prune "$DEST/db/weekly" "$WEEKLY_KEEP"

touch "$stamp"
echo "Synced to $DEST at $(date '+%Y-%m-%d %H:%M:%S')."
