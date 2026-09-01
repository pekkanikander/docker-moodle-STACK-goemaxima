# Backups of oivus.pnr.iki.fi

Offsite copy of the Moodle server's database dumps and data directory,
pulled by `bin/mbp-sync.sh` via the launchd agent `fi.iki.pnr.oivus.backup`:
hourly attempts, an actual sync at most once per 20 h, silently skipped
while this Mac cannot reach the server.

Everything here except the backup data itself is installed by
`infra/mbp/deploy.sh` from the repo — do not edit these files in place.
Repo: `~/Development/Moodle/docker-moodle-STACK-goemaxima`, upstream
<https://github.com/pekkanikander/docker-moodle-STACK-goemaxima>.

## Layout

- `db/daily/` — daily DB dumps, newest 7 (server keeps 14)
- `db/weekly/` — Sunday DB dumps, newest 53, about a year (server keeps
  ~3 years)
- `moodledata/` — mirror of the Moodle data directory (minus caches)
- `bin/` — sync and restore scripts; they need only ssh access to the
  server, not a repo clone
- `.last-sync` — timestamp guarding the 20 h sync interval
- `.launchd.log` — agent output
- Older history: Time Machine snapshots of this directory

## Restore: database

```sh
bin/mbp-restore-db.sh                              # newest local daily dump
bin/mbp-restore-db.sh db/weekly/moodle-YYYYMMDD.sql.gz
```

Uploads the dump and runs the server-side restore: stops Moodle, imports
(the dump drops and recreates the database), restarts, purges caches.
Attempt history after the dump's date is lost.

## Restore: full disaster (server or volume gone)

1. Recreate the server per `infra/hetzner/DEPLOY.md` §2 in the repo
   (clone from GitHub if there is no local copy). Cloud-init rebuilds
   everything except data and `.env` values.
2. Set `.env` values on the server (DEPLOY.md §6), then start the stack —
   `up -d` only; do NOT run `moodle-init.sh`, it forces a fresh install:

   ```sh
   ssh moodle-hetzner 'cd /opt/moodle-stack && docker compose --env-file .env.versions --env-file .env up -d'
   ```

3. `bin/mbp-restore-moodledata.sh` — pushes the moodledata mirror back;
   asks for confirmation, overwrites the server's moodledata.
4. `bin/mbp-restore-db.sh`
5. Verify: site loads over https, admin login works, STACK health green.

## Requirements

- ssh alias `moodle-hetzner` in `~/.ssh/config` (key auth, port 33101);
  created by `infra/hetzner/scripts/ssh-keygen.sh` in the repo.
- After a suspected compromise, restore a weekly dump old enough to
  predate the suspicion, then work through the post-restore checklist in
  `infra/BACKUP.md`.
