# rustdesk-multiline-triage

**Stop guessing why RustDesk dropped.** A Claude Code skill that carries the pitfalls learned
from months of running [RustDesk](https://rustdesk.com) over several lines (a self-hosted relay,
overlay VPNs, the LAN), so Claude checks the cause that is actually likely instead of the obvious
one.

## The pitfalls it saves you from

| What you see | What everyone tries first | What it actually was |
|---|---|---|
| `os error 10054`, "forcibly closed by the remote host" | Restart or rebuild the server | Usually **local**: a wedged Wi-Fi adapter, self-inflicted congestion through a VPN hub, an overlay path flapping, or a version mismatch. The skill makes Claude find out which line each drop used before touching the server |
| Session stuck at ~3 fps, both CPUs idle, network clean | Lower quality, switch codec, reconnect | The **controlled side's capture/encode pipeline has stalled**, typically after a RustDesk or GPU-driver upgrade. Only rebooting the controlled machine fixes it |
| Low fps on the quality monitor | Tune settings | Normal on a static screen: fps follows screen changes. Judge only while something moves |
| Laggy despite a fast link | Blame the network | **Old RustDesk on the controlled side** caps fps, or a per-peer setting is stuck on `low` |
| Your fix to a peer's settings file "didn't take" | Edit it again | RustDesk **rewrites the peer `.toml` when the session closes**; edit only with no session open |
| Host doesn't answer ping | Declare it offline | Many hosts drop ICMP but answer TCP 21118. Test the port |
| Two machines in the same room lag each other | Upgrade the VPN server | Their traffic is **hairpinning** out to a VPN hub and back. Pin them to the LAN line |
| Log full of `Failed to connect to ...:21115` | Chase it | Harmless when the server firewall doesn't open 21115 |
| "Did it sleep or did the network die?" | Guess | Windows System log: Kernel-Power 42/107 (sleep/resume), User32 1074 (who rebooted) |

`SKILL.md` has the full list, a symptom-to-layer table (10054, 10060, "Not ready", "Key
mismatch", relay-only, black screen) and a cheapest-first checklist for each line.

## Tools

Two standard-library Python scripts, no dependencies:

| Script | What it does |
|---|---|
| `scripts/check_lines.py` | Probes each line's TCP ports, separating DNS failure, "refused" and "timed out", and prints which lines work right now. Exit code 0 if at least one line is up, so it can run on a schedule and alert you |
| `scripts/scan_logs.py` | Counts known failure signatures in RustDesk logs, marks the harmless ones, and shows the hours where drops cluster, so "random disconnects" become a pattern |

```bash
cd rustdesk-multiline-triage
python scripts/check_lines.py --demo   # offline: local stand-in server, a closed port, a bad hostname
python scripts/scan_logs.py --demo     # fictional sample log in demo/
```

For real use, copy `lines.example.json` to `lines.json`, add your own hosts, and keep that file
out of version control (it is in `.gitignore`).

## Notes

Pitfalls come from hands-on operation; port numbers and log locations also match RustDesk's
public documentation; error codes are the standard Windows socket ones (10054 `WSAECONNRESET`,
10060 `WSAETIMEDOUT`, 10061 `WSAECONNREFUSED`). Not affiliated with the RustDesk project.

## Licence

MIT, see the repository root.
