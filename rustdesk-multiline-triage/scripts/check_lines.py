"""Probe every RustDesk access line and say which ones are usable right now.

A "line" is one way of reaching the remote machine: a self-hosted ID/relay server, the
public RustDesk servers, a VPN overlay (Tailscale, ZeroTier, WireGuard) with direct IP
access, or the LAN. Each line lists the TCP ports that must answer for it to work.

    python check_lines.py lines.json          # probe your lines
    python check_lines.py --demo              # self-contained demo, no network needed
    python check_lines.py lines.json --json   # machine-readable result

Standard library only. UDP cannot be verified by a connect test; see the notes printed
for lines that rely on UDP 21116 (hole punching / registration).
"""
from __future__ import annotations

import argparse
import json
import socket
import sys
import threading
import time
from pathlib import Path

# Default TCP ports per line kind (RustDesk documentation, self-hosting section).
DEFAULT_PORTS = {
    "id-server": [21115, 21116],   # NAT test, ID registration / signalling
    "relay": [21117],              # relay
    "id-relay": [21115, 21116, 21117],
    "direct-ip": [21118],          # "Enable direct IP access" on the controlled side
    "web": [21118, 21119],         # web client websockets
}

UDP_NOTE = ("UDP 21116 carries registration heartbeats and hole punching; a TCP pass does "
            "not prove it is open. If sessions only ever run via relay, check UDP on the "
            "server firewall / cloud security group.")


def probe(host: str, port: int, timeout: float) -> tuple[bool, float | None, str]:
    """TCP connect; returns (ok, milliseconds, detail)."""
    start = time.perf_counter()
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True, (time.perf_counter() - start) * 1000, "open"
    except socket.timeout:
        return False, None, "timeout (filtered or host down)"
    except ConnectionRefusedError:
        return False, None, "refused (host up, nothing listening)"
    except OSError as e:
        return False, None, f"{type(e).__name__}: {e.strerror or e}"


def resolve(host: str) -> tuple[bool, str]:
    try:
        infos = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
        return True, f"{len({i[4][0] for i in infos})} address(es)"
    except socket.gaierror as e:
        return False, f"DNS failed: {e.strerror}"


def check(lines: list[dict], timeout: float) -> list[dict]:
    results = []
    for line in lines:
        host = line["host"]
        ports = line.get("tcp_ports") or DEFAULT_PORTS.get(line.get("kind", ""), [])
        dns_ok, dns_detail = resolve(host)
        probes = []
        if dns_ok:
            for port in ports:
                ok, ms, detail = probe(host, port, timeout)
                probes.append({"port": port, "ok": ok, "ms": ms, "detail": detail})
        up = dns_ok and probes and all(p["ok"] for p in probes)
        partial = dns_ok and any(p["ok"] for p in probes) and not up
        status = "UP" if up else "PARTIAL" if partial else "DOWN"
        results.append({"name": line["name"], "kind": line.get("kind", ""), "host": host,
                        "status": status, "dns": dns_detail, "probes": probes,
                        "hint": hint(line, status, dns_ok, probes)})
    return results


def hint(line: dict, status: str, dns_ok: bool, probes: list[dict]) -> str:
    kind = line.get("kind", "")
    if not dns_ok:
        return "Fix name resolution first (typo, expired DDNS, VPN DNS not pushed)."
    if status == "UP":
        return UDP_NOTE if kind in ("id-server", "id-relay") else ""
    failed = [p for p in probes if not p["ok"]]
    if all("refused" in p["detail"] for p in failed):
        return ("Host answers but the service is not listening: is hbbs/hbbr (or the RustDesk "
                "service on the target) running and bound to these ports?")
    if kind == "direct-ip":
        return ("Direct IP needs 'Enable direct IP access' on the controlled machine, its "
                "firewall to allow 21118, and the overlay/VPN to be connected on both ends.")
    return ("Timeouts: firewall, cloud security group, ISP block or the host is down. "
            "Test from another network to tell which side drops it.")


def report(results: list[dict]) -> str:
    out = []
    width = max(len(r["name"]) for r in results)
    for r in results:
        ports = "  ".join(
            f'{p["port"]}:{"ok " + format(p["ms"], ".0f") + "ms" if p["ok"] else "FAIL"}'
            for p in r["probes"]) or r["dns"]
        out.append(f'{r["status"]:<8}{r["name"]:<{width + 2}}{r["host"]:<28}{ports}')
        if r["status"] != "UP":
            for p in r["probes"]:
                if not p["ok"]:
                    out.append(f'{"":8}  port {p["port"]}: {p["detail"]}')
        if r["hint"]:
            out.append(f'{"":8}  -> {r["hint"]}')
    usable = [r["name"] for r in results if r["status"] == "UP"]
    out.append("")
    out.append("Usable now: " + (", ".join(usable) if usable else "none"))
    return "\n".join(out)


def demo_lines() -> tuple[list[dict], list[socket.socket]]:
    """Two local listeners stand in for a healthy server; the rest fail on purpose."""
    # Bind to the address "localhost" resolves to first (IPv6 or IPv4), loopback only,
    # so probes connect at once and no firewall prompt appears.
    family, _, _, _, addr = socket.getaddrinfo("localhost", 0, type=socket.SOCK_STREAM)[0]

    def listener():
        return socket.create_server((addr[0], 0), family=family)

    socks = [listener() for _ in range(2)]
    ports = [s.getsockname()[1] for s in socks]

    def accept_forever(sock):
        while True:
            try:
                conn, _ = sock.accept()
                conn.close()
            except OSError:
                return

    for s in socks:
        threading.Thread(target=accept_forever, args=(s,), daemon=True).start()
    closed = listener()
    closed_port = closed.getsockname()[1]
    closed.close()  # nothing listens here any more -> refused
    lines = [
        {"name": "line-A self-hosted", "kind": "id-relay", "host": "localhost", "tcp_ports": ports},
        {"name": "line-B direct-ip", "kind": "direct-ip", "host": "localhost",
         "tcp_ports": [closed_port]},
        {"name": "line-C backup server", "kind": "id-server", "host": "rustdesk-backup.invalid"},
    ]
    return lines, socks


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("config", nargs="?", help="lines JSON (see lines.example.json)")
    ap.add_argument("--demo", action="store_true", help="run against local stand-in servers")
    ap.add_argument("--timeout", type=float, default=3.0, help="seconds per TCP probe")
    ap.add_argument("--json", action="store_true", help="print JSON instead of a table")
    args = ap.parse_args(argv)

    if args.demo:
        lines, _keep = demo_lines()
    elif args.config:
        lines = json.loads(Path(args.config).read_text(encoding="utf-8"))["lines"]
    else:
        ap.error("give a lines JSON file or --demo")
    results = check(lines, args.timeout)
    print(json.dumps(results, indent=2) if args.json else report(results))
    return 0 if any(r["status"] == "UP" for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
