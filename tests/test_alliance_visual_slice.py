"""Pure geometric silhouette contracts; real GL appearance acceptance is separate."""
import unittest
from render.faction_ships import ship_mesh
from render.faction_stations import station_mesh


def covered(mesh, point, axes=(0, 2), roles=('base',)):
    """Exact orthographic triangle coverage, independent of paint/detail count."""
    x,y = point
    i,j = axes
    for role in roles:
        for _, tri in mesh[role]:
            a,b,c = [(v[i],v[j]) for v in tri]
            d=(b[1]-c[1])*(a[0]-c[0])+(c[0]-b[0])*(a[1]-c[1])
            if abs(d)<1e-10:
                continue
            u=((b[1]-c[1])*(x-c[0])+(c[0]-b[0])*(y-c[1]))/d
            v=((c[1]-a[1])*(x-c[0])+(a[0]-c[0])*(y-c[1]))/d
            if min(u,v,1-u-v)>=-1e-8:
                return True
    return False


class AllianceVisualSliceTests(unittest.TestCase):
    def test_capital_pressure_shoulders_open_drives_and_ventral_keel_survive_base_lod(self):
        mesh=ship_mesh('rebel','battleship')
        for point in ((0,100),(22,82),(55,-75)):
            self.assertTrue(covered(mesh,point),('missing pressure hull',point))
        for point in ((20,10),(50,60),(-50,60)):
            self.assertFalse(covered(mesh,point),('filled waist/drive gap',point))
        self.assertTrue(covered(mesh,(-30,-23),axes=(2,1)), 'missing stepped belly keel')

    def test_escort_compact_prow_open_waist_and_staggered_aft_pods(self):
        mesh=ship_mesh('rebel','frigate')
        for point in ((14,48),(0,8),(28,-40),(-28,-40)):
            self.assertTrue(covered(mesh,point),('missing escort mass',point))
        for point in ((9,5),(23,18),(-23,18)):
            self.assertFalse(covered(mesh,point),('filled escort waist',point))
        self.assertTrue(covered(mesh,(-28,-66)))
        self.assertFalse(covered(mesh,(28,-66)), 'aft pods must have staggered lengths')

    def test_yard_has_open_top_lane_solid_rails_and_offset_control_loft(self):
        mesh=station_mesh('rebel','shipyard')
        for point in ((0,-24),(0,0),(0,24),(-16,0),(16,0)):
            self.assertFalse(covered(mesh,point),('cradle lane roofed over',point))
        for point in ((-40,0),(40,0),(-40,32),(40,-32)):
            self.assertTrue(covered(mesh,point),('missing service rail',point))
        high=[v for _,tri in mesh['base'] for v in tri if v[1]>30]
        self.assertTrue(high)
        self.assertGreater(min(v[0] for v in high),20, 'control loft must be offset beyond lane')
