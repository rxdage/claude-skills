---
name: docker-windows-ops
description: >-
  Deploying, running, and un-breaking Dockerized apps on Windows (Docker Desktop +
  WSL2 backend), distilled from a real end-to-end deployment. Use this whenever you
  work with Docker Compose / Docker Desktop on Windows and hit any of: Docker Desktop
  failing to start or crash-looping (especially errors mentioning "Inference manager",
  "Secrets Engine", "listener", or "the file cannot be accessed by the system");
  image pulls, pip/apt installs, WSL installs, or model-weight downloads that time out
  or fail TLS on a mainland-China network; setting up unattended / auto-start-after-reboot
  operation (auto-login, Task Scheduler, container restart policy, lock screen);
  PowerShell scripts that garble, die parsing, kill themselves, or spew red error text;
  or deploying a Docker project to a new Windows machine, restoring a database volume,
  and making code edits take effect in a running container. Reach for this even if the
  user only says something short like "Docker won't start on Windows", "make it run on
  boot", or "pulling the image is stuck" — the root causes and fixes here are non-obvious
  and were expensive to discover.
---

# Docker on Windows: deploy, run, and un-break

This skill is hard-won operational knowledge from taking a Docker Compose app all the way
to *unattended, reboot-surviving production* on a Windows 11 desktop behind a mainland-China
network. The failures below look cryptic and the fixes are counter-intuitive — that's exactly
why they're written down. Prefer these over guessing; each one cost real debugging time.

Nothing here is app-specific — the running example was a Python/FastAPI + pgvector stack, but
the traps (Docker Desktop sockets, network blocks, autostart, PowerShell encoding) hit any
Dockerized project on Windows.

## First, orient before you act

Cheap checks that decide which reference file you need:

- **Is Docker even up?** `docker version` (client+server), `docker compose ps`. A server error
  usually means Docker Desktop crashed on start → `crash-recovery.md`.
- **WSL2 backend healthy?** `wsl -l -v` — the distro (e.g. `docker-desktop`) should be `Running`.
- **Mainland-China network?** If pulls/downloads time out or TLS-fail, assume the network is
  blocking and go to `china-network.md` *before* burning time on retries.
- **Does it need to survive reboots with nobody watching?** That's a whole chain, not one setting
  → `unattended-operation.md`.

## Symptom → reference

| What you see | Read |
|---|---|
| Docker Desktop won't start, crash-loops, or logs `Inference manager` / `Secrets Engine` / `listening on unix://…` / `the file cannot be accessed by the system` / `syntax is incorrect` | [references/crash-recovery.md](references/crash-recovery.md) |
| `docker pull` EOF/`TLS handshake timeout`; `pip`/`apt` failing in a build; `wsl --install` hangs; `winget` `0x8a15000f`; HuggingFace/model download 302s to a blocked host | [references/china-network.md](references/china-network.md) |
| Must run after reboot with no human (auto-login, autostart, lock screen, restart policy), or "it worked when I was logged in but not on boot" | [references/unattended-operation.md](references/unattended-operation.md) |
| A `.ps1` garbles non-ASCII, dies with `Missing closing '}'`, kills its own process, or every native command prints scary red text | [references/windows-scripting.md](references/windows-scripting.md) |
| Deploying to a new Windows box, restoring a DB volume, or "I edited the code but the container didn't change" | [references/deploy-workflow.md](references/deploy-workflow.md) |

## Principles that generalize (skim these even if you don't open a reference)

1. **Docker Desktop's worst Windows failure is an orphaned AF_UNIX socket, not a config error.**
   A hard stop (crash/force-quit/power-loss) leaves undeletable reparse-point socket files under
   `%LOCALAPPDATA%\Docker\run\` and `%LOCALAPPDATA%\docker-secrets-engine\`. Docker tries to
   remove+recreate them on next start and crash-loops. You **cannot delete** them
   (`Remove-Item`/.NET `Delete` both fail) — but you **can rename the parent directory**
   (a metadata op that sidesteps the access error). Rename it away, Docker rebuilds clean.
   Toggling `EnableInference`/`EnableDockerAI` does **not** fix it. See `crash-recovery.md`.

2. **On a mainland-China network, reach for mirrors first, direct second.** Docker Hub,
   `winget`, online `wsl --install`, `deb.debian.org`, and HuggingFace large weights are blocked
   or flaky. Registry mirrors, Tsinghua pip/apt, an offline WSL MSI, and ModelScope for model
   weights are the reliable paths. `desktop.docker.com` and GitHub releases *do* connect direct.
   See `china-network.md`.

3. **Under Windows auto-login, `HKCU\...\Run` autostart entries silently do NOT fire.** Use a
   Task Scheduler task triggered **At Log On** instead. This is the single biggest gotcha in
   unattended setups. See `unattended-operation.md`.

4. **Write `.ps1` files ASCII-only.** PowerShell 5.1 reads a UTF-8-without-BOM file as GBK; any
   non-ASCII (e.g. Chinese comments) corrupts brace matching → `Missing closing '}'` → the script
   dies instantly leaving no log. Keep scripts pure ASCII; log in English. See `windows-scripting.md`.

5. **Mounted code = restart, not rebuild.** If `docker-compose.yml` bind-mounts the source
   (`./:/app`), a code edit takes effect on `docker compose restart <svc>` — no image rebuild.
   Only rebuild when dependencies/Dockerfile change. Verify logic changes with a throwaway
   `docker compose exec <svc> python …` dry-run *before* letting the real schedule fire, so you
   never test by spamming a live output channel. See `deploy-workflow.md`.

6. **Respect single-writer constraints.** If the app pushes to an external channel on a schedule,
   only one machine may run the scheduler at a time — two copies = duplicate sends. Bring the old
   one down (`docker compose down`) before starting the new one.

7. **Claude cannot silently gain admin.** Any system change needing elevation must be confirmed by
   the human in a UAC prompt (`Start-Process -Verb RunAs` triggers it). Mark such steps clearly as
   **"需手动操作 / manual step"** — the operator here is Chinese-speaking and infra-light, and
   values step-by-step guidance with the hands-on moments called out. Auto-permission modes also
   block `ExecutionPolicy Bypass + elevation`, so don't route around the prompt.

## How to extend this skill

When a new non-obvious Windows/Docker failure gets solved, add it to the matching reference file
(symptom → root cause → the exact fix that worked, and what *didn't* work). The "what didn't work"
line is often the most valuable part — it stops the next person re-trying dead ends.
