"""Presentation-only movie contract; real ZIPs and pygame decoders."""
import io
import json
import zipfile

import pygame
import pytest


def movie_file(root, metadata=None, bad_frame=False):
    path = root / 'menu' / 'battle.zip'
    path.parent.mkdir(parents=True, exist_ok=True)
    meta = dict(version=1, width=8, height=6, fps=2, frame_count=4,
                still_frame=1, loop='baked-crossfade')
    if metadata:
        meta.update(metadata)
    with zipfile.ZipFile(path, 'w', compression=zipfile.ZIP_STORED) as z:
        z.writestr('metadata.json', json.dumps(meta))
        for i in range(4):
            s = pygame.Surface((8, 6))
            s.fill((40 + i * 50, 10, 20))
            out = io.BytesIO()
            pygame.image.save(s, out, 'frame.jpg')
            z.writestr(f'frames/{i:05d}.jpg', b'broken' if bad_frame and i == 2 else out.getvalue())
    return path


@pytest.mark.parametrize('bad', [
    {'version': 2}, {'fps': 0}, {'fps': float('nan')}, {'fps': True},
    {'width': 0}, {'height': 90000}, {'frame_count': 0},
    {'frame_count': 90000}, {'frame_count': 4.5}, {'still_frame': 4},
    {'loop': 'hard-cut'}, {'width': '8'},
])
def test_invalid_metadata_is_safe_fallback(tmp_path, bad):
    from render.menu_movie import MenuMovie
    movie_file(tmp_path, bad)
    with MenuMovie(tmp_path) as movie:
        assert not movie.available
        assert movie._zip is None


