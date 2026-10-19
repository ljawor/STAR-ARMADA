"""Independent ZIP readback; never modifies the shipped menu movie.

Binds to an explicitly named independent review, not to "the renderer": the review
records the renderer bytes it examined, and this verifier refuses a candidate baked
by different bytes. That is what makes it a check rather than a formality.
"""
import argparse
import hashlib
import io
import json
from pathlib import Path
import subprocess
import zipfile
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / 'artifacts/s07-runtime-final'
sha = lambda value: hashlib.sha256(value).hexdigest()


def review_facts(review):
    """Accept the current review schema and the earlier scoped-review schema."""
    if 'overall' in review:
        return (review['overall'], review.get('renderer_sha256'),
                [f for f in review.get('findings', []) if f.get('severity') == 'blocking'])
    # Legacy scoped review: a pass flag plus review_scope.renderer_sha256.
    return ('pass' if review.get('passed') else 'fail',
            review.get('review_scope', {}).get('renderer_sha256'),
            list(review.get('security_concerns', [])) + list(review.get('logic_errors', [])))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--folder', type=Path, default=BASE / 'candidate-movie-final')
    parser.add_argument('--review', type=Path, default=BASE / 'INDEPENDENT-MOTION-REVIEW.json')
    parser.add_argument('--receipt', type=Path, default=BASE / 'candidate-movie-final-readback.json')
    a = parser.parse_args()
    folder, review_path = a.folder, a.review

    review = json.loads(review_path.read_bytes())
    overall, reviewed_renderer, blocking = review_facts(review)
    assert overall in ('pass', 'pass_with_findings'), overall
    assert not blocking, blocking
    renderer_sha = sha((ROOT / 'render/renderer.py').read_bytes())
    assert reviewed_renderer == renderer_sha, (
        'the named review examined different renderer bytes than the tree carries',
        reviewed_renderer, renderer_sha)

    report = json.loads((folder / 'render-report.json').read_bytes())
    assert report['provenance']['code_sha256']['render/renderer.py'] == renderer_sha, (
        'the candidate was baked by different renderer bytes than the review examined')
    asset = folder / 'review/candidate.zip'
    with zipfile.ZipFile(asset) as archive:
        assert archive.testzip() is None
        metadata = json.loads(archive.read('metadata.json'))
        assert metadata['provenance'] == report['provenance']
        assert metadata['provenance']['selection_policy'] == 'preview'
        names = [f'frames/{i:05d}.jpg' for i in range(metadata['frame_count'])]
        assert metadata['frame_count'] == 360
        assert set(archive.namelist()) == {'metadata.json', *names}
        frame_hashes = []
        for name in names:
            data = archive.read(name)
            with Image.open(io.BytesIO(data)) as image:
                image.load()
                assert image.size == (metadata['width'], metadata['height'])
                assert max(image.convert('L').getextrema()) > 40
            frame_hashes.append(sha(data))
        assert len(set(frame_hashes)) > 1
    provenance = metadata['provenance']
    for path, expected in provenance['code_sha256'].items():
        assert sha((ROOT / path).read_bytes()) == expected, path
    for row in provenance['models']:
        assert row['legacy_fallback'] is None and row['revision']
        assert sha((ROOT / row['runtime_path']).read_bytes()) == row['runtime_sha256']
    assert report['full_render_gl_errors'] == 0
    assert report['playback']['frames_verified'] == 360
    shipped = 'assets/menu/battle.zip'
    assert (ROOT / shipped).read_bytes() == subprocess.check_output(
        ['git', 'show', f'HEAD:{shipped}'], cwd=ROOT)
    receipt = dict(status='passed', candidate_zip_sha256=sha(asset.read_bytes()),
                   frames_decoded=len(frame_hashes), frame_sha256=frame_hashes,
                   code_pins_verified=len(provenance['code_sha256']),
                   model_instances_verified=len(provenance['models']),
                   shipped_movie_unchanged=True, review_renderer_pin_matches=True,
                   review_path=str(review_path.relative_to(ROOT)),
                   candidate_folder=str(folder.relative_to(ROOT)),
                   renderer_sha256=renderer_sha,
                   limitations=['Offline presentation fixture, not gameplay simulation or packaged-build acceptance.',
                                'Independent review excludes geometry-matrix ownership outside its stated scope.'])
    a.receipt.write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps({k: v for k, v in receipt.items() if k != 'frame_sha256'}, indent=2))


if __name__ == '__main__':
    main()
