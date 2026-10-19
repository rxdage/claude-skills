# claude-skills

**Hard-won troubleshooting knowledge, packaged so Claude uses it for you.**

These are [Claude Code](https://claude.com/claude-code) skills built from real incidents. Each
one records the failures that cost hours, the cause that turned out to be real, the fix that
worked, and **what did not work**. With a skill installed, Claude reaches for the likely cause
first instead of the obvious-but-wrong one.

| Skill | Saves you from |
|---|---|
| [`docker-windows-ops`](docker-windows-ops/) | Docker Desktop crash loops that survive reboots and reinstalls; autostart that silently doesn't fire under auto-login; PowerShell scripts that die on one Chinese comment; image and model downloads failing on a mainland-China network |
| [`rustdesk-multiline-triage`](rustdesk-multiline-triage/) | Chasing the server for `10054` drops that are really local; the ~3 fps encoder stall only a reboot of the controlled machine fixes; settings edits that vanish when the session closes. Ships with a line prober and a log scanner |

Each skill's README opens with a table: *what you see / what everyone tries first / what
actually works*.

## Install

Skills are discovered from `~/.claude/skills/<skill-name>/SKILL.md` (personal, all projects) or
`.claude/skills/<skill-name>/SKILL.md` inside a project (shared with that repo).

```bash
git clone https://github.com/rxdage/claude-skills.git
mkdir -p ~/.claude/skills
cp -r claude-skills/docker-windows-ops ~/.claude/skills/
cp -r claude-skills/rustdesk-multiline-triage ~/.claude/skills/
```

On Windows PowerShell:

```powershell
git clone https://github.com/rxdage/claude-skills.git
New-Item -ItemType Directory -Force "$HOME\.claude\skills" | Out-Null
Copy-Item -Recurse claude-skills\docker-windows-ops "$HOME\.claude\skills\"
Copy-Item -Recurse claude-skills\rustdesk-multiline-triage "$HOME\.claude\skills\"
```

Start a new Claude Code session afterwards. Claude picks a skill when your problem matches its
description ("Docker won't start on Windows", "RustDesk keeps dropping with 10054"), or you can
ask for it by name.

## Try the RustDesk tools

Standard-library Python only, no network needed:

```bash
cd rustdesk-multiline-triage
python scripts/check_lines.py --demo
python scripts/scan_logs.py --demo
```

`docker-windows-ops` is reference knowledge only; there is nothing to run.

## Contributing

Hit a new non-obvious failure and found the real fix? Open a PR adding it to the matching
reference as *symptom → real cause → fix → what didn't work*. The "what didn't work" line is
often the most valuable part.

## Licence

[MIT](LICENSE)
