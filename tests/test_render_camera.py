"""The camera ring: the game's pose, on the wire, so the window looks where the player looks."""
from __future__ import annotations

import struct
import unittest

from render_bridge import camera as cam


class Pose:
    def __init__(self, target, distance, yaw, pitch):
        self.target, self.distance, self.yaw, self.pitch = list(target), distance, yaw, pitch


class CameraRingTest(unittest.TestCase):
    def test_round_trip_keeps_every_number(self):
        pose = Pose((1200.5, 0.0, -3400.25), 2750.0, 33.5, 61.0)
        got = cam.decode(cam.encode(pose))
        self.assertEqual(got['target'], (1200.5, 0.0, -3400.25))
        self.assertEqual(got['distance'], 2750.0)
        self.assertEqual(got['yaw'], 33.5)
        self.assertEqual(got['pitch'], 61.0)

    def test_negative_yaw_survives(self):
        got = cam.decode(cam.encode(Pose((0, 0, 0), 900.0, -179.5, 5.0)))
        self.assertAlmostEqual(got['yaw'], -179.5, places=4)

    def test_a_corrupt_payload_is_refused(self):
        raw = bytearray(cam.encode(Pose((1, 2, 3), 4.0, 5.0, 6.0)))
        raw[-1] ^= 0xFF
        with self.assertRaises(cam.CameraError):
            cam.decode(bytes(raw))

    def test_a_truncated_payload_is_refused(self):
        raw = cam.encode(Pose((1, 2, 3), 4.0, 5.0, 6.0))
        with self.assertRaises(cam.CameraError):
            cam.decode(raw[:-1])

    def test_trailing_bytes_are_refused(self):
        raw = cam.encode(Pose((1, 2, 3), 4.0, 5.0, 6.0))
        with self.assertRaises(cam.CameraError):
            cam.decode(raw + b'\x00')

    def test_another_magic_is_refused(self):
        raw = bytearray(cam.encode(Pose((1, 2, 3), 4.0, 5.0, 6.0)))
        raw[0:8] = b'ARMARK01'
        with self.assertRaises(cam.CameraError):
            cam.decode(bytes(raw))

    def test_the_header_is_twenty_bytes_and_the_pose_six_floats(self):
        raw = cam.encode(Pose((0, 0, 0), 1.0, 2.0, 3.0))
        self.assertEqual(len(raw), cam.HEADER_BYTES + cam.PAYLOAD_BYTES)
        self.assertEqual(cam.HEADER_BYTES, 20)
        self.assertEqual(cam.PAYLOAD_BYTES, struct.calcsize('<6f'))


if __name__ == '__main__':
    unittest.main()
