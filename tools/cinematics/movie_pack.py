"""Assemble existing native JPEG renders; never renders or upscales imagery.

Pillow is an optional OFFLINE dependency (install into the build environment only).
The game has no Pillow dependency. Run from repo root with
``python -m tools.cinematics.movie_pack FRAME_DIR DESTINATION.zip``.
Source SHA-256 hashes exact source JPEG bytes in numerical filename order.
Publication is atomic only after every staged frame passes the actual MenuMovie
CPU decoder. No display/GL initialization is needed. Memory is O(one frame), not
O(movie duration); a few bounded RGB images coexist during crossfading.
Source directories must contain only the exact sequence; symlink components and
symlink/nonregular frame files are rejected. The destination parent must exist.
"""
from contextlib import contextmanager
import hashlib
import io
import json
import math
import os
from pathlib import Path
import stat
import tempfile
import zipfile

MAX_JPEG_BYTES = 4 * 1024 * 1024
MAX_METADATA_BYTES = 16384


def _metadata_bytes(metadata):
    try:
        payload = json.dumps(metadata, allow_nan=False, sort_keys=True,
                             separators=(',', ':')).encode('utf-8')
    except (TypeError, ValueError, OverflowError, RecursionError) as exc:
        raise ValueError('metadata must be finite JSON') from exc
    if len(payload) > MAX_METADATA_BYTES:
        raise ValueError('metadata exceeds 16384 bytes')
    return payload


@contextmanager
def _source_directory(path):
    # Walk from root by descriptor: no symlink component or path escape/race.
    path = Path(path).absolute()
    if '..' in path.parts:
        raise ValueError('source traversal is forbidden')
    fd = os.open(path.anchor, os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in path.parts[1:]:
            next_fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                              dir_fd=fd)
            os.close(fd)
            fd = next_fd
        yield fd
    finally:
        os.close(fd)


