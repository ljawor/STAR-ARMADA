"""W02 single-producer frame ring in a memory-mapped file.

The writer never blocks and never waits for the consumer: a frame that is published
while the consumer is still reading the previous one simply overwrites it, which is
the drop-oldest rule in the migration plan (a renderer that cannot keep up degrades
the frame rate of the picture, never the simulation). Readers detect a torn slot with
a sequence counter written before and after the payload, so a partially written frame
is never decoded.

Layout (little-endian, all offsets from the start of the mapping):

    ring header, 64 bytes:
        0  8s  magic  b'ARMADAR1'
        8  u16 version (1)
       10  u16 slot count
       13  u32 slot bytes (payload capacity is slot_bytes - 28)
       16  u64 published count (monotonic; the newest slot is (count - 1) % slots)
       24  .. reserved

    each slot, `slot_bytes`:
        0   u64 sequence tag (2n + 1 while slot n is being written, 2n + 2 when complete)
        +8  u32 payload length
       +12  frame bytes
        end u64 the completing sequence tag, written after the payload

One process writes; any number of processes read. `head` is written last, so a reader
that sees published == n can trust slot n once both tags agree.
"""
from __future__ import annotations

import mmap
import os
from pathlib import Path
import struct
import weakref

RING = struct.Struct('<8sHHIQ')
MAGIC = b'ARMADAR1'
VERSION = 1
HEADER_BYTES = 64
TAG = struct.Struct('<Q')
LENGTH = struct.Struct('<I')
SLOT_OVERHEAD = 2 * TAG.size + LENGTH.size   # offset of the frame bytes inside a slot
# ...and the completing tag occupies the slot's last 8 bytes, so a frame one tag shorter than the
# nominal capacity would have its tail overwritten by that tag. It went unnoticed because every
# existing producer leaves slack; a fog mask sized exactly to capacity lost its last two texels and
# failed its own crc.
SLOT_TRAILER = TAG.size
MIN_SLOT_BYTES = 1024
# Shared with native producers: one byte outside every supported ring extent.
# Windows byte-range locks must never cover the header/payload read by native I/O.
PRODUCER_LOCK_OFFSET = 1 << 62


def _lock_producer(fd):
    if os.name == 'nt':
        import msvcrt
        os.lseek(fd, PRODUCER_LOCK_OFFSET, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        os.lseek(fd, 0, os.SEEK_SET)
    else:
        import fcntl
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)


class RingError(ValueError):
    """Malformed ring file, or a reader that does not match the file's layout."""


