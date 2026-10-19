"""Summarise RustDesk logs: which failure signatures occur, how often, and when.

    python scan_logs.py                     # scan the default log folders for this OS
    python scan_logs.py path/to/logs ...    # files or folders
    python scan_logs.py --demo              # scan the bundled fictional sample log
    python scan_logs.py --since 2026-10-01  # ignore older lines

Prints a count per signature, the hours in which drops cluster, and the first and last
example line of each signature, so you can see whether "random disconnects" are actually
one cause at one time of day. Standard library only.
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent

# (key, regex, meaning) - checked in order, first match wins, so the specific
# signatures come before the generic socket errors they often contain
SIGNATURES = [
    ("noise-21115", r"failed to connect to \S+:21115",
     "HARMLESS: online-status port 21115 closed on the server firewall; ignore"),
    ("key-mismatch", r"key mismatch",
     "client and server keys differ (key field empty, old key, or wrong server)"),
    ("relay-failed", r"failed to connect via relay|relay.*(fail|error)",
     "relay server unreachable or rejected the session"),
    ("not-ready", r"not ready|failed to register|register.*(fail|timeout)",
     "client could not register with the ID server (UDP/TCP 21116)"),
    ("id-not-exist", r"id does not exist|id not exist",
     "target is not registered on this ID server (offline, or using another server)"),
    ("punch-failed", r"hole.?punch|punch.*(fail|timeout)",
     "P2P hole punching failed; session falls back to relay (slower)"),
    ("reset-10054", r"10054|connection reset|forcibly closed|ECONNRESET",
     "TCP stream reset; usually LOCAL (Wi-Fi wedge, congestion, overlay flap) - find the line it rode"),
    ("timeout-10060", r"10060|timed out|deadline has elapsed",
     "no answer: host down, port filtered, or the line itself is down"),
    ("refused-10061", r"10061|connection refused",
     "host reachable but nothing listening (service stopped, wrong port)"),
    ("network-changed", r"network.*(changed|unreachable)|10051|10065",
     "local network changed or route lost (Wi-Fi switch, VPN reconnect, sleep)"),
]
COMPILED = [(k, re.compile(rx, re.I), m) for k, rx, m in SIGNATURES]
STAMP = re.compile(r"(\d{4}-\d{2}-\d{2})[ T](\d{2}):(\d{2})")


def default_dirs() -> list[Path]:
    home = Path.home()
    dirs = []
    if os.name == "nt":
        appdata = os.environ.get("APPDATA")
        if appdata:
            dirs.append(Path(appdata) / "RustDesk" / "log")
        # logs of the RustDesk Windows service (runs as LocalService)
        windir = os.environ.get("WINDIR", "C:/Windows")
        dirs.append(Path(windir) / "ServiceProfiles/LocalService/AppData/Roaming/RustDesk/log")
    elif sys.platform == "darwin":
        dirs.append(home / "Library/Logs/RustDesk")
    else:
        dirs += [home / ".local/share/logs/RustDesk", Path("/root/.local/share/logs/RustDesk")]
    found = []
    for d in dirs:
        try:
            if d.is_dir():
                found.append(d)
        except PermissionError:  # the service profile needs an elevated shell
            print(f"(no permission to read {d}; run elevated to include service logs)")
    return found


def iter_files(paths: list[Path]):
    for p in paths:
        if p.is_file():
            yield p
        elif p.is_dir():
            yield from sorted(f for f in p.rglob("*") if f.is_file() and f.suffix in (".log", ".txt", ""))


def scan(files, since: str | None):
    counts = Counter()
    hours = defaultdict(Counter)
    first, last = {}, {}
    scanned = 0
    for f in files:
        scanned += 1
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for line in text.splitlines():
            m = STAMP.search(line)
            if since and m and m.group(1) < since:
                continue
            for key, rx, _ in COMPILED:
                if rx.search(line):
                    counts[key] += 1
                    if m:
                        hours[key][m.group(2)] += 1
                    first.setdefault(key, line.strip())
                    last[key] = line.strip()
                    break
    return scanned, counts, hours, first, last


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("paths", nargs="*", type=Path)
    ap.add_argument("--demo", action="store_true", help="scan demo/sample.log")
    ap.add_argument("--since", help="YYYY-MM-DD; skip older lines")
    args = ap.parse_args(argv)

    paths = [HERE.parent / "demo" / "sample.log"] if args.demo else args.paths or default_dirs()
    if not paths:
        print("No RustDesk log folder found; pass a path.")
        return 2
    scanned, counts, hours, first, last = scan(iter_files(paths), args.since)
    print(f"Scanned {scanned} file(s) under: " + ", ".join(str(p) for p in paths))
    if not counts:
        print("No known failure signatures found.")
        return 0
    meaning = {k: m for k, _, m in SIGNATURES}
    for key, n in counts.most_common():
        peak = ", ".join(f"{h}:00 x{c}" for h, c in sorted(hours[key].items(), key=lambda x: -x[1])[:3])
        print(f"\n{key}  x{n}   {meaning[key]}")
        if peak:
            print(f"  busiest hours: {peak}")
        print(f"  first: {first[key][:160]}")
        if last[key] != first[key]:
            print(f"  last:  {last[key][:160]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
