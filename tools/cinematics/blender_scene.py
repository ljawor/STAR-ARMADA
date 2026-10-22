"""Blender-only offline authoring of the HD menu cinematic (no game renderer import).

Script-authoritative scene: approved core triangles are read, never rewritten.
Cinematic materials/light/effects are isolated here; output is a pre-rendered movie,
not a claim about native gameplay graphics. Run with Blender5.0.1 --background.
"""
from pathlib import Path
import argparse
import hashlib
import json
import math
import random
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.cinematics.scene_spec import camera_pose, ship_pose


def arguments():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--frames', default='24,144,264', help='Comma-separated source frames, or all')
    parser.add_argument('--samples', type=int, default=64)
    return parser.parse_args(sys.argv[sys.argv.index('--')+1:])


def main():
    args = arguments()
    plan = json.loads(args.plan.read_text(encoding='utf-8'))
    root = Path(plan['repo_root']).resolve()
    out = args.out.resolve()
    if (out / 'scene.blend').exists():
        raise ValueError('Refusing to overwrite an existing scene master; use a fresh output directory')
    if out.is_relative_to(root / 'assets'):
        raise ValueError('Candidates must remain outside shipped assets until owner review')
    assert plan['resolution'] == [2560, 1440] and plan['fps'] == 24
    assert 16 <= args.samples <= 256
    payloads = {}
    for row in plan['ships']:
        path = (root / row['runtime_path']).resolve()
        if not path.is_relative_to(root / 'assets/models'):
            raise ValueError('Model path escapes core assets')
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != row['runtime_sha256']:
            raise ValueError('Approved mesh differs from scene plan: ' + row['binding'])
        payloads[row['runtime_path']] = json.loads(data)
    import bpy
    from mathutils import Vector
    if bpy.app.version_string != '5.0.1':
        raise RuntimeError('Pinned Blender5.0.1 required: ' + bpy.app.version_string)
    out.mkdir(parents=True, exist_ok=True)
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)
    scene = bpy.context.scene
    scene.render.engine = 'BLENDER_EEVEE'
    scene.render.resolution_x, scene.render.resolution_y = plan['resolution']
    scene.render.resolution_percentage = 100
    scene.render.fps = plan['fps']
    scene.eevee.taa_render_samples = args.samples
    scene.eevee.use_raytracing = True
    scene.eevee.use_fast_gi = True
    scene.eevee.fast_gi_distance = 24
    scene.eevee.fast_gi_quality = .75
    scene.eevee.shadow_ray_count = 3
    scene.render.use_motion_blur = False  # Preserve fine hull detail; motion is sampled analytically.
    scene.render.image_settings.file_format = 'JPEG'
    scene.render.image_settings.quality = 98
    scene.render.image_settings.color_mode = 'RGB'
    scene.view_settings.view_transform = 'AgX'
    scene.view_settings.look = 'AgX - Medium High Contrast'
    scene.view_settings.exposure = .45
    scene.render.film_transparent = False
    scene['scope'] = plan['scope']
    scene['authority'] = 'script-authoritative; blender_scene.py + pinned plan'
    scene['plan_json'] = json.dumps(plan)

    def emission(name, color, strength):
        mat = bpy.data.materials.new(name)
        mat.use_nodes = True
        nodes=mat.node_tree.nodes;nodes.clear()
        shader=nodes.new('ShaderNodeEmission');shader.inputs['Color'].default_value=(*color,1)
        shader.inputs['Strength'].default_value=strength
        output=nodes.new('ShaderNodeOutputMaterial')
        mat.node_tree.links.new(shader.outputs[0],output.inputs['Surface'])
        return mat

    palettes = {
        'imperial': {'base':(.17,.23,.30), 'dark':(.024,.035,.05), 'trim':(.42,.49,.57),
                     'accent':(.025,.28,.65), 'lit':(1,.58,.17), 'cool':(.025,.65,1)},
        'rebel': {'base':(.44,.40,.33), 'dark':(.035,.043,.055), 'trim':(.68,.64,.52),
                  'accent':(.72,.105,.025), 'lit':(1,.62,.24), 'cool':(.08,.68,1)}}
    materials = {}
    for faction, palette in palettes.items():
        for role,color in palette.items():
            if role in ('lit','cool'):
                mat=emission(faction+'_'+role,color,2.8 if role=='lit' else 2.2)
                if role=='lit':
                    nodes=mat.node_tree.nodes;links=mat.node_tree.links
                    coord=nodes.new('ShaderNodeTexCoord');separate=nodes.new('ShaderNodeSeparateXYZ')
                    links.new(coord.outputs['Generated'],separate.inputs[0])
                    frequency=nodes.new('ShaderNodeMath');frequency.operation='MULTIPLY';frequency.inputs[1].default_value=82
                    links.new(separate.outputs['Y'],frequency.inputs[0])
                    repeat=nodes.new('ShaderNodeMath');repeat.operation='PINGPONG';repeat.inputs[1].default_value=1
                    links.new(frequency.outputs[0],repeat.inputs[0])
                    window=nodes.new('ShaderNodeMath');window.operation='GREATER_THAN';window.inputs[1].default_value=.42
                    links.new(repeat.outputs[0],window.inputs[0])
                    tint=nodes.new('ShaderNodeMixRGB');tint.blend_type='MULTIPLY';tint.inputs[0].default_value=.94
                    tint.inputs[1].default_value=(*color,1);links.new(window.outputs[0],tint.inputs[2])
                    links.new(tint.outputs[0],next(n for n in nodes if n.type=='EMISSION').inputs['Color'])
                materials[faction,role]=mat
                continue
            mat=bpy.data.materials.new(faction+'_'+role)
            mat.use_nodes=True
            nodes=mat.node_tree.nodes;links=mat.node_tree.links
            bsdf=nodes.get('Principled BSDF')
            bsdf.inputs['Metallic'].default_value=.68 if role in ('base','trim') else .22
            bsdf.inputs['Roughness'].default_value=.32 if role!='dark' else .52
            bsdf.inputs['Base Color'].default_value=(*color,1)
            if role in ('base','trim'):
                coord=nodes.new('ShaderNodeTexCoord')
                noise=nodes.new('ShaderNodeTexNoise');noise.inputs['Scale'].default_value=64
                noise.inputs['Detail'].default_value=2
                links.new(coord.outputs['Generated'],noise.inputs['Vector'])
                ramp=nodes.new('ShaderNodeValToRGB')
                ramp.color_ramp.elements[0].color=(*(c*.72 for c in color),1)
                ramp.color_ramp.elements[1].color=(*(c*1.12 for c in color),1)
                links.new(noise.outputs['Fac'],ramp.inputs[0]);links.new(ramp.outputs[0],bsdf.inputs['Base Color'])
                bump=nodes.new('ShaderNodeBump');bump.inputs['Strength'].default_value=.12
                bump.inputs['Distance'].default_value=.11
                links.new(noise.outputs['Fac'],bump.inputs['Height'])
                mapping=nodes.new('ShaderNodeVectorMath');mapping.operation='MULTIPLY'
                mapping.inputs[1].default_value=(9,24,8)
                links.new(coord.outputs['Generated'],mapping.inputs[0])
                plating=nodes.new('ShaderNodeTexBrick');plating.offset=.25
                plating.inputs['Scale'].default_value=1
                plating.inputs['Mortar Size'].default_value=.013
                plating.inputs['Mortar Smooth'].default_value=.005
                plating.inputs['Brick Width'].default_value=.8
                plating.inputs['Row Height'].default_value=.5
                plating.inputs['Color1'].default_value=(.78,.78,.78,1)
                plating.inputs['Color2'].default_value=(1,1,1,1)
                plating.inputs['Mortar'].default_value=(.14,.14,.14,1)
                links.new(mapping.outputs[0],plating.inputs['Vector'])
                tint=nodes.new('ShaderNodeMixRGB');tint.blend_type='MULTIPLY';tint.inputs[0].default_value=.40
                links.new(ramp.outputs[0],tint.inputs[1]);links.new(plating.outputs['Color'],tint.inputs[2])
                links.new(tint.outputs[0],bsdf.inputs['Base Color'])
                grooves=nodes.new('ShaderNodeBump');grooves.inputs['Strength'].default_value=.20
                grooves.inputs['Distance'].default_value=.40;grooves.invert=True
                links.new(plating.outputs['Fac'],grooves.inputs['Height'])
                links.new(bump.outputs['Normal'],grooves.inputs['Normal']);links.new(grooves.outputs['Normal'],bsdf.inputs['Normal'])
            materials[faction,role]=mat

    world=bpy.data.worlds.new('Original procedural deep-space sky')
    scene.world=world;world.use_nodes=True
    nodes=world.node_tree.nodes;links=world.node_tree.links
    background=nodes.get('Background');background.inputs['Strength'].default_value=.20
    coord=nodes.new('ShaderNodeTexCoord')
    noise=nodes.new('ShaderNodeTexNoise');noise.inputs['Scale'].default_value=3.3
    noise.inputs['Detail'].default_value=5;noise.inputs['Roughness'].default_value=.68
    links.new(coord.outputs['Normal'],noise.inputs['Vector'])
    ramp=nodes.new('ShaderNodeValToRGB')
    ramp.color_ramp.elements[0].position=.28;ramp.color_ramp.elements[0].color=(.001,.003,.009,1)
    ramp.color_ramp.elements[1].position=.76;ramp.color_ramp.elements[1].color=(.10,.20,.38,1)
    midpoint=ramp.color_ramp.elements.new(.57);midpoint.color=(.013,.032,.072,1)
    links.new(noise.outputs['Fac'],ramp.inputs[0]);links.new(ramp.outputs[0],background.inputs['Color'])

    def light(name,kind,location,color,power,size=0,target=(0,0,0)):
        data=bpy.data.lights.new(name,kind);data.energy=power;data.color=color
        if kind=='AREA':data.shape='DISK';data.size=size
        elif kind=='POINT':data.shadow_soft_size=size
        obj=bpy.data.objects.new(name,data);scene.collection.objects.link(obj);obj.location=location
        if kind!='POINT':obj.rotation_euler=(Vector(target)-obj.location).to_track_quat('-Z','Y').to_euler()
        return obj
    sun=light('Grazing warm starlight','SUN',(-600,-700,900),(1,.84,.64),2.2)
    sun.data.angle=.035
    light('Broad cinematic key','AREA',(100,-420,670),(.68,.82,1),2800000,620)
    light('Blue edge separation','AREA',(-500,420,180),(.18,.44,1),1900000,500)
    light('Warm opposing rim','AREA',(620,300,280),(1,.44,.19),1500000,420)

    camera_data=bpy.data.cameras.new('Cinematic camera');camera=bpy.data.objects.new('Cinematic camera',camera_data)
    scene.collection.objects.link(camera);scene.camera=camera
    camera_data.lens=47;camera_data.sensor_width=36;camera_data.clip_start=2;camera_data.clip_end=10000
    camera_data.shift_y=.10
    camera_data.dof.use_dof=False  # No blur substituted for low resolution.
    objects=[]
    for row in plan['ships']:
        payload=payloads[row['runtime_path']]
        vertices=[(p[0],-p[2],p[1]) for p in payload['vertices']]
        faces=[];roles=[]
        for role,batch in payload['batches'].items():
            faces.extend(tuple(face[3:]) for face in batch);roles.extend([role]*len(batch))
        mesh=bpy.data.meshes.new(row['binding']+' mesh');mesh.from_pydata(vertices,[],faces);mesh.update()
        obj=bpy.data.objects.new(row['binding']+' '+str(row['id']),mesh);scene.collection.objects.link(obj)
        role_names=list(payload['batches'])
        for role in role_names:mesh.materials.append(materials[row['faction'],role])
        for polygon,role in zip(mesh.polygons,roles):polygon.material_index=role_names.index(role)
        obj.scale=(row['scale'],)*3
        obj['approved_mesh_sha256']=row['runtime_sha256'];obj['binding']=row['binding']
        objects.append(obj)

    # Preserve shields as thin Fresnel envelopes, not opaque giant blue discs.
    # All changes are cinematic-only; gameplay shield rendering is untouched.
    shield_material=bpy.data.materials.new('Thin transparent shield envelope')
    shield_material.use_nodes=True
    shield_material.surface_render_method='DITHERED'
    nodes=shield_material.node_tree.nodes;nodes.clear();links=shield_material.node_tree.links
    transparent=nodes.new('ShaderNodeBsdfTransparent')
    energy=nodes.new('ShaderNodeEmission');energy.inputs['Color'].default_value=(.055,.30,.8,1)
    energy.inputs['Strength'].default_value=1.8
    fresnel=nodes.new('ShaderNodeFresnel');fresnel.inputs['IOR'].default_value=1.035
    strength=nodes.new('ShaderNodeMath');strength.operation='MULTIPLY';strength.inputs[1].default_value=.004
    links.new(fresnel.outputs[0],strength.inputs[0])
    mix=nodes.new('ShaderNodeMixShader');links.new(strength.outputs[0],mix.inputs[0])
    links.new(transparent.outputs[0],mix.inputs[1]);links.new(energy.outputs[0],mix.inputs[2])
    output=nodes.new('ShaderNodeOutputMaterial');links.new(mix.outputs[0],output.inputs['Surface'])
    shields=[]
    for row in plan['ships']:
        bpy.ops.mesh.primitive_uv_sphere_add(segments=64,ring_count=32,radius=row['length']*.57)
        shell=bpy.context.object;shell.name='Thin shield '+str(row['id'])
        shell.data.materials.append(shield_material)
        for polygon in shell.data.polygons:polygon.use_smooth=True
        shields.append(shell)

    # Sparse original stars, one cheap mesh of emissive camera-facing triangles.
    rng=random.Random(7718);star_vertices=[];star_faces=[]
    cam_direction=Vector((385,-875,420)).normalized();right=Vector((0,0,1)).cross(cam_direction).normalized();up=cam_direction.cross(right)
    for _ in range(900):
        center=-cam_direction*rng.uniform(2400,4200)+right*rng.uniform(-3100,3100)+up*rng.uniform(-1800,1800)
        radius=rng.uniform(.55,1.7)
        index=len(star_vertices)
        star_vertices.extend([tuple(center-right*radius-up*radius),tuple(center+right*radius-up*radius),tuple(center+up*radius)])
        star_faces.append((index,index+1,index+2))
    mesh=bpy.data.meshes.new('Sparse star geometry');mesh.from_pydata(star_vertices,[],star_faces)
    obj=bpy.data.objects.new('Sparse deep stars',mesh);scene.collection.objects.link(obj)
    mesh.materials.append(emission('Distant starlight',(.54,.70,1),2.5))

    cyan=emission('Ion cannon cyan',(.025,.58,1),12)
    amber=emission('Opposing plasma', (1,.11,.025),14)
    def streak(name,material,radius):
        curve=bpy.data.curves.new(name,'CURVE');curve.dimensions='3D';curve.bevel_depth=radius;curve.bevel_resolution=2
        spline=curve.splines.new('POLY');spline.points.add(1)
        curve.materials.append(material)
        obj=bpy.data.objects.new(name,curve);scene.collection.objects.link(obj)
        return obj
    links_table=[(0,4),(4,0),(1,6),(5,2),(2,5),(6,1)]
    bolts=[];hit_lights=[];impact_rings=[]
    for index,(a,b) in enumerate(links_table):
        material=cyan if plan['ships'][a]['faction']=='imperial' else amber
        bolts.append([streak(f'Volley {index}.{n}',material,.46) for n in range(3)])
        color=(.08,.55,1) if plan['ships'][a]['faction']=='imperial' else (1,.19,.045)
        hit_lights.append(light('Localized shield/armor impact '+str(index),'POINT',(0,0,0),color,0,12))
        mat=emission('Shield impact ripple '+str(index),(.06,.42,1),0)
        ring=streak('Localized expanding shield ripple '+str(index),mat,.23)
        ring.data.splines.clear();spline=ring.data.splines.new('POLY');spline.points.add(63);spline.use_cyclic_u=True
        impact_rings.append(ring)

    # Subtle photographic glare from emissive geometry, never a whole-frame blur.
    group=bpy.data.node_groups.new('Cinematic restrained emission glow','CompositorNodeTree')
    group.interface.new_socket(name='Image',in_out='OUTPUT',socket_type='NodeSocketColor')
    scene.compositing_node_group=group
    layers=group.nodes.new('CompositorNodeRLayers')
    glare=group.nodes.new('CompositorNodeGlare')
    glare.inputs['Type'].default_value='Fog Glow'
    glare.inputs['Quality'].default_value='High'
    if 'Threshold' in glare.inputs:glare.inputs['Threshold'].default_value=1.5
    if 'Strength' in glare.inputs:glare.inputs['Strength'].default_value=.20
    output=group.nodes.new('NodeGroupOutput')
    group.links.new(layers.outputs['Image'],glare.inputs['Image']);group.links.new(glare.outputs['Image'],output.inputs['Image'])

    def sample(frame):
        t=frame/plan['fps']
        scene.frame_set(frame)
        pose=camera_pose(t);camera.location=pose['location']
        camera.rotation_euler=(Vector(pose['target'])-camera.location).to_track_quat('-Z','Y').to_euler()
        for row,obj,shell in zip(plan['ships'],objects,shields):
            pose=ship_pose(row,t);obj.location=pose['location'];obj.rotation_euler=pose['rotation']
            shell.location=obj.location
        for index,(a,b) in enumerate(links_table):
            source=objects[a];target=objects[b]
            forward=Vector((math.sin(source.rotation_euler.z),-math.cos(source.rotation_euler.z),0))
            start=source.location+forward*plan['ships'][a]['length']*.40+Vector((0,0,4))
            normal=(start-target.location).normalized()
            shield_radius=plan['ships'][b]['length']*.57
            end=target.location+normal*shield_radius
            delta=end-start
            age=min((t+index*.17+n*.27-.65)%.88 for n in range(3))
            ring=impact_rings[index];ring.hide_render=age>.24
            ring_material=ring.data.materials[0]
            next(n for n in ring_material.node_tree.nodes if n.type=='EMISSION').inputs['Strength'].default_value=6*max(0,1-age/.24)**2
            radius=4+18*min(1,age/.24)
            tangent=normal.cross(Vector((0,0,1))).normalized();up=normal.cross(tangent)
            center=target.location+normal*(math.sqrt(max(0,shield_radius**2-radius**2))+.3)
            for k,point in enumerate(ring.data.splines[0].points):
                angle=math.tau*k/64
                point.co=(*(center+radius*(tangent*math.cos(angle)+up*math.sin(angle))),1)
            for n,bolt in enumerate(bolts[index]):
                flight=(t+index*.17+n*.27)%.88
                bolt.hide_render=flight>.65
                head=start+delta*(flight/.65)
                tail=head-delta*.055
                bolt.data.splines[0].points[0].co=(*tail,1)
                bolt.data.splines[0].points[1].co=(*head,1)
            hit_lights[index].location=end
            hit_lights[index].data.energy=60000*max(0,1-age/.24)**2
        bpy.context.view_layer.update()

    sample(24)
    scene.frame_start=0;scene.frame_end=int(plan['source_seconds']*plan['fps'])-1
    bpy.ops.wm.save_as_mainfile(filepath=str(out/'scene.blend'))
    frames=range(scene.frame_end+1) if args.frames=='all' else [int(f) for f in args.frames.split(',')]
    report={'plan':plan,'blender_version':bpy.app.version_string,'engine':scene.render.engine,
            'samples':args.samples,'resolution':plan['resolution'],'renders':[],
            'source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    for frame in frames:
        assert 0<=frame<=scene.frame_end
        sample(frame)
        path=out/f'frame_{frame:05d}.jpg';scene.render.filepath=str(path)
        started=time.monotonic();bpy.ops.render.render(write_still=True)
        image=bpy.data.images['Render Result']
        scene.render.image_settings.file_format='PNG';png=out/f'preview_{frame:05d}.png'
        image.save_render(str(png),scene=scene)
        scene.render.image_settings.file_format='JPEG'
        report['renders'].append(dict(frame=frame,seconds=time.monotonic()-started,
                                      jpeg=str(path),png=str(png),sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
        (out/'render-report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        print('CINEMATIC_FRAME',frame,report['renders'][-1]['seconds'],flush=True)
    print('CINEMATIC_PREVIEW_OK',len(report['renders']),flush=True)


if __name__ == '__main__':
    main()
