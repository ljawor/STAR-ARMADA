#!/usr/bin/env python3
"""B5 scope probe: classify every environment row by what the renderer actually draws for it.

    PYTHONPATH=tests .venv/bin/python tools/art/probe_b5_scope.py

The B5 batch is written into the roadmap as "environment props", which reads like fourteen meshes.
This probe answers what they are, from the live code rather than from the inventory's prose: a planet
surface here is a numpy-generated equirect texture bound onto a shared unit UV sphere, a starfield is
an effect, the menu backdrop is a baked movie, and the asteroid field is the one row whose geometry is
per-instance and could be replaced by a shared authored prop.

No artifact is written: the scope note is the record, and this probe regenerates the table.
"""
import ast
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

INVENTORY = json.loads((ROOT / 'art/manifests/model_inventory.json').read_text(encoding='utf-8'))
ROWS = [r for r in (INVENTORY.get('rows') or INVENTORY.get('bindings'))
        if r['category'] in ('environment_prop', 'menu_cinematic')]

TEXTURES = (ROOT / 'render/textures.py').read_text(encoding='utf-8')
RENDERER = (ROOT / 'render/renderer.py').read_text(encoding='utf-8')
MATERIALS = (ROOT / 'render/fleet_materials.py').read_text(encoding='utf-8')

# What each row is, keyed by the kind in its binding. Read off the dispatch the inventory names and
# confirmed against the source below: "texture" means the visible surface is a generated
# GL_TEXTURE_2D with no asset file, "effect" means the row is drawn from primitives with no surface
# or geometry asset, "geometry" means real triangles exist per instance, "movie" means a baked video.
KINDS = {
    'agricultural': 'planet surface texture', 'barren': 'planet surface texture',
    'gas_giant': 'planet surface texture', 'industrial': 'planet surface texture',
    'military': 'planet surface texture', 'research': 'planet surface texture',
    'temperate': 'planet surface texture', 'trade': 'planet surface texture',
    'star': 'billboard texture', 'nebula': 'billboard texture',
    'deep_space_sky_dome': 'effect (starfield)', 'jump_point': 'effect (jump glyph)',
    'asteroid_field': 'geometry (per-instance rocks)',
}


def seam_consults(prefix):
    """Does any render/game module consult the authored-model seam for this prefix?"""
    hits = []
    for path in list((ROOT / 'render').rglob('*.py')) + list((ROOT / 'game').rglob('*.py')):
        text = path.read_text(encoding='utf-8', errors='replace')
        for match in re.finditer(r"mesh_for\(([^\n)]*)\)", text):
            if prefix in match.group(1):
                hits.append(f'{path.relative_to(ROOT)}:{text[:match.start()].count(chr(10)) + 1}')
    return hits


def constants(name, source=RENDERER):
    """The literal numbers a function is written with, so the note quotes the code not a memory."""
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            body = ast.get_source_segment(source, node) or ''
            return {'range_n': len(re.findall(r'range\((\w+)\)', body)),
                    'uniform_bounds': re.findall(r'rng\.uniform\((-?[\d.]+),\s*(-?[\d.]+)\)', body),
                    'radius_scale': re.findall(r'e\.radius \* \(([\d.]+) \+ ([\d.]+)', body)}
    return {}


print(f"{'row':34s} {'what it is':28s} {'mesh_for seam'}")
for row in ROWS:
    kind = row['canonical_binding'].split(':')[-1]
    what = KINDS.get(kind, '?')
    seam = seam_consults(kind)
    print(f"{row['canonical_binding']:34s} {what:28s} {seam or 'none'}")

print()
print('textures generated in render/textures.py (no asset files):')
for node in ast.parse(TEXTURES).body:
    if isinstance(node, ast.FunctionDef):
        print('   ', node.name)
print()
print('planet surface is bound from a texture on a shared unit sphere:')
print('    render/renderer.py: %s' % [l.strip() for l in MATERIALS.splitlines()
                                    if 'surfaceMap' in l][:1])
print('    asteroid field constants:', constants('_draw_asteroid_field'))
print('    draw list builder:', 'def _build_textured_sphere_list' in RENDERER)
print()
movie = ROOT / 'tools/build_menu_movie.py'
print('menu backdrop pipeline:', movie.relative_to(ROOT) if movie.exists()
      else 'tools/build_menu_movie.py (named by the inventory; not present at this revision)')
print('storage policy gate:',
      [l.strip() for l in (ROOT / 'art/manifests/pipeline_policy.json').read_text(encoding='utf-8')
       .splitlines() if 'textures' in l][:1])
print()
print('rows:', len(ROWS),
      '| by class:', {v: sum(1 for r in ROWS
                             if KINDS.get(r['canonical_binding'].split(':')[-1]) == v)
                      for v in sorted(set(KINDS.values()))})
