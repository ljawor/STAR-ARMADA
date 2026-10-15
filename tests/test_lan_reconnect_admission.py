"""Real-TCP admission attacks must not occupy authenticated recovery slots."""
import socket
import struct
import time
import unittest
import test_lan_production_reconnect as production


class AdmissionTests(unittest.TestCase):
    setup_match = production.ProductionReconnectTests.setup_match
    align = production.ProductionReconnectTests.align
    recover = production.ProductionReconnectTests.recover

    def test_incomplete_outsiders_cannot_starve_original_slot(self):
        for humans in (2, 3, 4):
            with self.subTest(humans=humans):
                sessions, managers = self.setup_match(humans)
                self.align(sessions, managers, 8)
                host, client = sessions[:2]
                client._peers[0].sock.shutdown(socket.SHUT_RDWR)
                client.poll()
                client._recovery.retry_at = float('inf')
                for s in [host] + sessions[2:]:
                    s.poll()
                outsiders = []
                for _ in range(4):
                    sock = socket.create_connection(('127.0.0.1', host.port))
                    self.addCleanup(sock.close)
                    outsiders.append(sock)
                    sock.sendall(struct.pack('!I', 10000) + b'{')
                    host.poll()
                self.assertEqual(host.snapshot['status'], 'recovering')
                self.assertLessEqual(len([p for p in host._peers if p.slot is None]), 4)
                self.assertEqual(len([p for p in host._peers if p.slot is not None]), humans-2)
                client._recovery.retry_at = 0.
                # Keep incomplete sockets alive while the original authenticated
                # slot reconnects, drains, installs, and continues over real TCP.
                self.recover(sessions, managers)
                self.align(sessions, managers, 12)
                for s in sessions:
                    s.close()

    def test_partial_bytes_do_not_renew_absolute_authentication_budget(self):
        sessions, managers = self.setup_match(2)
        host = sessions[0]
        outsider = socket.create_connection(('127.0.0.1', host.port))
        self.addCleanup(outsider.close)
        outsider.sendall(struct.pack('!I', 10000) + b'{')
        host.poll()
        peer = next(p for p in host._peers if p.slot is None)
        # Age only this socket, not the match or authenticated peers. This tests
        # the real socket parser/deadline without a 15-second test sleep.
        peer.last -= 16.
        if hasattr(peer, 'accepted_at'):
            peer.accepted_at -= 16.
        outsider.sendall(b' ')
        import select
        self.assertTrue(select.select([peer.sock], [], [], 1.)[0])
        host.poll()
        self.assertNotIn(peer, host._peers)
        self.assertEqual(host.snapshot['status'], 'running')
        self.align(sessions, managers, 5)

    def test_complete_unauthenticated_traffic_cannot_refresh_budget(self):
        from game.net.lan import _Peer
        sessions, managers = self.setup_match(2)
        host = sessions[0]
        outsider = _Peer(socket.create_connection(('127.0.0.1', host.port)))
        self.addCleanup(outsider.close)
        host.poll()
        peer = next(p for p in host._peers if p.slot is None)
        accepted = peer.accepted_at
        last = peer.last
        outsider.send(dict(type='ping'))
        outsider.flush()
        # The complete unauthenticated message is rejected, never assigned a
        # human slot or allowed to change authenticated participant state.
        import select
        self.assertTrue(select.select([peer.sock], [], [], 1.)[0])
        host.poll()
        self.assertNotIn(peer, host._peers)
        self.assertEqual(peer.last, last)
        self.assertEqual(peer.accepted_at, accepted)
        self.assertEqual(host.snapshot['status'], 'running')
        self.align(sessions, managers, 5)
