"""Read-only orbital construction visuals, independent of sim entity lifetime.

ARMADAF2 instances with FLAG_DYNAMIC_MESH refer to ARMHWR01 geometry, not
planet/surface hardware. Synthetic IDs occupy the high half of uint32 and are
render-only: never feed them to selection, commands or simulation lookup.
"""
from . import packed

SCAFFOLD = 'shared:construction_scaffold'


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
        if not 0 <= builder.id < 0x40000000:
            raise packed.FrameError('constructor ID overlaps render-only station namespace')
        position = item['pos']
        if isinstance(position, dict):
            position = (position['x'], position['y'], position['z'])
        fraction = max(0., min(1., 1. - max(0., item.get('time_left', 0.)) /
                               max(.1, item.get('total', 1.))))
        scale = data.radius / 50.
        matrix = list(packed.matrix_from_pose((position[0], 0., position[2]), 0., scale))
        matrix[4] *= .4 + .6 * fraction
        color = state.players[builder.owner].color
        yield packed.instance_record(entity_id=0x80000000 | builder.id, binding_id=binding,
            matrix=matrix, tint=(*color[:3], 1.), flags=packed.FLAG_DYNAMIC_MESH,
            hp=1., shield=0.)
        # Full-sized planned hull, separate from the vertically growing scaffold.
        # The top two render-only ID quarters cannot collide with one another.
        from render.faction_visuals import normalize_station_key
        faction = state.players[builder.owner].faction
        hull_binding = binding_index.get(':'.join(normalize_station_key(item['item'], faction)))
        if hull_binding is not None:
            yield packed.instance_record(entity_id=0xC0000000 | builder.id,
                binding_id=hull_binding,
                matrix=packed.matrix_from_pose(tuple(position), 0., scale),
                tint=(*color[:3], .20 + .35 * fraction), flags=packed.FLAG_DYNAMIC_MESH,
                hp=1., shield=0.)
