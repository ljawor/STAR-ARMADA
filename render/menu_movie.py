"""Read-only, lazy pygame playback of a baked presentation (never a simulation)."""
from collections import OrderedDict
import io
import json
import math
import pygame
from pathlib import Path
import zipfile


class MenuMovie:
    """ASSET_ROOT-relative movie. Unavailable movies return None for caller fallback."""

    def __init__(self, asset_root, relative_path='menu/battle.zip'):
        self._zip = None
        self.metadata = {}
        self.available = False
        self.error = None
        self._cache = OrderedDict()
        try:
            self._zip = zipfile.ZipFile(Path(asset_root) / relative_path)
            info = self._zip.getinfo('metadata.json')
            if info.file_size > 16384:
                raise ValueError('oversized metadata')
            if info.compress_type != zipfile.ZIP_STORED:
                raise ValueError('metadata must be ZIP_STORED')
            meta = json.loads(self._zip.read(info))
            if not isinstance(meta, dict) or type(meta.get('version')) is not int or meta['version'] != 1:
                raise ValueError('unsupported movie version')
            for key, minimum, maximum in [('width', 1, 4096), ('height', 1, 2160),
                                          ('frame_count', 1, 3600)]:
                value = meta.get(key)
                if type(value) is not int or not minimum <= value <= maximum:
                    raise ValueError('invalid ' + key)
            fps = meta.get('fps')
            if type(fps) not in (int, float) or not 0 < fps <= 60:
                raise ValueError('invalid fps')
            still = meta.get('still_frame')
            if type(still) is not int or not 0 <= still < meta['frame_count']:
                raise ValueError('invalid still frame')
            if meta.get('loop') != 'baked-crossfade':
                raise ValueError('movie must contain a baked seamless transition')
            self.metadata = meta
            self.available = True
        except (OSError, ValueError, KeyError, zipfile.BadZipFile, RuntimeError) as exc:
            self.error = str(exc)
            self.close()

    def get_frame(self, elapsed, size, reduced_motion=False):
        """Return a borrowed Surface (do not mutate), or None for static fallback.

        Elapsed is seconds since menu entry. Only the requested frame is decoded;
        frames skipped by a slow display never create catch-up work. Two scaled
        frames are retained; resizing discards that cache. Transition is baked.
        """
        if not self.available:
            return None
        try:
            size = tuple(size)
            if len(size) != 2 or any(type(v) is not int or not 0 < v <= 4096 for v in size):
                return None
            t = float(elapsed)
            if not math.isfinite(t) or t < 0:
                t = 0.
            meta = self.metadata
            # Reduce before multiply: finite huge elapsed must not overflow.
            index = meta['still_frame'] if reduced_motion else int(
                (t % (meta['frame_count'] / meta['fps'])) * meta['fps'] + 1e-9) % meta['frame_count']
            if getattr(self, '_size', None) != size:
                self._cache.clear()
                self._size = size
            if index in self._cache:
                self._cache.move_to_end(index)
                return self._cache[index]
            # Evict before decoding so memory never grows with movie duration.
            while len(self._cache) >= 2:
                self._cache.popitem(last=False)
            info = self._zip.getinfo(f'frames/{index:05d}.jpg')
            if info.file_size > 4 * 1024 * 1024 or info.compress_type != zipfile.ZIP_STORED:
                raise ValueError('frame must be bounded ZIP_STORED JPEG')
            payload = self._zip.read(info)
            # Check SOF before SDL allocates decoded pixels; a corrupt JPEG may
            # claim giant dimensions despite small metadata/encoded byte count.
            self._check_jpeg_dimensions(payload)
            with io.BytesIO(payload) as stream:
                frame = pygame.image.load(stream, 'frame.jpg')
            if frame.get_size() != (meta['width'], meta['height']):
                raise ValueError('frame dimensions disagree with metadata')
            if frame.get_size() != size:
                frame = pygame.transform.smoothscale(frame, size)
            self._cache[index] = frame
            return frame
        except (OSError, ValueError, TypeError, KeyError, zipfile.BadZipFile,
                RuntimeError, pygame.error) as exc:
            self.error = str(exc)
            self.close()
            return None

    def _check_jpeg_dimensions(self, data):
        if not data.startswith(b'\xff\xd8'):
            raise ValueError('not a JPEG')
        pos = 2
        while pos + 3 < len(data):
            if data[pos] != 255:
                raise ValueError('invalid JPEG marker')
            while pos < len(data) and data[pos] == 255:
                pos += 1
            if pos >= len(data):
                break
            marker = data[pos]
            pos += 1
            if marker == 0xDA or marker == 0xD9:
                break  # Scan data/end before any size-bearing SOF is invalid.
            if marker == 0x01 or 0xD0 <= marker <= 0xD8:
                continue
            if pos + 2 > len(data):
                break
            length = int.from_bytes(data[pos:pos+2], 'big')
            if length < 2 or pos + length > len(data):
                raise ValueError('truncated JPEG header')
            if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7,
                          0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
                if length < 8:
                    raise ValueError('invalid JPEG SOF')
                height = int.from_bytes(data[pos+3:pos+5], 'big')
                width = int.from_bytes(data[pos+5:pos+7], 'big')
                if (width, height) != (self.metadata['width'], self.metadata['height']):
                    raise ValueError('JPEG dimensions disagree with metadata')
                return
            pos += length
        raise ValueError('missing JPEG dimensions')

    def cache_info(self):
        return {'frames': len(self._cache),
                'bytes': sum(s.get_pitch() * s.get_height() for s in self._cache.values())}

    def close(self):
        if self._zip is not None:
            self._zip.close()
            self._zip = None
        self._cache.clear()
        self.available = False

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
