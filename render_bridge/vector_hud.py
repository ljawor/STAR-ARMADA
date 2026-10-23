"""Display-only vector HUD producer. Capture before rasterization, never from dirty ops.

Coordinates and clips share one edge-rounded affine mapping. Source layout stays
unchanged so Python alone allocates rows and owns all interaction payloads.
"""
from __future__ import annotations

import copy
import json
import math
from typing import Any

import pygame

MAX_PAYLOAD = 5 * 1024 * 1024
MAX_OPS = 4096


class BoundedText(str):
    """An unabridged translated label with its source-layout line-box width."""
    width: float
    def __new__(cls, text, width):
        obj = super().__new__(cls, text)
        obj.width = width
        return obj


def color4(color):
    values = list(color)
    return values if len(values) == 4 else values + [255]


class Capture:
    def __init__(self, width, height):
        self.width, self.height = width, height
        self.ops = []
        self.fog = None
        self.text_bytes = 0

    def snapshot(self, active):
        return copy.deepcopy({'version': 1, 'active': bool(active),
                              'logical_size': [self.width, self.height],
                              'ops': self.ops if active else [],
                              'fog': self.fog if active else None})

    def append(self, op):
        if len(self.ops) >= MAX_OPS:
            raise ValueError('Native vector HUD operation budget exceeded')
        if op['kind'] == 'text':
            n = len(op['text'].encode('utf-8'))
            if n > 4096 or self.text_bytes + n > 65536:
                raise ValueError('Native vector HUD text budget exceeded')
            self.text_bytes += n
        self.ops.append(op)


class Sink:
    def __init__(self, capture, scope, *, source_x=0, target_x=0,
                 source_y=44, target_y=44, scale: float=1):
        self.capture = capture
        self.scope = pygame.Rect(scope)
        self.source_x, self.target_x, self.scale = source_x, target_x, scale
        self.source_y, self.target_y = source_y, target_y

    def point(self, point):
        x, y = point
        return [round(self.target_x + self.scale * (x - self.source_x)),
                round(self.target_y + self.scale * (y - self.source_y))]

    def rect(self, rect):
        r = pygame.Rect(rect)
        x0, y0 = self.point(r.topleft)
        x1, y1 = self.point(r.bottomright)
        return [x0, y0, max(0, x1 - x0), max(0, y1 - y0)]

    def clip(self, surface):
        clip = surface.get_clip().clip(self.scope)
        if clip.width <= 0 or clip.height <= 0:
            return None
        result = self.rect(clip)
        return result if result[2] > 0 and result[3] > 0 else None

    def emit(self, surface, kind, **fields):
        clip = self.clip(surface)
        if clip is not None:
            self.capture.append({'kind': kind, 'clip': clip, **fields})

    def geometry(self, kind, surface, color, args, kwargs):
        fields: dict[str, Any] = {'color': color4(color)}
        if kind in ('rect', 'ellipse'):
            fields.update(rect=self.rect(args[0]), stroke=args[1] * self.scale)
            if kind == 'rect':
                fields['radius'] = max(0, kwargs.get('border_radius', 0)) * self.scale
        elif kind == 'circle':
            fields.update(center=self.point(args[0]), radius=args[1] * self.scale,
                          stroke=args[2] * self.scale)
        elif kind == 'line':
            fields.update(points=[self.point(args[0]), self.point(args[1])],
                          stroke=args[2] * self.scale)
        elif kind == 'polygon':
            fields.update(points=[self.point(p) for p in args[0]], stroke=args[1] * self.scale)
        else:
            raise ValueError('Unsupported native vector HUD primitive: ' + kind)
        self.emit(surface, kind, **fields)
        return pygame.Rect(0, 0, 0, 0)

    def text(self, surface, x, y, text, color, size, width, height, *, fit='shrink'):
        bounds = self.rect((x, y, max(0, width), max(0, height)))
        self.emit(surface, 'text', pos=self.point((x, y)), size=size * self.scale,
                  text=str(text), color=color4(color), bounds=bounds, fit=fit)

    def fog_mask(self, surface, state, player_id, rect):
        """Match FogMask.surface's authoritative sphere/cell sampling, not pixels.

        numpy uses [x,z]; transpose before flattening to put negative-z at the top.
        The visible class wins even if its exploration cell has not been charted.
        """
        import numpy as np
        bounds, cell = state.map_info.bounds, state.visibility_cell_size
        n = max(1, math.ceil(bounds / cell))
        if n > 2048:
            raise ValueError('Native vector HUD fog cell budget exceeded')
        centers = np.arange(n, dtype=float) * (bounds / n) - bounds / 2 + bounds / n / 2
        visible = np.zeros((n, n), dtype=bool)
        for entity, radius in state.sensor_sources(player_id):
            visible |= ((centers[:, None] - entity.pos.x)**2 + entity.pos.y**2
                        + (centers[None, :] - entity.pos.z)**2 <= radius**2)
        explored = frozenset(c for pid in state.allied_player_ids(player_id)
                             for c in state.explored_cells.get(pid, set()))
        indices = np.floor(centers / cell).astype(int)
        charted = np.fromiter(((int(x), int(z)) in explored for x in indices for z in indices),
                             dtype=bool, count=n*n).reshape(n, n)
        states = np.where(visible, ord('2'), np.where(charted, ord('1'), ord('0'))).astype('uint8')
        self.capture.fog = {'cells': n, 'states': states.T.tobytes().decode('ascii')}
        self.emit(surface, 'fog', rect=self.rect(rect))


