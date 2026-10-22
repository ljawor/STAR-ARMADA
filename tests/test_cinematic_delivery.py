"""Native-resolution delivery/compression guardrails; no SDL display or GPU."""
import io
import zipfile
from pathlib import Path

import pytest

pytest.importorskip('PIL', reason='offline cinematic authoring extra is not installed')
from PIL import Image


def make_frames(path, count=8):
    path.mkdir()
    for i in range(count):
        Image.new('RGB',(12,8),(i*20,80,120)).save(path/f'frame_{i:05d}.jpg',quality=95,subsampling=0)
    return path


def test_explicit_crossfade_quality_preserves_native_size_and_copies_normal_frames(tmp_path):
    from tools.cinematics.movie_pack import assemble_movie
    source=make_frames(tmp_path/'source');destination=tmp_path/'movie.zip'
    result=assemble_movie(source,destination,width=12,height=8,fps=2,source_seconds=4,
                          overlap_seconds=1,jpeg_quality=86,max_archive_bytes=100000)
    with zipfile.ZipFile(destination) as archive:
        assert archive.read('frames/00000.jpg')==(source/'frame_00002.jpg').read_bytes()
        last=Image.open(io.BytesIO(archive.read('frames/00005.jpg')))
        expected=io.BytesIO();Image.new('RGB',(12,8)).save(expected,format='JPEG',quality=86,subsampling=0)
        assert last.size==(12,8)
        assert last.quantization==Image.open(io.BytesIO(expected.getvalue())).quantization
    assert result['metadata']['crossfade_jpeg_quality']==86
    assert result['metadata']['crossfade_jpeg_subsampling']=='4:4:4'


@pytest.mark.parametrize('quality',[0,101,True,86.5,'86'])
def test_invalid_crossfade_quality_fails_before_source_access(tmp_path,quality):
    from tools.cinematics.movie_pack import assemble_movie
    with pytest.raises(ValueError,match='quality'):
        assemble_movie(tmp_path/'absent',tmp_path/'movie.zip',jpeg_quality=quality)


def test_archive_budget_is_checked_before_replacing_previous_movie(tmp_path):
    from tools.cinematics.movie_pack import assemble_movie
    source=make_frames(tmp_path/'source');destination=tmp_path/'movie.zip'
    destination.write_bytes(b'previous accepted movie')
    with pytest.raises(ValueError,match='archive exceeds'):
        assemble_movie(source,destination,width=12,height=8,fps=2,source_seconds=4,
                       overlap_seconds=1,max_archive_bytes=1024)
    assert destination.read_bytes()==b'previous accepted movie'
    assert not list(tmp_path.glob('.movie.zip.*.stage'))


@pytest.mark.parametrize('alias',[False,True])
def test_preview_rejects_existing_output_before_initializing_game(tmp_path,alias):
    import subprocess
    import sys
    root=Path(__file__).resolve().parents[1]
    existing=tmp_path/'owner-output';existing.mkdir()
    (existing/'capture.json').write_bytes(b'owner capture')
    (existing/'user').mkdir();(existing/'user/settings.json').write_bytes(b'owner settings')
    output=existing
    if alias:
        output=tmp_path/'alias';output.symlink_to(existing,target_is_directory=True)
    # Block the game import so RED cannot accidentally allocate a GPU context.
    code="import sys,runpy;sys.modules['game']=None;sys.argv=[sys.argv[1],'--out',sys.argv[2]];runpy.run_path(sys.argv[0],run_name='__main__')"
    result=subprocess.run([sys.executable,'-c',code,str(root/'tools/cinematics/verify_preview.py'),str(output)],
                          capture_output=True,text=True,timeout=10)
    assert result.returncode!=0
    assert 'FileExistsError' in result.stderr
    assert (existing/'capture.json').read_bytes()==b'owner capture'
    assert (existing/'user/settings.json').read_bytes()==b'owner settings'
