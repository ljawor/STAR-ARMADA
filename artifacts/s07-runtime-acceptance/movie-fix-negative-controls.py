"""CPU-only test discrimination: mutate function objects, never source files."""
import inspect
import io
import json
import unittest
from pathlib import Path
from tools import build_menu_movie as baker
import test_s07_movie_provenance as tests

source = inspect.getsource(baker.build_movie)
original = baker.build_movie
controls = [
    ('predictable-alias-staging',
     "with tempfile.NamedTemporaryFile(prefix='.'+args.asset.name+'-', suffix='.tmp',\n                                         dir=args.asset.parent, delete=False) as staging:",
     "with open(args.asset.with_suffix('.tmp'), 'w+b') as staging:",
     ['test_predictable_symlink_canary_is_untouched', 'test_predictable_hardlink_canary_is_untouched']),
    ('decode-wrong-directory',
     'MenuMovie(temporary.parent, temporary.name)',
     "MenuMovie(args.asset.parent.parent, 'menu/'+args.asset.name)",
     ['test_success_verifies_exact_staged_zip_before_atomic_publication']),
    ('publish-before-decode',
     'timings = []',
     'temporary.replace(args.asset)\n                timings = []',
     ['test_decode_failure_preserves_previous_bytes_and_cleans_staging']),
    ('skip-last-decode',
     'for i in range(360):\n                        before',
     'for i in range(359):\n                        before',
     ['test_decode_failure_preserves_previous_bytes_and_cleans_staging']),
    ('leak-staging',
     'temporary.unlink(missing_ok=True)',
     'pass  # deliberate staging leak',
     ['test_decode_failure_preserves_previous_bytes_and_cleans_staging']),
]
results = []
for name, old, new, names in controls:
    assert source.count(old) == 1, (name, source.count(old))
    namespace = vars(baker)
    exec(compile(source.replace(old, new), baker.__file__, 'exec'), namespace)
    baker.build_movie = namespace['build_movie']
    stream = io.StringIO()
    try:
        suite = unittest.TestSuite(tests.MoviePublicationTests(test) for test in names)
        result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
        print(name, stream.getvalue(), sep='\n')
        assert len(result.failures) + len(result.errors) == len(names), name
        results.append(dict(control=name, tests=result.testsRun,
                            failures=len(result.failures), errors=len(result.errors)))
    finally:
        baker.build_movie = original
print(json.dumps(results, indent=2))
