"""Offline-only native PNG delivery encoding. No resize or video decoder dependency.

Pillow is needed by the authoring tool, never by the game. The fresh output
folder is staging, not the shipped movie; movie_pack verifies the final ZIP.
"""
from pathlib import Path
import hashlib
import io
import json
import math
import shutil


def encode_frames(source_dir, destination_dir, *, count=384, width=2560,
                  height=1440, quality=86, min_psnr_db=42):
    from PIL import Image, ImageChops, ImageStat
    for value, maximum, name in ((count,7200,'count'),(width,4096,'width'),(height,2160,'height')):
        if type(value) is not int or not 1<=value<=maximum:
            raise ValueError('invalid '+name)
    if type(quality) is not int or not 1<=quality<=100:
        raise ValueError('invalid JPEG quality')
    if type(min_psnr_db) not in (int,float) or not math.isfinite(min_psnr_db) or min_psnr_db<0:
        raise ValueError('invalid PSNR threshold')
    source=Path(source_dir).resolve(strict=True)
    destination=Path(destination_dir).absolute()
    if destination.resolve().is_relative_to(source):
        raise ValueError('encoded staging must not modify the source directory')
    expected={f'preview_{i:05d}.png' for i in range(count)}
    if {p.name for p in source.glob('preview_*.png')}!=expected:
        raise ValueError('native PNG sequence is incomplete or contains extra frames')
    for name in expected:
        path=source/name
        if path.is_symlink() or not path.is_file() or path.stat().st_size>32*1024*1024:
            raise ValueError('source must be a bounded regular native PNG')
    destination.mkdir(exist_ok=False)
    digest=hashlib.sha256();rows=[]
    try:
        for i in range(count):
            path=source/f'preview_{i:05d}.png'
            data=path.read_bytes();digest.update(data)
            with Image.open(io.BytesIO(data)) as original:
                if original.format!='PNG' or original.size!=(width,height):
                    raise ValueError('native PNG dimensions disagree; refusing any resize')
                with original.convert('RGB') as image:
                    target=destination/f'frame_{i:05d}.jpg'
                    with target.open('xb') as stream:
                        image.save(stream,format='JPEG',quality=quality,subsampling=0,optimize=True)
                    with Image.open(target) as decoded:
                        with ImageChops.difference(image,decoded) as difference:
                            rms=ImageStat.Stat(difference).rms
                    mse=sum(value*value for value in rms)/3
                    psnr=10*math.log10(255**2/mse) if mse else None
                    if psnr is not None and psnr<min_psnr_db:
                        raise ValueError(f'JPEG PSNR gate failed at frame {i}: {psnr:.3f} dB')
            rows.append(dict(frame=i,bytes=target.stat().st_size,psnr_db=psnr,
                             lossless=mse==0,sha256=hashlib.sha256(target.read_bytes()).hexdigest()))
    except BaseException:
        shutil.rmtree(destination)
        raise
    finite=[row['psnr_db'] for row in rows if row['psnr_db'] is not None]
    return dict(count=count,width=width,height=height,quality=quality,subsampling='4:4:4',
                resize_operations=0,min_psnr_db=min(finite) if finite else None,
                source_png_sha256=digest.hexdigest(),encoded_bytes=sum(row['bytes'] for row in rows),
                frames=rows)


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source',type=Path);parser.add_argument('destination',type=Path)
    parser.add_argument('--report',type=Path,required=True)
    args=parser.parse_args()
    source=args.source.resolve(strict=True)
    destination=args.destination.resolve()
    report=args.report.absolute()
    resolved_report=report.resolve()
    if (report.exists() or report.is_symlink() or
            resolved_report.is_relative_to(source) or
            resolved_report.is_relative_to(destination) or not report.parent.is_dir()):
        parser.error('report path must be fresh, outside source/output directories, with an existing parent')
    receipt=encode_frames(args.source,args.destination)
    # Exclusive creation also refuses a file/symlink created after preflight.
    with report.open('x',encoding='utf-8') as stream:
        json.dump(receipt,stream,indent=2,allow_nan=False)
    print('NATIVE_DELIVERY_OK',receipt['count'],receipt['encoded_bytes'],receipt['min_psnr_db'])
