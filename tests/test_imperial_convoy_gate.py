"""The Imperial convoy gate: the only seam that reaches ``imperial:convoy``.

An Imperial convoy hull cannot be reached today, and that is measured here rather than assumed:
with no resolver, ``ship_visual_key(ds, 'trade_convoy', 'imperial')`` and
``ship_visual_key(ds, 'imperial_crew_transport')`` both answer ``box`` today, while the same two
calls for rebel, confederacy and syndicate answer ``<faction>:convoy``. Both convoy branches of
``render/faction_visuals.py::ship_visual_key`` did that by gating on ``FACTIONS[1:]`` - the three
already-authored factions - so an Imperial row fell past them into the legacy shape:

    data_id == 'trade_convoy' and faction in FACTIONS[1:]
    data.category == 'crew_transport' and data.crew_capacity > 0 and data.faction in FACTIONS[1:]

``render/asset_selection.py::ship_binding`` builds the key for the same two shapes of row. It was
already faction-agnostic there - the same probe records it constructing ``imperial:convoy`` today -
which is why the seam is written as one declared gate (``faction_visuals.convoy_key``) that both
paths read, instead of each path deciding for itself which rows are convoys.

The owner settled that the Imperial convoy follows the other three (decision
``s06-imperial-convoy-parity-2026-10-18`` in ``art/manifests/pipeline_policy.json``), so the
convoy branches have to admit Imperial. The general faction gate in ``ship_visual_key`` must NOT
move with them: ``SHIP_KEYS`` is built from ``FACTIONS[1:]``, so ``imperial:cruiser`` is not in it.
Widening the general gate makes every Imperial combat hull return a key that ``normalize_ship_key``
turns into ``box`` - every Imperial corvette, cruiser, battleship and squadron in the game starts
drawing the crate it does not draw today. Test (4) below is the regression guard for exactly that,
and it fails if the general gate is widened.

Driving the functions without a game
------------------------------------
``ship_binding`` returns early and ``None`` when no resolver is configured, and a resolver serves a
binding only while a hull is *authored* for it - the registry row for ``imperial:convoy`` is
``procedural_legacy`` until the separate landing decision this seam does not make. So the key
construction (which is what the seam changes) is exercised the way the task allows: a real preview
session exactly as ``tests/test_generic_model_preview.py`` configures one, with
``render.asset_selection.selected_binding`` stubbed to accept the key. The stub is never in scope
while geometry is asked for: "selected but not authored" is a state the resolver cannot produce,
and asking such a key for its mesh hands an un-normalized ``imperial:convoy`` to the faction mesh
table, which has no Imperial entry and raises.

Run:  env -u SDL_VIDEODRIVER PYTHONPATH=tests .venv/bin/python -m unittest test_imperial_convoy_gate
"""

import json
import unittest
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import game.core
from game.data.store import DataStore
from render import asset_selection as selection
from render import faction_visuals as visuals
from render.fleet_geometry import ship_mesh

ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / 'art/manifests/pipeline_policy.json'
DECISION = 's06-imperial-convoy-parity-2026-10-18'
SIBLINGS = ('rebel', 'confederacy', 'syndicate')

# The nine Imperial ship rows, and the key each one has today. Measured on this tree with
# ``DataStore.get()`` and no resolver, before the convoy seam was written; the seam must not move
# any of them, in particular not to ``imperial:<role>``.
SHIP_ROWS = ('imperial_corvette', 'imperial_frigate', 'imperial_cruiser', 'imperial_battleship',
             'imperial_supercapital', 'imperial_constructor', 'imperial_colonizer',
             'imperial_tie_squadron', 'imperial_tie_bomber_squadron')
STOCK_KEYS = {'imperial_corvette': 'needle',
              'imperial_frigate': 'needle',
              'imperial_cruiser': 'cruiser',
              'imperial_battleship': 'dagger',
              'imperial_supercapital': 'dagger',
              'imperial_constructor': 'box',
              'imperial_colonizer': 'box',
              'imperial_tie_squadron': 'wedge',
              'imperial_tie_bomber_squadron': 'wedge'}