def test_corrupt_deflated_metadata_is_safe_and_closes_archive(tmp_path, monkeypatch):
    import zlib
    from render.menu_movie import MenuMovie
    path = movie_file(tmp_path)
    with zipfile.ZipFile(path) as archive:
        metadata = archive.read('metadata.json')
    with zipfile.ZipFile(path, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('metadata.json', metadata)
        info = archive.getinfo('metadata.json')
    payload = bytearray(path.read_bytes())
    header = info.header_offset
    start = header + 30 + int.from_bytes(payload[header+26:header+28], 'little') + int.from_bytes(
        payload[header+28:header+30], 'little')
    # BFINAL=1, BTYPE=3 is an invalid real DEFLATE block, not a mocked read.
    payload[start:start+info.compress_size] = b'\x07' + b'\x00' * (info.compress_size - 1)
    path.write_bytes(payload)
    with zipfile.ZipFile(path) as archive:
        with pytest.raises(zlib.error):
            archive.read('metadata.json')
    real_zipfile = zipfile.ZipFile
    opened = []
    def tracked_zipfile(*args, **kwargs):
        archive = real_zipfile(*args, **kwargs)
        opened.append(archive)
        return archive
    monkeypatch.setattr(zipfile, 'ZipFile', tracked_zipfile)
    movie = MenuMovie(tmp_path)
    assert not movie.available
    assert movie.error
    assert movie._zip is None
    assert len(opened) == 1 and opened[0].fp is None
    assert movie.get_frame(0, (8, 6)) is None


def test_missing_archive_is_safe(tmp_path):
    from render.menu_movie import MenuMovie
    with MenuMovie(tmp_path) as movie:
        assert not movie.available


def test_frame_timing_wrap_and_reduced_motion(tmp_path):
    from render.menu_movie import MenuMovie
    movie_file(tmp_path)
    with MenuMovie(tmp_path) as movie:
        def red(t, reduced=False):
            return movie.get_frame(t, (16, 12), reduced).get_at((0, 0)).r
        assert red(0) == red(.499)
        assert red(.5) != red(0)
        assert red(2) == red(0)
        assert red(-1) == red(0)
        assert red(float('nan')) == red(0)
        assert red(100, True) == red(.5)
        assert red(200, True) == red(.5)


def test_cache_bounded_and_size_change_replaces_scaled_surfaces(tmp_path):
    from render.menu_movie import MenuMovie
    movie_file(tmp_path)
    with MenuMovie(tmp_path) as movie:
        first = movie.get_frame(0, (16, 12))
        assert first is movie.get_frame(.1, (16, 12))
        for i in range(40):
            assert movie.get_frame(i * .5, (16, 12)).get_size() == (16, 12)
            assert movie.cache_info()['frames'] <= 2
            assert movie.cache_info()['bytes'] <= 2 * 16 * 12 * 4
        assert movie.get_frame(0, (32, 24)).get_size() == (32, 24)
        assert movie.cache_info()['frames'] == 1
        assert movie.get_frame(0, (0, 12)) is None
        assert movie.get_frame(0, (90000, 12)) is None


def test_corrupt_frame_disables_movie_and_releases_resources(tmp_path):
    from render.menu_movie import MenuMovie
    movie_file(tmp_path, bad_frame=True)
    movie = MenuMovie(tmp_path)
    archive = movie._zip
    assert movie.get_frame(0, (8, 6)) is not None
    assert movie.get_frame(1, (8, 6)) is None
    assert not movie.available
    assert archive.fp is None
    assert movie.cache_info()['frames'] == 0
    assert movie.get_frame(0, (8, 6)) is None
    movie.close()


def test_close_is_idempotent(tmp_path):
    from render.menu_movie import MenuMovie
    movie_file(tmp_path)
    movie = MenuMovie(tmp_path)
    archive = movie._zip
    movie.get_frame(0, (8, 6))
    movie.close()
    movie.close()
    assert archive.fp is None
    assert movie.cache_info()['frames'] == 0
    assert movie.get_frame(0, (8, 6)) is None


def test_presentation_plan_uses_approved_models_without_a_game_manager():
    from pathlib import Path
    from tools.cinematics.scene_spec import build_plan, ship_pose
    plan = build_plan(Path(__file__).resolve().parents[1])
    assert len(plan['ships']) == 7
    assert {'imperial_frigate', 'rebel_frigate', 'imperial_battleship',
            'imperial_supercapital'} <= {s['data_id'] for s in plan['ships']}
    assert {s['faction'] for s in plan['ships']} == {'imperial', 'rebel'}
    assert all(s['runtime_sha256'] and s['revision'] for s in plan['ships'])
    assert ship_pose(plan['ships'][0], .2) != ship_pose(plan['ships'][0], 3.7)
    assert 'no gameplay' in plan['scope']


def test_cinematic_camera_is_slow_and_periodic():
    from tools.cinematics.scene_spec import camera_pose
    a, b, c = camera_pose(0), camera_pose(16), camera_pose(1 / 24)
    assert a['location'] == pytest.approx(b['location'])
    assert a['target'] == b['target'] == c['target']
    assert all(abs(x - y) < 1 for x, y in zip(a['location'], c['location']))


def test_baked_crossfade_matches_head_continuation(tmp_path):
    pytest.importorskip('PIL', reason='offline cinematic authoring extra is not installed')
    from tools.cinematics.movie_pack import assemble_movie
    source = tmp_path / 'source'; source.mkdir()
    for i in range(8):
        surface = pygame.Surface((3, 2)); surface.fill((i * 30, 0, 0))
        pygame.image.save(surface, str(source / f'frame_{i:05d}.jpg'))
    movie = tmp_path / 'movie.zip'
    assemble_movie(source, movie, width=3, height=2, fps=2,
                   source_seconds=4, overlap_seconds=1)
    with zipfile.ZipFile(movie) as archive:
        assert archive.read('frames/00000.jpg') == (source / 'frame_00002.jpg').read_bytes()
        end = pygame.image.load(io.BytesIO(archive.read('frames/00005.jpg')), 'frame.jpg')
        head = pygame.image.load(str(source / 'frame_00001.jpg'))
        assert abs(end.get_at((0, 0)).r - head.get_at((0, 0)).r) <= 2


@pytest.mark.skipif(__import__('os').environ.get('STAR_ARMADA_GL_TEST') != '1',
                    reason='requires pinned Blender5.0.1 and an idle GPU')
def test_offline_builder_real_gl_preview(tmp_path):
    import subprocess
    import shutil
    from pathlib import Path
    from tools.cinematics.scene_spec import build_plan
    root = Path(__file__).resolve().parents[1]
    blender = shutil.which('blender') or '/Applications/Blender.app/Contents/MacOS/Blender'
    plan_path = tmp_path / 'plan.json'
    plan_path.write_text(json.dumps(build_plan(root)), encoding='utf-8')
    output = tmp_path / 'render'
    completed = subprocess.run([blender, '--background', '--factory-startup',
        '--python-exit-code', '1', '--python', 'tools/cinematics/blender_scene.py',
        '--', '--plan', str(plan_path), '--out', str(output)],
        cwd=root, capture_output=True, text=True, timeout=120)
    assert completed.returncode == 0, completed.stdout + completed.stderr
    report = json.loads((output / 'render-report.json').read_text())
    assert report['samples'] == 64
    assert report['resolution'] == [2560, 1440]
    assert len(report['renders']) == 3
    assert report['engine'] == 'BLENDER_EEVEE'
    for sample in report['renders']:
        assert pygame.image.load(sample['png']).get_size() == (2560, 1440)


@pytest.mark.skipif(__import__('os').environ.get('STAR_ARMADA_MOVIE_BUILD_TEST') != '1',
                    reason='offline packaging gate requires completed 384-frame native PNG renders')
def test_full_movie_asset_preview_and_lazy_playback(tmp_path):
    # Full Blender rendering is a separate bounded process: do not secretly
    # rebake half an hour of GPU work inside a packaging/playback test.
    import os
    from pathlib import Path
    from tools.cinematics.prepare_frames import encode_frames
    from tools.cinematics.movie_pack import assemble_movie, encode_preview
    from render.menu_movie import MenuMovie
    source = os.environ.get('STAR_ARMADA_CINEMATIC_FRAMES')
    assert source, 'Set STAR_ARMADA_CINEMATIC_FRAMES to the completed native PNG directory'
    encoded = tmp_path / 'encoded'
    quality = encode_frames(Path(source), encoded)
    movie_path = tmp_path / 'battle.zip'
    assemble_movie(encoded, movie_path, jpeg_quality=86, max_archive_bytes=95*1024*1024)
    preview = tmp_path / 'preview.mp4'
    encode_preview(movie_path, preview, os.environ.get('STAR_ARMADA_FFMPEG'))
    assert quality['min_psnr_db'] >= 42
    assert quality['resize_operations'] == 0
    with zipfile.ZipFile(movie_path) as archive:
        assert len(archive.namelist()) == 361
        assert all(info.compress_type == zipfile.ZIP_STORED for info in archive.infolist())
    with MenuMovie(movie_path.parent, movie_path.name) as movie:
        assert movie.metadata['fps'] == 24
        assert movie.metadata['frame_count'] == 360
        for t in (0., 7.5, 14.958333333, 15.):
            assert movie.get_frame(t, (2560, 1440)).get_size() == (2560, 1440)
            assert movie.cache_info()['frames'] <= 2
    assert preview.stat().st_size > 100000


@pytest.mark.parametrize('problem', ['zip', 'json', 'missing', 'dimensions', 'large', 'compressed'])
def test_corrupt_movie_variants_safe_and_resources_closed(tmp_path, problem):
    from render.menu_movie import MenuMovie
    path = movie_file(tmp_path)
    if problem == 'zip':
        path.write_bytes(b'not a zip')
    elif problem in ('json', 'missing', 'large', 'compressed'):
        with zipfile.ZipFile(path, 'w') as z:
            z.writestr('metadata.json', b'{' if problem == 'json' else
                       b'x'*20000 if problem == 'large' else json.dumps(dict(
                           version=1, width=8, height=6, fps=2, frame_count=4,
                           still_frame=1, loop='baked-crossfade')))
            if problem == 'compressed':
                s = pygame.Surface((8, 6)); out = io.BytesIO(); pygame.image.save(s, out, 'x.jpg')
                z.writestr('frames/00000.jpg', out.getvalue(), compress_type=zipfile.ZIP_DEFLATED)
    elif problem == 'dimensions':
        movie_file(tmp_path, {'width': 9})
    movie = MenuMovie(tmp_path)
    assert movie.get_frame(0, (8, 6)) is None
    assert movie._zip is None
    assert not movie.available
    movie.close()


def test_runtime_does_not_write_or_import_simulation(tmp_path):
    import ast
    from pathlib import Path
    from render.menu_movie import MenuMovie
    movie_file(tmp_path)
    before = {p: (p.stat().st_mtime_ns, p.read_bytes()) for p in tmp_path.rglob('*') if p.is_file()}
    with MenuMovie(tmp_path) as movie:
        for i in range(40):
            assert movie.get_frame(i*.5, (16, 12)) is not None
    after = {p: (p.stat().st_mtime_ns, p.read_bytes()) for p in tmp_path.rglob('*') if p.is_file()}
    assert before == after
    source = Path(__file__).resolve().parents[1] / 'render/menu_movie.py'
    imports = [n.module for n in ast.walk(ast.parse(source.read_text())) if isinstance(n, ast.ImportFrom)]
    assert not any(m and (m.startswith('game') or m.startswith('PIL')) for m in imports)


def test_jpeg_dimensions_checked_before_decoder_allocation(tmp_path, monkeypatch):
    from render.menu_movie import MenuMovie
    path = movie_file(tmp_path)
    with zipfile.ZipFile(path) as z:
        entries = {n: z.read(n) for n in z.namelist()}
    data = bytearray(entries['frames/00000.jpg'])
    sof = data.index(b'\xff\xc0')
    data[sof+7:sof+9] = (40000).to_bytes(2, 'big')
    entries['frames/00000.jpg'] = bytes(data)
    with zipfile.ZipFile(path, 'w') as z:
        for name, content in entries.items():
            z.writestr(name, content)
    def forbidden(*args):
        raise AssertionError('huge mismatched JPEG reached image decoder')
    monkeypatch.setattr(pygame.image, 'load', forbidden)
    with MenuMovie(tmp_path) as movie:
        assert movie.get_frame(0, (8, 6)) is None
        assert not movie.available


def test_exact_24fps_boundaries_do_not_round_back_one_frame(tmp_path):
    from render.menu_movie import MenuMovie
    movie_file(tmp_path, {'fps': 24})
    with MenuMovie(tmp_path) as movie:
        colors = [movie.get_frame((i+.25)/24, (8, 6)).get_at((0, 0)) for i in range(4)]
        for i in range(1000):
            assert movie.get_frame(i/24, (8, 6)).get_at((0, 0)) == colors[i%4]
        assert movie.get_frame(1e308, (8, 6)) is not None


def test_valid_metadata_opens_without_decoding(tmp_path):
    from render.menu_movie import MenuMovie
    movie_file(tmp_path)
    with MenuMovie(tmp_path) as movie:
        assert movie.available
        assert movie.metadata['frame_count'] == 4
        assert movie.cache_info()['frames'] == 0
