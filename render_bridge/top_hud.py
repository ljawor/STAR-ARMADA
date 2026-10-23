"""Versioned display-only native upper-HUD model; no surfaces, fonts or sim writes.

The remaining HUD stays in hud.ring. This small self-contained snapshot can be
read by a late-attaching viewer without a bitmap keyframe or patch history.
"""
from __future__ import annotations

import json

from render import i18n

MAX_PAYLOAD = 16384
TXT = [214, 224, 238]
DIM = [128, 142, 164]
WARN = [232, 168, 76]
BAD = [232, 92, 76]


def build(state, local_player: int, *, paused=False, fps=0.0, active=True) -> dict:
    """Copy authoritative values, including command usage and real income rates."""
    player = state.players.get(local_player)
    income = (getattr(player, 'income_frame', None) or {}) if player else {}
    used = player.command_used(state.entities) if player else 0
    capacity = player.command_capacity if player else 0
    rows = (
        ('CR', 'credits', [86, 140, 220]),
        ('MT', 'materials', [200, 170, 120]),
        ('EN', 'energy', [150, 220, 240]),
        ('CRW', 'crew', [110, 200, 120]),
    )
    cells = []
    for label, attr, color in rows:
        rate = income.get(attr, 0.0)
        zero = abs(rate) < 1e-9
        cells.append({'label': label, 'value': f'{getattr(player, attr, 0):,.0f}',
                      'rate': '0/s' if zero else f'{rate:0.1f}/s',
                      'color': color, 'rate_color': BAD if zero else DIM})
    cells.append({'label': 'CMD', 'value': f'{used}/{capacity}', 'rate': '',
                  'color': WARN if used >= capacity else TXT, 'rate_color': DIM})
    seconds = max(0, int(state.time))
    return {'version': 1, 'active': bool(active and player is not None), 'cells': cells,
            'clock': f'{seconds // 60:02d}:{seconds % 60:02d}',
            'paused': i18n.t('PAUSED') if paused else '',
            'fps': f'{fps:0.0f} FPS' if fps > 0 else ''}


def encode(model: dict) -> bytes:
    """Encode a bounded UTF-8 snapshot. Native code validates the full schema."""
    payload = json.dumps(model, ensure_ascii=False, allow_nan=False,
                         separators=(',', ':')).encode('utf-8')
    if len(payload) > MAX_PAYLOAD:
        raise ValueError('Native top HUD payload exceeds its bound')
    return payload