# Non-convoy rows of the three approved factions: they pin that only the convoy branches moved.
SIBLING_ROWS = {'rebel_corvette': 'rebel:corvette',
                'rebel_x_squadron': 'rebel:fighter',
                'confed_cruiser': 'confederacy:cruiser',
                'syndicate_frigate': 'syndicate:frigate',
                'syndicate_raid_squadron': 'syndicate:fighter'}


def store():
    return DataStore.get()


def no_capacity(data_id):
    """The same catalogue row with the crew space taken out: not a convoy, by the gate's own test."""
    ds = store()
    return SimpleNamespace(ships={data_id: replace(ds.ships[data_id], crew_capacity=0)},
                           ship_visual=ds.ship_visual)


def stubbed():
    """A preview session whose resolver accepts any key the branches construct."""
    return patch.object(selection, 'selected_binding', return_value=True)


class ImperialConvoyKeyConstruction(unittest.TestCase):
    """(1) and (2): an Imperial convoy row reaches ``imperial:convoy`` in both functions.

    ``ship_binding``'s own branch is observed twice: with a recorder that captures the key it
    constructs and then answers "not authored" - so the branch is exercised without anything being
    served - and with the accept-all stub, which is the only way to see the key come back out of a
    function that hands it to the resolver. ``ship_visual_key``'s branch is observed where it has
    to answer for itself: no resolver at all, and a preview session in which nothing is authored.
    """

    def setUp(self):
        selection.configure({'model_preview': True}, asset_root=ROOT)

    def tearDown(self):
        selection.configure({})

    def recorded(self, call):
        """Run ``call`` with the resolver's authorship probe replaced by a recorder."""
        asked = []
        with patch.object(selection, 'selected_binding',
                          side_effect=lambda binding: asked.append(binding) or False):
            result = call()
        return result, asked

    def test_an_imperial_trade_convoy_row_reaches_the_imperial_convoy_key(self):
        ds = store()
        result, asked = self.recorded(
            lambda: selection.ship_binding(ds, 'trade_convoy', 'imperial'))
        self.assertEqual(asked, ['imperial:convoy'])
        self.assertIsNone(result, 'an unauthored binding must not be served')
        self.assertEqual(visuals.ship_visual_key(ds, 'trade_convoy', 'imperial'),
                         'imperial:convoy')
        with stubbed():
            self.assertEqual(selection.ship_binding(ds, 'trade_convoy', 'imperial'),
                             'imperial:convoy')
            self.assertEqual(visuals.ship_visual_key(ds, 'trade_convoy', 'imperial'),
                             'imperial:convoy')
        selection.configure({})
        self.assertEqual(visuals.ship_visual_key(ds, 'trade_convoy', 'imperial'),
                         'imperial:convoy')

    def test_an_imperial_crew_transport_with_crew_space_reaches_the_same_key(self):
        ds = store()
        data = ds.ships['imperial_crew_transport']
        self.assertEqual(data.category, 'crew_transport')
        self.assertGreater(data.crew_capacity, 0)
        result, asked = self.recorded(
            lambda: selection.ship_binding(ds, 'imperial_crew_transport'))
        self.assertEqual(asked, ['imperial:convoy'])
        self.assertIsNone(result, 'an unauthored binding must not be served')
        self.assertEqual(visuals.ship_visual_key(ds, 'imperial_crew_transport'),
                         'imperial:convoy')
        with stubbed():
            self.assertEqual(selection.ship_binding(ds, 'imperial_crew_transport'),
                             'imperial:convoy')
            self.assertEqual(visuals.ship_visual_key(ds, 'imperial_crew_transport'),
                             'imperial:convoy')
        selection.configure({})
        self.assertEqual(visuals.ship_visual_key(ds, 'imperial_crew_transport'),
                         'imperial:convoy')

    def test_a_crew_transport_without_crew_space_is_not_a_convoy(self):
        """The gate's own test - crew space - still has to hold for Imperial."""
        empty = no_capacity('imperial_crew_transport')
        with stubbed():
            # The branch keeps the row on its own role, which is not the convoy hull.
            self.assertNotEqual(selection.ship_binding(empty, 'imperial_crew_transport'),
                                'imperial:convoy')
            self.assertEqual(selection.ship_binding(empty, 'imperial_crew_transport'),
                             'imperial:crew_transport')
            self.assertNotEqual(visuals.ship_visual_key(empty, 'imperial_crew_transport'),
                                'imperial:convoy')

    def test_nothing_authored_is_served_by_the_real_registry(self):
        """The seam extends a gate; it does not author or activate a hull for Imperial."""
        ds = store()
        for data_id, faction in (('trade_convoy', f) for f in ('imperial',) + SIBLINGS):
            with self.subTest(data_id=data_id, faction=faction):
                binding = f'{faction}:convoy'
                self.assertFalse(selection.selected_binding(binding))
                self.assertIsNone(selection.mesh_for(binding))
                self.assertIsNone(selection.ship_binding(ds, data_id, faction))
        self.assertIsNone(selection.ship_binding(ds, 'imperial_crew_transport'))


