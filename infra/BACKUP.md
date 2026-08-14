# Backups and restore

Three generations protect against different failures:

1. **Server dumps** (`/srv/moodle-persistent/backups/db/`) — fast recovery
   from self-inflicted damage: bad upgrade, operator error, DB corruption.
   Daily (kept 14) + Sunday weeklies (kept ~3 years, ~160). Driven by the
   `moodle-db-backup.timer` systemd unit (03:30 UTC, `Persistent=true`),
   installed by `server-bootstrap.sh`. A dump is only kept if it passes
   integrity checks (gzip, size, completion marker).
2. **MBP copy** (`~/Sites/oivus.pnr.iki.fi/`) — the actual disaster
   protection: server compromise, volume loss, Hetzner account problems.
   Daily dumps (kept 7), weeklies (kept 4), plus a moodledata mirror.
3. **Time Machine** snapshots of the MBP copy — older history.

## MBP sync setup (one-time)

```sh
cp infra/mbp/fi.iki.pnr.oivus.backup.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/fi.iki.pnr.oivus.backup.plist
```

The agent fires `tools/mbp-sync.sh` hourly; the script syncs at most once
per 20 h and exits silently when the server is unreachable, so an offline
laptop just catches up at the next opportunity. Log: `~/Sites/oivus.pnr.iki.fi/.launchd.log`.

## Restore: recent server-side mishap

On the VM, from `/opt/moodle-stack`:

```sh
./init/scripts/restore-db.sh                       # newest daily dump
./init/scripts/restore-db.sh /srv/moodle-persistent/backups/db/weekly/moodle-YYYYMMDD.sql.gz
```

That is the whole procedure: the dump is self-contained (drops and recreates
the database), the script stops Moodle during the import and purges caches
after. Attempt history after the dump's date is lost.

## Restore: full disaster (server or volume gone)

1. Recreate the server: DEPLOY.md §2 (`RECREATE=1` if it still exists).
   Cloud-init rebuilds everything except data and `.env` values.
2. Set `.env` values on the VM (DEPLOY.md §6).
3. Push the data back from the MBP:

   ```sh
   rsync -az --rsync-path="sudo rsync" ~/Sites/oivus.pnr.iki.fi/db/ moodle-hetzner:/srv/moodle-persistent/backups/db/
   rsync -az --rsync-path="sudo rsync" ~/Sites/oivus.pnr.iki.fi/moodledata/ moodle-hetzner:/srv/moodle-persistent/moodledata/
   ssh moodle-hetzner 'sudo chown -R 33:33 /srv/moodle-persistent/moodledata'
   ```

4. On the VM: `docker compose --env-file .env.versions --env-file .env up -d`
   then `./init/scripts/restore-db.sh`. Do NOT run `moodle-init.sh` — it
   forces a fresh install.
5. Verify: site loads over https, admin login works, STACK health check green.

## Caveat

A restored backup taken after a compromise restores the attacker's changes
too (accounts, tokens, content). Hardening/auditing of backups is a separate,
planned topic; until then, after any suspected compromise prefer an older
weekly dump and review users and web-service tokens after restoring.
