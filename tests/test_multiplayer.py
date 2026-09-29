"""Multiplayer + replay: lockstep protocol, replay record/verify (Phase 8/§32)."""
import os
import tempfile
import unittest

from helpers import make_game, run_for
from game.core.commands import PlayerCommand
from game.core.manager import GameManager
from game.net.replay import (ReplayRecorder, ReplayPlayer, load_replay,
                             state_checksum)
from game.net.lockstep import (LockstepSession, LoopbackTransport,
                               DesyncError, INPUT_DELAY_TICKS)


class TestChecksum(unittest.TestCase):
    def test_identical_runs_same_checksum(self):
        a, b = make_game(ai=True), make_game(ai=True)
        run_for(a, 5.0)
        run_for(b, 5.0)
        self.assertEqual(state_checksum(a.state), state_checksum(b.state))

    def test_divergent_runs_differ(self):
        a = make_game(ai=False)
        b = make_game(ai=False)
        a.state.players[0].credits += 100.0   # perturb one run
        self.assertNotEqual(state_checksum(a.state), state_checksum(b.state))


class TestReplay(unittest.TestCase):
    def test_replay_reproduces_checksums_ai_on(self):
        """Full e2e: record a game WITH AI (AI commands are NOT recorded —
        they re-derive deterministically), replay from initial_state and
        compare checksums every 30 ticks."""
        gm = make_game(ai=True)
        rec = ReplayRecorder(gm.state)
        gm.state._recorder = rec
        scheduled = {30: PlayerCommand(type="move", player=0, unit_ids=(1,),
                                       target_pos=(2000.0, 0.0, 0.0)),
                     90: PlayerCommand(type="move", player=0, unit_ids=(2,),
                                       target_pos=(-2000.0, 0.0, 0.0))}
        ckpts_record = {}
        for _ in range(150):
            tick = gm.state.tick + 1
            if tick in scheduled:
                gm.state.queue_command(scheduled[tick])
            gm.step(1 / 30)
            if gm.state.tick % 30 == 0:
                ckpts_record[gm.state.tick] = state_checksum(gm.state)
        # only the 2 human moves recorded (AI build orders self-derive)
        self.assertEqual([c["cmd"]["type"] for c in rec.to_dict()["commands"]],
                         ["move", "move"])
        path = os.path.join(tempfile.gettempdir(), "sa_test_replay.json")
        rec.save(path)

        data = load_replay(path)
        state = GameState_from_dict(data["initial_state"])
        gm2 = GameManager(state=state)
        rebind_systems(gm2, state)
        player = ReplayPlayer(data)
        ckpts_replay = {}
        for _ in range(150):
            tick = gm2.state.tick + 1
            for cmd in player.commands_for_tick(tick):
                gm2.state.command_queue.append(cmd)
            gm2.step(1 / 30)
            if gm2.state.tick % 30 == 0:
                ckpts_replay[gm2.state.tick] = state_checksum(gm2.state)
        self.assertEqual(ckpts_record, ckpts_replay)

    def test_replay_skips_ai_commands(self):
        # AI-generated commands must not be recorded (they'd double-execute)
        gm = make_game(ai=True)
        rec = ReplayRecorder(gm.state)
        gm.state._recorder = rec
        run_for(gm, 2.0)
        ai_cmds = [c for c in rec.to_dict()["commands"] if c["cmd"]["player"] == 1]
        self.assertEqual(ai_cmds, [])

    def test_replay_file_format(self):
        gm = make_game(ai=False)
        rec = ReplayRecorder(gm.state, map_name="skirmish01")
        rec.on_command(PlayerCommand(type="stop", player=0, unit_ids=(1,)), 5)
        d = rec.to_dict()
        self.assertEqual(d["format"], "star-armada-replay")
        self.assertEqual(d["version"], 1)
        self.assertEqual(d["seed"], gm.state.seed)
        self.assertEqual(len(d["commands"]), 1)
        self.assertEqual(d["commands"][0]["tick"], 5)