class ApprovedFactionsUnchanged(unittest.TestCase):
    """(3): the three already-authored factions keep exactly the keys they have today."""

    def tearDown(self):
        selection.configure({})

    def test_the_three_approved_convoys_are_byte_for_byte_unchanged(self):
        ds = store()
        selection.configure({})
        legacy = {}
        for faction in SIBLINGS:
            legacy[faction] = visuals.ship_visual_key(ds, 'trade_convoy', faction)
        self.assertEqual(legacy, {f: f + ':convoy' for f in SIBLINGS})
        selection.configure({'model_preview': True}, asset_root=ROOT)
        with stubbed():
            self.assertEqual({f: selection.ship_binding(ds, 'trade_convoy', f) for f in SIBLINGS},
                             {f: f + ':convoy' for f in SIBLINGS})
            self.assertEqual({f: visuals.ship_visual_key(ds, 'trade_convoy', f) for f in SIBLINGS},
                             {f: f + ':convoy' for f in SIBLINGS})

    def test_a_rebel_crew_transport_and_the_non_convoy_rows_are_unchanged(self):
        ds = store()
        selection.configure({})
        for data_id, expected in SIBLING_ROWS.items():
            with self.subTest(data_id=data_id):
                self.assertEqual(visuals.ship_visual_key(ds, data_id), expected)
        self.assertEqual(visuals.ship_visual_key(ds, 'rebel_crew_transport'), 'rebel:convoy')
        self.assertEqual(visuals.ship_visual_key(ds, 'confed_crew_transport'), 'confederacy:convoy')
        self.assertEqual(visuals.ship_visual_key(ds, 'syndicate_crew_transport'),
                         'syndicate:convoy')
        self.assertEqual(visuals.ship_visual_key(no_capacity('rebel_crew_transport'),
                                                 'rebel_crew_transport'), 'box')
        # Nothing of the three factions lost its faction prefix to the seam.
        for data_id, data in ds.ships.items():
            if data.faction == 'imperial':
                continue
            with self.subTest(data_id=data_id):
                self.assertTrue(visuals.ship_visual_key(ds, data_id)
                                .startswith(data.faction + ':'))


class ImperialShipRowsUnchanged(unittest.TestCase):
    """(4): the regression guard for the trap - no Imperial ship row may move."""

    def tearDown(self):
        selection.configure({})

    def test_every_imperial_ship_row_keeps_its_stock_key(self):
        ds = store()
        selection.configure({})
        self.assertEqual(sorted(STOCK_KEYS), sorted(SHIP_ROWS))
        for data_id in SHIP_ROWS:
            expected = STOCK_KEYS[data_id]
            data = ds.ships[data_id]
            with self.subTest(data_id=data_id):
                self.assertEqual(data.faction, 'imperial')
                self.assertIn(expected, visuals.LEGACY_SHAPES,
                              'a stock Imperial key is a legacy shape, never a faction key')
                self.assertEqual(visuals.ship_visual_key(ds, data_id), expected,
                                 'an Imperial row moved: the general faction gate was widened')
                self.assertEqual(visuals.ship_visual_key(ds, data_id),
                                 ds.ship_visual(data_id)['shape'])

    def test_the_general_faction_gate_still_excludes_imperial(self):
        self.assertNotIn('imperial', visuals.FACTIONS[1:])
        for role in visuals.SHIP_ROLES:
            with self.subTest(role=role):
                self.assertNotIn('imperial:' + role, visuals.SHIP_KEYS)
        # The three factions the gate does admit are still built from it.
        for role in ('corvette', 'convoy', 'colonizer'):
            with self.subTest(role=role):
                for faction in SIBLINGS:
                    self.assertIn(faction + ':' + role, visuals.SHIP_KEYS)

    def test_the_convoy_key_is_deliberately_not_a_ship_key(self):
        """The other obvious fix - putting ``imperial:convoy`` into ``SHIP_KEYS`` - is not one.

        ``normalize_ship_key`` passes a key straight through when it is in ``SHIP_KEYS``, and
        ``ship_mesh`` then hands ``faction:role`` to the faction mesh table, whose factions are the
        three siblings: an Imperial entry there raises. So the key stays out of ``SHIP_KEYS`` and
        the legacy fallback is the same box the Imperial convoy draws today.
        """
        self.assertNotIn('imperial:convoy', visuals.SHIP_KEYS)
        self.assertEqual(visuals.normalize_ship_key('imperial:convoy'), 'box')
        self.assertEqual(ship_mesh('imperial:convoy'), ship_mesh('box'))
        with patch.object(visuals, 'SHIP_KEYS', visuals.SHIP_KEYS + ('imperial:convoy',)):
            self.assertEqual(visuals.normalize_ship_key('imperial:convoy'), 'imperial:convoy')
            with self.assertRaises(ValueError):
                ship_mesh('imperial:convoy')


