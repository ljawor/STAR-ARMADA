"""W02 ring transport: publish/read, drop-oldest, torn-write and corruption rejection."""
from __future__ import annotations

import gc
import hashlib
import weakref
import os
import tempfile
import subprocess
import sys
import threading
import time
import unittest
from pathlib import Path

from render_bridge import ring

ROOT = Path(__file__).resolve().parents[1]


class ImportPortabilityTest(unittest.TestCase):
    def test_reader_import_does_not_require_posix_fcntl(self):
        # Exercise the actual import in a fresh process with the POSIX-only module
        # unavailable. This is an import regression, not Windows lock acceptance.
        script = (
            'import sys\n'
            f'sys.path.insert(0, {str(ROOT)!r})\n'
            'sys.modules["fcntl"] = None\n'
            'from render_bridge.ring import Ring\n'
        )
        result = subprocess.run([sys.executable, '-c', script],
                                capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)


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
            with ring.Ring.open(path) as reader:
                sequence, payload = reader.latest()
                self.assertEqual((sequence, payload), (0, b'first'))

    def _run(self, script):
        return subprocess.run([sys.executable, '-c',
                               f'import sys\nsys.path.insert(0, {str(ROOT)!r})\n' + script],
                              capture_output=True, text=True, timeout=15)

    def _owner(self, path):
        ready = path.with_suffix('.ready')
        script = (
            f'import sys\nsys.path.insert(0, {str(ROOT)!r})\n'
            'from pathlib import Path\n'
            'from render_bridge.ring import Ring\n'
            f'with Ring.create({str(path)!r}, slots=2, slot_bytes=4096) as owner:\n'
            ' owner.publish(b"independent-owner")\n'
            f' Path({str(ready)!r}).write_text("ready")\n'
            ' sys.stdin.read()\n'
        )
        owner = subprocess.Popen([sys.executable, '-c', script], stdin=subprocess.PIPE,
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

        def cleanup():
            if owner.poll() is None:
                owner.kill()
            owner.communicate(timeout=10)

        self.addCleanup(cleanup)
        deadline = time.monotonic() + 10
        while not ready.exists():
            if owner.poll() is not None:
                self.fail(f'producer exited before ready: {owner.communicate(timeout=5)}')
            if time.monotonic() >= deadline:
                self.fail('producer readiness timed out')
            time.sleep(0.01)
        return owner

    def test_independent_owner_refuses_contender_without_changing_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'ring.bin'
            owner = self._owner(path)
            try:
                before = path.read_bytes()
                contender = self._run(
                    'from render_bridge.ring import Ring, RingError\n'
                    'try:\n'
                    f' contender = Ring.create({str(path)!r}, slots=1, slot_bytes=1024)\n'
                    'except RingError as error:\n'
                    ' assert "already has a producer" in str(error), str(error)\n'
                    ' print("producer-refused")\n'
                    'else:\n'
                    ' contender.close()\n'
                    ' raise AssertionError("second producer acquired ownership")\n'
                )
                self.assertEqual(contender.returncode, 0, contender.stderr)
                self.assertEqual(contender.stdout.strip(), 'producer-refused')
                self.assertEqual(path.read_bytes(), before)
                reader = self._run(
                    'import hashlib\n'
                    'from pathlib import Path\n'
                    'from render_bridge.ring import Ring\n'
                    f'assert hashlib.sha256(Path({str(path)!r}).read_bytes()).hexdigest() == {hashlib.sha256(before).hexdigest()!r}\n'
                    f'with Ring.open({str(path)!r}) as reader:\n'
                    ' assert reader.latest() == (0, b"independent-owner")\n'
                )
                self.assertEqual(reader.returncode, 0, reader.stderr)
            finally:
                owner.communicate('', timeout=10)
            self.assertEqual(owner.returncode, 0)
            with ring.Ring.create(path, slots=2, slot_bytes=4096) as successor:
                self.assertIsNone(successor.latest())

    def test_producer_death_releases_ownership(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'ring.bin'
            owner = self._owner(path)
            owner.kill()
            owner.communicate(timeout=10)
            with ring.Ring.create(path, slots=2, slot_bytes=4096) as successor:
                self.assertEqual(successor.publish(b'takeover'), 0)

    def test_same_process_refusal_and_repeated_close(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'ring.bin'
            producer = ring.Ring.create(path, slots=2, slot_bytes=4096)
            try:
                producer.publish(b'unchanged')
                before = path.read_bytes()
                with self.assertRaisesRegex(ring.RingError, 'already has a producer'):
                    ring.Ring.create(path, slots=1, slot_bytes=1024)
                self.assertEqual(path.read_bytes(), before)
                with ring.Ring.open(path) as reader:
                    self.assertEqual(reader.latest(), (0, b'unchanged'))
            finally:
                producer.close()
                producer.close()
            with ring.Ring.create(path, slots=1, slot_bytes=1024):
                pass

    def test_producer_holds_original_lock_descriptor_until_close(self):
        with tempfile.TemporaryDirectory() as tmp:
            producer = ring.Ring.create(Path(tmp) / 'ring.bin', slots=1, slot_bytes=1024)
            try:
                fd = producer._lock_fd
                self.assertEqual(os.fstat(fd).st_size, 64 + 1024)
            finally:
                producer.close()
            with self.assertRaises(OSError):
                os.fstat(fd)

    def test_abandoned_producer_releases_descriptor_and_allows_takeover(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'ring.bin'
            producer = ring.Ring.create(path, slots=1, slot_bytes=1024)
            fd = producer._lock_fd
            reference = weakref.ref(producer)
            del producer
            gc.collect()
            self.assertIsNone(reference())
            with self.assertRaises(OSError):
                os.fstat(fd)
            with ring.Ring.create(path, slots=1, slot_bytes=1024) as successor:
                self.assertEqual(successor.publish(b'takeover'), 0)

    def test_abandoned_producer_keeps_ownership_while_a_view_keeps_the_mapping_alive(self):
        # The lock is owned by the mmap's lifetime, not by the Ring object: an exported
        # view keeps the mapping writable, so releasing producer ownership there would
        # let a second writer truncate a file that is still being written to.
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'ring.bin'
            producer = ring.Ring.create(path, slots=1, slot_bytes=1024)
            fd = producer._lock_fd
            view = memoryview(producer._buffer())
            del producer
            gc.collect()
            self.assertEqual(os.fstat(fd).st_size, 64 + 1024)
            with self.assertRaisesRegex(ring.RingError, 'already has a producer'):
                ring.Ring.create(path, slots=1, slot_bytes=1024)
            view.release()
            del view
            gc.collect()
            with self.assertRaises(OSError):
                os.fstat(fd)
            with ring.Ring.create(path, slots=1, slot_bytes=1024) as successor:
                self.assertEqual(successor.publish(b'takeover'), 0)

    def test_failed_close_retains_ownership_and_can_be_retried(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'ring.bin'
            producer = ring.Ring.create(path, slots=1, slot_bytes=1024)
            view = memoryview(producer._buffer())
            try:
                with self.assertRaises(BufferError):
                    producer.close()
                # mmap.close() failed, so the writable mapping is still live: ownership
                # must be retained, and the ring must not claim to be closed.
                self.assertFalse(producer._closed)
                with self.assertRaisesRegex(ring.RingError, 'already has a producer'):
                    ring.Ring.create(path, slots=1, slot_bytes=1024)
            finally:
                view.release()
            producer.close()                          # retry succeeds once the export is gone
            self.assertTrue(producer._closed)
            with ring.Ring.create(path, slots=1, slot_bytes=1024) as successor:
                self.assertEqual(successor.publish(b'takeover'), 0)

    def test_failed_constructor_closes_mapping_and_releases_ownership(self):
        mappings = []

        class FailedRing(ring.Ring):
            def __init__(self, *args, **kwargs):
                mappings.append(kwargs['mapping'])
                raise RuntimeError('constructor failed')

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'ring.bin'
            with self.assertRaisesRegex(RuntimeError, 'constructor failed'):
                FailedRing.create(path, slots=1, slot_bytes=1024)
            try:
                self.assertTrue(mappings[0].closed)
                with ring.Ring.create(path, slots=1, slot_bytes=1024):
                    pass
            finally:
                mappings[0].close()

    def test_unsupported_extent_is_rejected_before_truncation(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'ring.bin'
            path.write_bytes(b'preserve-existing-file')
            with self.assertRaises(ring.RingError):
                ring.Ring.create(path, slots=1, slot_bytes=1 << 62)
            self.assertEqual(path.read_bytes(), b'preserve-existing-file')


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

    def test_a_frame_at_exact_capacity_keeps_its_last_byte(self):
        # The completing tag lives in the slot's last 8 bytes, so capacity is slot_bytes - 28, not
        # slot_bytes - 20. The difference only shows up for a frame sized to capacity: two texels of
        # a fog mask were being overwritten by the tag, and the mask failed its own crc.
        with self.ring(slots=2, slot_bytes=4096) as producer:
            frame = bytes([7]) * producer.payload_bytes
            producer.publish(frame)
            sequence, read_back = producer.latest()
            self.assertEqual(sequence, 0)
            self.assertEqual(len(read_back), producer.payload_bytes)
            self.assertEqual(read_back, frame)
            end_tag = ring.HEADER_BYTES + producer.slot_bytes - ring.TAG.size
            self.assertEqual(ring.TAG.unpack_from(producer._buffer(), end_tag)[0], 2)

    def test_reopened_file_with_bad_header_is_refused(self):
        path = self.root / 'ring.bin'
        with ring.Ring.create(path, slots=2, slot_bytes=4096) as producer:
            producer.publish(b'x')
        raw = bytearray(path.read_bytes())
        raw[8] = 9                                    # version
        path.write_bytes(bytes(raw))
        with self.assertRaises(ring.RingError):
            ring.Ring.open(path)

    def test_malformed_open_closes_mapping(self):
        valid_header = ring.RING.pack(ring.MAGIC, ring.VERSION, 1, 1024, 0)
        cases = {
            'empty': b'',
            'short': b'ARMADAR1',
            'magic': b'x' * (64 + 1024),
            'layout': ring.RING.pack(ring.MAGIC, ring.VERSION, 0, 1024, 0) + b'\0' * 64,
            'size': valid_header + b'\0' * 64,
        }
        for name, raw in cases.items():
            with self.subTest(name=name):
                path = self.root / 'malformed.bin'
                path.write_bytes(raw)
                # Retain the actual validation traceback so GC cannot hide a leak.
                try:
                    ring.Ring.open(path)
                except ring.RingError as error:
                    trace = error.__traceback__
                    while trace and trace.tb_frame.f_code.co_name != 'open':
                        trace = trace.tb_next
                    mapping = trace.tb_frame.f_locals.get('mapping') if trace else None
                    if mapping is not None:
                        try:
                            self.assertTrue(mapping.closed, name)
                        finally:
                            mapping.close()
                else:
                    self.fail(f'malformed ring accepted: {name}')

    def test_open_constructor_failure_closes_mapping(self):
        mappings = []

        class FailedReader(ring.Ring):
            def __init__(self, *args, **kwargs):
                mappings.append(kwargs['mapping'])
                raise RuntimeError('reader constructor failed')

        path = self.root / 'ring.bin'
        with self.ring():
            with self.assertRaisesRegex(RuntimeError, 'reader constructor failed'):
                FailedReader.open(path)
            try:
                self.assertTrue(mappings[0].closed)
            finally:
                mappings[0].close()

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
