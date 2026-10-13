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


def test_presentation_fixture_contains_real_models_and_animated_contacts():
    from tools.build_menu_movie import PresentationFixture
    fixture = PresentationFixture()
    state = fixture.state
    assert state._manager is None
    ids = {e.data_id for e in state.entities.values()}
    assert {'imperial_frigate', 'rebel_frigate', 'imperial_battleship',
            'imperial_supercapital'} <= ids
    assert len(state.entities) >= 6
    assert state.players[0].color != state.players[1].color
    assert all(state.can_see(0, e.id) for e in state.entities.values())
    fixture.sample(.2)
    a = [tuple(e.pos.to_dict()) for e in state.entities.values()]
    assert {'beam', 'shield_hit', 'muzzle'} <= {fx['kind'] for fx in state.effects}
    assert len(state.projectiles) >= 4
    assert sum(fx['kind'] == 'beam' for fx in state.effects) >= 2
    assert all(fx.get('size', 0) <= 18 for fx in state.effects if fx['kind'] == 'shield_hit')
    fixture.sample(3.7)
    b = [tuple(e.pos.to_dict()) for e in state.entities.values()]
    assert a != b
    assert state.tick > 0


def test_cinematic_camera_is_slow_and_periodic():
    from tools.build_menu_movie import camera_pose
    a, b, c = camera_pose(0), camera_pose(16), camera_pose(.0416667)
    assert a == pytest.approx(b)
    assert abs(c[0] - a[0]) < .2
    assert abs(c[1] - a[1]) < .2
    assert abs(c[2] - a[2]) < 1


def test_baked_crossfade_matches_head_continuation():
    from tools.build_menu_movie import loop_frame
    surfaces = []
    for i in range(8):
        s = pygame.Surface((3, 2)); s.fill((i * 30, 0, 0)); surfaces.append(s)
    assert loop_frame(surfaces[2], None, 0).get_at((0, 0)).r == 60
    assert loop_frame(surfaces[7], surfaces[1], 1).get_at((0, 0)).r == 30
    assert 60 < loop_frame(surfaces[6], surfaces[0], .5).get_at((0, 0)).r < 130


@pytest.mark.skipif(__import__('os').environ.get('STAR_ARMADA_GL_TEST') != '1',
                    reason='requires real desktop GL context')
def test_offline_builder_real_gl_preview(tmp_path):
    import subprocess
    import sys
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    completed = subprocess.run([sys.executable, 'tools/build_menu_movie.py',
                                '--preview-only', '--output-dir', str(tmp_path)],
                               cwd=root, capture_output=True, text=True, timeout=120)
    assert completed.returncode == 0, completed.stdout + completed.stderr
    report = json.loads((tmp_path / 'render-report.json').read_text())
    assert report['msaa_samples'] >= 4
    assert len(report['samples']) == 3
    for sample in report['samples']:
        assert sample['gl_error'] == 0
        assert sample['lit_pixels'] > 40000
        assert sample['red_pixels'] > 1500
        assert sample['blue_pixels'] > 1500
        assert sample['visible_centers'] == 7
        assert sample['weapon_effect_pixels'] > 100
        assert sample['shield_hit_pixels'] > 10
    assert all((tmp_path / name).is_file() for name in ['start.png', 'middle.png', 'end.png'])


@pytest.mark.skipif(__import__('os').environ.get('STAR_ARMADA_MOVIE_BUILD_TEST') != '1',
                    reason='offline 360-frame GL/ffmpeg build acceptance')
def test_full_movie_asset_preview_and_lazy_playback(tmp_path):
    import subprocess
    import sys
    from pathlib import Path
    from render.menu_movie import MenuMovie
    root = Path(__file__).resolve().parents[1]
    import os
    import shutil
    ffmpeg = os.environ.get('STAR_ARMADA_FFMPEG') or shutil.which('ffmpeg')
    assert ffmpeg, 'Set STAR_ARMADA_FFMPEG for the opt-in offline build test'
    asset_root = tmp_path / 'assets'
    result = subprocess.run([sys.executable, 'tools/build_menu_movie.py',
                             '--asset', str(asset_root / 'menu/battle.zip'),
                             '--output-dir', str(tmp_path / 'preview'), '--ffmpeg', ffmpeg],
                             cwd=root, capture_output=True, text=True, timeout=240)
    assert result.returncode == 0, result.stdout + result.stderr
    with zipfile.ZipFile(asset_root / 'menu/battle.zip') as z:
        assert len(z.namelist()) == 361
        assert all(i.compress_type == zipfile.ZIP_STORED for i in z.infolist())
    with MenuMovie(asset_root) as movie:
        assert movie.metadata['fps'] == 24
        assert movie.metadata['frame_count'] == 360
        for t in (0., 7.5, 14.958333333, 15.):
            assert movie.get_frame(t, (1280, 720)).get_size() == (1280, 720)
            assert movie.cache_info()['frames'] <= 2
    assert (tmp_path / 'preview/intro-battle-preview.mp4').stat().st_size > 100000
    report = json.loads((tmp_path / 'preview/render-report.json').read_text())
    assert report['full_render_gl_errors'] == 0
    assert report['asset_bytes'] > 100000
    assert report['playback']['decode_scale_p95_ms'] < 45
    assert report['loop_seam_mean_abs_rgb'] < 8


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
