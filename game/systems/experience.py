"""Authoritative XP-derived ship ranks, shared by simulation and presentation.

Rank 1 is baseline; stored Entity.level is a compatibility/event mirror only.
"""
from ..data.store import DataStore

SAFETY_MAX_RANK = 5
DEFAULT_LEVELS = (0, 120, 320, 700, 1400)


def _ship(entity):
    return (DataStore.get().ships.get(entity.data_id)
            if (entity.is_ship or entity.is_squadron) and not entity.is_station else None)


def max_rank(entity):
    ship = _ship(entity)
    if ship is None:
        return 1
    cfg = DataStore.get().rules.get('experience', {})
    return max(1, min(SAFETY_MAX_RANK, ship.max_rank,
                      int(cfg.get('max_effective_level', 5)),
                      len(cfg.get('levels', DEFAULT_LEVELS))))


def _thresholds(entity):
    ship = _ship(entity)
    scale = ship.veteran_xp / 100.0 if ship else 1.0
    return [value * scale for value in
            DataStore.get().rules.get('experience', {}).get('levels', DEFAULT_LEVELS)]


def rank_for(entity):
    rank = 1
    for i, threshold in enumerate(_thresholds(entity)[:max_rank(entity)]):
        if entity.xp >= threshold:
            rank = i + 1
    return rank


def rank_progress(entity):
    rank = rank_for(entity)
    if rank >= max_rank(entity):
        return 1.0
    thresholds = _thresholds(entity)
    return max(0.0, min(1.0, (entity.xp - thresholds[rank - 1]) /
                        (thresholds[rank] - thresholds[rank - 1])))


def attack_multiplier(entity):
    bonus = DataStore.get().rules.get('experience', {}).get('per_level', {}).get('attack_bonus', .05)
    return 1.0 + (rank_for(entity) - 1) * bonus


def defense_multiplier(entity):
    """Incoming damage multiplier, not shield capacity or an armor divisor."""
    bonus = DataStore.get().rules.get('experience', {}).get('per_level', {}).get('defense_bonus', .05)
    return max(0.0, 1.0 - (rank_for(entity) - 1) * bonus)


def rank_info(entity):
    rank = rank_for(entity)
    return {'rank': rank, 'max_rank': max_rank(entity), 'xp': entity.xp,
            'next_threshold': _thresholds(entity)[rank] if rank < max_rank(entity) else None,
            'progress': rank_progress(entity),
            'attack_bonus': attack_multiplier(entity) - 1.0,
            'defense_bonus': 1.0 - defense_multiplier(entity)}
