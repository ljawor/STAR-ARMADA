"""Input events travelling back from the C++ window to the Python game (W04).

The window owns the OS events; the simulation owns every decision about what they mean. This module
is only the format: a batch of fixed-size records inside one ring frame, so the existing
single-producer / drop-oldest ring (`render_bridge/ring.py`) carries input exactly the way it carries
frames, just in the other direction.

Layout (little-endian):

    batch header, 20 bytes:
        0  8s  magic b'ARMINP01'
        8  u16 version (1)
       10  u16 record count (0..1024)
       12  u16 reserved (0)
       14  u16 padding
       16  u32 crc32 of the records

    record, 16 bytes each: <BBHiiI
        0  u8  kind
        1  u8  button   mouse button, wheel direction, or modifier flags for keys
        2  u16 code     key code (see KEY_* below) or 0
        4  i32 x        pointer x in window pixels (HUD surface coordinates)
        8  i32 y        pointer y in window pixels
       12  u32 extra    resize: (width << 16) | height

Key codes are deliberately *not* SDL or platform numbers. Printable keys carry their ASCII value, so
a letter is the same number everywhere; everything else is one of the `KEY_*` constants below, which
the native side and this module share. A window that mapped SDL keycodes itself would silently drift
whenever SDL renumbers a scancode, and the failure would look like "that key does nothing".

Nothing here creates commands: `InputController.handle_event` still turns events into PlayerCommands,
and the simulation still validates them.
"""
from __future__ import annotations

import struct
import zlib

MAGIC = b'ARMINP01'
VERSION = 1
MAX_RECORDS = 1024
HEADER = struct.Struct('<8sHHII')
RECORD = struct.Struct('<BBHiiI')
HEADER_BYTES = HEADER.size     # 20: magic, version, count, reserved, crc
RECORD_BYTES = RECORD.size     # 16

# Event kinds.
MOTION = 1
BUTTON_DOWN = 2
BUTTON_UP = 3
WHEEL = 4
KEY_DOWN = 5
KEY_UP = 6
FOCUS_LOST = 7
RESIZE = 8
QUIT = 9

KINDS = {MOTION: 'motion', BUTTON_DOWN: 'button_down', BUTTON_UP: 'button_up', WHEEL: 'wheel',
         KEY_DOWN: 'key_down', KEY_UP: 'key_up', FOCUS_LOST: 'focus_lost', RESIZE: 'resize',
         QUIT: 'quit'}

# Non-printable keys. Printable keys send their ASCII value instead.
KEYCODE_ESCAPE = 0x100
KEYCODE_RETURN = 0x101
KEYCODE_TAB = 0x102
KEYCODE_BACKSPACE = 0x103
KEYCODE_DELETE = 0x104
KEYCODE_INSERT = 0x105
KEYCODE_SPACE = 0x106
KEYCODE_LEFT = 0x110
KEYCODE_RIGHT = 0x111
KEYCODE_UP = 0x112
KEYCODE_DOWN = 0x113
KEYCODE_HOME = 0x114
KEYCODE_END = 0x115
KEYCODE_PAGEUP = 0x116
KEYCODE_PAGEDOWN = 0x117
KEYCODE_LSHIFT = 0x120
KEYCODE_RSHIFT = 0x121
KEYCODE_LCTRL = 0x122
KEYCODE_RCTRL = 0x123
KEYCODE_LALT = 0x124
KEYCODE_RALT = 0x125
KEYCODE_F1 = 0x130
KEYCODE_F12 = KEYCODE_F1 + 11

# Modifier bits carried in `button` for key and button events.
MOD_SHIFT_LEFT = 0x01
MOD_SHIFT_RIGHT = 0x02
MOD_CTRL = 0x04
MOD_ALT = 0x08
MOD_GUI = 0x10
#: Convenience: either shift key.
MOD_SHIFT = MOD_SHIFT_LEFT | MOD_SHIFT_RIGHT

