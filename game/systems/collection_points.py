"""Eligibility and coordinate policy shared by simulation and human controls."""
from game.core import detmath as math
from game.data.store import DataStore


def collection_capable(entity):
    if entity is None or not entity.is_station or not entity.operational or entity.boarding:
        return False
    definition = DataStore.get().stations.get(entity.data_id)
    return bool(definition and definition.builds_ships)


def valid_point(point):
    return (isinstance(point, (tuple, list)) and len(point) == 3
            and all(type(value) in (int, float) and abs(value) <= 1e9
                    and math.isfinite(value) for value in point))