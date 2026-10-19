# PowerShell & Windows scripting traps

These bit hard during this deployment. Most cost an hour each because the failure mode looks like
something else.

## Trap #1 — ASCII-only `.ps1`, or it dies parsing

**Windows PowerShell 5.1 reads a UTF-8-without-BOM file as the legacy ANSI code page (GBK on a
Chinese system).** Any non-ASCII byte (a Chinese comment, a smart quote, `→`, `μ`) gets mis-decoded,
which corrupts brace/quote matching and throws:

```
Missing closing '}' in statement block or type definition.
```

The script then **exits instantly with no log**, so it looks like "the task didn't run" rather than
"the script failed to parse."

**Fix:** write scripts that will run under 5.1 as **pure ASCII** — English comments and log lines,
no fancy punctuation. If you must emit UTF-8, write it *with* a BOM, but ASCII-only is the safe
default for autostart scripts. (This is also why the startup script in `unattended-operation.md`
logs in English.)

## Trap #2 — native-command stderr looks like a failure but isn't

When PowerShell runs a native exe (`docker`, `git`, `python`) that writes to **stderr**, it renders
those lines as red `NativeCommandError` text, e.g.:

```
docker.exe :
At line:2 char:1
+ & $docker compose ...
    + FullyQualifiedErrorId : NativeCommandError
```

This is **not** a failure — `docker`, `git push`, `pip`, etc. write normal progress to stderr. Judge
success by the actual output / exit code (`$LASTEXITCODE`), not the red text. Don't add `2>&1`
to "fix" it: in 5.1 that wraps each stderr line in an ErrorRecord and can flip `$?` to `$false`
even on exit 0.

## Trap #3 — a kill-filter that matches its own process

A cleanup line like "kill any powershell whose command line contains `startup`" will match **the
very command you're running** (its own command line contains the pattern) and the script kills
itself (exit 255).

**Fix:** exclude your own PID, and build the match string so your command line doesn't literally
contain it:

```powershell
$me = $PID
$needle = 'start' + 'up'   # so THIS process's command line doesn't contain the literal
Get-CimInstance Win32_Process |
  Where-Object { $_.ProcessId -ne $me -and $_.CommandLine -like "*$needle*" } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
```

## Trap #4 — Claude can't silently elevate; UAC is the human's job

Anything needing admin (registry under HKLM, registering a scheduled task with `-RunLevel Highest`,
installing an MSI) must be confirmed by the operator in a **UAC prompt**. `Start-Process -Verb RunAs`
is the way to *trigger* that prompt — but the click is theirs. Auto-permission modes additionally
block `ExecutionPolicy Bypass + elevation`, so don't try to route around the prompt; surface it and
label the step **"需手动操作 / manual"**.

## Trap #5 — this shell is PowerShell 5.1, mind the syntax

- No `&&` / `||` pipeline chain operators. Use `cmd1; if ($?) { cmd2 }`.
- No ternary `?:`, null-coalescing `??`, or `?.` — use `if/else` and explicit `$null -eq` checks.
- Unix commands don't exist: `head`→`Select-Object -First N`, `which`→`(Get-Command x).Source`,
  `touch`→`New-Item -ItemType File` (never `New-Item -Force` on an existing file — it truncates),
  `rm -rf`→`Remove-Item -Recurse -Force`.
- Multi-line strings (commit messages, file bodies) to a native exe: use a **single-quoted
  here-string** `@'…'@`, and the closing `'@` must be at **column 0** (no indentation) or it's a
  parse error.
- Default file encoding is UTF-16LE-BOM; pass `-Encoding ascii`/`utf8` when another tool will read
  the file.

## When a Bash tool is also available

Git Bash / a POSIX `sh` is often present alongside PowerShell. For quick file ops (`rm -f`,
heredocs, `sed`) it can be simpler and dodges the encoding traps — just remember each tool needs its
own syntax and the working directory may differ. Use whichever avoids the trap you're near.
