---
name: rustdesk-multiline-triage
description: >-
  Triage RustDesk remote-desktop problems on setups with more than one access "line"
  (several self-hosted hbbs/hbbr servers, the public servers, a VPN overlay such as
  Tailscale / ZeroTier / WireGuard with direct IP access, the LAN). Use when the user
  reports RustDesk sessions dropping (os error 10054, "connection reset", "forcibly
  closed"), timeouts (10060), "Not ready. Please check your connection", "Key mismatch",
  "ID does not exist", laggy or blurry sessions, sessions that only work via relay,
  a remote PC unreachable from outside, or wants to know which of their lines is
  usable right now. Carries field-tested pitfalls (10054 that is really a local Wi-Fi
  wedge, the ~3 fps encoder stall, peer settings rewritten on close) that save hours.
---

# RustDesk multi-line triage

Goal: find **which line** is failing and **which layer** (name resolution, server process,
firewall/ports, NAT traversal, the target machine, or the session settings), then fix only that.
Most "RustDesk is broken" reports are one line down while the user keeps retrying it.

Tools in this skill (Python 3.8+, standard library only):

- `scripts/check_lines.py lines.json` probes every line's TCP ports and prints which are usable.
  Copy `lines.example.json` to `lines.json` with the user's hosts. `--demo` runs offline.
- `scripts/scan_logs.py [paths]` counts failure signatures in RustDesk logs and shows the hours
  in which they cluster. With no path it scans this OS's default log folders. `--demo` uses a
  bundled sample.

## 0. Pitfalls that each cost hours (read these first)

These come from months of running RustDesk over several lines (self-hosted relay, overlay VPNs,
LAN). Each one looked like something else.

1. **10054 is usually NOT the far end.** "Connection reset by the remote host" sends everyone to
   the server. In practice the causes were local: a wedged Wi-Fi adapter (seen with a Realtek
   8821CE; reboot cures it for a while, a cable cures it for good), self-inflicted congestion
   (bulk traffic hairpinning through a small VPS hub), an overlay path flapping, or version
   skew. Prove which line each drop rode before suspecting the server.
2. **Attribute every drop to a line.** Drops on *all* lines at once mean a local cause; drops on
   one line mean that path. While a session runs, list RustDesk's TCP connections and read the
   remote address: overlay subnet = VPN line, LAN subnet = LAN, `:21117` = relay.
   ```powershell
   $ids = (Get-Process rustdesk -ErrorAction SilentlyContinue).Id
   Get-NetTCPConnection -State Established | Where-Object { $ids -contains $_.OwningProcess } |
     Select-Object LocalAddress, RemoteAddress, RemotePort
   ```
3. **Three-layer probe before blaming anything far away:** ping the local gateway, connect to
   the ID server's TCP 21116, ping/connect to a LAN peer. Gateway answers in ~2 ms but
   everything beyond is dead = local adapter wedged or uplink saturated, not the server.
4. **"~3 fps, CPU and GPU idle, link clean" = the controlled side's capture/encode pipeline has
   stalled.** New sessions do not fix it; rebooting the *controlled* machine does. Typically
   follows an in-place RustDesk or GPU-driver upgrade. Judge by what you see, not status icons.
5. **Low fps on a static screen is normal.** The quality monitor's fps is driven by screen
   changes; only judge fps while something is moving.
6. **Lag: check versions on both ends first.** The controlled side's encoder sets the fps
   ceiling, so an old version there caps a new client. Then check the per-peer settings in
   `%APPDATA%\RustDesk\config\peers\<peer-id>.toml` (`image_quality` may be stuck on `low`,
   custom fps; `show_quality_monitor = true` gives live numbers).
7. **Never edit a peer `.toml` while a session to that peer is open.** RustDesk rewrites it on
   close and your edit silently disappears.
8. **Ping-dead is not host-dead.** Many hosts drop ICMP but answer TCP 21118 (direct IP). Test
   the port, not ping.
9. **Machines in the same room must use the LAN line.** Otherwise their traffic goes out to a VPN
   hub and back, which is slow and congests the hub for every other session. Move big files over
   SMB, not through the remote session.
10. **Log noise that means nothing:** repeated `Failed to connect to <server>:21115` is harmless
    when the server firewall simply does not open 21115 (online-status queries).
11. **Did it sleep, or did the network wedge?** The Windows System log answers it: Kernel-Power
    42/107 = sleep/resume (none = it never slept), User32 1074 = who triggered a reboot.
12. **A watchdog task you cannot see may still be running.** Tasks registered as SYSTEM do not
    show up in a non-elevated `Get-ScheduledTask`; that is normal, not a missing task.

## 1. Get the facts first (ask, don't guess)

1. Which lines exist? For each: ID server, relay server, key, or direct IP/hostname.
   `lines.json` is the inventory; build it with the user if none exists.
2. Exact error text, and on which side (controlling or controlled machine).
3. When: always, at certain hours, after sleep/reboot, after a network change, after N minutes.
4. Does the session toolbar / connection info say **direct** or **relay**?
5. Versions of the client, the controlled side and the server (`hbbs`/`hbbr` image tag).

## 2. Map the symptom to the layer

| Symptom | Most likely layer | First check |
|---|---|---|
| `os error 10054`, "connection reset", "forcibly closed" mid-session | Usually local (pitfall 1): Wi-Fi wedge, congestion, overlay flap, version skew. Less often the relay restarted, a NAT/firewall idle timeout, or the target slept | Which line did each drop ride (pitfall 2)? `scan_logs.py`: do drops cluster at fixed times? Then the three-layer probe (pitfall 3). Only then `docker logs hbbr` |
| `10060` / "timed out" | Port filtered or host down | `check_lines.py`: timeout on every port means firewall, security group or host down |
| `10061` / "refused" | Host up, service not listening | Is `hbbs`/`hbbr` running? On the target: is the RustDesk service running? |
| "Not ready. Please check your connection" | Client cannot register with the ID server | TCP 21116 and **UDP 21116** reachable; correct ID server in settings; DNS |
| "Key mismatch" | Client key field differs from the server's `id_ed25519.pub` | Copy the key again from the server's data folder; check the client is not pointed at another server |
| "ID does not exist" | Target is offline or registered on a different ID server | Both ends must use the same ID server; check the target's own status line |
| Works only via relay, never direct | Hole punching failing (symmetric NAT, UDP blocked, CGNAT) | Normal on many networks; if latency matters, add a direct-IP line over a VPN overlay |
| Laggy, blurry, low FPS | Relay far away, low bandwidth, software codec | See section 4 |
| Black screen / no input after connecting | Target-side permissions or display state | Windows: UAC / login screen needs the service install; macOS: Screen Recording and Accessibility permissions; Linux: Wayland support is limited, try an X11 session |

## 3. Per-line checks, cheapest first

1. **Name resolution.** `check_lines.py` reports DNS failures separately. Dynamic DNS that
   expired, or a VPN that does not push its DNS, looks exactly like a dead server.
2. **TCP ports.** Self-hosted defaults: `21115` (NAT test), `21116` (ID/signalling, TCP **and
   UDP**), `21117` (relay), `21118`/`21119` (web client websockets). Direct IP access listens on
   `21118` on the controlled machine. Custom ports go in `tcp_ports`.
3. **UDP 21116.** A TCP probe cannot prove it. If registration flaps ("Not ready") while TCP
   checks pass, check UDP in the server firewall and cloud security group.
4. **Server process.** `docker ps`, `docker logs hbbs`, `docker logs hbbr`; restart counts and
   timestamps that match the client's drops explain 10054 storms.
5. **Target machine.** Power plan sleep/hibernate, the RustDesk service, Wi-Fi power saving,
   the overlay VPN client staying connected after sleep, Windows Firewall rules for 21118.

Log locations (client side): Windows `%APPDATA%\RustDesk\log\` (outgoing sessions in
`flutter_ffi\rustdesk_rCURRENT.log`: look for `Connection closed`, `Set fps`,
`handle_peer_info` for the peer's version; incoming sessions under `cm\`), and for the service
`C:\Windows\ServiceProfiles\LocalService\AppData\Roaming\RustDesk\log\`; macOS
`~/Library/Logs/RustDesk/`; Linux `~/.local/share/logs/RustDesk/`. Settings live next to them
under `config\` (`RustDesk2.toml` holds the server and key settings).

## 4. Lag and image quality

- Check **direct vs relay** first. A relay in another region adds its round trip to every frame.
  Fix the line before touching codec settings.
- Image quality: "Optimize reaction time" for remote work over weak links, "Balanced" otherwise.
  Lower the resolution or turn off the remote wallpaper for large displays.
- Codec: prefer a hardware codec (H.264/H.265) when both ends support it; VP8 is lighter on old
  CPUs than VP9/AV1.
- If FPS is low on a fast link, the bottleneck is CPU encode on the controlled side; check its
  CPU in Task Manager / `top` during the session.

## 5. Fallback order and keeping lines healthy

- Keep at least two independent lines (different server, different network path). Write the
  fallback order down so the user switches lines instead of retrying a dead one.
- Run `check_lines.py` on a schedule (Task Scheduler / cron) and alert on a change of
  `Usable now`. Exit code is `0` when at least one line is up, `1` when none is.
- After a fix, re-run `check_lines.py` and reproduce the original action (connect, idle for the
  usual drop interval, transfer a file) before calling it solved.

## Safety

- Never paste the user's server key, device IDs, passwords or public IPs into issues, chats or
  files that will be shared. `lines.json` belongs in `.gitignore`.
- Changing firewall rules, security groups or installing the RustDesk service needs the user's
  confirmation; say exactly what will change.
