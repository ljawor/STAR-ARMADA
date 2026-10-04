"""LAN human commands wait for a shared turn; AI remains a sim output."""
import unittest
from game.core.state import GameState, PlayerState
from game.core.commands import StopCommand

class Session:
    intercepts_commands = True
    def __init__(self): self.sent = []
    def submit(self, command, tick): self.sent.append((command, tick))

class LanQueueTests(unittest.TestCase):
    def state(self):
        state = GameState()
        state.players = {0: PlayerState(id=0, is_ai=False), 1: PlayerState(id=1, is_ai=True)}
        state._net_session = Session()
        return state

    def test_human_waits_for_shared_turn(self):
        state = self.state()
        command = StopCommand(0, [1])
        state.queue_command(command)
        self.assertEqual(state.command_queue, [])
        self.assertEqual(state._net_session.sent, [(command, state.tick)])

    def test_ai_is_queued_locally_without_network_echo(self):
        state = self.state()
        command = StopCommand(1, [1])
        state.queue_command(command)
        self.assertEqual(state.command_queue, [command])
        self.assertEqual(state._net_session.sent, [])

    def test_legacy_session_retains_original_queue_behavior(self):
        state = self.state()
        state._net_session.intercepts_commands = False
        command = StopCommand(0, [1])
        state.queue_command(command)
        self.assertEqual(state.command_queue, [command])
        self.assertEqual(state._net_session.sent, [(command, state.tick)])
