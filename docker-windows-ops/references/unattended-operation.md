# Unattended operation: survive reboots with nobody logged in

Goal: the machine reboots (power blip, Windows update) and the whole stack comes back — proxy up,
Docker up, containers up — with no human. This is a **chain**, and every link has a Windows-specific
trap.

## The chain (in order)

1. **Windows auto-login** — so a reboot reaches a logged-in session without someone typing a password.
2. **Proxy/VPN autostart** (if the app needs it at runtime, e.g. Clash TUN mode).
3. **Docker autostart via a cleanup-then-start script** (NOT Docker directly — see below and
   `crash-recovery.md`).
4. **Container `restart: unless-stopped`** — containers rejoin once the engine is healthy.
5. **(Optional) lock the screen** after login so an auto-logged-in machine isn't left open.
6. **(App-level) a self-heal / watchdog** so a missed scheduled action retries itself.

## Trap #1 — `HKCU\...\Run` does NOT fire under auto-login

The single biggest surprise. Registry `Run` autostart entries that work on a normal interactive
login **silently do not run** in an auto-login session. Symptoms: "I set it up, rebooted, and
nothing started — proxy, Docker, lock, all missing."

**Fix: use Task Scheduler, triggered "At log on."** One task that runs your startup `.ps1` is
reliable where `HKCU\Run` isn't.

```powershell
# Register once (run elevated). Script must be ASCII-only — see windows-scripting.md.
$action  = New-ScheduledTaskAction -Execute "powershell.exe" `
             -Argument '-NoProfile -ExecutionPolicy Bypass -File "C:\Users\<you>\startup.ps1"'
$trigger = New-ScheduledTaskTrigger -AtLogOn
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERNAME" -LogonType Interactive -RunLevel Highest
Register-ScheduledTask -TaskName "AppStack-Startup" -Action $action -Trigger $trigger -Principal $principal
```

## Trap #2 — auto-login is a secret, set it safely

Use **Sysinternals Autologon** (or `AutoAdminLogon=1` under
`HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon`). Autologon stores the password as an
**LSA secret**, not plaintext in the registry — prefer it. This is a **manual step** for the
operator (they type their password into the Autologon dialog once).

## Trap #3 — launch Docker's GUI exe, and clean orphans first

In the startup script, don't call `docker desktop start` (hangs early in a login session) — use
`Start-Process "C:\Program Files\Docker\Docker\Docker Desktop.exe"`. And **before** launching,
rename away any orphaned sockets (see `crash-recovery.md`), or the boot will crash-loop Docker.

## Trap #4 — the lock ran too early / didn't stick

If you lock the screen right after login, it can fire before the shell is ready and not take.
Add a delay:

```powershell
Start-Sleep -Seconds 25
rundll32.exe user32.dll,LockWorkStation
```

## Reference: shape of the startup script

ASCII-only, logs in English, one section per boot for easy triage:

```powershell
# startup.ps1  (ASCII only!)  logs to C:\Users\<you>\startup.log
$log = "C:\Users\<you>\startup.log"
"=== boot $(Get-Date -Format o) ===" | Out-File $log -Append -Encoding ascii

# 1) proxy/VPN (only if not already running)
if (-not (Get-Process clash-verge -ErrorAction SilentlyContinue)) {
  Start-Process "C:\Program Files\Clash Verge\clash-verge.exe"
  "started proxy" | Out-File $log -Append -Encoding ascii
}

# 2) clean orphan Docker sockets (rename, never delete)
foreach ($d in @("$env:LOCALAPPDATA\Docker\run", "$env:LOCALAPPDATA\docker-secrets-engine")) {
  if (Test-Path $d) {
    $orphan = Get-ChildItem -Force $d -EA SilentlyContinue |
              Where-Object { $_.Attributes -band [IO.FileAttributes]::ReparsePoint }
    if ($orphan) { Rename-Item $d "$d.broken" -Force; "renamed $d" | Out-File $log -Append -Encoding ascii }
  }
}

# 3) start Docker Desktop GUI (not `docker desktop start`)
Start-Process "C:\Program Files\Docker\Docker\Docker Desktop.exe"

# 4) delayed lock so nobody walks up to an open session
Start-Sleep -Seconds 25
rundll32.exe user32.dll,LockWorkStation
```

## Verifying it actually worked

Don't trust "looks fine" — **actually reboot** and check:
- the `startup.log` has a fresh boot section with each step logged,
- `docker compose ps` shows containers `Up`,
- the screen is locked,
- the app produced its next scheduled output.

The operator's report ("I rebooted, entered my password, programs were already open") is the real
signal. Beware self-reported "it works" before a genuine reboot test — earlier attempts here passed
on paper and failed on the actual reboot.

## Single-writer constraint

If the app pushes to an external channel on a schedule, **only one machine may run the scheduler at
a time**. Before moving the stack to a new machine, `docker compose down` on the old one, or both
will double-send.
