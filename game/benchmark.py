"""Player-runnable fixed-scene benchmark. No wall clock enters the simulation.

Use main.py --benchmark --help (also available in the frozen executable).
Full mode uses real SDL/OpenGL, not the dummy driver. Its glFinish boundaries
measure CPU + driver + completed GPU work, not pure GPU timer-query durations.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import platform
from pathlib import Path
import statistics
import sys
import tempfile
import time

TICK_DT = 1 / 30
SCHEMA_VERSION = 1


def make_scene(units):
    """Factory-built combat; remote command stations prevent no-op victory ticks."""
    from game.core.manager import GameManager
    from game.core.state import PlayerState
    from game.core.vectors import Vec3
    gm = GameManager()
    st = gm.state
    st.seed = 12345
    st.players = {0: PlayerState(0, team=0), 1: PlayerState(1, team=1)}
    st.map_info.nebulas = []
    for i in range(units):
        owner, index = i % 2, i // 2
        e = gm.factory.spawn_ship('imperial_corvette', owner,
            Vec3(-300 if owner == 0 else 300, 0,
                 (index % 20 - 10) * 65 + (index // 20) * 7),
            yaw=math.pi / 2 if owner == 0 else -math.pi / 2)
        e.order_type = 'hold'
    for owner in (0, 1):
        station = gm.factory.spawn_station('command_station', owner,
            Vec3(-10000 if owner == 0 else 10000, 0, 0))
        station.sensor_range = 0
    st.grid.rebuild(st.entities)
    gm.visibility.update()
    return gm


def state_hash(st):
    # Full precise dictionary, including runtime; not the narrower replay hash.
    data = json.dumps(st.to_dict(precise=True), sort_keys=True,
                      separators=(',', ':'), allow_nan=False).encode('utf-8')
    return hashlib.sha256(data).hexdigest()


def counts(st):
    alive = [e for e in st.entities.values() if e.alive]
    return dict(entities=len(st.entities), alive=len(alive),
                ships=sum(e.is_ship for e in alive),
                stations=sum(e.is_station for e in alive),
                projectiles=len(st.projectiles), effects=len(st.effects))


def summarize(samples):
    """Nearest-rank p95/p99, all durations in ms; raw samples retained for auditing."""
    if not samples:
        raise ValueError('at least one timing sample is required')
    ordered = sorted(samples)
    return dict(count=len(samples), mean_ms=statistics.mean(samples),
                median_ms=statistics.median(samples),
                p95_ms=ordered[math.ceil(.95 * len(samples)) - 1],
                p99_ms=ordered[math.ceil(.99 * len(samples)) - 1],
                max_ms=max(samples), samples_ms=samples)


def reported_swap_interval(pygame):
    """Read the linked SDL, or report unknown; GL_SWAP_CONTROL aliases RED_SIZE.

    Resolving through pygame.base works on Cocoa. Some Windows loaders do not
    expose dependency symbols through a .pyd; never substitute the request then.
    """
    import ctypes
    try:
        getter = ctypes.CDLL(pygame.base.__file__).SDL_GL_GetSwapInterval
        getter.argtypes = []
        getter.restype = ctypes.c_int
        return int(getter())
    except (OSError, AttributeError):
        return None


def reported_drawable_size(pygame):
    """Ask the current SDL GL window, not the requested/logical window size.

    The linked SDL symbols may not be exported through Windows pygame.base.
    Unknown stays null; never label a requested size as observed pixels.
    """
    import ctypes
    try:
        library = ctypes.CDLL(pygame.base.__file__)
        current = library.SDL_GL_GetCurrentWindow
        current.argtypes, current.restype = [], ctypes.c_void_p
        window = current()
        if not window:
            return None
        getter = library.SDL_GL_GetDrawableSize
        getter.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int)]
        getter.restype = None
        width, height = ctypes.c_int(), ctypes.c_int()
        getter(window, ctypes.byref(width), ctypes.byref(height))
        return [width.value, height.value] if width.value > 0 and height.value > 0 else None
    except (OSError, AttributeError, TypeError):
        return None


def run_benchmark(*, units=200, frames=60, warmup=10, mode='full',
                  width=1280, height=800, vsync=0, msaa=4, screenshot=None,
                  fixture='corvette-combat-v1', lan_checksum=False):
    for name, value, low, high in (('units', units, 2, 2000),
            ('frames', frames, 1, 3600), ('warmup', warmup, 0, 300),
            ('width', width, 800, 7680), ('height', height, 600, 4320)):
        if type(value) is not int or not low <= value <= high:
            raise ValueError(f'{name} must be an integer in [{low}, {high}]')
    if mode not in ('sim', 'full') or vsync not in (0, 1) or msaa not in (0, 2, 4, 8):
        raise ValueError('invalid mode, vsync or msaa')
    if mode == 'sim' and screenshot is not None:
        raise ValueError('screenshots require full mode')
    from game.graphics_benchmark import FIXTURES, make_fixture, semantic_inventory, visibility_sample, Activity
    if fixture not in ('corvette-combat-v1',) + FIXTURES:
        raise ValueError(f'unknown fixture: {fixture}')
    if type(lan_checksum) is not bool:
        raise ValueError('lan_checksum must be a boolean')
    if fixture != 'corvette-combat-v1':
        if units != 200:
            raise ValueError('units is only configurable for corvette-combat-v1; representative inventory is fixed')
        if warmup + frames > 300:
            raise ValueError('representative fixtures require warmup + frames <= 300 (10 simulated seconds)')
    if mode == 'full':
        for key in ('STAR_ARMADA_SKIP', 'STAR_ARMADA_NO_CULL'):
            if os.environ.get(key):
                raise ValueError(f'{key} must be unset or empty for acceptance full mode')
    from game import __version__
    scene = None if fixture == 'corvette-combat-v1' else make_fixture(fixture)
    gm = make_scene(units) if scene is None else scene.manager
    st = gm.state
    initial_hash, initial_counts = state_hash(st), counts(st)
    report: dict = dict(schema_version=SCHEMA_VERSION, status='ok', version=__version__,
        environment=dict(platform=platform.platform(), machine=platform.machine(),
                         python=platform.python_version(), frozen=bool(getattr(sys, 'frozen', False))),
        fixture=fixture, seed=st.seed, tick_dt=TICK_DT,
        mode=mode, units=units if scene is None else 600, frames=frames, warmup_frames=warmup,
        initial_state_sha256=initial_hash, counts_initial=initial_counts,
        timing_semantics='perf_counter_ns; fixed 1/30 simulation tick; no pacing; '
            'full mode glFinish after camera/world/HUD; world includes Renderer camera.apply; '
            'audio/input/menu/cinematic excluded; warmup excluded from samples')
    samples = {'sim': []}
    activity = None
    if scene is not None:
        report.update(scene=scene.metadata(), inventory_initial=semantic_inventory(st),
                      inventory_per_sample=[], visibility_per_sample=[], activity_per_sample=[])
        report['diagnostics_semantics'] = ('Read-only event callbacks included in sim timing; inventory/visibility/driver sampling '
            'outside stage/frame samples; frame is not end-to-end live gameplay pacing. AI/audio/input/network excluded.')
        activity = Activity(st)
    if lan_checksum:
        from game.net.lan import precise_checksum
        samples['lan_precise_checksum'] = []
        report['lan_checksum_semantics'] = ('Separate precise_checksum(manager) cost after simulation/render/presentation; '
            'excluded from sim and frame stages; no sockets/barrier/input delay; not real-network pacing')
    pygame = GL = camera = renderer = hud = None
    primary_error = None
    report['sample_exclusions'] = {}
    try:
        if mode == 'full':
            import pygame
            from OpenGL import GL
            from render.camera import Camera
            from render.renderer import Renderer
            from render.hud import HUD
            # No pygame.init(): audio is intentionally excluded from this probe.
            pygame.display.init()
            pygame.display.set_caption('STAR ARMADA — deterministic performance report')
            pygame.display.gl_set_attribute(pygame.GL_MULTISAMPLEBUFFERS, int(msaa > 0))
            pygame.display.gl_set_attribute(pygame.GL_MULTISAMPLESAMPLES, msaa)
            pygame.display.set_mode((width, height), pygame.OPENGL | pygame.DOUBLEBUF, vsync=vsync)
            requested_resolution = [width, height]
            drawable = reported_drawable_size(pygame)
            if scene is not None and drawable is not None:
                width, height = drawable
            GL.glViewport(0, 0, width, height)
            pygame.event.pump()
            camera = Camera(width, height)
            camera.distance = 4500
            if scene is not None:
                scene.camera.apply(camera)
            renderer = Renderer(st, camera)
            hud = HUD(width, height, st)
            samples.update({name: [] for name in ('camera', 'world', 'hud', 'swap', 'frame')})
            def gl_string(name):
                raw = GL.glGetString(name)
                return raw.decode('utf-8', errors='replace') if raw else None
            actual_vsync = reported_swap_interval(pygame)
            report['graphics'] = dict(resolution=requested_resolution, drawable_size=drawable,
                render_size=[width, height],
                drawable_note='Actual SDL_GL_GetDrawableSize, null when unavailable; render_size is the viewport/capture extent used.',
                viewport=[int(x) for x in GL.glGetIntegerv(GL.GL_VIEWPORT)],
                requested_vsync=vsync, reported_swap_interval=actual_vsync,
                vsync_note='swap interval may be unavailable or overridden by driver; inspect swap samples',
                requested_msaa=msaa, actual_msaa=int(GL.glGetIntegerv(GL.GL_SAMPLES)),
                sdl_driver=pygame.display.get_driver(), pygame=pygame.version.ver,
                sdl=list(pygame.get_sdl_version()), vendor=gl_string(GL.GL_VENDOR),
                gpu=gl_string(GL.GL_RENDERER), driver=gl_string(GL.GL_VERSION),
                shader_enabled=renderer.materials.available)
            if scene is not None:
                report['graphics']['window_size'] = list(pygame.display.get_window_size())
                report['graphics_per_sample'] = []
            report['sample_exclusions'] = dict(swap=[frames - 1], frame=[frames - 1])
            report['capture_timing_note'] = ('Final back-buffer capture preserves the frame hash; '
                'capture-adjacent swap and frame samples excluded (zero-based measured indices). '
                'One-frame runs have no swap/frame timing evidence.')
            GL.glFinish()
        selection = (set(scene.selection) if scene is not None else
                     {next(e.id for e in st.entities.values() if e.is_ship and e.owner == 0)})
        count_history = []
        for frame in range(warmup + frames):
            if activity is not None:
                activity.frame.clear()
            if pygame is not None:
                if any(ev.type == pygame.QUIT for ev in pygame.event.get()):
                    raise RuntimeError('benchmark cancelled; no complete acceptance result')
            frame_start = time.perf_counter_ns()
            start = frame_start
            gm.step(TICK_DT)
            durations = {'sim': (time.perf_counter_ns() - start) / 1e6}
            if st.tick != frame + 1 or st.game_over:
                raise RuntimeError('fixture stopped early; simulation samples would be vacuous')
            if renderer is not None:
                start = time.perf_counter_ns()
                camera.apply(width, height)
                GL.glFinish()
                durations['camera'] = (time.perf_counter_ns() - start) / 1e6
                start = time.perf_counter_ns()
                renderer.draw(TICK_DT, selection)
                GL.glFinish()
                durations['world'] = (time.perf_counter_ns() - start) / 1e6
                start = time.perf_counter_ns()
                hud.set_floating_texts(renderer.floating_texts_screen())
                hud.render(selection, None, 0, False)
                hud.draw_gl()
                GL.glFinish()
                durations['hud'] = (time.perf_counter_ns() - start) / 1e6
                if frame == warmup + frames - 1:
                    # Preserve back-buffer evidence, but exclude the adjacent
                    # presentation: readback can change the vsync wait.
                    capture_start = time.perf_counter_ns()
                    pixels = bytes(GL.glReadPixels(0, 0, width, height, GL.GL_RGB, GL.GL_UNSIGNED_BYTE))
                    report['framebuffer_sha256'] = hashlib.sha256(pixels).hexdigest()
                    report['framebuffer_nonuniform'] = pixels != pixels[:3] * (len(pixels) // 3)
                    report['framebuffer_evidence_note'] = ('RGB spatial nonuniformity only; '
                        'not world/combat acceptance (HUD/background can be nonuniform).')
                    if screenshot is not None:
                        image = pygame.image.frombytes(pixels, (width, height), 'RGB')
                        pygame.image.save(pygame.transform.flip(image, False, True), str(screenshot))
                    capture_ns = time.perf_counter_ns() - capture_start
                else:
                    capture_ns = 0
                start = time.perf_counter_ns()
                pygame.display.flip()
                durations['swap'] = (time.perf_counter_ns() - start) / 1e6
                durations['frame'] = (time.perf_counter_ns() - frame_start - capture_ns) / 1e6
            if lan_checksum:
                start = time.perf_counter_ns()
                checksum = precise_checksum(gm)
                durations['lan_precise_checksum'] = (time.perf_counter_ns() - start) / 1e6
                report['lan_precise_checksum_final'] = checksum
            if frame >= warmup:
                for name, value in durations.items():
                    if frame - warmup in report['sample_exclusions'].get(name, []):
                        continue
                    samples[name].append(value)
                count_history.append(counts(st))
                if scene is not None:
                    report['inventory_per_sample'].append(semantic_inventory(st))
                    report['visibility_per_sample'].append(visibility_sample(st, camera))
                    report['activity_per_sample'].append(activity.snapshot(activity.frame))
                    if GL is not None:
                        report['graphics_per_sample'].append(dict(
                            drawable_size=reported_drawable_size(pygame),
                            viewport=[int(x) for x in GL.glGetIntegerv(GL.GL_VIEWPORT)],
                            camera_target=list(camera.target), camera_eye=list(camera.eye_position()),
                            camera_distance=camera.distance, camera_yaw=camera.yaw, camera_pitch=camera.pitch,
                            sdl_driver=report['graphics']['sdl_driver'], gpu=report['graphics']['gpu'],
                            driver=report['graphics']['driver']))
        report.update(stages={name: summarize(values) if values else dict(
                          count=0, mean_ms=None, median_ms=None, p95_ms=None, p99_ms=None,
                          max_ms=None, samples_ms=[]) for name, values in samples.items()},
                      state_sha256=state_hash(st), counts_final=counts(st),
                      counts_per_sample=count_history, executed_ticks=st.tick,
                      game_over=st.game_over)
        if scene is not None:
            report.update(inventory_final=semantic_inventory(st), activity_total=activity.snapshot(activity.total))
        return report
    except BaseException as exc:
        primary_error = exc
        raise
    finally:
        # Attempt both GL owners before destroying their context, even if one
        # fails. Shutdown must not replace the original measurement failure.
        cleanup_errors = []
        for name, owner in (('hud', hud), ('renderer', renderer), ('pygame', pygame)):
            if owner is not None:
                try:
                    owner.quit() if name == 'pygame' else owner.close()
                except BaseException as exc:
                    cleanup_errors.append(dict(owner=name, error=f'{type(exc).__name__}: {exc}'))
        if cleanup_errors:
            error = primary_error if primary_error is not None else RuntimeError('benchmark cleanup failed')
            setattr(error, 'cleanup_errors', cleanup_errors)
            error.add_note('Cleanup diagnostics: ' + json.dumps(cleanup_errors))
            if primary_error is None:
                raise error


def default_output_path():
    """Stable per-user report location, including console-less frozen builds."""
    if sys.platform == 'win32':
        root = Path(os.environ.get('LOCALAPPDATA') or Path.home() / 'AppData/Local')
    elif sys.platform == 'darwin':
        root = Path.home() / 'Library/Application Support'
    else:
        root = Path(os.environ.get('XDG_DATA_HOME') or Path.home() / '.local/share')
    return root / 'STAR ARMADA/benchmark.json'


class _ReportParser(argparse.ArgumentParser):
    def error(self, message):
        raise ValueError(message)


def _validate_output(path, default):
    if path == default:
        path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        # Also catch read-only files when atomic replacement would otherwise
        # bypass their permissions. No truncation of an earlier report here.
        if not path.is_file() or not os.access(path, os.W_OK):
            raise OSError(f'output is not a writable file: {path}')
        with path.open('r+', encoding='utf-8'):
            pass
    # Probe the parent without creating/truncating the destination.
    with tempfile.TemporaryFile(dir=path.parent):
        pass


def _write_report(path, result):
    data = json.dumps(result, indent=2, allow_nan=False) + '\n'
    # Stage in the report's directory for atomic replacement. This is output
    # I/O, not measurement; incomplete JSON must never look like a valid run.
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', newline='\n',
                                         dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _announce(message, *, error=False):
    stream = sys.stderr if error else sys.stdout
    if stream is not None:
        try:
            print(message, file=stream)
        except (OSError, ValueError):
            pass  # JSON is the interface; a closed console is not fatal.


def cli(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    default = default_output_path()
    parser = _ReportParser(description=__doc__, add_help=False, allow_abbrev=False,
        epilog=f'Help and errors are also saved as JSON. Default report: {default}')
    parser.add_argument('-h', '--help', action='store_true', help='write JSON help without measuring')
    parser.add_argument('--mode', choices=('full', 'sim'), default='full')
    from game.graphics_benchmark import FIXTURES
    parser.add_argument('--fixture', choices=('corvette-combat-v1',) + FIXTURES, default='corvette-combat-v1',
                        help='versioned starting state; four-player fixtures fix inventory and require warmup + frames <= 300')
    parser.add_argument('--lan-checksum', action='store_true', help='time LAN precise_checksum separately; no real-network pacing')
    parser.add_argument('--units', type=int, default=200)
    parser.add_argument('--frames', type=int, default=60)
    parser.add_argument('--warmup', type=int, default=10)
    parser.add_argument('--width', type=int, default=1280)
    parser.add_argument('--height', type=int, default=800)
    parser.add_argument('--vsync', type=int, choices=(0, 1), default=0)
    parser.add_argument('--msaa', type=int, choices=(0, 2, 4, 8), default=4)
    parser.add_argument('--output', type=Path, default=default,
                        help=f'JSON report destination (default: {default})')
    parser.add_argument('--screenshot', type=Path)
    # Recover an explicit destination even when another argument cannot parse.
    output = default
    for index, token in enumerate(argv):
        if token == '--':
            break
        if token.startswith('--output=') and token[len('--output='):]:
            output = Path(token[len('--output='):])
        elif token == '--output' and index + 1 < len(argv) and not argv[index + 1].startswith('-'):
            output = Path(argv[index + 1])
    try:
        args = parser.parse_args(argv)
        output = args.output
        try:
            _validate_output(output, default)
        except OSError as exc:
            raise OSError(f'output validation failed for {output}: {exc}') from exc
        if args.help:
            result = dict(schema_version=SCHEMA_VERSION, status='help',
                          help=parser.format_help(), default_output=str(default))
        else:
            if args.fixture != 'corvette-combat-v1' and any(token == '--units' or token.startswith('--units=') for token in argv):
                raise ValueError('--units is only valid for corvette-combat-v1')
            result = run_benchmark(**{key: value for key, value in vars(args).items()
                                      if key not in ('output', 'help')})
    except Exception as exc:
        result = dict(schema_version=SCHEMA_VERSION, status='error',
                      error=f'{type(exc).__name__}: {exc}', requested_argv=argv,
                      default_output=str(default), requested_output=str(output))
        if hasattr(exc, 'cleanup_errors'):
            result['cleanup_errors'] = exc.cleanup_errors
    try:
        _validate_output(output, default)
        _write_report(output, result)
    except Exception as exc:
        failed_output = output
        result = dict(schema_version=SCHEMA_VERSION, status='error',
            error=f'output delivery failed for {failed_output}: {type(exc).__name__}: {exc}',
            requested_output=str(failed_output), default_output=str(default),
            measurement_result=result)
        output = default
        try:
            _validate_output(output, default)
            _write_report(output, result)
        except Exception as fallback_exc:
            _announce(f'BENCHMARK_ERROR report NOT delivered: {exc}; '
                      f'default {default}: {fallback_exc}', error=True)
            return 1
    _announce(f"BENCHMARK_{result['status'].upper()} {output}")
    return 0 if result['status'] in ('ok', 'help') else 1


if __name__ == '__main__':
    raise SystemExit(cli())
