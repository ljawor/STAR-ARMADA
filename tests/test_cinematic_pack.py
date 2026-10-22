"""CPU-only offline packaging tests; no renderer, display, or simulation."""
import hashlib
import io
import json
import os
import zipfile
from pathlib import Path

import pytest

pytest.importorskip('PIL', reason='offline cinematic authoring extra is not installed')
from PIL import Image


def frames(root, count=384, size=(8, 6)):
    root.mkdir()
    for i in range(count):
        Image.new('RGB', size, (i % 256, 20, 40)).save(
            root / f'frame_{i:05d}.jpg', quality=95, subsampling=0)
    return root


def pack(source, dest, **kwargs):
    from tools.cinematics.movie_pack import assemble_movie
    return assemble_movie(source, dest, width=8, height=6, **kwargs)


def test_default_timing_preserves_normal_bytes_and_runtime_decodes_all(tmp_path):
    from render.menu_movie import MenuMovie
    source = frames(tmp_path / 'source')
    dest = tmp_path / 'movie.zip'
    receipt = pack(source, dest, provenance={'scene': 'approved-core-meshes'})
    with zipfile.ZipFile(dest) as z:
        assert len(z.namelist()) == 361
        assert all(i.compress_type == zipfile.ZIP_STORED for i in z.infolist())
        meta = json.loads(z.read('metadata.json'))
        assert len(z.read('metadata.json')) <= 16384
        assert {k: meta[k] for k in ('version', 'width', 'height', 'fps', 'frame_count', 'still_frame', 'loop')} == dict(
            version=1, width=8, height=6, fps=24, frame_count=360,
            still_frame=180, loop='baked-crossfade')
        for i in range(336):
            assert z.read(f'frames/{i:05d}.jpg') == (source / f'frame_{i+24:05d}.jpg').read_bytes()
        last = Image.open(io.BytesIO(z.read('frames/00359.jpg')))
        from PIL.JpegImagePlugin import get_sampling
        assert get_sampling(last) == 0  # JPEG 4:4:4.
        with Image.open(source / 'frame_00023.jpg') as quality95:
            assert last.quantization == quality95.quantization
        head = Image.open(source / 'frame_00023.jpg')
        assert abs(last.getpixel((0, 0))[0] - head.getpixel((0, 0))[0]) <= 1
        assert meta['native_width'] == 8 and meta['ai_upscaled'] is False
        assert meta['provenance'] == {'scene': 'approved-core-meshes'}
        digest = hashlib.sha256()
        for p in sorted(source.iterdir()):
            digest.update(p.read_bytes())
        assert meta['source_sha256'] == digest.hexdigest()
        assert receipt['metadata'] == meta
    with MenuMovie(dest.parent, dest.name) as movie:
        for i in range(360):
            assert movie.get_frame((i + .25) / 24, (8, 6)) is not None


@pytest.mark.parametrize('problem', ['missing', 'extra', 'wrong_name', 'corrupt_last',
                                    'dimensions', 'huge_header', 'oversized', 'symlink',
                                    'directory_symlink', 'ancestor_symlink', 'corrupt_head',
                                    'png_named_jpeg', 'truncated_last'])