def _read_frame(directory_fd, index):
    fd = os.open(f'frame_{index:05d}.jpg',
                 os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory_fd)
    with os.fdopen(fd, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_JPEG_BYTES:
            raise ValueError('source must be a bounded regular JPEG')
        payload = stream.read(MAX_JPEG_BYTES + 1)
    if len(payload) > MAX_JPEG_BYTES:
        raise ValueError('source JPEG exceeds 4 MiB')
    return payload


def _check_image(payload, width, height):
    from PIL import Image
    with Image.open(io.BytesIO(payload)) as image:
        # Pillow only parses the header on open. Check BEFORE load/convert.
        if image.format != 'JPEG' or image.size != (width, height):
            raise ValueError('source must be JPEG with exact native dimensions')
        image.load()


def _validate_movie(path, metadata):
    # Deliberately late: assembling is an offline tool, not a runtime import.
    from render.menu_movie import MenuMovie
    with MenuMovie(path.parent, path.name) as movie:
        if not movie.available:
            raise ValueError('staged movie rejected: ' + str(movie.error))
        for index in range(metadata['frame_count']):
            frame = movie.get_frame((index + .25) / metadata['fps'],
                                    (metadata['width'], metadata['height']))
            if frame is None:
                raise ValueError(f'staged frame {index} rejected: {movie.error}')


def _timing(width, height, fps, source_seconds, overlap_seconds):
    for value, maximum, name in ((width, 4096, 'width'), (height, 2160, 'height')):
        if type(value) is not int or not 1 <= value <= maximum:
            raise ValueError('invalid ' + name)
    for value, name in ((fps, 'fps'), (source_seconds, 'source_seconds'),
                        (overlap_seconds, 'overlap_seconds')):
        try:
            valid = type(value) in (int, float) and math.isfinite(value) and value > 0
        except OverflowError:
            valid = False
        if not valid:
            raise ValueError('invalid ' + name)
    if fps > 60:
        raise ValueError('fps exceeds runtime bound')
    counts = []
    for seconds in (source_seconds, overlap_seconds):
        value = seconds * fps
        if not math.isfinite(value) or value > 7200:
            raise ValueError('source frame count exceeds bounds')
        nearest = round(value)
        if not math.isclose(value, nearest, abs_tol=1e-8, rel_tol=0):
            raise ValueError('timing must specify whole frames')
        counts.append(nearest)
    count, overlap = counts
    if not (2 <= overlap and 2 * overlap <= count and 1 <= count - overlap <= 3600):
        raise ValueError('invalid overlap or output frame count')
    return count, overlap


def assemble_movie(frame_dir, destination, width=2560, height=1440, fps=24,
                   source_seconds=16, overlap_seconds=1, provenance=None,
                   jpeg_quality=95, max_archive_bytes=None):
    """Return a receipt after atomically publishing a runtime-validated ZIP.

    First overlap frames are omitted from normal output and blended into the
    final overlap. Smoothstep has inclusive endpoints: alpha(0)=0, alpha(last)=1.
    Defaults: 384 source frames, 360 output frames, 15 seconds, still frame 180.
    Normal JPEG bytes are copied verbatim; blends use explicit JPEG quality
    (default95), always4:4:4. An optional archive byte cap is checked before publish.
    Invalid input, encoding, validation, or replacement failure leaves the old
    destination unchanged. The destination is never opened for writing in place.
    """
    count, overlap = _timing(width, height, fps, source_seconds, overlap_seconds)
    if type(jpeg_quality) is not int or not 1 <= jpeg_quality <= 100:
        raise ValueError('invalid JPEG quality')
    if max_archive_bytes is not None and (type(max_archive_bytes) is not int or max_archive_bytes < 1):
        raise ValueError('invalid archive byte budget')
    output_count = count - overlap
    metadata = dict(version=1, width=width, height=height, fps=fps,
                    frame_count=output_count, still_frame=output_count // 2,
                    loop='baked-crossfade', native_width=width, native_height=height,
                    ai_upscaled=False, source_frame_count=count,
                    source_seconds=source_seconds, overlap_seconds=overlap_seconds,
                    crossfade_jpeg_quality=jpeg_quality, crossfade_jpeg_subsampling='4:4:4',
                    provenance={} if provenance is None else provenance,
                    source_sha256='0' * 64)
    _metadata_bytes(metadata)  # Bounds/serialization before opening source files.
    from PIL import Image
    source = Path(frame_dir)
    destination = Path(destination).absolute()
    if destination.resolve().is_relative_to(source.resolve()):
        raise ValueError('destination must be outside source directory')
    staged = None
    with _source_directory(source) as directory_fd:
        expected = {f'frame_{i:05d}.jpg' for i in range(count)}
        if set(os.listdir(directory_fd)) != expected:
            raise ValueError(f'source directory must contain exactly {count} named JPEGs')
        digest = hashlib.sha256()
        hashes = []
        for index in range(count):
            payload = _read_frame(directory_fd, index)
            _check_image(payload, width, height)
            digest.update(payload)
            hashes.append(hashlib.sha256(payload).digest())
        metadata['source_sha256'] = digest.hexdigest()

        def read_unchanged(index):
            payload = _read_frame(directory_fd, index)
            if hashlib.sha256(payload).digest() != hashes[index]:
                raise ValueError('source JPEG changed during assembly')
            return payload

        try:
            fd, name = tempfile.mkstemp(prefix=f'.{destination.name}.', suffix='.stage',
                                       dir=destination.parent)
            staged = Path(name)
            with os.fdopen(fd, 'w+b') as stream:
                identity = os.fstat(stream.fileno())
                with zipfile.ZipFile(stream, 'w', compression=zipfile.ZIP_STORED) as archive:
                    archive.writestr('metadata.json', _metadata_bytes(metadata))
                    for index in range(output_count):
                        payload = read_unchanged(index + overlap)
                        if index >= output_count - overlap:
                            j = index - (output_count - overlap)
                            t = j / (overlap - 1)
                            alpha = t * t * (3 - 2 * t)
                            with Image.open(io.BytesIO(payload)) as tail, Image.open(
                                    io.BytesIO(read_unchanged(j))) as head:
                                with tail.convert('RGB') as a, head.convert('RGB') as b:
                                    with Image.blend(a, b, alpha) as blend:
                                        out = io.BytesIO()
                                        blend.save(out, format='JPEG', quality=jpeg_quality, subsampling=0, optimize=True)
                                        payload = out.getvalue()
                        if len(payload) > MAX_JPEG_BYTES:
                            raise ValueError('encoded JPEG exceeds runtime 4 MiB bound')
                        archive.writestr(f'frames/{index:05d}.jpg', payload)
                stream.flush()
                os.fsync(stream.fileno())
            _validate_movie(staged, metadata)
            current = staged.lstat()
            if (not stat.S_ISREG(current.st_mode) or current.st_nlink != 1 or
                    (current.st_dev, current.st_ino) != (identity.st_dev, identity.st_ino)):
                raise ValueError('staging identity changed')
            published_bytes = current.st_size
            if max_archive_bytes is not None and published_bytes > max_archive_bytes:
                raise ValueError(f'archive exceeds byte budget: {published_bytes} > {max_archive_bytes}')
            os.replace(staged, destination)
        finally:
            if staged is not None:
                staged.unlink(missing_ok=True)
    return dict(destination=str(destination), bytes=published_bytes,
                metadata=metadata, validated_frames=output_count)


def _stream_encoder(process, frames, deadline):
    """POSIX nonblocking pipes: one frame and at most 8 KiB stderr retained.

    No buffered stdin flush or writer threads can outlive the encoder deadline.
    Drain stderr concurrently even after a broken pipe, so early-exit diagnostics
    survive and a verbose encoder cannot deadlock or grow a temporary file.
    """
    import selectors
    import time
    diagnostic = bytearray()
    complete = False
    pending = memoryview(b'')
    os.set_blocking(process.stdin.fileno(), False)
    os.set_blocking(process.stderr.fileno(), False)

    def read_errors():
        try:
            data = os.read(process.stderr.fileno(), 65536)
        except BlockingIOError:
            return True
        diagnostic.extend(data[:max(0, 8192 - len(diagnostic))])
        return bool(data)

    def message():
        return diagnostic.decode(errors='replace')

    try:
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdin, selectors.EVENT_WRITE, 'input')
            selector.register(process.stderr, selectors.EVENT_READ, 'errors')
            while True:
                if time.monotonic() >= deadline:
                    raise TimeoutError('ffmpeg timed out: ' + message())
                if not process.stdin.closed and not pending:
                    try:
                        pending = memoryview(next(frames))
                    except StopIteration:
                        complete = True
                        selector.unregister(process.stdin)
                        process.stdin.close()  # unbuffered; never flushes
                if process.poll() is not None and not any(
                        key.data == 'errors' for key in selector.get_map().values()):
                    break
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    continue
                for key, _ in selector.select(min(remaining, .05)):
                    if key.data == 'errors':
                        if not read_errors():
                            selector.unregister(process.stderr)
                    else:
                        try:
                            written = os.write(process.stdin.fileno(), pending[:65536])
                            pending = pending[written:]
                        except BlockingIOError:
                            pass
                        except BrokenPipeError:
                            selector.unregister(process.stdin)
                            process.stdin.close()
            if process.returncode or not complete:
                raise RuntimeError('ffmpeg failed: ' + message())
    finally:
        if process.poll() is None:
            process.kill()
        process.wait()
        process.stdin.close()
        process.stderr.close()