class Ring:
    """A memory-mapped ring of fixed-size slots. One writer, many readers."""

    def __init__(self, path, *, slots, slot_bytes, mapping, writable):
        self.path = Path(path)
        self.slots = slots
        self.slot_bytes = slot_bytes
        self._mapping: mmap.mmap = mapping
        self._writable = writable
        self._published = 0
        self._closed = False
        self._lock_fd = None
        self._release_lock = None

    def _buffer(self) -> mmap.mmap:
        if self._closed:
            raise RingError('ring is closed')
        return self._mapping

    # -- construction ---------------------------------------------------------
    @classmethod
    def create(cls, path, *, slots=8, slot_bytes=1 << 20):
        slots = int(slots)
        slot_bytes = int(slot_bytes)
        if not 1 <= slots <= 4096:
            raise RingError('slot count must be 1..4096')
        if not MIN_SLOT_BYTES <= slot_bytes <= 0xffffffff:
            raise RingError(f'slot bytes must be {MIN_SLOT_BYTES}..4294967295')
        extent = HEADER_BYTES + slots * slot_bytes
        if extent >= PRODUCER_LOCK_OFFSET:
            raise RingError('ring extent overlaps producer lock byte')
        path = Path(path)
        if path.parent and not path.parent.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
        # No O_TRUNC here: the file must survive a refused second producer intact, so it
        # is emptied only after the lock is held.
        fd = os.open(path, os.O_RDWR | os.O_CREAT | getattr(os, 'O_BINARY', 0), 0o600)
        mapping = None
        try:
            # Readers never take this lock; contention must fail before truncation.
            try:
                _lock_producer(fd)
            except OSError as error:
                raise RingError(f'ring already has a producer: {path}') from error
            os.ftruncate(fd, 0)                      # a new session starts from zeroed slots
            os.ftruncate(fd, extent)
            mapping = mmap.mmap(fd, 0, access=mmap.ACCESS_WRITE)
            RING.pack_into(mapping, 0, MAGIC, VERSION, slots, slot_bytes, 0)
            ring = cls(path, slots=slots, slot_bytes=slot_bytes, mapping=mapping, writable=True)
            # mmap does not retain the original descriptor on every platform.
            ring._lock_fd = fd
            # Exports retain the mmap, not the Ring. Keep ownership for that entire
            # lifetime; the callback must not retain the mapping itself.
            ring._release_lock = weakref.finalize(mapping, os.close, fd)
            return ring
        except BaseException:
            try:
                if mapping is not None:
                    mapping.close()
            finally:
                os.close(fd)
            raise

    @classmethod
    def open(cls, path, *, writable=False):
        path = Path(path)
        if not path.exists():
            raise RingError(f'ring file does not exist: {path}')
        flags = (os.O_RDWR if writable else os.O_RDONLY) | getattr(os, 'O_BINARY', 0)
        fd = os.open(path, flags)
        mapping = None
        try:
            try:
                if os.fstat(fd).st_size < HEADER_BYTES:
                    raise RingError('ring file is shorter than its header')
                mapping = mmap.mmap(fd, 0, access=mmap.ACCESS_WRITE if writable else mmap.ACCESS_READ)
            finally:
                os.close(fd)
            magic, version, slots, slot_bytes, published = RING.unpack_from(mapping, 0)
            if magic != MAGIC or version != VERSION:
                raise RingError('unknown ring magic or version')
            if not 1 <= slots <= 4096 or slot_bytes < MIN_SLOT_BYTES:
                raise RingError('ring header declares an invalid layout')
            extent = HEADER_BYTES + slots * slot_bytes
            if extent >= PRODUCER_LOCK_OFFSET or len(mapping) != extent:
                raise RingError('ring file size does not match its header')
            ring = cls(path, slots=slots, slot_bytes=slot_bytes, mapping=mapping, writable=writable)
            ring._published = published
            return ring
        except BaseException:
            if mapping is not None:
                mapping.close()
            raise

    # -- accessors ------------------------------------------------------------
    @property
    def payload_bytes(self):
        return self.slot_bytes - SLOT_OVERHEAD - SLOT_TRAILER

    @property
    def published(self):
        """Number of frames published so far (monotonic, not a slot index)."""
        return self._published if self._writable else RING.unpack_from(self._buffer(), 0)[4]

    def _slot_offset(self, sequence):
        return HEADER_BYTES + (sequence % self.slots) * self.slot_bytes

    # -- writer ---------------------------------------------------------------
    def publish(self, frame) -> int:
        """Copy one frame into the next slot and return its sequence number."""
        if not self._writable:
            raise RingError('ring opened read-only')
        frame = bytes(frame)
        if len(frame) > self.payload_bytes:
            raise RingError(f'frame of {len(frame)} bytes exceeds slot capacity {self.payload_bytes}')
        sequence = self._published
        offset = self._slot_offset(sequence)
        in_progress = 2 * sequence + 1
        complete = in_progress + 1
        TAG.pack_into(self._buffer(), offset, in_progress)
        LENGTH.pack_into(self._buffer(), offset + TAG.size, len(frame))
        start = offset + SLOT_OVERHEAD
        self._buffer()[start:start + len(frame)] = frame
        TAG.pack_into(self._buffer(), offset + self.slot_bytes - TAG.size, complete)
        self._published = sequence + 1
        RING.pack_into(self._buffer(), 0, MAGIC, VERSION, self.slots, self.slot_bytes,
                       self._published)
        return sequence

    # -- reader ---------------------------------------------------------------
    def latest(self):
        """Return (sequence, frame bytes) for the newest complete slot, or None."""
        published = RING.unpack_from(self._buffer(), 0)[4]
        if published == 0:
            return None
        # Read against this one header snapshot: re-reading it inside `read` lets a writer
        # that advanced by a full ring of frames make the newest frame look overwritten,
        # and the reader then silently shows an older picture.
        return self._read_at(published - 1, published)

    def read(self, sequence):
        """Return (sequence, frame bytes) for an exact slot, or None if torn/overwritten."""
        if sequence < 0:
            return None
        return self._read_at(sequence, RING.unpack_from(self._buffer(), 0)[4])

    def _read_at(self, sequence, published):
        if sequence >= published:
            return None
        if published - sequence > self.slots:      # already overwritten by newer frames
            return None
        # Seqlock: the writer stamps 2n+1 before copying and 2n+2 after. Both must
        # match this sequence, or the slot has been reused by a newer frame or is
        # half-written.
        expected_begin, expected_end = 2 * sequence + 1, 2 * sequence + 2
        offset = self._slot_offset(sequence)
        if TAG.unpack_from(self._buffer(), offset)[0] != expected_begin:
            return None                            # slot reused by a newer frame
        end_tag = offset + self.slot_bytes - TAG.size
        if TAG.unpack_from(self._buffer(), end_tag)[0] != expected_end:
            return None                            # torn write in progress
        length = LENGTH.unpack_from(self._buffer(), offset + TAG.size)[0]
        if length > self.payload_bytes:
            return None                            # corrupt length; never trust it
        start = offset + SLOT_OVERHEAD
        frame = bytes(self._buffer()[start:start + length])
        # Validate again *after* copying: the writer may have started re-using this
        # slot while the bytes were being copied, which a check before the copy alone
        # cannot see. Both tags are written outside the payload region, so this second
        # read is the one that makes the copy atomic from the reader's point of view.
        if TAG.unpack_from(self._buffer(), offset)[0] != expected_begin:
            return None
        if TAG.unpack_from(self._buffer(), end_tag)[0] != expected_end:
            return None
        return sequence, frame

    def close(self):
        if self._closed:
            return
        mapping = self._mapping
        if not mapping.closed:
            # Close the mapping first: it can refuse while an exported buffer is live,
            # and releasing producer ownership then would let a second writer truncate
            # a file that is still mapped writable. A refusal leaves the ring owned and
            # retryable instead of permanently half-closed.
            mapping.close()
        self._closed = True
        self._release_ownership()

    def _release_ownership(self):
        release, self._release_lock = self._release_lock, None
        fd, self._lock_fd = self._lock_fd, None
        if release is None:
            # Readers retain no descriptor; a producer always owns exactly one finalizer.
            assert fd is None, 'producer descriptor without an owner'
            return
        if release.alive:
            release()        # closes the original descriptor, releasing the producer lock
            return
        # Already closed by the finalizer; a second os.close() could hit a reused number.
        assert fd is None or not _descriptor_open(fd), 'producer descriptor already released'

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False


def _descriptor_open(fd):
    try:
        os.fstat(fd)
    except OSError:
        return False
    return True