def encode(model):
    """Strict, bounded UTF-8 JSON. Refuse malformed/oversize input; never truncate."""
    _validate(model)
    payload = json.dumps(model, ensure_ascii=False, allow_nan=False,
                         separators=(',', ':')).encode('utf-8', errors='strict')
    if len(payload) > MAX_PAYLOAD:
        raise ValueError('Native vector HUD payload exceeds its bound')
    return payload


def _validate(model):
    # Also guard data supplied by callers rather than this module's capture path.
    def walk(value, depth=0):
        if depth > 12:
            raise ValueError('Native vector HUD nesting budget exceeded')
        if isinstance(value, str):
            if any(ord(c) < 32 or 127 <= ord(c) <= 159 or ord(c) in (0x2028, 0x2029)
                   or 0x202a <= ord(c) <= 0x202e or 0x2066 <= ord(c) <= 0x2069 for c in value):
                raise ValueError('Native vector HUD text contains control characters')
            value.encode('utf-8', errors='strict')
        elif isinstance(value, float) and not math.isfinite(value):
            raise ValueError('Native vector HUD nonfinite number')
        elif isinstance(value, dict):
            for key, item in value.items():
                walk(key, depth + 1)
                walk(item, depth + 1)
        elif isinstance(value, (list, tuple)):
            for item in value:
                walk(item, depth + 1)
    walk(model)
    if set(model) != {'version', 'active', 'logical_size', 'ops', 'fog'}:
        raise ValueError('Invalid native vector HUD snapshot keys')
    if type(model['version']) is not int or model['version'] != 1 or type(model['active']) is not bool:
        raise ValueError('Invalid native vector HUD version/active')
    size = model['logical_size']
    if len(size) != 2 or any(type(v) is not int or not 64 <= v <= 16384 for v in size):
        raise ValueError('Invalid native vector HUD logical size')
    if len(model['ops']) > MAX_OPS:
        raise ValueError('Native vector HUD operation budget exceeded')
    fields = {'rect': {'rect', 'color', 'stroke', 'radius'},
              'ellipse': {'rect', 'color', 'stroke'},
              'circle': {'center', 'radius', 'color', 'stroke'},
              'line': {'points', 'color', 'stroke'},
              'polygon': {'points', 'color', 'stroke'},
              'text': {'pos', 'size', 'text', 'color', 'bounds', 'fit'}, 'fog': {'rect'}}
    text_bytes = 0
    def numbers(values, length):
        if not isinstance(values, (list, tuple)) or len(values) != length:
            raise ValueError('Invalid native vector HUD geometry')
        if any(type(v) not in (int, float) or not math.isfinite(v) or abs(v) > 65536 for v in values):
            raise ValueError('Invalid native vector HUD geometry number')
    for op in model['ops']:
        kind = op.get('kind')
        if kind not in fields or set(op) != fields[kind] | {'kind', 'clip'}:
            raise ValueError('Invalid native vector HUD operation keys')
        if kind == 'fog' and model['fog'] is None:
            raise ValueError('Native vector HUD fog operation has no states')
        for key in ('clip', 'rect', 'bounds'):
            if key in op:
                numbers(op[key], 4)
                if min(op[key][2:]) < 0:
                    raise ValueError('Negative native vector HUD size')
        for key in ('center', 'pos'):
            if key in op:
                numbers(op[key], 2)
        if 'color' in op and (len(op['color']) != 4 or any(type(v) is not int or not 0 <= v <= 255 for v in op['color'])):
            raise ValueError('Invalid native vector HUD color')
        for key in ('radius', 'stroke', 'size'):
            if key in op:
                numbers([op[key]], 1)
                maximum = 64 if key == 'stroke' else 256 if key == 'size' else 65536
                if not 0 <= op[key] <= maximum or (key == 'size' and op[key] == 0):
                    raise ValueError('Invalid native vector HUD ' + key)
        if 'points' in op:
            minimum = 3 if kind == 'polygon' else 2
            if not (minimum <= len(op['points']) <= 256) or (kind == 'line' and len(op['points']) != 2):
                raise ValueError('Invalid native vector HUD points')
            for point in op['points']:
                numbers(point, 2)
        if kind == 'text':
            n = len(op['text'].encode('utf-8'))
            text_bytes += n
            if n > 4096 or text_bytes > 65536 or op['fit'] not in ('shrink', 'clip', 'center'):
                raise ValueError('Invalid native vector HUD text')
    fog = model['fog']
    if fog is not None:
        if set(fog) != {'cells', 'states'} or type(fog['cells']) is not int or not 1 <= fog['cells'] <= 2048:
            raise ValueError('Invalid native vector HUD fog')
        if len(fog['states']) != fog['cells']**2 or set(fog['states']) - set('012'):
            raise ValueError('Invalid native vector HUD fog states')
