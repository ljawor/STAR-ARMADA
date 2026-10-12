# LAN diagnostics across two machines (`--netdiag`)

A mixed-platform connect failure needs **both** platforms, so the game ships one
command that each machine runs once and writes one JSON file. Diff the two
files instead of guessing: bind address and port, every local address a peer
could dial, the raw `connect_ex` code the join path classifies, whether TCP
arrived at the listener, and — separately — whether the `hello`/`welcome`
handshake completed. That last split is what distinguishes a blocked SYN from a
version/content rejection.

## What is known about issue #56

The Windows **client** was rejected before any packet mattered: `connect_ex()`
returns the raw Winsock in-progress code (`WSAEWOULDBLOCK` = 10035) on Windows,
while `LanSession.join` compared that number against POSIX `errno` values, so
every join from Windows failed with `Connection failed` no matter who hosted.
`classify_connect_result()` now accepts both code families and the failure text
names the code (`connect_failure_message`). Windows **hosting** is a different
failure mode and is what the listen probe below is for: an inbound firewall rule
(a dismissed first-run prompt leaves a *block* rule that also blocks outgoing
traffic) or the client dialing the wrong interface address.

## Running it

From a console (source checkout):

```sh
python main.py --netdiag info
python main.py --netdiag listen --wait 60
python main.py --netdiag connect --address 192.168.1.42 --wait 20
```

In a frozen build there is no console (`console=False`), so the report file is
the deliverable. On Windows:

```powershell
Start-Process -FilePath '.\STAR ARMADA.exe' -ArgumentList '--netdiag','info' -Wait
Start-Process -FilePath '.\STAR ARMADA.exe' -ArgumentList '--netdiag','listen','--wait','60' -Wait
Start-Process -FilePath '.\STAR ARMADA.exe' -ArgumentList '--netdiag','connect','--address','192.168.1.97','--wait','20' -Wait
```

Reports default to `<user data dir>/netdiag/netdiag-<mode>-<stamp>.json`
(`%APPDATA%\STAR ARMADA\netdiag\` on Windows,
`~/Library/Application Support/STAR ARMADA/netdiag/` on macOS) and `--out FILE`
overrides the path. On Windows a message box shows the verdict and the path.
Exit status: `0` completed, `1` the probe found a connectivity failure, `2` the
run itself failed (bad arguments, unwritable report path).

## Test both directions

1. **Windows hosts, macOS joins.** On Windows: `--netdiag listen --wait 60`.
   Read the address it prints (route-preferred, first in the list). On the Mac:
   `--netdiag connect --address <that address>`. Then compare the two files.
2. **macOS hosts, Windows joins.** Same with the roles swapped.
3. **The game itself**, not just the probe: host in the Multiplayer/LAN lobby on
   one machine, join the other, both READY, launch.

## Reading the outcome

| Listen report | Connect report | Meaning |
|---|---|---|
| peer with `handshake_completed: true` | `reached_lobby: true` | The pairing works; the earlier failure is gone. |
| peer with `tcp_arrived: true`, no handshake, `session.error` mentions *mismatch* | `Connection failed` / mismatch | Version or data mismatch — install the same release on both machines and compare `game_version` + `content_hash`. |
| `connections: []` | `blocking_code` 10060/60 (timeout) | Nothing answers: the host's firewall drops the SYN (Windows: allow the program inbound on the **Private** profile), or the client dialed an address that is not the host's LAN address. |
| `connections: []` | `blocking_code` 10061/61 (refused) | Nothing is listening on that port — the host was not in the lobby yet, or a different port. |
| `bind_error` / `port_status.bindable: false` | — | The port is taken or blocked on the host machine. |

Only `info` mode needs no peer: it reports the environment, the addresses, the
port's bindability, a real host+join pairing on that machine (so a local defect
is visible before any cross-machine test), and the code that platform reports
for a connection that cannot finish — printed by both machines, so neither side
is assumed to behave like the other.

## What this does and does not prove

- `info` and the loopback pairing prove the app's own listen/accept/handshake
  path on that machine — never the platform pairing.
- A real two-machine run proves the pairing; a LAN match played to a launched
  game is the acceptance that closes the issue.
- CI (`windows-signal.yml`) runs the same probe and the focused LAN tests on
  `windows-latest`: portability evidence, not GL, input-feel or LAN pairing.
