# LAN multiplayer

## Network contract

- Transport: **TCP**, direct IPv4 connection to the host.
- Default host port: **7777**, selectable from **1–65535** before hosting.
- Joiners enter the host's LAN address and the **same host port**. Their local TCP source ports are automatically allocated; they do not each need their own listening port.
- No UDP discovery, router forwarding, automatic firewall changes or Internet matchmaking.
- Use a trusted local network. The game connection is not encrypted or authenticated as an Internet service.
- All participants need matching game versions and simulation content. Mods/content mismatches are rejected.

## Play together

1. Connect the computers to the same trusted Ethernet/Wi-Fi network.
2. On one computer open **Multiplayer → Host**. Choose a map, number of human players, optional AI, colors, factions, difficulty and a port.
3. Allow inbound TCP on that host port if a firewall blocks it. Share the host's actual LAN IPv4 address, not `127.0.0.1`.
4. Other players use **Multiplayer → Join** and enter that address and port.
5. Each player marks themselves ready. The host starts when all configured human slots are connected and ready.

The map catalogue is the same as Skirmish: Sector Duel / Kotarri Sector (2 total players), Trinary Reach (3), Crossroads (4), and Nebula Frontier (4). Humans and AI share the map's capacity. Two humans can play alone or add AI on a larger map. Cooperative mode puts humans on one team against AI; free-for-all gives each player a separate team. Teammates share sensors, but not control of each other's ships.

Gameplay advances only when every human has contributed the next turn. The UI stays responsive while waiting. Synchronization failures stop the match rather than silently allowing divergent simulations. Unexpected post-launch transport interruption now attempts experimental same-host recovery as described below; recovery can still fail. LAN matches do not support independent pause, quickload or restoring a saved multiplayer session.

### Human orders and local limits

Boarding, crew loading (**L**), crew delivery and crew cancellation use the same delayed lockstep path as other human orders. `board` and `crew_deliver` require a target hull; `crew_load` and `crew_cancel` carry selected unit IDs without a target. Crew orders require a nonempty selection and reject unrelated payload fields. `crew_recover` remains AI-only and cannot be submitted by a peer. The wire authenticates the player slot; the simulation separately rechecks source ownership and current target legality when the order executes. Teammates cannot command each other's ships; delivery requires an owned hull, while boarding requires a visible, in-range, shieldless enemy capturable hull.

The protocol remains limited to **256 selected unit IDs per order** and **64 pending human orders per turn per player**. A local order exceeding either limit is rejected as a whole with an in-match notice. Previously accepted pending orders and the LAN session survive. No automatic splitting or partial paid action occurs; reduce the selection or wait for the next turn and retry. A malicious or malformed peer message still terminates the match.

Controlled in-match LAN failures and uncaught Python exceptions now have small, sanitized, best-effort durable reports; see [Network diagnostics](NETWORK_DIAGNOSTICS.md). They are not full crash dumps.

### Recovery status

**Experimental same-host reconnect.** The LAN host/join menus enable it before
handshake. An unexpected socket interruption can pause all humans, retry the original host
and restore the delayed pipeline within one absolute 60-second grace. The paused
overlay shows missing peers, deadline and phase; camera controls remain available,
while world orders are blocked. **Escape / Cancel reconnect leaves the match.**
Delivered shutdown, abort, protocol errors and desync remain terminal. There is no
host migration or process-restart recovery; returning to Join starts a new session.

The v0.15.0 source increment bounds unauthenticated admission independently of
reserved human slots, recovers a ready original client that lost the initial
launch, and rolls back partially constructed renderer resources. Historical
integration failures remain recorded separately from fresh release verification.
Native mixed Mac/Windows physical-machine acceptance, silent-blackhole behavior
and original crash attribution remain open. Plaintext bearer credentials and the
bounded admission pool are not Internet-facing security or flood protection.
Use only a trusted isolated LAN. See [scope and verification limits](LAN_RECONNECT.md).

## Windows Firewall: host rule

Keep Windows Firewall enabled. For a trusted home LAN, use the **Private** network profile. On managed/company networks, ask the administrator instead of changing policy.

Open **PowerShell as Administrator on the host**. Replace the port and executable path below with your selected port and installed/extracted game's actual path:

```powershell
$Port = 7777
$Game = 'C:\Games\STAR ARMADA\STAR ARMADA.exe'
New-NetFirewallRule -Name "STAR-ARMADA-LAN-TCP-$Port" `
  -DisplayName "STAR ARMADA LAN TCP $Port" `
  -Direction Inbound -Action Allow -Enabled True `
  -Profile Private -Protocol TCP -LocalPort $Port `
  -RemoteAddress LocalSubnet -Program $Game
```

This limits the exception to that executable, the chosen TCP port, local-subnet peers and the Private profile. A Private-only rule will not permit hosting while the active network is Public. Change a network to Private only when you trust it. For source execution, the program must be the exact Python executable running the game instead of `STAR ARMADA.exe`.

Check the rule:

```powershell
Get-NetFirewallRule -Name "STAR-ARMADA-LAN-TCP-$Port" |
  Get-NetFirewallPortFilter
```

Remove it when no longer needed:

```powershell
Remove-NetFirewallRule -Name "STAR-ARMADA-LAN-TCP-$Port"
```

If you change the game's path or selected port, update/recreate the rule and remove the obsolete one. Do not open all ports or disable the firewall.

Joining normally needs no inbound exception: the client connects outbound to the host. If your organization's policy blocks outbound traffic, ask its administrator to allow **TCP outbound to the host address and destination port**, rather than opening the client's local port.

## Troubleshooting

From a joining Windows computer, with the host lobby already listening:

```powershell
Test-NetConnection -ComputerName 192.168.1.50 -Port 7777
```

Use the actual host address/port. `TcpTestSucceeded: True` proves TCP reachability, not game-version compatibility or lobby readiness.

- **Address already in use:** choose another port on the host, update the firewall rule, and give joiners the new port.
- **Connection refused:** verify the host lobby is running and the address/port are correct.
- **Timeout:** check the host firewall, network profile, VPN routes, and Wi-Fi guest/client isolation. Guest Wi-Fi may prevent local peers from reaching each other.
- **Different game/content:** install the same release on every computer; remove mismatched mods.
- **Multiple LAN addresses:** choose the physical LAN interface shared with your friends, not a VPN/virtual adapter. `ipconfig` on Windows shows IPv4 addresses.
- **macOS hosting:** allow incoming connections for STAR ARMADA when macOS asks. Do not disable the entire firewall.

## Microsoft references

- New-NetFirewallRule: https://learn.microsoft.com/en-us/powershell/module/netsecurity/new-netfirewallrule
- Windows Firewall rules/default outbound behavior: https://learn.microsoft.com/en-us/windows/security/operating-system-security/network-security/windows-firewall/configure
- Keep the firewall enabled: https://learn.microsoft.com/en-us/windows/security/operating-system-security/network-security/windows-firewall/
