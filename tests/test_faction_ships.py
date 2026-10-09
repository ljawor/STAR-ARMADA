"""Headless contracts for original, renderer-only faction ship hardware."""
import importlib
import importlib.util
import math
import unittest


FACTIONS = ('rebel', 'confederacy', 'syndicate')
SHIP_ROLES = ('fighter', 'bomber', 'corvette', 'frigate', 'cruiser',
              'battleship', 'supercapital', 'constructor', 'colonizer', 'convoy')
MATERIAL_ROLES = ('base', 'dark', 'trim', 'accent', 'lit', 'cool')


def feature():
    return importlib.import_module('render.faction_ships')


def vertices(mesh, role=None):
    return [v for key in ((role,) if role else MATERIAL_ROLES)
            for _, triangle in mesh[key] for v in triangle]


class FactionShipTests(unittest.TestCase):
    def test_alliance_corvette_is_solid_twin_nacelle_hardware(self):
        self.assertIsNotNone(importlib.util.find_spec('render.faction_ships'),
                             'missing original faction ship feature')
        mesh = feature().ship_mesh('rebel', 'corvette')
        self.assertEqual(tuple(mesh), MATERIAL_ROLES)
        for role in MATERIAL_ROLES:
            self.assertIsInstance(mesh[role], tuple)
            self.assertTrue(mesh[role], role)
        with self.assertRaises(TypeError):
            mesh['base'] = ()
        points = vertices(mesh, 'base')
        self.assertGreater(max(v[2] for v in points), 40)
        self.assertLess(min(v[2] for v in points), -40)
        self.assertTrue(any(v[0] > 20 for v in points))
        self.assertTrue(any(v[0] < -20 for v in points))
        self.assertGreater(sum(map(len, mesh.values())), 900)

    def test_approved_line_ships_have_three_distinct_faction_silhouettes(self):
        silhouettes = set()
        for faction in FACTIONS:
            for role in ('corvette', 'frigate', 'cruiser'):
                with self.subTest(faction=faction, role=role):
                    mesh = feature().ship_mesh(faction, role)
                    self.assertTrue(all(mesh[k] for k in MATERIAL_ROLES))
                    points = vertices(mesh, 'base')
                    silhouettes.add(tuple(points))
                    if faction == 'confederacy':
                        # A physical split bow, not a wedge with stripes.
                        forward = [v for v in points if v[2] > {'corvette':25, 'frigate':45, 'cruiser':60}[role]]
                        self.assertTrue(forward)
                        self.assertGreater(min(abs(v[0]) for v in forward), 4)
                    if faction == 'syndicate':
                        # Raised bridge remains off-axis on starboard.
                        bridge = [v for v in points if v[1] > 20]
                        self.assertTrue(bridge)
                        self.assertGreater(sum(v[0] for v in bridge)/len(bridge), 5)
        self.assertEqual(len(silhouettes), 9)

    def test_fighters_and_bombers_are_original_small_airframes(self):
        for faction in FACTIONS:
            fighter = feature().ship_mesh(faction, 'fighter')
            bomber = feature().ship_mesh(faction, 'bomber')
            self.assertNotEqual(len(fighter['base']), len(bomber['base']))
            for mesh in (fighter, bomber):
                self.assertTrue(all(mesh[k] for k in MATERIAL_ROLES))
                points = vertices(mesh)
                length = max(v[2] for v in points) - min(v[2] for v in points)
                self.assertLess(length, 70)
                self.assertGreater(length, 20)
                self.assertGreater(sum(map(len, mesh.values())), 500)
                self.assertGreater(max(v[2] for v in points), 10)
                self.assertLess(min(v[2] for v in vertices(mesh, 'cool')), -7)

    def test_capitals_gain_modules_hangars_and_weapon_banks(self):
        for faction in FACTIONS:
            meshes = [feature().ship_mesh(faction, role)
                      for role in ('cruiser','battleship','supercapital')]
            counts = [sum(map(len, mesh.values())) for mesh in meshes]
            self.assertLess(counts[0], counts[1])
            self.assertLess(counts[1], counts[2])
            self.assertNotEqual(len(meshes[1]['base']), len(meshes[2]['base']))
            for mesh in meshes[1:]:
                self.assertTrue(all(mesh[k] for k in MATERIAL_ROLES))
                points = vertices(mesh)
                self.assertGreater(max(v[2] for v in points)-min(v[2] for v in points), 240)
                # Hangar mouth rails add luminous forward surfaces.
                self.assertTrue(any(v[2] > 50 for v in vertices(mesh,'cool')))
                self.assertTrue(any(v[2] < -100 for v in vertices(mesh,'cool')))

    def test_logistics_have_bespoke_work_habitat_and_freight_hardware(self):
        for faction in FACTIONS:
            meshes = {role:feature().ship_mesh(faction, role)
                      for role in ('constructor','colonizer','convoy')}
            signatures = {tuple(len(mesh[k]) for k in MATERIAL_ROLES)
                          for mesh in meshes.values()}
            self.assertEqual(len(signatures),3, faction)
            for mesh in meshes.values():
                self.assertTrue(all(mesh[k] for k in MATERIAL_ROLES))
                self.assertGreater(sum(map(len,mesh.values())),900)
                points = vertices(mesh)
                self.assertGreater(max(v[2] for v in points),20)
                self.assertLess(min(v[2] for v in vertices(mesh,'cool')),-20)
            self.assertGreater(max(v[1] for v in vertices(meshes['constructor'])),20)
            self.assertGreater(max(v[1] for v in vertices(meshes['colonizer'],'lit')),10)
            # Cargo carriers expose dark cargo surfaces in the forward half.
            self.assertTrue(any(v[2]>10 for v in vertices(meshes['convoy'],'dark')))

    def test_complete_catalogue_is_immutable_finite_and_outward_wound(self):
        signatures = set()
        for faction in FACTIONS:
            for role in SHIP_ROLES:
                with self.subTest(faction=faction, role=role):
                    mesh = feature().ship_mesh(faction,role)
                    signatures.add(tuple(len(mesh[k]) for k in MATERIAL_ROLES))
                    self.assertEqual(tuple(mesh), MATERIAL_ROLES)
                    self.assertTrue(all(mesh[k] for k in MATERIAL_ROLES))
                    for triangles in mesh.values():
                        self.assertIsInstance(triangles,tuple)
                        for normal, triangle in triangles:
                            self.assertIsInstance(normal,tuple)
                            self.assertIsInstance(triangle,tuple)
                            self.assertTrue(all(math.isfinite(c) for v in triangle for c in v))
                            self.assertAlmostEqual(sum(c*c for c in normal),1,places=10)
                            a,b,c = triangle
                            u = tuple(b[i]-a[i] for i in range(3))
                            v = tuple(c[i]-a[i] for i in range(3))
                            cross = (u[1]*v[2]-u[2]*v[1],u[2]*v[0]-u[0]*v[2],u[0]*v[1]-u[1]*v[0])
                            self.assertGreater(sum(n*c for n,c in zip(normal,cross)),1e-9)
        # Different topology, not 30 copies of an affine-scaled hull.
        self.assertEqual(len(signatures),30)

    def test_canonicalization_precedes_the_thirty_entry_cache(self):
        module = feature()
        module._ship_mesh.cache_clear()
        for faction in FACTIONS:
            for role in SHIP_ROLES:
                mesh = module.ship_mesh(faction,role)
                self.assertIs(module.ship_mesh('  '+faction.upper()+' ', '\t'+role.upper()+'\n'),mesh)
        info = module._ship_mesh.cache_info()
        self.assertEqual((info.maxsize,info.currsize,info.misses,info.hits),(30,30,30,30))
        for faction,role in (('imperial','fighter'),('rebel','scout'),([],{}),(None,None)):
            with self.assertRaises(ValueError):
                module.ship_mesh(faction,role)
        self.assertEqual(module._ship_mesh.cache_info(),info)

    def test_aft_engine_throats_are_not_buried_inside_solid_hulls(self):
        for faction in FACTIONS:
            for role in SHIP_ROLES:
                mesh = feature().ship_mesh(faction,role)
                def engine_face(normal, tri):
                    if normal[2] >= -.999 or max(v[2] for v in tri) >= -5:
                        return False
                    a,b,c = tri
                    # Broad aft-facing nozzle throats, excluding the tiny end
                    # faces of side-facing hangar guide strips / work lights.
                    area2 = abs((b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0]))
                    return area2 > 2
                throats = [tri for n,tri in mesh['cool'] if engine_face(n,tri)]
                self.assertTrue(throats,(faction,role))
                opaque = [tri for key in ('base','dark','trim','accent') for _,tri in mesh[key]]
                for triangle in throats:
                    x,y,z = (sum(v[i] for v in triangle)/3 for i in range(3))
                    blocked = False
                    for a,b,c in opaque:
                        denominator = (b[1]-c[1])*(a[0]-c[0])+(c[0]-b[0])*(a[1]-c[1])
                        if abs(denominator) < 1e-10:
                            continue
                        wa = ((b[1]-c[1])*(x-c[0])+(c[0]-b[0])*(y-c[1]))/denominator
                        wb = ((c[1]-a[1])*(x-c[0])+(a[0]-c[0])*(y-c[1]))/denominator
                        wc = 1-wa-wb
                        if min(wa,wb,wc) > -1e-8 and wa*a[2]+wb*b[2]+wc*c[2] < z-1e-5:
                            blocked = True
                            break
                    with self.subTest(faction=faction,role=role,throat=(x,y,z)):
                        self.assertFalse(blocked,(faction,role,(x,y,z)))

    def test_capital_launch_mouths_face_clear_space_not_neighbor_modules(self):
        for faction in FACTIONS:
            for role in ('battleship','supercapital'):
                mesh = feature().ship_mesh(faction,role)
                mouths = [tri for n,tri in mesh['cool'] if n[2] > .999 and min(v[2] for v in tri)>30]
                self.assertTrue(mouths,(faction,role))
                for triangle in mouths:
                    x,y,z = (sum(v[i] for v in triangle)/3 for i in range(3))
                    for key in ('base','dark','trim','accent'):
                        for _,(a,b,c) in mesh[key]:
                            denominator = (b[1]-c[1])*(a[0]-c[0])+(c[0]-b[0])*(a[1]-c[1])
                            if abs(denominator)<1e-10:
                                continue
                            wa = ((b[1]-c[1])*(x-c[0])+(c[0]-b[0])*(y-c[1]))/denominator
                            wb = ((c[1]-a[1])*(x-c[0])+(a[0]-c[0])*(y-c[1]))/denominator
                            wc = 1-wa-wb
                            with self.subTest(faction=faction,role=role,mouth=(x,y,z)):
                                self.assertFalse(min(wa,wb,wc)>-1e-8 and wa*a[2]+wb*b[2]+wc*c[2]>z+1e-5)


if __name__ == '__main__':
    unittest.main()
