#!/usr/bin/env python3
"""Export-only from the editable Legion fighter platform master. Never reconstructs or saves source.

Blender --background --python-exit-code 1 --python tools/art/export_legion_fighter_platform.py
Optional after --: --blend SOURCE --output TARGET. Defaults are repository-relative.

Self-contained by design: the S03 pipeline refuses an exporter that does not itself
open the declared source (E_EXPORT_NOT_FROM_SOURCE), so this file carries its own
open/validate/write path instead of importing a shared helper.
"""
from pathlib import Path
import argparse
import json
import math
import sys
import bpy

ROOT = Path(__file__).resolve().parents[2]
ROLES = ('base','dark','trim','accent','lit','cool')
IDENTIFIER = 'legion_fighter_platform'
# The binding's legacy procedural envelope. The authored mesh fills this box, so the
# renderer's class scale (ship_size: drawn length / authored Z span) is unchanged and
# the drawn length, camera framing and collision radius stay as they are today.
ENVELOPE = ((-42.4021, 42.4021), (-8.8, 11.88), (-36.4, 36.0))
MIN_LENGTH = 72.2
# The asset's own floor. 1,800 for hulls and structures; a declared small prop - the renderer draws
# it many times per frame - carries its own, per the owner decision `s06-small-prop-class-2026-10-17`.
MIN_TRIANGLES = 1800
MAX_TRIANGLES = 11500
MAX_VERTICES = 8000
MAX_BYTES = 2_000_000


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--blend', type=Path, default=ROOT / ('art/blender/' + IDENTIFIER + '.blend'))
    parser.add_argument('--output', type=Path, default=ROOT / ('assets/models/' + IDENTIFIER + '.mesh.json'))
    args = parser.parse_args(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else [])
    if (args.output.resolve() == args.blend.resolve()
            or (args.output.exists() and args.blend.exists() and args.output.samefile(args.blend))):
        raise ValueError('output must not overwrite the input Blender master')
    bpy.ops.wm.open_mainfile(filepath=str(args.blend.resolve()))
    assert bpy.context.scene['asset'] == IDENTIFIER
    vertices=[]; lookup={}; batches={role:[] for role in ROLES}; parts=[]
    depsgraph=bpy.context.evaluated_depsgraph_get()
    for obj in sorted(bpy.context.scene.objects,key=lambda o:o.name):
        if obj.type!='MESH':continue
        evaluated=obj.evaluated_get(depsgraph)
        mesh=evaluated.to_mesh(); mesh.calc_loop_triangles()
        role=obj['engine_material_role']; count=0
        for tri in mesh.loop_triangles:
            # Snap only float32 representation noise at the envelope edges.
            # This is quantization, not scaling or widening the approved policy.
            def quantize(point):
                result=[]
                for axis,c in enumerate(point):
                    value=round(float(c),6)
                    for edge in ENVELOPE[axis]:
                        if abs(value-edge)<0.000005:value=edge
                    result.append(value)
                return tuple(result)
            points=[quantize(obj.matrix_world @ mesh.vertices[i].co) for i in tri.vertices]
            a,b,c=points; u=[b[i]-a[i] for i in range(3)]; v=[c[i]-a[i] for i in range(3)]
            n=(u[1]*v[2]-u[2]*v[1],u[2]*v[0]-u[0]*v[2],u[0]*v[1]-u[1]*v[0])
            length=math.sqrt(sum(t*t for t in n))
            if length<1e-6:continue
            normal=[round(t/length,15) for t in n]
            indices=[]
            for p in points:
                if p not in lookup:lookup[p]=len(vertices);vertices.append(p)
                indices.append(lookup[p])
            batches[role].append(normal+indices);count+=1
        parts.append(dict(name=obj.name,role=role,triangles=count))
        evaluated.to_mesh_clear()
    lo=[min(p[i] for p in vertices) for i in range(3)]
    hi=[max(p[i] for p in vertices) for i in range(3)]
    for axis,(low,high) in enumerate(ENVELOPE):
        assert low-1e-6 <= lo[axis] and hi[axis] <= high+1e-6, (IDENTIFIER,axis,lo[axis],hi[axis])
    asset=dict(schema=1,asset=IDENTIFIER,authoring='Blender evaluated bevel mesh',
               coordinates='X beam; Y up; +Z forward',vertices=vertices,batches=batches,
               bounds=[lo,hi],parts=parts,triangle_count=sum(map(len,batches.values())),
               features=json.loads(bpy.context.scene['features_json']))
    assert MIN_TRIANGLES < asset['triangle_count'] <= MAX_TRIANGLES,asset['triangle_count']
    assert len(vertices)<=MAX_VERTICES,len(vertices)
    assert hi[2]-lo[2] >= MIN_LENGTH, (IDENTIFIER, hi[2]-lo[2])
    payload=json.dumps(asset,separators=(',',':'),allow_nan=False)+'\n'
    assert len(payload.encode())<MAX_BYTES
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(payload,encoding='utf-8',newline='\n')
    print('GAME_EXPORT',json.dumps(dict(asset=asset['asset'],triangles=asset['triangle_count'],vertices=len(vertices),bounds=asset['bounds'],bytes=len(payload.encode()))))


if __name__=='__main__':main()