def test_bad_sources_preserve_previous_destination(tmp_path, problem, monkeypatch):
    source = frames(tmp_path / 'source', count=8)
    last = source / 'frame_00007.jpg'
    if problem == 'missing':
        last.unlink()
    elif problem == 'extra':
        (source / 'frame_00008.jpg').write_bytes(last.read_bytes())
    elif problem == 'wrong_name':
        last.rename(source / 'frame_7.jpg')
    elif problem == 'corrupt_last':
        last.write_bytes(b'not a jpeg')
    elif problem == 'dimensions':
        Image.new('RGB', (9, 6)).save(last)
    elif problem == 'huge_header':
        payload = bytearray(last.read_bytes())
        sof = payload.index(b'\xff\xc0')
        payload[sof+7:sof+9] = (50000).to_bytes(2, 'big')
        last.write_bytes(payload)
        original = Image.Image.load
        def forbid_huge(self, *a, **kw):
            assert self.width <= 4096, 'huge image reached allocation'
            return original(self, *a, **kw)
        monkeypatch.setattr(Image.Image, 'load', forbid_huge)
    elif problem == 'oversized':
        last.write_bytes(last.read_bytes() + b'x' * (4 * 1024 * 1024))
    elif problem == 'symlink':
        outside = tmp_path / 'outside.jpg'
        last.rename(outside)
        last.symlink_to(outside)
    elif problem == 'corrupt_head':
        (source / 'frame_00000.jpg').write_bytes(b'not a jpeg')
    elif problem == 'png_named_jpeg':
        Image.new('RGB', (8, 6)).save(last, format='PNG')
    elif problem == 'truncated_last':
        last.write_bytes(last.read_bytes()[:100])
    elif problem == 'ancestor_symlink':
        alias = tmp_path / 'ancestor'
        alias.symlink_to(tmp_path, target_is_directory=True)
        source = alias / 'source'
    else:
        alias = tmp_path / 'alias'
        alias.symlink_to(source, target_is_directory=True)
        source = alias
    dest = tmp_path / 'movie.zip'
    dest.write_bytes(b'previous destination')
    with pytest.raises((ValueError, OSError)):
        pack(source, dest, fps=2, source_seconds=4, overlap_seconds=1)
    assert dest.read_bytes() == b'previous destination'
    assert not list(tmp_path.glob('.movie.zip.*.stage'))


@pytest.mark.parametrize('options', [
    {'width': 4097}, {'height': 2161}, {'width': True}, {'width': 0},
    {'fps': 0}, {'fps': 61}, {'fps': True}, {'fps': float('nan')},
    {'source_seconds': float('inf')}, {'source_seconds': -1},
    {'source_seconds': .1}, {'source_seconds': 4000},
    {'overlap_seconds': 0}, {'overlap_seconds': 16},
    {'overlap_seconds': .01}, {'provenance': {'blob': 'x' * 17000}},
    {'provenance': {'bad': float('nan')}},
])
def test_invalid_parameters_fail_before_reading_sources(tmp_path, options):
    from tools.cinematics.movie_pack import assemble_movie
    dest = tmp_path / 'movie.zip'
    dest.write_bytes(b'previous')
    with pytest.raises(ValueError):
        assemble_movie(tmp_path / 'absent', dest, **options)
    assert dest.read_bytes() == b'previous'


def test_actual_runtime_validates_every_frame_before_atomic_replace(tmp_path, monkeypatch):
    from render.menu_movie import MenuMovie
    source = frames(tmp_path / 'source', count=8)
    dest = tmp_path / 'movie.zip'
    dest.write_bytes(b'previous')
    real_get = MenuMovie.get_frame
    seen = []
    def reject_last(self, elapsed, size, reduced_motion=False):
        assert dest.read_bytes() == b'previous'
        assert Path(self._zip.filename).name != dest.name
        seen.append(elapsed)
        if len(seen) == 6:
            return None
        return real_get(self, elapsed, size, reduced_motion)
    monkeypatch.setattr(MenuMovie, 'get_frame', reject_last)
    with pytest.raises(ValueError, match='staged frame 5'):
        pack(source, dest, fps=2, source_seconds=4, overlap_seconds=1)
    assert len(seen) == 6
    assert dest.read_bytes() == b'previous'
    assert not list(tmp_path.glob('.movie.zip.*.stage'))


