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
   Daily dumps (kept 7), weeklies (kept 53, about a year), plus a
   moodledata mirror.
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

## Compromise stance (decided 2026-09-01)

The GitHub repos are the source of truth; the Moodle state, attempt history
included, is expendable. A restored dump taken after a compromise restores
the attacker's changes too (accounts, tokens, content), so the response to a
suspected compromise is rebuild-from-scratch — the full-disaster runbook
above, with a weekly dump old enough to predate the suspicion, or with no
dump at all — never forensic cleaning of a running server. Bespoke detection
machinery (baselining or diffing security-relevant tables across dumps) was
considered and rejected as disproportionate to the assets.

What a compromise actually threatens is not availability but the student's
personal data (name, email, attempt history — present in every dump, on the
server and here) and the Anthropic API key (in the Moodle database, hence in
every dump). The key lives in a dedicated Claude Platform workspace with a
hard cost cap (10 USD/month), so its blast radius is bounded and rotation
takes minutes.

## Post-restore checklist

After any restore; mandatory when compromise is suspected. In the admin UI:

1. Site administrators (*Users → Permissions → Site administrators*): only
   the expected account.
2. User list (*Users → Browse list of users*): no unexpected accounts, and
   every account authenticates via "Manual accounts".
3. Web-service tokens (*Server → Web services → Manage tokens*): none.
4. Authentication plugins (*Plugins → Authentication*): only "Manual
   accounts" enabled, and the site posture checks in
   `infra/hetzner/DEPLOY.md` §7 still pass.
5. Outgoing-mail settings unchanged (*Server → Email*), the
   `divertallemailsto` diversion included.

When compromise is suspected, additionally rotate: the Anthropic API key
(Claude Console workspace, then re-enter in the admin UI), the Moodle admin
password, and the IKI SMTP service password.
