#!/bin/sh
set -eu

# (Re)populate ~/Sites/oivus.pnr.iki.fi from this repo: helper scripts,
# README and the launchd agent — never the backup data itself. Idempotent;
# re-run after changing anything under infra/mbp/.

src=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
dest=${BACKUP_DEST:-$HOME/Sites/oivus.pnr.iki.fi}

install -d "$dest/bin" "$dest/db/daily" "$dest/db/weekly" "$dest/moodledata"
install -m 0755 "$src"/bin/mbp-sync.sh "$src"/bin/mbp-restore-db.sh \
  "$src"/bin/mbp-restore-moodledata.sh "$dest/bin/"
install -m 0644 "$src/README.md" "$dest/README.md"

agents="$HOME/Library/LaunchAgents"
plist="$agents/fi.iki.pnr.oivus.backup.plist"
install -d "$agents"
launchctl unload "$plist" 2>/dev/null || true
install -m 0644 "$src/fi.iki.pnr.oivus.backup.plist" "$plist"
launchctl load "$plist"

echo "Deployed to $dest; launchd agent (re)loaded."
