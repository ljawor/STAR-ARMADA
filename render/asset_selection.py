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
    report = _coverage_for_session()
    if report is not None and not report['ok']:
        # Loud, once per configuration, and carried in diagnostics(): the session still
        # starts (a player with a damaged install can reach the menu) but nothing pretends
        # the authored catalogue is complete.
        import logging
        logging.getLogger(__name__).error(
            'Authored catalogue incomplete: %d required binding(s) failed: %s',
            len(report['required_core_failures']),
            ', '.join(report['required_core_failures'][:8]))
    return diagnostics()


def configure_from_settings(settings, *, data_store=None):
    """Application session seam: bundle assets plus verified loaded gameplay data."""
    from pathlib import Path
    from render import menus
    result = configure(settings, asset_root=menus.ASSET_ROOT,
                       pack_root=Path(menus.USER_DIR) / 'visual_packs',
                       gameplay_entities=active_gameplay_entities(data_store))
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


_coverage_report = None
_coverage_generation = -1


def _coverage_for_session():
    """The authored catalogue's own verdict for this session, computed once.

    `AssetResolver.coverage()` loads every required core manifest, so it is not
    something to re-run from a draw path; one report per generation is enough and
    keeps diagnostics() cheap.
    """
    global _coverage_report, _coverage_generation
    if _resolver is None:
        _coverage_report, _coverage_generation = None, -1
        return None
    if _coverage_report is None or _coverage_generation != _generation:
        _coverage_report = _resolver.coverage()
        _coverage_generation = _generation
    return _coverage_report


def diagnostics():
    import json
    coverage = _coverage_for_session()
    return {'mode': 'preview' if _selection['model_preview'] else 'legacy',
            'enabled_order': list(_selection['visual_packs']),
            'generation': _generation,
            'pack_order': [dict(entry) for entry in _resolver.active_order] if _resolver else [],
            'effective_bindings': _resolver.pack_bindings() if _resolver else [],
            'issues': json.loads(json.dumps(_resolver.diagnostics, default=dict)) if _resolver else [],
            # S11: a session drawn from a partly broken catalogue must say so instead of
            # looking complete. `ok` is False when any required core binding failed to load,
            # and `procedural` names the bindings that would still fall back to legacy.
            'coverage': None if coverage is None else {
                'ok': coverage['ok'],
                'required_core_failures': list(coverage['required_core_failures']),
                'authored': list(coverage['authored']),
                'procedural': list(coverage['procedural'])}}


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


def active_gameplay_entities(data_store):
    """Only ship IDs actually loaded by a gameplay mod satisfy an additive pack.

    Provenance is captured by DataStore's loader, not inferred from files merely
    present on disk or from a visual pack's own declarations. Effective last
    gameplay writer wins. This metadata never enters saves/replays/checksums.
    """
    result = {}
    for data_id, mod_name in getattr(data_store, 'ship_mod_sources', {}).items():
        if data_id in data_store.ships:
            key = _ship_binding(data_store, data_id)
            result.setdefault('gameplay:' + mod_name, set()).add(key)
    return result


def ship_binding(ds, data_id, faction=None):
    if _resolver is None:
        return None
    binding = _ship_binding(ds, data_id, faction)
    return binding if selected_binding(binding) else None


def _ship_binding(ds, data_id, faction=None):
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
    return binding


def is_authored(binding):
    return mesh_for(binding) is not None
