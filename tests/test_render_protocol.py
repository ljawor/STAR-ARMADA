"""Offline transport controls; synthetic fixtures are not gameplay evidence."""
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import unittest

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / 'tests/fixtures/render_protocol'


class RenderProtocolTests(unittest.TestCase):
    def test_roundtrip(self):
        self.assertIsNotNone(importlib.util.find_spec('render_bridge'), 'offline protocol package missing')
        from render_bridge.protocol import HEADER, WORLD, UI, encode, decode
        self.assertEqual(HEADER.format, '<8sHHIQII')
        self.assertEqual(HEADER.size, 32)
        for kind, payload in ((WORLD, {'schema': 1, 'instances': [], 'label': 'fleet Ω'}),
                              (UI, {'schema': 1, 'commands': []})):
            raw = encode(payload, kind=kind, tick=17, frame_index=2**40)
            frame = decode(raw)
            self.assertEqual((frame.kind, frame.tick, frame.frame_index, frame.payload),
                             (kind, 17, 2**40, payload))
            self.assertEqual(encode(frame.payload, kind=frame.kind, tick=frame.tick,
                                    frame_index=frame.frame_index), raw)
            self.assertEqual(raw[32:], json.dumps(payload, sort_keys=True, separators=(',', ':'),
                                                  allow_nan=False).encode('utf-8'))
    def test_fixture_bytes(self):
        from render_bridge.protocol import WORLD, UI, encode, decode
        self.assertTrue((FIXTURES / 'checksums.json').exists(), 'frozen transport bytes missing')
        checksums = json.loads((FIXTURES / 'checksums.json').read_text())
        self.assertEqual(set(checksums), {'empty.world.snap', 'synthetic600.world.snap', 'ui500.snap'})
        for name, record in checksums.items():
            raw = (FIXTURES / name).read_bytes()
            self.assertEqual(hashlib.sha256(raw).hexdigest(), record['sha256'])
            self.assertEqual(len(raw), record['bytes'])
            frame = decode(raw)
            self.assertEqual(encode(frame.payload, kind=frame.kind, tick=frame.tick,
                                    frame_index=frame.frame_index), raw)
            self.assertTrue(frame.payload['metadata']['synthetic_transport_fixture'])
            key = 'commands' if frame.kind == UI else 'instances'
            expected = 500 if frame.kind == UI else (600 if name.startswith('synthetic') else 0)
            self.assertEqual(len(frame.payload[key]), expected)
            self.assertEqual(frame.kind, UI if key == 'commands' else WORLD)

    def test_rejections(self):
        import zlib
        from render_bridge.protocol import HEADER, MAGIC, VERSION, WORLD, MAX_PAYLOAD, ProtocolError, encode, decode
        good = encode({'schema': 1})
        def framed(payload):
            return HEADER.pack(MAGIC, VERSION, WORLD, 0, 0, len(payload), zlib.crc32(payload)) + payload
        bad = [good[:20], good[:-1], good + b'x', good[:32] + b'X' + good[33:]]
        for index, value in ((0, b'BADMAGIC'), (1, 2), (2, 0), (2, 3), (5, MAX_PAYLOAD + 1)):
            fields = list(HEADER.unpack_from(good)); fields[index] = value
            bad.append(HEADER.pack(*fields) + good[32:])
        bad.extend(framed(p) for p in (b'\xff', b'{', b'[]', b'{"a":NaN}', b'{"a":1,"a":2}', b'{ "schema": 1 }', b'{"a":1e999}'))
        for raw in bad:
            with self.subTest(raw=raw[:40]):
                with self.assertRaises(ProtocolError):
                    decode(raw)
        for kwargs in ({'kind': 9}, {'kind': True}, {'tick': -1}, {'tick': 2**32},
                       {'frame_index': 2**64}, {'tick': 1.5}):
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(ProtocolError):
                    encode({}, **kwargs)
        for payload in ({'x': float('nan')}, {'x': float('inf')}, [], {1: 'key'}):
            with self.assertRaises(ProtocolError):
                encode(payload)


if __name__ == '__main__':
    unittest.main()