#: pygame constant for every non-printable key, resolved at import so a wrong name fails loudly.
_PYGAME_SPECIAL = {
    KEYCODE_ESCAPE: 'K_ESCAPE', KEYCODE_RETURN: 'K_RETURN', KEYCODE_TAB: 'K_TAB',
    KEYCODE_BACKSPACE: 'K_BACKSPACE', KEYCODE_DELETE: 'K_DELETE', KEYCODE_INSERT: 'K_INSERT',
    KEYCODE_SPACE: 'K_SPACE', KEYCODE_LEFT: 'K_LEFT', KEYCODE_RIGHT: 'K_RIGHT', KEYCODE_UP: 'K_UP',
    KEYCODE_DOWN: 'K_DOWN', KEYCODE_HOME: 'K_HOME', KEYCODE_END: 'K_END', KEYCODE_PAGEUP: 'K_PAGEUP',
    KEYCODE_PAGEDOWN: 'K_PAGEDOWN', KEYCODE_LSHIFT: 'K_LSHIFT', KEYCODE_RSHIFT: 'K_RSHIFT',
    KEYCODE_LCTRL: 'K_LCTRL', KEYCODE_RCTRL: 'K_RCTRL', KEYCODE_LALT: 'K_LALT', KEYCODE_RALT: 'K_RALT',
}
for _index in range(12):
    _PYGAME_SPECIAL[KEYCODE_F1 + _index] = f'K_F{_index + 1}'


class InputError(ValueError):
    """Malformed input batch."""


class Event:
    """One input event, in the window's own terms."""

    __slots__ = ('kind', 'button', 'code', 'x', 'y', 'extra')

    def __init__(self, kind, button=0, code=0, x=0, y=0, extra=0):
        if kind not in KINDS:
            raise InputError(f'unknown event kind {kind}')
        self.kind = kind
        self.button = int(button) & 0xFF
        self.code = int(code) & 0xFFFF
        self.x = int(x)
        self.y = int(y)
        self.extra = int(extra) & 0xFFFFFFFF

    def __eq__(self, other):
        return isinstance(other, Event) and self.as_tuple() == other.as_tuple()

    def __repr__(self):
        return (f'Event({KINDS[self.kind]}, button={self.button}, code={self.code:#x}, '
                f'x={self.x}, y={self.y}, extra={self.extra})')

    def as_tuple(self):
        return (self.kind, self.button, self.code, self.x, self.y, self.extra)

    # -- semantic helpers ------------------------------------------------------
    @property
    def name(self):
        return KINDS[self.kind]

    @property
    def pos(self):
        return (self.x, self.y)

    @property
    def size(self):
        """Window size for a RESIZE event."""
        return (self.extra >> 16, self.extra & 0xFFFF)

    def pygame_key(self):
        """pygame key constant for a key event."""
        import pygame

        if not 0x100 <= self.code < 0x10000:
            return self.code                      # printable keys are their ASCII value
        name = _PYGAME_SPECIAL.get(self.code)
        if name is None:
            raise InputError(f'no pygame constant for key code {self.code:#x}')
        return getattr(pygame, name)

    def pygame_mod(self):
        import pygame

        mod = 0
        if self.button & MOD_SHIFT:
            mod |= pygame.KMOD_SHIFT
        if self.button & MOD_CTRL:
            mod |= pygame.KMOD_CTRL
        if self.button & MOD_ALT:
            mod |= pygame.KMOD_ALT
        if self.button & MOD_GUI:
            mod |= pygame.KMOD_META
        return mod


def encode_batch(events):
    """Pack events into one ring frame."""
    events = list(events)
    if len(events) > MAX_RECORDS:
        raise InputError(f'{len(events)} events exceeds the {MAX_RECORDS} record ceiling')
    records = b''.join(RECORD.pack(*event.as_tuple()) for event in events)
    return HEADER.pack(MAGIC, VERSION, len(events), 0,
                       zlib.crc32(records) & 0xFFFFFFFF) + records


