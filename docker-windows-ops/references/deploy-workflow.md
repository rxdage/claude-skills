# Deploy to a new machine, restore data, and iterate on a running stack

## Bringing the stack up on a fresh Windows box

Order that avoids the common dead-ends:

1. **Prereqs** (mostly manual / UAC): enable VirtualMachinePlatform, install WSL2 (offline MSI on a
   CN network — see `china-network.md`), install Docker Desktop (`desktop.docker.com` connects
   direct). Set registry mirrors before the first pull.
2. **Clone the repo** (GitHub connects direct on a CN network).
3. **Restore the secrets/config that are NOT in git.** `.env`, `backups/`, and any bind-mounted
   model weights are gitignored by design — copy them from the old machine by hand. Missing `.env`
   is the #1 "it builds but does nothing" cause.
4. **Restore the database** (below) if the app is stateful.
5. `docker compose up -d --build`. Watch `docker compose logs -f`.
6. Configure unattended operation only after a manual run works — see `unattended-operation.md`.

## Restoring a Postgres volume from a SQL dump

If the dump was made with `pg_dump` and includes schema + data (+ the migration version table), you
**do not** re-run migrations or seed afterward — the dump already carries that state.

```powershell
# DB service must be up and healthy first.
docker compose up -d db
Get-Content .\backups\app_backup.sql | docker compose exec -T db psql -U <user> -d <dbname>
```

`-T` disables TTY allocation (required when piping stdin). If the DB uses an extension image
(e.g. `pgvector/pgvector:pg16`), make sure `docker-compose.yml` pins that image so the extension
exists before the restore runs.

## Making code changes take effect — restart vs rebuild

Look at `docker-compose.yml`:

- **Source is bind-mounted** (`volumes: - ./:/app`): a code edit is live after
  `docker compose restart <service>`. **No rebuild.** This is the fast path — most logic changes.
- **No mount / baked into the image, or you changed `requirements`/Dockerfile/deps**: rebuild —
  `docker compose up -d --build <service>`.

Confirm a restart actually reloaded by checking the startup lines in `docker compose logs`.

## Verify logic changes with a dry-run *before* the real schedule fires

When a change affects real external output (pushes, emails, posts), don't test by triggering the
live path — you'll spam the channel. Run the pure logic in the container against real data with a
throwaway script and print the decisions instead of sending:

```powershell
# write a temp _check.py that imports the app's functions and PRINTS what it would do
docker compose exec -T <service> python _check.py
# inspect the output, then delete the temp file
```

Prefer read-only dry-runs (compute + print, no writes/sends). This caught real bugs here (a
dedup/selection change) before anything reached the live channel. Clean up the temp file after —
don't commit it (or add such scratch files to `.gitignore`, as was done for local diagnostic
scripts).

## Idempotency & self-heal are your safety net

- Make scheduled jobs **idempotent** (guard on "already produced/sent today") so a retry or an
  overlapping run doesn't double-fire.
- A **watchdog** that re-checks "did today's action actually succeed?" and retries/alerts covers the
  gap that an agent can't sit and watch 24/7. Combined with `restart: unless-stopped`, the stack
  self-recovers from most transient failures.

## Time & scheduling gotcha (cron day-of-week)

If the stack uses cron-style schedules, beware library differences in **day-of-week numbering**.
Standard cron uses `0 = Sunday`; some schedulers (e.g. APScheduler's native `CronTrigger`) use
`0 = Monday`, and helpers like `from_crontab` may not translate — silently shifting every
day-of-week job by one day. When a job fires on the wrong day, suspect this first; translate the
DOW field explicitly and verify with a next-fire-time test.