@pytest.mark.parametrize('link', ['symlink', 'hardlink'])
def test_predictable_staging_traps_are_not_written(tmp_path, link, monkeypatch):
    import tempfile
    monkeypatch.setattr(tempfile, '_get_candidate_names', lambda: iter(['known', 'safe']))
    source = frames(tmp_path / 'source', count=8)
    victim = tmp_path / 'victim'
    victim.write_bytes(b'untouched')
    for name in ('.movie.zip.known.stage', 'movie.zip.tmp', '.movie.zip.tmp',
                 '.movie.zip.stage', 'movie.zip.part'):
        path = tmp_path / name
        if link == 'symlink':
            path.symlink_to(victim)
        else:
            os.link(victim, path)
    dest = tmp_path / 'movie.zip'
    pack(source, dest, fps=2, source_seconds=4, overlap_seconds=1)
    assert victim.read_bytes() == b'untouched'
    assert dest.is_file()


def test_crossfade_uses_smoothstep_and_inclusive_endpoints(tmp_path):
    source = frames(tmp_path / 'source', count=16)
    for i, p in enumerate(sorted(source.iterdir())):
        Image.new('RGB', (8, 6), (0 if i < 4 else 240, 0, 0)).save(p, quality=95, subsampling=0)
    dest = tmp_path / 'movie.zip'
    pack(source, dest, fps=4, source_seconds=4, overlap_seconds=1)
    with zipfile.ZipFile(dest) as z:
        reds = [Image.open(io.BytesIO(z.read(f'frames/{i:05d}.jpg'))).getpixel((0, 0))[0]
                for i in range(8, 12)]
    assert reds == pytest.approx([240, 178, 62, 0], abs=2)


