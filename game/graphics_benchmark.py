"""Versioned, factory-built four-player graphics workloads (no rule overrides).

Fixtures are starting-state construction, not saved games or new gameplay rules.
The immutable descriptor is separate from the live manager. Public entry points
are make_fixture(), semantic_inventory(), and Fixture.camera/metadata().
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from collections import Counter

from game.core import detmath as math
from game.core.manager import GameManager
from game.core.state import PlayerState
from game.core.vectors import Vec3
from game.systems.economy import EconomySystem
from game.systems.satellite_orbits import orbit_position


FIXTURES = ('four-player-distributed-v1', 'four-player-combat-v1', 'four-player-close-v1')
# No artificial immortal hulls, weapon changes, AI income multipliers or tech.
COMBAT_MIX = (('imperial_corvette', 60), ('imperial_frigate', 40),
              ('imperial_cruiser', 30), ('imperial_battleship', 16),
              ('imperial_supercapital', 4))
ORDINARY_STATIONS = ('command_station', 'mining_station', 'shipyard',
                     'research_station', 'defense_platform', 'sensor_station',
                     'fighter_platform', 'repair_dock', 'energy_relay', 'mining_station')
CATEGORIES = ('combat_ships', 'ordinary_stations', 'trade_stations',
              'transports', 'planets', 'satellites')


@dataclass(frozen=True)
class CameraSpec:
    target: tuple[float, float, float]
    distance: float
    yaw: float = 0.0
    pitch: float = 65.0
    fov: float = 55.0

    def apply(self, camera):
        camera.target = list(self.target)
        for key in ('distance', 'yaw', 'pitch', 'fov'):
            setattr(camera, key, getattr(self, key))


@dataclass(frozen=True)
class Fixture:
    manager: GameManager
    name: str
    camera: CameraSpec
    selection: tuple[int, ...]
    command_budget_initial: tuple[tuple[int, int, int], ...]
    max_ticks: int = 300

    def metadata(self) -> dict:
        # A fresh JSON-compatible copy: report mutation cannot change the recipe.
        return dict(name=self.name, players=4, factions=['imperial'] * 4,
                    teams=[0, 1, 2, 3], ai=False, local_player=0,
                    combat_mix_per_player=dict(COMBAT_MIX),
                    ordinary_station_mix_per_player=dict(Counter(ORDINARY_STATIONS)),
                    planet_mix_per_player={'temperate': 1, 'industrial': 1},
                    satellite_mix_per_planet={'defense_satellite': 2, 'attack_satellite': 2},
                    camera=asdict(self.camera), selection=list(self.selection),
                    command_budget_initial={str(owner): dict(used=used, capacity=capacity)
                                            for owner, used, capacity in self.command_budget_initial},
                    max_ticks=self.max_ticks,
                    assumptions=[
                        'Four human slots, same Imperial faction, distinct colours, hostile teams; no strategic AI.',
                        'Direct valid starting-state setup; unresearched stock catalogue hulls; no build queues.',
                        'Requested pre-existing fleet exceeds current stock construction command capacity (906 used / 78 available per player); no capacity rules changed. This is a scale workload, not a proof this exact economy can build the fleet.',
                        'Four extra trade stations per player; four pre-existing convoys per source, nearest own market.',
                        'Convoys start at staggered route progress; deliveries remove hulls normally, never respawned by fixture.',
                        'At most 300 fixed 30 Hz ticks (10 simulated seconds), below the stock 45s convoy spawn interval.',
                        'Player 0 live fog/sensors, not an omniscient all-map graphics load; visibility reported per sample.',
                        'Close inspection uses the distributed world with a fixed flagship camera; not all assets are on screen.',
                        'Versioned class mix is a benchmark assumption, not an approved gameplay distribution.',
                        'Combat is an established interleaved four-way melee, held stock hulls with automatic targeting; no forced damage or godmode.',
                    ])


def _rotate(x: float, z: float, owner: int) -> tuple[float, float]:
    # Exact quarter turns avoid trigonometric placement noise.
    return ((x, z), (z, -x), (-x, -z), (-z, x))[owner]


def _home(x, z, owner):
    x, z = _rotate(x, z + 18000, owner)
    return Vec3(x, 0, z)


def semantic_inventory(state, *, entities=None):
    """Alive semantic roles (satellites are stations in the underlying engine)."""
    players = {str(p): dict.fromkeys(CATEGORIES, 0) for p in sorted(state.players)}
    classes = Counter()
    for e in state.entities.values() if entities is None else entities:
        if not e.alive:
            continue
        owner = e.colonized_by if e.is_planet else e.owner
        if str(owner) not in players:
            continue
        if e.is_planet:
            category = 'planets'
        elif e.satellite_slot is not None:
            category = 'satellites'
        elif e.data_id == 'trade_convoy':
            category = 'transports'
        elif e.is_station:
            category = 'trade_stations' if e.data_id == 'trade_station' else 'ordinary_stations'
        elif e.is_ship or e.is_squadron:
            category = 'combat_ships'
        else:
            continue
        players[str(owner)][category] += 1
        classes[e.data_id] += 1
    return dict(total={key: sum(p[key] for p in players.values()) for key in CATEGORIES},
                players=players, classes=dict(sorted(classes.items())))


def visibility_sample(state, camera=None):
    """Live local detection, then centre-in-viewport; not a draw-call census."""
    detected = [e for e in state.entities.values() if e.alive and state.can_see(0, e.id)]
    on_screen = None
    if camera is not None:
        on_screen = []
        for e in detected:
            point = camera.world_to_screen(*e.pos.to_tuple())
            if point is not None and 0 <= point[0] < camera.width and 0 <= point[1] < camera.height:
                on_screen.append(e)
    return dict(detected=semantic_inventory(state, entities=detected),
                centres_in_viewport=None if on_screen is None else semantic_inventory(state, entities=on_screen),
                note='Player 0 live detection; projected centres only, not occlusion or exact renderer draw counts')


class Activity:
    """Read-only event counters; callback work is included in simulation timing."""
    def __init__(self, state):
        self.state = state
        self.total, self.frame = Counter(), Counter()
        state.events.subscribe('weapon_fired', self._shot)
        state.events.subscribe('convoy_arrived', self._arrival)

    def _add(self, key):
        self.total[key] += 1
        self.frame[key] += 1

    def _shot(self, event):
        self._add('owner:' + str(event.data['owner']))
        attacker = self.state.entities[event.data['attacker_id']]
        self._add('class:' + attacker.data_id)
        if self.state.can_see(0, attacker.id):
            self._add('visible_shots')

    def _arrival(self, event):
        self._add('deliveries')

    @staticmethod
    def snapshot(counter):
        return dict(shots_by_owner={key[6:]: value for key, value in sorted(counter.items()) if key.startswith('owner:')},
                    shots_by_class={key[6:]: value for key, value in sorted(counter.items()) if key.startswith('class:')},
                    visible_shots=counter['visible_shots'], deliveries=counter['deliveries'])


def make_fixture(name):
    if name not in FIXTURES:
        raise ValueError(f'unknown graphics fixture: {name}')
    gm = GameManager()
    st = gm.state
    st.seed = 12345
    st.map_info.bounds = 36000.0
    st.map_info.nebulas = []
    colors = ((.35, .65, 1.), (1., .35, .25), (.3, 1., .5), (1., .8, .2))
    st.players = {p: PlayerState(p, team=p, color=colors[p],
                                credits=10000., materials=10000., energy=10000., crew=10000.)
                  for p in range(4)}
    flagships = []
    for owner in range(4):
        for index, kind in enumerate(ORDINARY_STATIONS):
            gm.factory.spawn_station(kind, owner, _home((index % 5 - 2) * 2000,
                                                       (index // 5) * 2000, owner))
        for x in (-3500, 3500):
            planet = gm.factory.spawn_planet(dict(id=f'p{owner}-{x}',
                type='temperate' if x < 0 else 'industrial',
                pos=_home(x, 6000, owner).to_tuple(), radius=600))
            planet.colonized_by = owner
            for slot in range(4):
                kind = 'defense_satellite' if slot % 2 == 0 else 'attack_satellite'
                phase = slot * 2 * math.pi / 6
                radius = gm.ds.stations[kind].radius
                pos = orbit_position(planet, radius, phase, slot, state=st)
                if pos is None:
                    raise ValueError('fixture satellite ring does not fit map')
                satellite = gm.factory.spawn_station(kind, owner, pos)
                satellite.planet_id = planet.id
                satellite.satellite_slot = slot
                satellite.satellite_orbit_phase = phase
        markets = [gm.factory.spawn_station('trade_station', owner, _home(x, z, owner))
                   for x, z in ((-6000, -2500), (-6000, -4500),
                                (6000, -2500), (6000, -4500))]
        for src in markets:
            dest = min((d for d in markets if d is not src),
                       key=lambda d: (src.pos.dist_sq(d.pos), d.id))
            for slot in range(4):
                convoy = gm.trading._make_convoy(src, dest,
                    float(gm.trading.cfg['cargo_credits']), float(gm.trading.cfg['hull']))
                fraction = (.08, .32, .56, .80)[slot]
                convoy.pos = src.pos + (dest.pos - src.pos) * fraction
                delta = dest.pos - src.pos
                convoy.yaw = math.atan2(delta.x, delta.z)
        # Class bands have physically separated centres at stock hull sizes.
        # Alternating owners make an already-engaged melee, not a march into
        # contact; all four owners remain visible through ordinary sensors.
        bands = ((24, 130, -3500), (20, 200, -1700), (20, 320, 500),
                 (16, 500, 2900), (8, 900, 5500))
        for (kind, number), (columns, spacing, start_z) in zip(COMBAT_MIX, bands):
            for index in range(number):
                slot = index * 4 + owner
                x = (slot % columns - (columns - 1) / 2) * spacing
                z = start_z + (slot // columns) * spacing
                if name == 'four-player-combat-v1':
                    pos = Vec3(x, 0, z)
                    yaw = math.pi / 2 if owner % 2 == 0 else -math.pi / 2
                else:
                    pos = _home(x, z - 10000, owner)
                    yaw = math.pi + owner * math.pi / 2
                ship = gm.factory.spawn_ship(kind, owner, pos, yaw=yaw)
                ship.order_type = 'hold'
                if kind == 'imperial_supercapital':
                    flagships.append(ship)

    st.grid.rebuild(st.entities)
    EconomySystem.recompute_command_capacity(st)
    gm.visibility.update()
    selected = flagships[0]
    camera = CameraSpec((0., 0., 16000.), 23000.)
    if name == 'four-player-combat-v1':
        camera = CameraSpec((0., 0., 1400.), 14000., pitch=70.)
    elif name == 'four-player-close-v1':
        camera = CameraSpec(selected.pos.to_tuple(), 1800., yaw=35., pitch=30.)
    budget = tuple((owner, player.command_used(st.entities), player.command_capacity)
                   for owner, player in sorted(st.players.items()))
    return Fixture(gm, name, camera, (selected.id,), budget)
