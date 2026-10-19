"""Render-only visual selection. Never imported by authoritative simulation."""


import re


MAX_ENABLED_PACKS = 32
_PACK_DIRECTORY = re.compile(r'[a-zA-Z0-9][a-zA-Z0-9._-]{0,63}')


def selection_preferences(settings):
    """Validate a separate, explicitly ordered render-only preference list."""
    settings = settings if isinstance(settings, dict) else {}
    packs = settings.get('visual_packs', [])
    if (not isinstance(packs, list) or len(packs) > MAX_ENABLED_PACKS
            or any(not isinstance(p, str) or not _PACK_DIRECTORY.fullmatch(p) for p in packs)
            or len(packs) != len(set(packs))):
        raise ValueError('Invalid visual_packs: expected unique pack directory names (maximum 32)')
    return {'model_preview': settings.get('model_preview') is True,
            'visual_packs': list(packs)}


_selection = {'model_preview': False, 'visual_packs': []}
_resolver = None
_generation = 0
_renderer_owners = set()


def attach_renderer():
    """A renderer owns its context resources until explicit, idempotent release."""
    token = object()
    _renderer_owners.add(token)
    return token


def release_renderer(token):
    _renderer_owners.discard(token)


def configure(settings, *, asset_root=None, pack_root=None, gameplay_entities=None):
    """Prepare a resolver, then publish it only at an explicit session boundary."""
    global _selection, _generation, _resolver
    if _renderer_owners:
        raise RuntimeError('Model selection changes require a session boundary with renderers closed')
    selection = selection_preferences(settings)
    candidate = None
    if selection['model_preview']:
        from render.asset_registry import AssetResolver
        candidate = AssetResolver(asset_root, gameplay_entities=gameplay_entities)
        if selection['visual_packs']:
            if pack_root is None:
                raise ValueError('An explicit external visual pack root is required')
            from pathlib import Path
            root = Path(pack_root).resolve()
            candidate.activate_packs([root / name / 'visual-pack.json'
                                      for name in selection['visual_packs']], pack_root=root)
    previous = _resolver
    _selection, _resolver = selection, candidate
    if previous is not None:
        previous.cache_clear()
    invalidate_geometry_helpers()
    _generation += 1
    return diagnostics()


def configure_from_settings(settings):
    """Application session seam: assets in bundle, visual packs in writable user storage."""
    from pathlib import Path
    from render import menus
    result = configure(settings, asset_root=menus.ASSET_ROOT,
                       pack_root=Path(menus.USER_DIR) / 'visual_packs')
    import logging
    logging.getLogger(__name__).info('Model selection: %s', result)
    return result


def invalidate_geometry_helpers():
    """Drop derived CPU data without importing renderer/GL modules for tooling."""
    import sys
    targets = {
        'render.ship_sizes': ('_canonical_bounds', '_canonical_ray_mesh', '_station_ray_mesh'),
        'render.camera_geometry': ('_station_bounds', '_station_radius'),
        'render.planet_building_geometry': ('_station_local_bounds',),
    }
    for name, functions in targets.items():
        module = sys.modules.get(name)
        if module is not None:
            for function in functions:
                getattr(module, function).cache_clear()


def diagnostics():
    import json
    return {'mode': 'preview' if _selection['model_preview'] else 'legacy',
            'enabled_order': list(_selection['visual_packs']),
            'generation': _generation,
            'pack_order': [dict(entry) for entry in _resolver.active_order] if _resolver else [],
            'issues': json.loads(json.dumps(_resolver.diagnostics, default=dict)) if _resolver else []}


def mesh_for(binding):
    """Return validated immutable geometry, or explicit legacy selection/fallback."""
    if _resolver is None or not _resolver.has_binding(binding):
        return None
    resolved = _resolver.resolve(binding)
    return None if resolved is None else resolved.mesh


def gpu_cache_key(binding, role, legacy_key):
    """Content/material/LOD identity; the owning Renderer supplies context scope."""
    if _resolver is None or not _resolver.has_binding(binding):
        return legacy_key
    key = _resolver.cache_key(binding)
    return legacy_key if key is None else ('authored', *key, role)


def selected_binding(binding):
    """Probe an optional entity mapping without guessing a filename or creating an entity."""
    return (_resolver is not None and _resolver.has_binding(binding)
            and _resolver.is_authored(binding))


def ship_binding(ds, data_id, faction=None):
    if _resolver is None:
        return None
    from render.faction_visuals import convoy_key
    data = ds.ships.get(data_id)
    if data is None:
        binding = convoy_key(faction) if data_id == 'trade_convoy' else None
    else:
        role = data.category
        if role == 'fighter_squadron':
            role = 'bomber' if ('bomber' in data_id or data_id == 'rebel_y_squadron') else 'fighter'
        elif role == 'construction':
            role = 'colonizer' if data_id.endswith('_colonizer') else 'constructor'
        elif role == 'crew_transport' and data.crew_capacity > 0:
            # A crew transport with crew space is a convoy: built by the same declared gate as
            # ship_visual_key's convoy branches (s06-imperial-convoy-parity-2026-10-18).
            role = 'convoy'
        binding = convoy_key(data.faction) if role == 'convoy' else f'{data.faction}:{role}'
    return binding if selected_binding(binding) else None


def is_authored(binding):
    return mesh_for(binding) is not None