class TestLockstep(unittest.TestCase):
    def test_input_delay_scheduling(self):
        a, _ = LoopbackTransport.pair()
        s = LockstepSession(local_player=0, transport=a)
        s.submit(PlayerCommand(type="stop", player=0, unit_ids=(1,)),
                 current_tick=100)
        # nothing due until tick 100 + INPUT_DELAY_TICKS
        self.assertEqual(s.commands_for_tick(100), [])
        due = s.commands_for_tick(100 + INPUT_DELAY_TICKS)
        self.assertEqual(len(due), 1)
        self.assertEqual(due[0].type, "stop")

    def test_command_exchange_and_delivery(self):
        ta, tb = LoopbackTransport.pair()
        sa = LockstepSession(local_player=0, transport=ta)
        sb = LockstepSession(local_player=1, transport=tb)
        sa.submit(PlayerCommand(type="move", player=0, unit_ids=(1,),
                                target_pos=(5.0, 0.0, 5.0)), current_tick=0)
        sb.submit(PlayerCommand(type="stop", player=1, unit_ids=(2,)),
                  current_tick=0)
        # end_turn blocks on the peer: drive both sessions in lockstep
        _paired_turn(sa, sb, current_tick=0, checksum="cA", checksum_b="cB")
        # each session received the other's command, scheduled with delay.
        # BOTH the local submit and the remote receive land in the same
        # scheduled bucket for a 2-player game (each side runs both players'
        # commands for the shared lockstep tick) — assert both delivered:
        due_a = sa.commands_for_tick(0 + INPUT_DELAY_TICKS)
        due_b = sb.commands_for_tick(0 + INPUT_DELAY_TICKS)
        self.assertEqual(sorted(c.type for c in due_a), ["move", "stop"])
        self.assertEqual(sorted(c.type for c in due_b), ["move", "stop"])
        # remote checksums crossed the wire
        self.assertEqual(sb._remote_last_checksum, "cA")
        self.assertEqual(sa._remote_last_checksum, "cB")

    def test_desync_detection(self):
        ta, tb = LoopbackTransport.pair()
        sa = LockstepSession(local_player=0, transport=ta)
        sb = LockstepSession(local_player=1, transport=tb)
        _paired_turn(sa, sb, current_tick=0, checksum="same", checksum_b="same")
        sa.check_desync("same")            # ok
        _paired_turn(sa, sb, current_tick=1, checksum="same1",
                     checksum_b="different!")
        with self.assertRaises(DesyncError):
            sa.check_desync("same1")


def GameState_from_dict(d):
    from game.core.state import GameState
    return GameState.from_dict(d)


def rebind_systems(gm, state):
    """Point every manager system at a freshly-restored GameState.

    Systems capture `state` at construction; from_dict() replaces the state
    object, so replays/saves must rebind before stepping (the damage system
    is also hung on the state for event payloads)."""
    gm.state = state
    state.dmg_system = gm.damage
    for name in ("abilities", "ai", "commands", "construction", "damage",
                 "economy", "factory", "formations", "mission", "movement",
                 "projectiles", "research", "separation", "squadrons",
                 "trading", "victory", "weapons"):
        s = getattr(gm, name, None)
        if s is not None and hasattr(s, "state"):
            s.state = state


def _paired_turn(sa, sb, current_tick: int, checksum: str,
                 checksum_b: str) -> None:
    """Drive both lockstep sessions through one turn without deadlocking:
    run each end_turn in its own thread and join both."""
    import threading
    t1 = threading.Thread(target=lambda: sa.end_turn(current_tick, checksum))
    t2 = threading.Thread(target=lambda: sb.end_turn(current_tick, checksum_b))
    t1.start(); t2.start()
    t1.join(5.0); t2.join(5.0)


if __name__ == "__main__":
    unittest.main()