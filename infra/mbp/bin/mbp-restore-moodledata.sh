#!/bin/sh
set -eu

# Push this Mac's moodledata mirror back to the server. For disaster
# recovery onto a fresh server ONLY: --delete makes the server's moodledata
# identical to the local mirror, discarding anything newer on the server.
# Needs only ssh access to the server, not a repo clone.

HOST=${BACKUP_SSH_HOST:-moodle-hetzner}
SRC=${BACKUP_DEST:-$HOME/Sites/oivus.pnr.iki.fi}

printf 'This OVERWRITES moodledata on %s with the local mirror. Type yes to continue: ' "$HOST"
read -r answer
[ "$answer" = yes ] || exit 1

rsync -az --delete --rsync-path="sudo rsync" \
  "$SRC/moodledata/" "$HOST":/srv/moodle-persistent/moodledata/
ssh "$HOST" 'sudo chown -R 33:33 /srv/moodle-persistent/moodledata'
echo "moodledata pushed; ownership reset to www-data."
