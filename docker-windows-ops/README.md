# docker-windows-ops

**The Docker-on-Windows failures that cost hours, and the fixes that actually worked.** A Claude
Code skill distilled from taking a Docker Compose app all the way to unattended,
reboot-surviving production on a Windows 11 desktop, on a mainland-China network.

Every entry records the symptom, the real cause, the fix, and **what did not work**, so you
skip the dead ends.

## The pitfalls it saves you from

| What you see | What everyone tries first | What actually works |
|---|---|---|
| Docker Desktop crash-loops: "Inference manager", "Secrets Engine", "the file cannot be accessed by the system" | Disable the AI/inference features, reboot, reinstall | An unclean stop left **orphaned AF_UNIX socket files** that cannot be deleted. **Rename their parent directory** and Docker rebuilds it clean. Rebooting does not clear them |
| Same crash 1 second after the rename fix | Rename again | The WSL VM itself is hung (`vmmemWSL` survives `wsl --shutdown`). Rename, then reboot Windows: the one case where a reboot is required |
| Autostart works when you log in by hand but not after an unattended reboot | Add more `Run` registry entries | Under Windows **auto-login, `HKCU\...\Run` entries silently don't fire**. Use a Task Scheduler task "At log on" |
| Startup `.ps1` "didn't run", no log at all | Debug the task | PowerShell 5.1 reads UTF-8 without BOM as the local code page; **one Chinese comment breaks brace matching** and the script dies while parsing. Keep scripts ASCII |
| Cleanup script kills itself (exit 255) | Add delays | The kill filter matched **its own command line**. Exclude `$PID` and build the pattern string at runtime |
| Red `NativeCommandError` text from `docker` or `git` | Add `2>&1` | That is normal stderr progress, not an error; `2>&1` in 5.1 makes it worse. Check `$LASTEXITCODE` |
| `docker pull` EOF / TLS timeout in China | Retry | Registry mirrors (list included), Tsinghua for pip/apt, offline WSL MSI |
| HuggingFace model still fails through `hf-mirror.com` | Try another mirror | Large weights redirect to a blocked host. **ModelScope + load from a local path** |
| Code edit "didn't take effect" | Rebuild the image | Source bind-mounted: `docker compose restart <svc>` is enough. Rebuild only for dependency changes |
| Scheduled job fires on the wrong weekday | Check timezones | **Day-of-week numbering differs** (cron 0 = Sunday, APScheduler 0 = Monday) |

## Contents

| Reference | Covers |
|---|---|
| `references/crash-recovery.md` | Socket orphans, the rename fix, hung WSL VM, model-runner |
| `references/china-network.md` | What fails direct, what connects direct, the working mirror paths |
| `references/unattended-operation.md` | The full reboot-survival chain: auto-login, Task Scheduler, restart policies, delayed lock |
| `references/windows-scripting.md` | PowerShell 5.1 encoding, stderr, self-kill, UAC, syntax traps |
| `references/deploy-workflow.md` | New machine bring-up, Postgres restore, restart vs rebuild, dry-runs, cron weekday trap |

`SKILL.md` maps symptoms to the right reference and lists the principles that apply everywhere.

## Using it

There is nothing to run. Copy the folder into `~/.claude/skills/` (see the root README) and
Claude loads it when a conversation matches, for example "Docker won't start on Windows",
"make it run on boot" or "pulling the image is stuck".

Written against Docker Desktop 4.7x to 4.8x on Windows 11 in 2026. Mirror hosts drift over time;
the reference says so where it matters. Steps that need administrator rights are marked as
manual: the user confirms the UAC prompt.

## Licence

MIT, see the repository root.