def encode_preview(movie_path, destination, ffmpeg=None, timeout=180):
    """Encode the *baked ZIP* to H.264 MP4 using an optional local ffmpeg.

    Streams bounded JPEGs, uses two encoding threads, and atomically replaces
    only the preview destination after success. No new renders or upscaling.
    Odd native dimensions are padded by at most one pixel for YUV 4:2:0.
    Preview failure does not undo a separately successful movie publication.
    A single finite timeout covers streaming, pipe closure and encoder completion.
    """
    import shutil
    import subprocess
    import time
    from render.menu_movie import MenuMovie
    if type(timeout) not in (int, float) or not math.isfinite(timeout) or timeout <= 0:
        raise ValueError('invalid preview timeout')
    movie_path = Path(movie_path).absolute()
    destination = Path(destination).absolute()
    if movie_path.resolve() == destination.resolve():
        raise ValueError('preview destination must differ from movie')
    executable = ffmpeg or shutil.which('ffmpeg')
    if not executable:
        raise FileNotFoundError('optional preview requires local ffmpeg')
    with MenuMovie(movie_path.parent, movie_path.name) as movie:
        if not movie.available:
            raise ValueError('invalid preview source: ' + str(movie.error))
        metadata = dict(movie.metadata)
    _validate_movie(movie_path, metadata)
    staged = None
    process = None
    try:
        fd, name = tempfile.mkstemp(prefix=f'.{destination.name}.', suffix='.stage',
                                   dir=destination.parent)
        staged = Path(name)
        with os.fdopen(fd, 'w+b') as output:
            identity = os.fstat(output.fileno())
            command = [str(executable), '-hide_banner', '-loglevel', 'error',
                       '-f', 'image2pipe', '-vcodec', 'mjpeg', '-framerate',
                       str(metadata['fps']), '-i', 'pipe:0', '-an', '-c:v', 'libx264',
                       '-threads', '2', '-preset', 'veryfast', '-crf', '18',
                       '-vf', 'pad=ceil(iw/2)*2:ceil(ih/2)*2', '-pix_fmt', 'yuv420p',
                       '-movflags', 'frag_keyframe+empty_moov', '-f', 'mp4', 'pipe:1']
            deadline = time.monotonic() + timeout
            process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=output,
                                       stderr=subprocess.PIPE, bufsize=0)

            def frames():
                with zipfile.ZipFile(movie_path) as archive:
                    for index in range(metadata['frame_count']):
                        info = archive.getinfo(f'frames/{index:05d}.jpg')
                        if info.file_size > MAX_JPEG_BYTES or info.compress_type != zipfile.ZIP_STORED:
                            raise ValueError('unbounded preview frame')
                        payload = archive.read(info)
                        _check_image(payload, metadata['width'], metadata['height'])
                        yield payload

            stream = frames()
            try:
                _stream_encoder(process, stream, deadline)
            finally:
                stream.close()
            output.flush()
            os.fsync(output.fileno())
        current = staged.lstat()
        if (not stat.S_ISREG(current.st_mode) or current.st_nlink != 1 or current.st_size == 0 or
                (current.st_dev, current.st_ino) != (identity.st_dev, identity.st_ino)):
            raise ValueError('invalid preview staging file')
        preview_bytes = current.st_size
        os.replace(staged, destination)
    finally:
        if staged is not None:
            staged.unlink(missing_ok=True)
    return dict(destination=str(destination), bytes=preview_bytes,
                frames=metadata['frame_count'], fps=metadata['fps'])


