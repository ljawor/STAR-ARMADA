"""CPU role-submission parity, not native GL or pixel parity.

Execute the actual production AST bodies with GL replaced before execution.
Only resolution and GL endpoints are seams; no native OpenGL is imported.
"""
import ast
import json
import unittest

from test_s07_lod_environment import (
    EPS, PIXELS, ROOT, ROLES, SHIP_BINDINGS, expected_roles,
    observed_roles, production_namespace,
)


class AuthoredLodParityTests(unittest.TestCase):
    def test_negative_control_restored_authored_role_suppression_is_detected(self):
        def restore_old_suppression(nodes):
            batch = next(n for n in nodes if isinstance(n, ast.FunctionDef)
                         and n.name == '_draw_ship_role_batch')
            changed = 0
            for node in ast.walk(batch):
                if isinstance(node, ast.If) and isinstance(node.test, ast.BoolOp):
                    values = node.test.values
                    if ast.unparse(values[0]) == 'not authored':
                        node.test.values = values[1:]
                        changed += 1
            self.assertEqual(changed, 2)
            return nodes
        ns = production_namespace(restore_old_suppression)
        for px in (16. - EPS, 34. - EPS):
            with self.subTest(apparent=px):
                observed = observed_roles(ns, SHIP_BINDINGS[0], px)
                self.assertEqual(observed, expected_roles(px))
                self.assertNotEqual(observed, ROLES)
        print('NEGATIVE_CONTROL_CAUGHT restored_authored_role_suppression')

    def test_authored_cached_keeps_every_uncached_role_at_all_sizes(self):
        rows = json.loads((ROOT / 'assets/models/registry.json').read_text(encoding='utf-8'))['bindings']
        bindings = sorted(row['binding'] for row in rows
                          if row['status'] == 'core' and row['category'] in
                          ('combat_hull', 'squadron', 'construction', 'logistics_hull'))
        self.assertTrue(set(SHIP_BINDINGS).issubset(bindings))
        ns = production_namespace()
        cases = []
        for binding in bindings:
            for px in (0., 1.) + PIXELS + (60., 1000.):
                with self.subTest(binding=binding, apparent=px):
                    uncached = observed_roles(ns, binding, px, uncached=True)
                    cached = observed_roles(ns, binding, px)
                    self.assertEqual(uncached, ROLES)
                    self.assertEqual(cached, uncached)
                    cases.append({'binding': binding, 'apparent': px, 'roles': cached})
        print('CPU_AUTHORED_ROLE_SUBMISSION_ONLY ' + json.dumps({
            'bindings': len(bindings), 'cases': len(cases), 'rows': cases}))

    def test_legacy_namespaced_and_procedural_thresholds_remain_unchanged(self):
        ns = production_namespace()
        ns['is_authored'] = lambda binding: False
        for binding in ('rebel:battleship', 'unregistered:custom', 'needle'):
            for px in (0., 1.) + PIXELS + (60.,):
                with self.subTest(binding=binding, apparent=px):
                    # The fixture needs a faction prefix; size.shape does not.
                    from test_s07_lod_environment import renderer_fixture, entity, fake_imports
                    renderer, size, calls = renderer_fixture(ns, binding)
                    e = entity('rebel:battleship')
                    cache = {'relation': {0: 'own'}, 'owner_color': {0: (.3, .6, .9)},
                             e.id: {'apparent': px, 'size': size}}
                    with fake_imports():
                        for index, role in enumerate(ROLES):
                            ns['_draw_ship_role_batch'](
                                renderer, role, [e], [], cache,
                                material_pass=float(index) if index < 3 else None)
                    roles = tuple('base' if call == binding else
                                  call.removeprefix(binding + '_') for call in calls)
                    self.assertEqual(roles, expected_roles(px))


if __name__ == '__main__':
    unittest.main()
