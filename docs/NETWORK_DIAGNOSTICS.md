# LAN diagnostics across two machines (`--netdiag`)

A mixed-platform connect failure needs **both** platforms, so the game ships one
command that each machine runs once and writes one JSON file. Diff the two
files instead of guessing: bind address and port, every local address a peer
could dial, the raw `connect_ex` code the join path classifies, whether TCP
arrived at the listener, and — separately — whether the `hello`/`welcome`
handshake completed. That last split is what distinguishes a blocked SYN from a
version/content rejection.

## What is known about issue #56

**Root cause (fixed, proven on a real Windows runner): the content hash.** The
host compared `content_hash()` of the game data and rejected the `hello` with
*content mismatch* in both directions. `content_hash()` read assets through
`Path.read_text()` **with no encoding**, so Windows used its locale default
(cp1252) and macOS UTF-8; `maps/skirmish01.json` is named
`Sector Duel — Kotarri Sector`, so the two machines hashed different text.

| Where | `content_hash` |
|---|---|
| Windows, real `windows-latest` runner, before the fix | `3caadfefd77d05af…` |
| macOS, before the fix | `c285da46fe94b83f…` |
| macOS with cp1252 emulated (before the fix) | `3caadfefd77d05af…` — the Windows value |
| Windows, real runner, after the fix | `c285da46fe94b83f…` — the macOS value |

Assets are now read as explicit UTF-8 everywhere (text mode also normalizes CRLF
vs LF, so a Windows checkout hashes like an LF one).

Secondary, kept as robustness — **not** the cause: `LanSession.join` compared the
`connect_ex()` result against POSIX `errno` values only. `classify_connect_result()`
now accepts both families and the failure text names the raw code
(`connect_failure_message`). Windows happened to alias `errno.EWOULDBLOCK` to
`10035`, so the join path already accepted the code it returns in practice.

**Still open: cross-platform simulation identity.** `sim_fingerprint` over 60
ticks of the real LAN scene differs between the two machines
(macOS `b8b05b9c…`, Windows `01a9f663…`). The handshake no longer blocks, but a
mixed pair whose ticks checksum differently will raise `Desync` as soon as the
match runs, so the report carries a per-tick timeline (first divergent tick) and
per-component digests (which part of the state diverged) to diff the two files.
Compare that value before playing; an equal value means the pair is safe to
launch.

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

Before step 3, compare `sim_fingerprint.checksum` in the two `info` reports. A
different value means the two machines simulate the same scene differently: the
handshake will succeed but the lockstep checksum comparison will desync the
match, so report the pair of values instead of playing a match that cannot last.

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

Two more keys are worth knowing when reading `info`:

- `socket_probes.refused_pending` — the production poll loop (`select` for
  writability, then `SO_ERROR`) dialing a port nothing listens on. Windows was
  observed not to report the refusal inside the wait at all
  (`completion_reported: false`), while macOS reports it in milliseconds; when
  that happens the report says so, because a join to a non-listening host will
  then wait for the lockstep timeout instead of failing at once. It does not mean
  the firewall blocked a loopback port.
- `sim_fingerprint.timeline` / `sim_fingerprint.components` — the per-tick
  checksums and the per-top-level-key digests of the 60-tick scene. Diff the two
  machines' files: the first differing tick entry localizes **when** the pair
  diverges and the differing `components` keys name **what** diverged.

## What this does and does not prove

- `info` and the loopback pairing prove the app's own listen/accept/handshake
  path on that machine — never the platform pairing.
- A real two-machine run proves the pairing; a LAN match played to a launched
  game is the acceptance that closes the issue.
- CI (`windows-signal.yml`) runs the same probe and the focused LAN tests on
  `windows-latest`: portability evidence, not GL, input-feel or LAN pairing.
- The Windows job lowers `STAR_ARMADA_PACING_FLOOR` (27 → 15 ticks/s). Pacing is
  hardware acceptance and a shared 2-vCPU runner paced 20.9 ticks/s; the
  correctness clauses — identical checksums every tick, every tick executed, AI
  and human commands present — still gate there. Measure the real floor on the
  machine that plays the match.