class NothingSelectedServesNothing(unittest.TestCase):
    """(5): with no preview and no resolver, nothing authored is served."""

    def tearDown(self):
        selection.configure({})

    def test_stock_keys_and_no_binding_when_no_resolver_is_configured(self):
        ds = store()
        selection.configure({})
        self.assertEqual(selection.diagnostics()['mode'], 'legacy')
        self.assertIsNone(selection.ship_binding(ds, 'trade_convoy', 'imperial'))
        self.assertIsNone(selection.ship_binding(ds, 'imperial_crew_transport'))
        self.assertIsNone(selection.mesh_for('imperial:convoy'))
        self.assertFalse(selection.selected_binding('imperial:convoy'))
        for data_id, expected in STOCK_KEYS.items():
            with self.subTest(data_id=data_id):
                self.assertEqual(visuals.ship_visual_key(ds, data_id), expected)
        empty = no_capacity('imperial_crew_transport')
        self.assertEqual(visuals.ship_visual_key(empty, 'imperial_crew_transport'), 'box')

    def test_the_imperial_convoy_row_draws_todays_stock_geometry(self):
        """The seam changes which key the row resolves to, not the geometry available for it."""
        ds = store()
        selection.configure({})
        self.assertEqual(visuals.ship_visual_key(ds, 'trade_convoy', 'imperial'),
                         'imperial:convoy')
        self.assertEqual(ship_mesh(visuals.ship_visual_key(ds, 'trade_convoy', 'imperial')),
                         ship_mesh(ds.ship_visual('trade_convoy')['shape']))


class TheGateIsDeclaredInWriting(unittest.TestCase):
    """(6): the seam is not a blanket change, and the record must keep saying so."""

    def decision(self):
        log = json.loads(POLICY.read_text(encoding='utf-8'))['decision_log']
        matches = [entry for entry in log if entry.get('id') == DECISION]
        self.assertEqual(len(matches), 1, f'{DECISION} is not in the policy decision log')
        return matches[0]

    def test_the_decision_exists_and_points_at_the_convoy_gate(self):
        entry = self.decision()
        self.assertIn('convoy', entry['applies_to'])
        self.assertTrue(any('imperial:convoy' in text for text in entry['what_this_authorizes']),
                        'the decision does not authorize the imperial:convoy hull')
        siblings = entry['what_the_siblings_settled_on']
        self.assertEqual(len(siblings['rows']), 3)
        for row in siblings['rows']:
            with self.subTest(row=row):
                self.assertTrue(row.split(':')[0] in SIBLINGS)

    def test_the_decision_still_refuses_a_blanket_change_to_the_gate(self):
        entry = self.decision()
        refusing = [text for text in entry['what_it_does_not_authorize']
                    if 'blanket' in text.lower() and 'convoy gate' in text.lower()]
        self.assertTrue(refusing, 'the decision no longer refuses a blanket change to the gate')
        self.assertTrue(any('seam change' in text.lower() for text in refusing),
                        'the refusal must call the extension a written, guarded seam change')


if __name__ == '__main__':
    unittest.main()
