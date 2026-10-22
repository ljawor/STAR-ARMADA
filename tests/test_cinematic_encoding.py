"""Offline PNG-to-JPEG delivery retains native pixels, with measured error."""
import importlib.util
from pathlib import Path

import pytest

pytest.importorskip('PIL', reason='offline cinematic authoring extra is not installed')
from PIL import Image


def encoder():
    assert importlib.util.find_spec('tools.cinematics.prepare_frames') is not None
    from tools.cinematics.prepare_frames import encode_frames
    return encode_frames


def pngs(root, count=4, size=(12,8)):
    root.mkdir()
    for i in range(count):
        Image.new('RGB',size,(40+i,80,120)).save(root/f'preview_{i:05d}.png')
    return root


def test_native_encoding_measures_quality_and_never_resizes(tmp_path):
    encode=encoder();source=pngs(tmp_path/'source');dest=tmp_path/'encoded'
    report=encode(source,dest,count=4,width=12,height=8,quality=86)
    assert len(list(dest.iterdir()))==4
    assert Image.open(dest/'frame_00000.jpg').size==(12,8)
    assert report['count']==4 and report['quality']==86 and report['subsampling']=='4:4:4'
    assert report['resize_operations']==0 and report['min_psnr_db']>=42
    assert len(report['source_png_sha256'])==64


@pytest.mark.parametrize('problem',['wrong_size','truncated','extra','missing','symlink'])
def test_bad_native_sources_do_not_publish_partial_directory(tmp_path,problem):
    encode=encoder();source=pngs(tmp_path/'source');dest=tmp_path/'encoded'
    frame=source/'preview_00003.png'
    if problem=='wrong_size':Image.new('RGB',(10,8)).save(frame)
    elif problem=='truncated':frame.write_bytes(b'notPNG')
    elif problem=='extra':Image.new('RGB',(12,8)).save(source/'preview_00004.png')
    elif problem=='missing':frame.unlink()
    else:
        outside=tmp_path/'outside.png';frame.rename(outside);frame.symlink_to(outside)
    with pytest.raises((ValueError,OSError)):
        encode(source,dest,count=4,width=12,height=8)
    assert not dest.exists()


def test_existing_directory_is_preserved(tmp_path):
    encode=encoder();source=pngs(tmp_path/'source');dest=tmp_path/'encoded';dest.mkdir()
    (dest/'owner_file').write_text('keep')
    with pytest.raises(FileExistsError):encode(source,dest,count=4,width=12,height=8)
    assert (dest/'owner_file').read_text()=='keep'


def test_quality_failure_cleans_up_and_keeps_source_png(tmp_path):
    encode=encoder();source=pngs(tmp_path/'source');dest=tmp_path/'encoded'
    before=(source/'preview_00000.png').read_bytes()
    with pytest.raises(ValueError,match='PSNR'):
        encode(source,dest,count=4,width=12,height=8,quality=1,min_psnr_db=80)
    assert not dest.exists()
    assert (source/'preview_00000.png').read_bytes()==before


@pytest.mark.parametrize('collision',['source','output','symlink','hardlink','source_parent','output_parent','existing_report'])
def test_cli_report_collision_is_rejected_before_encoding(tmp_path,collision):
    import subprocess
    import sys
    source=pngs(tmp_path/'source',count=1);destination=tmp_path/'encoded'
    original=source/'preview_00000.png';before=original.read_bytes()
    if collision=='source':report=original
    elif collision=='output':report=destination/'frame_00000.jpg'
    elif collision in ('symlink','hardlink'):
        report=tmp_path/'report.json'
        if collision=='symlink':report.symlink_to(original)
        else:
            import os
            os.link(original,report)
    elif collision=='source_parent':
        alias=tmp_path/'alias';alias.symlink_to(source,target_is_directory=True)
        report=alias/'preview_00000.png'
    elif collision=='output_parent':
        alias=tmp_path/'alias';alias.symlink_to(tmp_path,target_is_directory=True)
        report=alias/'encoded/frame_00000.jpg'
    else:
        report=tmp_path/'report.json';report.write_bytes(b'keep previous report')
    result=subprocess.run([sys.executable,'-m','tools.cinematics.prepare_frames',str(source),
                           str(destination),'--report',str(report)],capture_output=True,text=True,timeout=10)
    assert result.returncode!=0
    assert 'report path' in result.stderr
    assert original.read_bytes()==before
    assert not destination.exists()
    if collision=='existing_report':assert report.read_bytes()==b'keep previous report'
