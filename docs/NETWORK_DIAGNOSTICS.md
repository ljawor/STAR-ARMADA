# LAN diagnostics across two machines (`--netdiag`)

## Automatic bounded failure reports (separate from `--netdiag`)

The actual main failure paths write best-effort reports to
`USER_DIR/diagnostics/failure-0.json` through `failure-7.json`, using the same
persistence root as saves/settings, never the frozen application bundle.
Each report contains schema version, Unix timestamp, game build/version,
simulation tick (or `null`), phase (`transport`, `input`, `simulation`,
`termination`, `unhandled`), a fixed reason classification, and a built-in Python
exception class if available. Custom exception names become `Exception`.
Reasons include `disconnect`, `desync`, `loading_timeout`, `lockstep_timeout`,
`peer_timeout`, `connect_failure`, `protocol_rejection`, `controlled_termination`
and `python_exception`. Arbitrary caller/peer error text is never persisted.

Main records controlled launched-match LAN errors **before** session/state
teardown. Errors inside LAN `advance` retain their `simulation` phase when main
observes them through polling; other poll failures use `transport`. Main input
and simulation Python exception boundaries record those phases. The installed
`sys.excepthook` records other uncaught Python exceptions, including
renderer/display/input-update failures, as `unhandled`, then calls the original
Python hook. Its usual stderr traceback is **not copied into these files**.
The initiating peer may report `desync` while another reports `disconnect`;
collect reports from both computers.

The automatic ring deliberately omits addresses, ports, nicknames, bearer tokens,
command payloads, arbitrary messages, traceback paths/source/locals, snapshots,
and replay contents. It uploads nothing. Unlike this ring, the explicitly invoked
`--netdiag` reports below contain addresses and detailed environment information;
review/redact those files before sharing.

**Bounds:** at most eight JSON reports, each below 1 KiB. Slots wrap in-process
and restart at zero after a process restart; this does not guarantee retaining
the eight newest events across restarts. In-process writes are serialized;
contents are fsynced before atomic replacement. Permission, full-disk,
serialization and replace failures return `False`, never an exception into play.
At most eight bounded `.tmp` paths may remain after abrupt termination or failed
cleanup. Persistence is best effort, not guaranteed through power loss.
A normal voluntary leave or nonfatal local order rejection creates no failure
report; local rejections show an in-match notice instead.

**Limits:** captures controlled **launched-match** LAN termination and Python
exceptions reaching the installed hook. Ordinary lobby errors remain UI notices.
Imports before menu persistence-root initialization, background-thread errors,
signals, native GL/access violations, forced kills and `os._exit` are not captured.
Use OS crash reports/stderr for those incidents. These reports contain no scene
performance timings and do not implement production reconnect/resume; the
snapshot/transfer/ledger code remains a foundation only (`LAN_RECONNECT.md`).

Focused verification (temporary isolated report roots, real loopback TCP,
real managers, natural L/Backspace and AST-loaded actual main boundaries):

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=tests .venv/bin/python -m unittest \
  test_lan_human_safety test_lan_failure_diagnostics -v
```

The tests cover host/client origins, every exercised tick's full-precision hash,
atomic local limits, fatal malformed peer input, paid crew conservation,
boarding/capture, and accepted-command once-only recording/replay. They are not
native-GL/full-application or frozen Mac/Windows mixed-machine acceptance.


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

**Fixed: cross-platform simulation identity.** The same 60-tick LAN scene hashed
differently on the two machines (macOS `b8b05b9c…`, Windows `01a9f663…`) because
the simulation computed `sin`/`cos`/`atan2` with the platform's `libm` (macOS vs
UCRT). `game/core/detmath.py` now provides those functions built from the
correctly rounded operations only (`+ - * / sqrt`), and every simulation module
imports it instead of the platform module; rendering keeps the fast one. Both
machines now report the same `sim_fingerprint` — verified on real Windows in CI
(canonical and contact scene, 600 ticks of it identical every tick) and the value
is carried in every `info` report so a pair can check before playing.

The report carries, per profile, a per-tick timeline (first divergent tick) and
per-component digests (which part of the state diverged), so two files can be
diffed instead of guessed at if this ever regresses.

**Two scene profiles, because one scene was not evidence.** `canonical` is the
strategic LAN map: two fleets, 22000 units apart, where no weapon is ever in range
and no two ships are ever inside separation range. `contact` stages the same map's
ships into an actual engagement, so the collision, movement, weapon and AI maths
all execute every tick. A check that only runs `canonical` cannot see a divergence
in the collision maths — that gap let a broken separation module pass the Windows
job while 86 local tests failed — so a pair of machines is compatible only when
**every** profile agrees.

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

Before step 3, compare every `sim_fingerprints` entry in the two `info` reports —
`tools/compare_netdiag.py MAC.json WIN.json` does the comparison and names the
profile, the first divergent tick and the differing state components. A different
value means the two machines simulate the same scene differently: the handshake
will succeed but the lockstep checksum comparison will desync the match, so report
the pair of values instead of playing a match that cannot last.

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
- `sim_fingerprints.<profile>.timeline` / `.components` — the per-tick checksums
  and the per-top-level-key digests of that scene (60 ticks for `canonical`, 600
  for `contact`, which needs the longer run to keep the fleets engaged). Diff the
  two machines' files: the first differing tick entry localizes **when** the pair
  diverges and the differing `components` keys name **what** diverged.
  `sim_fingerprint` is still written and holds the `canonical` profile, so older
  tooling keeps working.
- `tools/lan_state_diff.py dump --scene contact --ticks 60` dumps the contact
  scene's canonical state: when a checksum differs, diffing two of these names the
  value instead of leaving "checksums differ" as the whole diagnosis.

## What this does and does not prove

- `info` and the loopback pairing prove the app's own listen/accept/handshake
  path on that machine — never the platform pairing.
- A real two-machine run proves the pairing; a LAN match played to a launched
  game is the acceptance that closes the issue.
- CI (`windows-signal.yml`) runs the same probe, both scene profiles and the
  focused LAN tests (including `test_sim_profiles`, which asserts that each profile
  reaches the subsystems it claims to) on `windows-latest`: portability evidence,
  not GL, input-feel or LAN pairing.
- The Windows job lowers `STAR_ARMADA_PACING_FLOOR` (27 → 15 ticks/s). Pacing is
  hardware acceptance and a shared 2-vCPU runner paced 20.9 ticks/s; the
  correctness clauses — identical checksums every tick, every tick executed, AI
  and human commands present — still gate there. Measure the real floor on the
  machine that plays the match.