def main(argv=None):
    """CLI: package existing frames, optionally encode an owner-review preview."""
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('frame_dir', type=Path)
    parser.add_argument('destination', type=Path)
    parser.add_argument('--width', type=int, default=2560)
    parser.add_argument('--height', type=int, default=1440)
    parser.add_argument('--fps', type=float, default=24)
    parser.add_argument('--source-seconds', type=float, default=16)
    parser.add_argument('--overlap-seconds', type=float, default=1)
    parser.add_argument('--jpeg-quality', type=int, default=95,
                        help='quality of the crossfade JPEGs; normal frames are copied unchanged')
    parser.add_argument('--max-archive-mib', type=int,
                        help='reject an oversized archive before atomic publication')
    parser.add_argument('--provenance', type=json.loads, help='JSON provenance object')
    parser.add_argument('--preview', type=Path, help='optional MP4 destination')
    parser.add_argument('--ffmpeg', help='optional ffmpeg executable path')
    args = parser.parse_args(argv)
    if args.preview and args.preview.resolve() == args.destination.resolve():
        parser.error('preview and movie destinations must differ')
    receipt = assemble_movie(args.frame_dir, args.destination, args.width, args.height,
                             args.fps, args.source_seconds, args.overlap_seconds,
                             args.provenance, jpeg_quality=args.jpeg_quality,
                             max_archive_bytes=None if args.max_archive_mib is None
                             else args.max_archive_mib * 1024 * 1024)
    if args.preview:
        receipt['preview'] = encode_preview(args.destination, args.preview, args.ffmpeg)
    print(json.dumps(receipt, sort_keys=True, allow_nan=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
