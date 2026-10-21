"""W02 ring transport: publish/read, drop-oldest, torn-write and corruption rejection."""
from __future__ import annotations

import tempfile
import subprocess
import sys
import threading
import time
import unittest
from pathlib import Path

from render_bridge import ring

ROOT = Path(__file__).resolve().parents[1]


class SingleProducerTest(unittest.TestCase):
    """Two producers on one ring must be an error, not a quietly reset counter."""

    def test_second_producer_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'ring.bin'
            with ring.Ring.create(path, slots=2, slot_bytes=4096) as out:
                out.publish(b'first')
                script = (
                    'import sys\n'
                    f'sys.path.insert(0, {str(ROOT)!r})\n'
                    'from render_bridge import ring\n'
                    f'ring.Ring.create({str(path)!r}, slots=2, slot_bytes=4096)\n'
                )
                result = subprocess.run([sys.executable, '-c', script],
                                        capture_output=True, text=True, timeout=60)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('already has a producer', result.stderr)
            # The surviving ring still holds its frame and its counter.
            reader = ring.Ring.open(path)
            sequence, payload = reader.latest()
            self.assertEqual((sequence, payload), (0, b'first'))


class RingTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix='w02-ring-'))
        self.addCleanup(self._cleanup)

    def _cleanup(self):
        for path in self.root.glob('*.bin'):
            try:
                path.unlink()
            except OSError:
                pass
        self.root.rmdir()

    def ring(self, **kwargs):
        options = {'slots': 4, 'slot_bytes': 4096}
        options.update(kwargs)
        created = ring.Ring.create(self.root / 'ring.bin', **options)
        self.addCleanup(created.close)
        return created

    def test_publish_then_read_returns_exact_bytes(self):
        with self.ring() as producer:
            sequence = producer.publish(b'frame-one')
            self.assertEqual(sequence, 0)
            self.assertEqual(producer.published, 1)
            self.assertEqual(producer.latest(), (0, b'frame-one'))
        with ring.Ring.open(self.root / 'ring.bin') as consumer:
            self.assertEqual(consumer.published, 1)
            self.assertEqual(consumer.latest(), (0, b'frame-one'))

    def test_drop_oldest_keeps_newest_and_reports_nothing_stale(self):
        with self.ring(slots=2) as producer:
            for index in range(5):
                producer.publish(b'f%d' % index)
            self.assertEqual(producer.latest(), (4, b'f4'))
            for stale in range(3):                    # slots reused by newer frames
                self.assertIsNone(producer.read(stale))
            self.assertEqual(producer.read(3), (3, b'f3'))

    def test_pending_write_is_not_readable(self):
        with self.ring() as producer:
            producer.publish(b'good')
            producer.publish(b'also-good')
            # Remove the completing tag of frame 1, which is what a consumer observes
            # while a writer is still copying that slot.
            slot_one = ring.HEADER_BYTES + 1 * producer.slot_bytes
            end_tag = slot_one + producer.slot_bytes - ring.TAG.size
            ring.TAG.pack_into(producer._buffer(), end_tag, 0)
            self.assertIsNone(producer.read(1))       # torn: never decoded
            self.assertEqual(producer.read(0), (0, b'good'))

    def test_oversized_frame_is_refused_before_it_corrupts_a_slot(self):
        with self.ring() as producer:
            producer.publish(b'small')
            with self.assertRaises(ring.RingError):
                producer.publish(b'x' * (producer.payload_bytes + 1))
            self.assertEqual(producer.latest(), (0, b'small'))

    def test_reopened_file_with_bad_header_is_refused(self):
        path = self.root / 'ring.bin'
        with ring.Ring.create(path, slots=2, slot_bytes=4096) as producer:
            producer.publish(b'x')
        raw = bytearray(path.read_bytes())
        raw[8] = 9                                    # version
        path.write_bytes(bytes(raw))
        with self.assertRaises(ring.RingError):
            ring.Ring.open(path)

    def test_writer_and_reader_threads_never_hand_back_a_torn_frame(self):
        with self.ring(slots=4, slot_bytes=8192) as producer:
            consumer = ring.Ring.open(producer.path)
            self.addCleanup(consumer.close)
            payloads = [bytes([index]) * (100 + index * 40) for index in range(6)]
            stop = threading.Event()
            seen = []

            def read_loop():
                while not stop.is_set():
                    frame = consumer.latest()
                    if frame is not None:
                        seen.append(frame[1])

            reader = threading.Thread(target=read_loop)
            reader.start()
            try:
                deadline = time.monotonic() + 0.3
                while time.monotonic() < deadline:
                    for payload in payloads:
                        producer.publish(payload)
                    time.sleep(0)          # let the reader run; a tight loop holds the GIL
            finally:
                stop.set()
                reader.join()
            self.assertTrue(seen, 'reader observed no frames')
            # Every frame a reader can observe must be one whole published payload.
            self.assertTrue(all(frame in payloads for frame in seen))


if __name__ == '__main__':
    unittest.main()
