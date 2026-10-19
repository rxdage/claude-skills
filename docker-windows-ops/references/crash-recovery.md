# Docker Desktop won't start / crash-loops on Windows

## The symptom

Docker Desktop hangs on "starting", or the engine dies seconds after start. Logs (or the error
dialog) show something like:

```
initializing Inference manager: listening on unix://C:/Users/<you>/AppData/Local/Docker/run/dockerInference:
  ... The file cannot be accessed by the system. (listener: ... syntax is incorrect)
```

Variants name **"Inference manager"**, **"Secrets Engine"**, `engine.sock`, or just
`the file cannot be accessed by the system`. It typically starts after an unclean shutdown
(crash, force-quit, power loss, or Docker being killed during a reboot).

## What does NOT fix it (don't waste time here)

- Toggling **`EnableDockerAI=false`** / **`EnableInference=false`** in
  `%APPDATA%\Docker\settings-store.json` (older builds: `settings.json`). The AI/inference
  feature is a *trigger*, not the root cause.
- `admin-settings.json` — ignored entirely on personal (non-Business) accounts.
- Restarting Windows. The offending files live in a **non-volatile** directory, so a reboot does
  not clear them — and if Docker auto-starts, it just crash-loops again.
- `Remove-Item` / .NET `File.Delete` on the socket files. They fail with the same
  "cannot be accessed" error.

## The root cause

The unclean stop left **orphaned AF_UNIX socket files** — reparse points that Windows reports as
present but refuses to open or delete. Docker's next start tries to `remove + recreate` them at the
same path and crashes on the remove. They live in:

- `%LOCALAPPDATA%\Docker\run\`  (e.g. `dockerInference`, other `*.sock`)
- `%LOCALAPPDATA%\docker-secrets-engine\`  (e.g. `engine.sock`)

## The fix that works: rename the parent directory (don't delete the file)

You can't delete the socket, but **renaming its parent directory is a directory-metadata
operation** that sidesteps the access error. Docker recreates a clean directory + sockets on next
start.

```powershell
# Docker Desktop must be fully quit first (tray → Quit, or Stop-Process on "Docker Desktop").
$run     = "$env:LOCALAPPDATA\Docker\run"
$secrets = "$env:LOCALAPPDATA\docker-secrets-engine"
foreach ($d in @($run, $secrets)) {
  if (Test-Path $d) {
    # Only move it if it actually contains the orphaned reparse-point sockets.
    $orphan = Get-ChildItem -Force $d -ErrorAction SilentlyContinue |
              Where-Object { $_.Attributes -band [IO.FileAttributes]::ReparsePoint }
    if ($orphan) { Rename-Item $d "$d.broken" -Force }
  }
}
# Now start Docker Desktop from the GUI exe (see note below), let it rebuild the dirs.
```

After it comes up healthy, permanently disable the feature most prone to leaving bad sockets:

```powershell
docker desktop disable model-runner   # requires the engine to be running
```

### Two traps in the cleanup command itself

- **Don't start Docker with `docker desktop start` early in a login session** — it can hang. Launch
  the GUI executable instead: `Start-Process "C:\Program Files\Docker\Docker\Docker Desktop.exe"`.
- **Don't put `Remove-Item` and a `C:\Program…` path in the same command / script** — an
  auto-permission safety classifier can misread it as "delete a system directory" and block it.
  Rename (as above); never delete.

## It recurs on every reboot — so don't auto-start Docker *directly*

Because any unclean stop re-creates the orphan sockets, a plain "launch Docker on boot" entry will
crash-loop every morning. The autostart entry must run a **cleanup-then-start** script (rename
orphans → launch Docker GUI), not Docker itself. Wire that through Task Scheduler, not `HKCU\Run`
— see `unattended-operation.md`.

## When the rename fix does NOT work: hung WSL VM (seen on 4.82, 2026-07-17)

After the 4.77→4.82 auto-update killed the old backend, the usual rename-then-start fix failed:
Docker recreated a clean `run\` dir, then crashed **1 second later** on the same
`remove …dockerInference: The file cannot be accessed by the system` — the fresh socket was
poisoned instantly.

Root cause: the **WSL utility VM itself was hung**. `wsl --shutdown` (run twice) did not kill
`vmmemWSL`, and a stale `wslrelay.exe` from an earlier session survived too. The kernel's AF_UNIX
binding state persists while that VM/process state is stuck, so every newly created socket is
born broken. No non-admin remedy exists at that point.

**Fix: rename the poisoned dirs first, then reboot Windows.** Reboot clears the kernel socket
state; the logon cleanup-then-start script handles the rest. (This is the one case where reboot
*is* required — normally it isn't, see above.)

What did NOT work here:
- Rename + restart Docker (fix recurred in 1s)
- `wsl --shutdown` ×2 + killing `wslrelay` (vmmemWSL survived at hypervisor level)
- `EnableInference=false` / `EnableDockerAI=false` — **4.82 initializes the Inference manager and
  binds `dockerInference` regardless of these flags**. After recovery, run
  `docker desktop disable model-runner` anyway (it disables the model-runner feature; verify with
  `docker model status` → "Docker Model Runner is not running").

Tell-tale check before wasting time: if `Get-Process vmmemWSL` still returns after
`wsl --shutdown`, go straight to rename-dirs → reboot.

## Belt-and-suspenders

- Keep `model-runner` disabled (above) so the inference socket stops being created at all.
- In `settings-store.json`: `EnableInference=false`, `EnableDockerAI=false` (won't fix an existing
  crash, but reduces how often the bad socket is generated).
- Give containers `restart: unless-stopped` so once the engine is healthy they come back on their own.