def decode_batch(buffer):
    """Unpack and validate one ring frame. Raises `InputError` rather than half-applying it."""
    buffer = bytes(buffer)
    if len(buffer) < HEADER_BYTES:
        raise InputError('shorter than the batch header')
    magic, version, count, reserved, crc = HEADER.unpack_from(buffer, 0)
    if reserved:
        raise InputError(f'reserved header field is {reserved}, not 0')
    if magic != MAGIC:
        raise InputError(f'bad magic {magic!r}')
    if version != VERSION:
        raise InputError(f'unsupported version {version}')
    if count > MAX_RECORDS:
        raise InputError(f'{count} records exceeds the {MAX_RECORDS} ceiling')
    expected = HEADER_BYTES + count * RECORD_BYTES
    if len(buffer) != expected:
        raise InputError(f'length {len(buffer)} but the header describes {expected}')
    records = buffer[HEADER_BYTES:]
    if zlib.crc32(records) & 0xFFFFFFFF != crc:
        raise InputError('record crc mismatch')
    events = []
    for index in range(count):
        fields = RECORD.unpack_from(records, index * RECORD_BYTES)
        try:
            events.append(Event(*fields))
        except InputError as error:
            raise InputError(f'record {index}: {error}') from error
    return events


def to_pygame(event):
    """Turn an `Event` into the pygame event object the game already handles."""
    import pygame

    if event.kind == MOTION:
        return pygame.event.Event(pygame.MOUSEMOTION, pos=event.pos, rel=(0, 0),
                                  buttons=(bool(event.button & 1), bool(event.button & 2),
                                           bool(event.button & 4)))
    if event.kind == BUTTON_DOWN:
        return pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=event.pos, button=event.button)
    if event.kind == BUTTON_UP:
        return pygame.event.Event(pygame.MOUSEBUTTONUP, pos=event.pos, button=event.button)
    if event.kind == WHEEL:
        return pygame.event.Event(pygame.MOUSEWHEEL, x=0, y=1 if event.button else -1,
                                  flipped=False, pos=event.pos)
    if event.kind in (KEY_DOWN, KEY_UP):
        kind = pygame.KEYDOWN if event.kind == KEY_DOWN else pygame.KEYUP
        return pygame.event.Event(kind, key=event.pygame_key(), mod=event.pygame_mod(),
                                  scancode=0, unicode='', repeat=False)
    if event.kind == FOCUS_LOST:
        return pygame.event.Event(pygame.WINDOWFOCUSLOST)
    if event.kind == RESIZE:
        width, height = event.size
        return pygame.event.Event(pygame.WINDOWRESIZED, x=0, y=0, width=width, height=height)
    if event.kind == QUIT:
        return pygame.event.Event(pygame.QUIT)
    raise InputError(f'no pygame event for kind {KINDS.get(event.kind)}')


def to_pygame_batch(events):
    return [to_pygame(event) for event in events]


class InputReader:
    """Reads batches from the ring the window writes; never blocks, never replays old batches."""

    def __init__(self, path, ring_module=None, from_oldest=False):
        if ring_module is None:
            from render_bridge import ring as ring_module
        self._ring = ring_module.Ring.open(path, writable=False)
        published = self._ring.published
        # A reader that attaches mid-session must not replay clicks from before it existed, so
        # the default starts at the head. Replaying is for tests and diagnostics only.
        self._consumed = max(0, published - self._ring.slots) if from_oldest else published
        #: Batches that were overwritten before this reader could consume them.
        self.skipped = 0

    @property
    def pending(self):
        return self._ring.published - self._consumed

    @property
    def dropped(self):
        """Batches the window published that this reader never consumed."""
        return max(0, self.pending - self._ring.slots)

    def read(self, limit=None):
        """Every batch published since the last call, oldest first. Overwritten batches are skipped.

        `limit` stops after that many batches, which is what a game loop following the window's
        frame cadence wants: one batch is one window frame, so a held key is still held when the
        next update runs.
        """
        published = self._ring.published
        batches = []
        if published - self._consumed > self._ring.slots:
            # The reader fell a whole ring behind: those slots already hold newer batches.
            self.skipped += published - self._consumed - self._ring.slots
            self._consumed = published - self._ring.slots
        while self._consumed < published:
            payload = self._ring.read(self._consumed)
            if payload is not None:
                batches.append(decode_batch(payload[1]))
            self._consumed += 1
            if limit is not None and len(batches) >= limit:
                break
        return batches

    def close(self):
        self._ring.close()
