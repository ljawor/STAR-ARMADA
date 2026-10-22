"""Read-only orbital construction visuals, independent of sim entity lifetime.

ARMADAF2 instances with FLAG_DYNAMIC_MESH refer to ARMHWR01 geometry, not
planet/surface hardware. Synthetic IDs occupy the high half of uint32 and are
render-only: never feed them to selection, commands or simulation lookup.
"""
from . import packed

SCAFFOLD = 'shared:construction_scaffold'

# The site being built draws twice: the authored scaffold frame at full opacity, and the station's
# own hull underneath it at the alpha below, rising as the work completes. A site that paid and then
# vanished for its whole build time read as a failed order; the hull says what is coming, the scaffold
# says that it is not there yet.
HULL_ALPHA_FIRST = 0.22
HULL_ALPHA_LAST = 0.85

# Render-only id space: 0x80000000 for the scaffold, 0x90000000 for the hull, both | builder id so a
# builder working one site cannot collide with itself or with the other row.
SCAFFOLD_ID_BASE = 0x80000000
HULL_ID_BASE = 0x90000000


def _hull_binding(binding_index, state, station_id, owner):
    """Binding id for the station's own mesh, or None when the faction has no such binding."""
    from render.faction_visuals import normalize_station_key
    player = state.players.get(owner)
    faction = getattr(player, 'faction', None) if player is not None else None
    if not faction:
        return None
    return binding_index.get(':'.join(normalize_station_key(station_id, faction)))


def construction_records(state, ds, binding_index, *, local_player, visible_ids=None,
                         all_visible=False):
    """Match the legacy constructor queue/owner gate, plus supplied visibility."""
    binding = binding_index.get(SCAFFOLD)
    if binding is None:
        return
    for builder in sorted(state.entities.values(), key=lambda e: e.id):
        if (not builder.alive or not builder.is_construction
                or builder.owner != local_player or not builder.build_queue):
            continue
        if not all_visible and (builder.id not in visible_ids if visible_ids is not None
                               else not state.can_see(local_player, builder.id)):
            continue
        item = builder.build_queue[0]
        if item.get('kind') != 'station' or not item.get('pos'):
            continue
        data = ds.stations.get(item.get('item'))
        if data is None:
            continue
        if not 0 <= builder.id < 0x80000000:
            raise packed.FrameError('constructor ID overlaps render-only station namespace')
        position = item['pos']
        if isinstance(position, dict):
            position = (position['x'], position['y'], position['z'])
        fraction = max(0., min(1., 1. - max(0., item.get('time_left', 0.)) /
                               max(.1, item.get('total', 1.))))
        scale = data.radius / 50.
        matrix = list(packed.matrix_from_pose((position[0], 0., position[2]), 0., scale))
        color = state.players[builder.owner].color
        hull = _hull_binding(binding_index, state, item.get('item'), builder.owner)
        if hull is not None:
            yield packed.instance_record(entity_id=HULL_ID_BASE | builder.id, binding_id=hull,
                matrix=list(matrix),
                tint=(*color[:3], HULL_ALPHA_FIRST + (HULL_ALPHA_LAST - HULL_ALPHA_FIRST) * fraction),
                flags=packed.FLAG_DYNAMIC_MESH, hp=1., shield=0.)
        scaffold_matrix = list(matrix)
        scaffold_matrix[4] *= .4 + .6 * fraction
        yield packed.instance_record(entity_id=SCAFFOLD_ID_BASE | builder.id, binding_id=binding,
            matrix=scaffold_matrix, tint=(*color[:3], 1.), flags=packed.FLAG_DYNAMIC_MESH,
            hp=1., shield=0.)
