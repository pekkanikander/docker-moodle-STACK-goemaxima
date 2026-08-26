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

## MBP setup

```sh
infra/mbp/deploy.sh
```

(Re)populates `~/Sites/oivus.pnr.iki.fi` from the master copies in
`infra/mbp/` — sync and restore scripts into `bin/`, the README, and the
launchd agent — never the backup data itself. Re-run after changing
anything under `infra/mbp/`. The agent fires `bin/mbp-sync.sh` hourly;
the script syncs at most once per 20 h and exits silently when the server
is unreachable, so an offline laptop just catches up at the next
opportunity. Log: `~/Sites/oivus.pnr.iki.fi/.launchd.log`.

The deployed `bin/` scripts and README are self-sufficient: sync and
restore need only the ssh alias, not a repo clone. Only recreating the
server itself needs the repo (from GitHub if no local clone).

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

From `~/Sites/oivus.pnr.iki.fi` (its README carries the same runbook):

1. Recreate the server: DEPLOY.md §2 (`RECREATE=1` if it still exists).
   Cloud-init rebuilds everything except data and `.env` values.
2. Set `.env` values on the VM (DEPLOY.md §6), then start the stack —
   `up -d` only; do NOT run `moodle-init.sh`, it forces a fresh install:

   ```sh
   ssh moodle-hetzner 'cd /opt/moodle-stack && docker compose --env-file .env.versions --env-file .env up -d'
   ```

3. `bin/mbp-restore-moodledata.sh` — pushes the moodledata mirror back
   (asks for confirmation; overwrites the server's moodledata).
4. `bin/mbp-restore-db.sh` — uploads the newest local dump and runs the
   server-side restore.
5. Verify: site loads over https, admin login works, STACK health check green.

## Caveat

A restored backup taken after a compromise restores the attacker's changes
too (accounts, tokens, content). Hardening/auditing of backups is a separate,
planned topic; until then, after any suspected compromise prefer an older
weekly dump and review users and web-service tokens after restoring.

The dumps also contain the Anthropic API key (stored in the Moodle database
by the AI provider config). If a dump may have leaked, rotate the key in the
Anthropic Console; after a compromise-related restore, rotate it as a matter
of course.