def test_cli_assembles_and_encodes_real_preview(tmp_path):
    import shutil
    import subprocess
    import sys
    ffmpeg = shutil.which('ffmpeg')
    ffprobe = shutil.which('ffprobe')
    if not ffmpeg or not ffprobe:
        pytest.skip('optional local ffmpeg/ffprobe unavailable')
    source = frames(tmp_path / 'source', count=8)
    dest = tmp_path / 'movie.zip'
    preview = tmp_path / 'preview.mp4'
    result = subprocess.run([sys.executable, '-m', 'tools.cinematics.movie_pack',
                             str(source), str(dest), '--width', '8', '--height', '6',
                             '--fps', '2', '--source-seconds', '4',
                             '--overlap-seconds', '1', '--jpeg-quality', '86',
                             '--max-archive-mib', '1', '--preview', str(preview)],
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    assert dest.is_file() and preview.is_file()
    receipt = json.loads(result.stdout.splitlines()[-1])
    assert receipt['validated_frames'] == 6
    assert receipt['preview']['frames'] == 6
    probe = subprocess.run([ffprobe, '-v', 'error', '-count_frames', '-select_streams', 'v:0',
                            '-show_entries', 'stream=width,height,nb_read_frames,r_frame_rate',
                            '-of', 'json', str(preview)], capture_output=True, text=True, check=True)
    assert json.loads(probe.stdout)['streams'][0] == dict(
        width=8, height=6, r_frame_rate='2/1', nb_read_frames='6')


def test_preview_encoder_failure_preserves_old_file(tmp_path):
    from tools.cinematics.movie_pack import encode_preview
    source = frames(tmp_path / 'source', count=8)
    movie = tmp_path / 'movie.zip'
    pack(source, movie, fps=2, source_seconds=4, overlap_seconds=1)
    preview = tmp_path / 'preview.mp4'
    preview.write_bytes(b'previous preview')
    with pytest.raises(OSError):
        encode_preview(movie, preview, ffmpeg='/nonexistent/ffmpeg')
    assert preview.read_bytes() == b'previous preview'
    assert not list(tmp_path.glob('.preview.mp4.*.stage'))


def preview_child(tmp_path, monkeypatch, body):
    """Real encoder stand-in, with enough input to fill a pipe."""
    import subprocess
    import sys
    source = frames(tmp_path / 'source', count=8)
    for path in source.iterdir():
        path.write_bytes(path.read_bytes() + b'x' * (256 * 1024))
    movie = tmp_path / 'movie.zip'
    pack(source, movie, fps=2, source_seconds=4, overlap_seconds=1)
    preview = tmp_path / 'preview.mp4'
    preview.write_bytes(b'previous preview')
    encoder = tmp_path / 'encoder'
    encoder.write_text(f'#!{sys.executable}\n' + body)
    encoder.chmod(0o700)
    children = []
    real_popen = subprocess.Popen
    def record_child(*args, **kwargs):
        # Invoke the interpreter directly: fresh-executable macOS inspection can
        # otherwise consume the small test deadline before the script starts.
        command, *rest = args
        child = real_popen([sys.executable, *command], *rest, **kwargs)
        children.append(child)
        return child
    monkeypatch.setattr(subprocess, 'Popen', record_child)
    return movie, preview, encoder, children


def assert_preview_failure_clean(tmp_path, preview, children):
    assert preview.read_bytes() == b'previous preview'
    assert not list(tmp_path.glob('.preview.mp4.*.stage'))
    assert len(children) == 1 and children[0].returncode is not None
    with pytest.raises(ChildProcessError):
        os.waitpid(children[0].pid, os.WNOHANG)


def test_preview_early_exit_retains_bounded_stderr(tmp_path, monkeypatch):
    from tools.cinematics.movie_pack import encode_preview
    movie, preview, encoder, children = preview_child(
        tmp_path, monkeypatch,
        "import os\nos.write(2, b'encoder diagnostic: unsupported input\\n' * 8192)\n"
        "raise SystemExit(7)\n")
    with pytest.raises(RuntimeError, match='encoder diagnostic: unsupported input') as error:
        encode_preview(movie, preview, ffmpeg=encoder)
    assert len(str(error.value)) < 9000
    assert_preview_failure_clean(tmp_path, preview, children)


@pytest.mark.parametrize('timeout', [0.15, 0.35])
@pytest.mark.parametrize('read_input', [False, True])
def test_preview_deadline_covers_pipe_and_encoder(tmp_path, monkeypatch, timeout, read_input):
    import time
    from tools.cinematics.movie_pack import encode_preview
    movie, preview, encoder, children = preview_child(
        tmp_path, monkeypatch,
        "import os, sys, time\nos.write(2, b'stalled encoder diagnostic\\n')\n"
        + ("sys.stdin.buffer.read()\n" if read_input else '') + "time.sleep(30)\n")
    start = time.monotonic()
    with pytest.raises(TimeoutError, match='stalled encoder diagnostic'):
        encode_preview(movie, preview, ffmpeg=encoder, timeout=timeout)
    assert time.monotonic() - start < timeout + 2
    assert_preview_failure_clean(tmp_path, preview, children)


@pytest.mark.parametrize('failure', ['replace', 'encode_bound', 'source_changed'])
def test_failures_during_publication_preserve_destination(tmp_path, monkeypatch, failure):
    import tools.cinematics.movie_pack as module
    source = frames(tmp_path / 'source', count=8)
    dest = tmp_path / 'movie.zip'
    dest.write_bytes(b'previous')
    if failure == 'replace':
        def fail_replace(*args):
            raise OSError('injected replacement failure')
        monkeypatch.setattr(module.os, 'replace', fail_replace)
    elif failure == 'encode_bound':
        def oversized_encode(self, out, **kwargs):
            out.write(b'x' * (module.MAX_JPEG_BYTES + 1))
        monkeypatch.setattr(Image.Image, 'save', oversized_encode)
    else:
        real_read = module._read_frame
        reads = []
        def changing_read(directory_fd, index):
            data = real_read(directory_fd, index)
            reads.append(index)
            return data + b'changed' if len(reads) > 8 else data
        monkeypatch.setattr(module, '_read_frame', changing_read)
    with pytest.raises((OSError, ValueError)):
        pack(source, dest, fps=2, source_seconds=4, overlap_seconds=1)
    assert dest.read_bytes() == b'previous'
    assert not list(tmp_path.glob('.movie.zip.*.stage'))
