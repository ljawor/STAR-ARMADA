"""Native C++ briefing card for the campaign mission start/outcome screen.

The campaign intro used to be composed in Python as two full-width raster strips in
`hud.ring`. The window already draws the HUD's text from the bundled Noto atlas and its
shapes as bgfx triangles, so this module authors the briefing as a complete display
snapshot instead: `render_bridge.vector_hud.Capture` ops, measured with the very TTF the
native side rasterizes, and never a `font.render`, `pygame.draw` or `blit` call.

Design constraints behind the numbers below:

* the card is a *card*, not a banner: bounded width (<= 900 logical px) and a content
  height that is capped by `MAX_ROWS`, centred horizontally and in the space below the
  native resource strip;
* hierarchy is size, weight by colour and a single accent rule - no invented art;
* every body line is wrapped with the body face and measured, so a page's glyph boxes
  always fit the card. Unbroken tokens wrap per character and long briefings page; no
  objective text is ever truncated (only an over-long *title* is ellipsized, like the
  legacy strip did);
* the layout is a pure function of the logical viewport, so a 640x480 and a 2560x1440
  window get the same composition at different sizes.

`plan()` measures, `page_layout()` slices the page out of that measurement and
`emit()` authors the ops; `build()` is the convenience pair. Nothing here mutates the
mission, the camera or the simulation, and the measured layout is reusable frame after
frame because the briefing screen is static.
"""
from __future__ import annotations

import math
import os

import pygame

from render import i18n

#: The native HUD draws Noto at 1.5x the pygame nominal size it replaced
#: (`render.hud.NATIVE_TEXT_EM_SCALE`); authoring sizes in nominal units keeps the
#: briefing's hierarchy comparable with the rest of the migrated HUD.
EM_SCALE = 1.5
#: Native upper-HUD resource strip the card must stay below.
STRIP_HEIGHT = 44
CARD_MAX_WIDTH = 900
CARD_MIN_WIDTH = 480
MAX_ROWS = 8
SECONDS_PER_PAGE = 5.0

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FONT_PATH = os.path.join(_ROOT, 'assets', 'fonts', 'NotoSans-Regular.ttf')

#: Calm, low-contrast presentation: the world stays readable behind the briefing.
DIM = (3, 7, 14, 158)
CARD = (8, 14, 26, 228)
BORDER = (84, 126, 176, 110)
EYEBROW = (126, 172, 214, 255)
TITLE = (238, 244, 252, 255)
BODY = (206, 216, 230, 255)
OBJECTIVE = (198, 214, 232, 255)
MUTED = (128, 148, 174, 255)
PAGE = (172, 200, 228, 255)
ACCENT = (104, 168, 232, 255)
TRACK = (32, 46, 66, 255)
SUCCESS = (128, 206, 158, 255)
FAILURE = (222, 118, 104, 255)

#: Codepoints `render_bridge.vector_hud.encode` refuses and the native decoder cannot
#: draw. Replaced (not dropped) so a modded briefing still publishes as visible text.
_FORBIDDEN = dict.fromkeys(
    [*range(32), *range(127, 160), 0x2028, 0x2029,
     *range(0x202a, 0x202f), *range(0x2066, 0x206a), *range(0xd800, 0xe000)], ' ')

_FACES: dict[int, pygame.font.Font] = {}
#: `(size, surface)` for the Sink's clip rect only. Reused instead of allocating a
#: full-screen surface every frame; nothing is ever drawn on it.
_CLIP: list = [None, None]


def _clean(text) -> str:
    """One line of displayable text: control characters become spaces, never NULs."""
    return str(text).translate(_FORBIDDEN)


def _face(pixels: int) -> pygame.font.Font:
    """The bundled face the C++ atlas rasterizes, at `pixels` em, for measurement only."""
    pixels = max(6, int(pixels))
    face = _FACES.get(pixels)
    if face is None:
        pygame.font.init()  # idempotent; the model must measure without a caller's init
        try:
            face = pygame.font.Font(FONT_PATH, pixels)
        except (OSError, pygame.error):
            # Same fallback family the legacy strip used; metrics only.
            face = pygame.font.SysFont('menlo,consolas,monaco',
                                       max(6, round(pixels / EM_SCALE)))
        _FACES[pixels] = face
    return face


def _clip_surface(width: int, height: int) -> pygame.Surface:
    """A whole-screen clip carrier for `Sink`; never painted, reused across frames."""
    if _CLIP[0] != (width, height):
        _CLIP[0], _CLIP[1] = (width, height), pygame.Surface((width, height), pygame.SRCALPHA)
        _CLIP[1].set_clip((0, 0, width, height))
    return _CLIP[1]


def _wrap(face: pygame.font.Font, text, width: float) -> list[str]:
    """Wrap to `width`, splitting unbroken tokens per character; never drop a glyph."""
    width = max(1., float(width))
    lines: list[str] = []
    for paragraph in _clean(text).splitlines():
        line = ''
        for char in paragraph:
            if line and face.size(line + char)[0] > width:
                split = line.rfind(' ')
                if split > 0:
                    lines.append(line[:split])
                    line = line[split + 1:] + char
                else:
                    lines.append(line)
                    line = char
            else:
                line += char
        if line:
            lines.append(line)
    return lines


def _ellipsize(face: pygame.font.Font, text: str, width: float) -> str:
    """`text` cut to fit `width` with a visible ellipsis; the only truncation allowed."""
    while text and face.size(text + '…')[0] > width:
        text = text[:-1]
    return text + '…'


def _title_lines(face: pygame.font.Font, title, width: float) -> list[str]:
    """Two title rows at most; the rest becomes an ellipsis rather than a fifth row."""
    wrapped = _wrap(face, title, width)
    if len(wrapped) <= 2:
        return wrapped or [_clean(title) or i18n.t('Mission')]
    return [wrapped[0], _ellipsize(face, wrapped[1], width)]


def _body_lines(face: pygame.font.Font, briefing, objectives, width: float,
                indent: float) -> list[dict]:
    """Briefing paragraphs first, then each objective; `indent` is its marker gutter."""
    lines: list[dict] = []
    for line in _wrap(face, briefing, width):
        lines.append({'text': line, 'kind': 'briefing'})
    objective_lines = []
    for objective in objectives:
        wrapped = _wrap(face, objective, width - indent)
        for index, line in enumerate(wrapped):
            objective_lines.append({'text': line, 'kind': 'objective' if index == 0 else 'objective-more'})
    if objective_lines and lines:
        lines.append({'text': '', 'kind': 'space'})
    lines.extend(objective_lines)
    return lines


def plan(width: int, height: int, *, title, briefing, objectives, outcome=None,
         elapsed: float = 0.0) -> dict:
    """Measure one page of the briefing card. Pure: no capture, no surface, no state."""
    width, height = int(width), int(height)
    if width < 64 or height < 64:
        raise ValueError('native briefing needs a viewport of at least 64x64')
    base = max(.78, min(1.5, min(width / 1280., height / 800.)))
    # Below the authored sizes a short viewport cannot hold the header, one readable row
    # and the footer; step the type down rather than letting the card outgrow its own
    # viewport, and refuse a viewport where even that does not fit.
    for factor in (1., .9, .8, .7, .6, .5):
        layout = _layout_at(base * factor, width, height, title=title, briefing=briefing,
                            objectives=objectives, outcome=outcome)
        if layout['fits']:
            return page_layout(layout, elapsed)
    raise ValueError(f'native briefing does not fit a {width}x{height} viewport')


def _layout_at(scale: float, width: int, height: int, *, title, briefing, objectives,
               outcome=None) -> dict:
    """Everything for one card at one type scale, before a page is chosen."""
    sizes = {
        'eyebrow': max(8, round(12 * scale * EM_SCALE)),
        'title': max(10, round(28 * scale * EM_SCALE)),
        'body': max(9, round(15 * scale * EM_SCALE)),
        'footer': max(8, round(11 * scale * EM_SCALE)),
    }
    eyebrow_face, title_face = _face(sizes['eyebrow']), _face(sizes['title'])
    body_face, footer_face = _face(sizes['body']), _face(sizes['footer'])
    eyebrow_h, title_lh = eyebrow_face.get_linesize(), title_face.get_linesize()
    body_lh, footer_lh = body_face.get_linesize(), footer_face.get_linesize()

    gutter = max(16, min(96, round(width * .035)))
    card_w = min(width - 2 * gutter, max(CARD_MIN_WIDTH,
                                         min(CARD_MAX_WIDTH, round(width * .62))))
    card_w = max(64, card_w)
    card_x = (width - card_w) // 2
    pad = max(12, min(40, round(card_w * .045)))
    inner_x, inner_w = card_x + pad, card_w - 2 * pad

    marker = max(5, round(sizes['body'] * .5))
    indent = marker + max(6, round(marker * .7))

    eyebrow = i18n.t(outcome) if outcome else i18n.t('CAMPAIGN / DEPLOYMENT')
    title_rows = _title_lines(title_face, title or i18n.t('Mission'), inner_w)
    if outcome is None:
        body = _body_lines(body_face, briefing, objectives, inner_w, indent)
    else:
        # The result screen replaces the briefing, exactly like the legacy compose path.
        message = i18n.t('Objectives secured. Return to fleet command.' if outcome == 'MISSION COMPLETE'
                         else 'The operation has ended. Regroup and try again.')
        body = [{'text': line, 'kind': 'briefing'}
                for line in _wrap(body_face, message, inner_w)]
    accent = SUCCESS if outcome == 'MISSION COMPLETE' else FAILURE if outcome == 'MISSION FAILED' else ACCENT

    # Vertical rhythm, authored in one place so header/body/footer cannot drift apart.
    bar = max(2, round(2 * scale))
    gap_bar = max(6, round(pad * .5))
    gap_eyebrow = max(4, round(pad * .45))
    gap_title = max(6, round(pad * .55))
    rule_h = max(2, round(scale * 2))
    gap_rule = max(6, round(pad * .5))
    gap_footer = max(8, round(pad * .7))
    footer_rule_h = max(1, round(scale))
    gap_footer_text = max(3, round(pad * .3))
    gap_progress = max(4, round(pad * .35))

    title_h = len(title_rows) * title_lh
    header_h = pad + eyebrow_h + gap_eyebrow + title_h + gap_title + rule_h + gap_rule
    footer_h = gap_footer + footer_rule_h + gap_footer_text + footer_lh + gap_progress + rule_h + pad

    avail_top = STRIP_HEIGHT + max(10, round(height * .02))
    avail_bottom = height - max(12, round(height * .03))
    avail_h = max(1, avail_bottom - avail_top)
    capacity = max(1, min(MAX_ROWS, int((avail_h - header_h - footer_h) // body_lh)))
    pages = max(1, math.ceil(len(body) / capacity)) if body else 1
    shown = capacity if pages > 1 else min(len(body), capacity)
    body_h = shown * body_lh
    card_h = min(avail_h, header_h + body_h + footer_h)
    card_y = avail_top + max(0, (avail_h - card_h) // 2)

    body_top = card_y + header_h
    body_bottom = body_top + body_h
    card_bottom = card_y + card_h
    progress_y = card_bottom - pad - rule_h
    footer_text_y = progress_y - gap_progress - footer_lh
    footer_rule_y = footer_text_y - gap_footer_text - footer_rule_h

    layout = {
        'width': width, 'height': height, 'scale': scale, 'sizes': sizes,
        'card': pygame.Rect(card_x, card_y, card_w, card_h),
        'inner_x': inner_x, 'inner_w': inner_w, 'pad': pad,
        'eyebrow': eyebrow, 'eyebrow_x': inner_x + bar + gap_bar, 'eyebrow_y': card_y + pad,
        'eyebrow_h': eyebrow_h, 'bar': bar, 'accent': accent,
        'title_x': inner_x,
        'title_y': card_y + pad + eyebrow_h + gap_eyebrow,
        'title_lh': title_lh, 'rule_y': card_y + header_h - gap_rule - rule_h,
        'rule_h': rule_h,
        'body_top': body_top, 'body_bottom': body_bottom, 'body_lh': body_lh,
        'body_width': inner_w, 'indent': indent, 'marker': marker,
        'title_lines': title_rows,
        'footer_text_y': footer_text_y, 'footer_rule_y': footer_rule_y,
        'progress_y': progress_y, 'progress_h': rule_h,
        'pages': pages, 'capacity': capacity, 'shown': shown,
        'lines': body,
        'skip': i18n.t('Enter / Space / Esc / click to skip'),
        'eyebrow_color': (SUCCESS if outcome == 'MISSION COMPLETE'
                          else FAILURE if outcome == 'MISSION FAILED' else EYEBROW),
        'fits': header_h + footer_h + body_lh <= avail_h,
    }
    return layout


def page_layout(layout: dict, elapsed: float) -> dict:
    """`layout` with the page `elapsed` falls on; the measured body is sliced, never cut."""
    page = max(0, min(layout['pages'] - 1,
                      int(max(0., float(elapsed or 0.)) / SECONDS_PER_PAGE)))
    start = page * layout['capacity']
    view = dict(layout)
    view.update(page=page, page_label=f'{page + 1}/{layout["pages"]}',
                page_lines=layout['lines'][start:start + layout['shown']])
    return view


def _rect(sink, surface, color, rect, *, stroke: float = 0, radius: float = 0) -> None:
    kwargs = {'border_radius': radius} if radius else {}
    sink.geometry('rect', surface, color, (pygame.Rect(rect), stroke), kwargs)


def _text(sink, surface, face, text, x, y, width, height, color, size: int) -> None:
    """Emit one measured line; `width` is the measured ink plus a hair of slack."""
    measured = min(width, face.size(text)[0] + 2)
    sink.text(surface, x, y, text, color, size, max(1, measured), max(1, height))


def build(width, height, *, title, briefing, objectives, outcome=None, elapsed=0.0):
    """`(validated snapshot, layout)`; ops are emitted in reading order, dim first."""
    return emit(plan(width, height, title=title, briefing=briefing, objectives=objectives,
                     outcome=outcome, elapsed=elapsed))


def emit(layout: dict):
    """`(validated snapshot, layout)` for an already measured page. No measurement, no state."""
    from render_bridge.vector_hud import Capture, Sink, encode

    width, height = layout['width'], layout['height']
    capture = Capture(width, height)
    # `Sink` only reads the carrier's clip rect; the whole screen is the scope, so the
    # model needs no affine mapping and every op carries the same full-screen clip.
    surface = _clip_surface(width, height)
    sink = Sink(capture, (0, 0, width, height), source_x=0, target_x=0,
                source_y=0, target_y=0)
    face_eyebrow = _face(layout['sizes']['eyebrow'])
    face_title = _face(layout['sizes']['title'])
    face_body = _face(layout['sizes']['body'])
    face_footer = _face(layout['sizes']['footer'])
    card = layout['card']

    _rect(sink, surface, DIM, (0, 0, width, height))
    _rect(sink, surface, CARD, card, radius=max(6, round(card.width * .012)))
    _rect(sink, surface, BORDER, card, stroke=1, radius=max(6, round(card.width * .012)))

    # Chapter marker + small eyebrow: context without competing with the mission name.
    _rect(sink, surface, layout['accent'],
          (layout['inner_x'], layout['eyebrow_y'] + max(1, layout['bar'] // 2),
           layout['bar'], max(4, layout['eyebrow_h'] - layout['bar'])))
    _text(sink, surface, face_eyebrow, layout['eyebrow'], layout['eyebrow_x'],
          layout['eyebrow_y'], layout['inner_w'] - (layout['eyebrow_x'] - layout['inner_x']),
          layout['eyebrow_h'], layout['eyebrow_color'], layout['sizes']['eyebrow'])

    for index, line in enumerate(layout['title_lines']):
        _text(sink, surface, face_title, line, layout['title_x'],
              layout['title_y'] + index * layout['title_lh'], layout['inner_w'],
              layout['title_lh'], TITLE, layout['sizes']['title'])

    # Accent rule: one bright short bar over a dim full-width hairline.
    _rect(sink, surface, TRACK, (layout['inner_x'], layout['rule_y'], layout['inner_w'], 1))
    _rect(sink, surface, layout['accent'],
          (layout['inner_x'], layout['rule_y'], min(layout['inner_w'], max(24, round(72 * layout['scale']))),
           layout['rule_h']))

    for index, line in enumerate(layout['page_lines']):
        y = layout['body_top'] + index * layout['body_lh']
        if line['kind'] == 'space':
            continue
        x = layout['inner_x']
        if line['kind'] == 'objective':
            size = layout['marker']
            # Centre the marker on the capitals, not on the font's full line box: the
            # native decoder anchors text at its ink top.
            cap = max(size, round(layout['sizes']['body'] * .72))
            top = y + max(0, (cap - size) // 2)
            x += layout['indent']
            sink.geometry('polygon', surface, layout['accent'], ([
                (layout['inner_x'] + 1, top), (layout['inner_x'] + 1, top + size),
                (layout['inner_x'] + 1 + size * .8, top + size / 2)], 0), {})
        elif line['kind'] == 'objective-more':
            x += layout['indent']
        _text(sink, surface, face_body, line['text'], x, y,
              layout['inner_w'] - (x - layout['inner_x']), layout['body_lh'],
              OBJECTIVE if line['kind'] != 'briefing' else BODY, layout['sizes']['body'])

    _rect(sink, surface, TRACK,
          (layout['inner_x'], layout['footer_rule_y'], layout['inner_w'], 1))
    _text(sink, surface, face_footer, layout['skip'], layout['inner_x'],
          layout['footer_text_y'], layout['inner_w'], layout['body_lh'], MUTED,
          layout['sizes']['footer'])
    page_label = layout['page_label']
    label_w = min(layout['inner_w'], face_footer.size(page_label)[0] + 2)
    _text(sink, surface, face_footer, page_label,
          layout['inner_x'] + layout['inner_w'] - label_w, layout['footer_text_y'],
          label_w, layout['body_lh'], PAGE, layout['sizes']['footer'])

    # Page progress: the only motion-free cue that the briefing continues. A single-page
    # briefing keeps the dim track only, so the accent stays reserved for "more follows".
    _rect(sink, surface, TRACK, (layout['inner_x'], layout['progress_y'],
                                 layout['inner_w'], layout['progress_h']))
    if layout['pages'] > 1:
        filled = max(1, round(layout['inner_w'] * (layout['page'] + 1) / layout['pages']))
        _rect(sink, surface, layout['accent'], (layout['inner_x'], layout['progress_y'],
                                                min(filled, layout['inner_w']), layout['progress_h']))

    model = capture.snapshot(True)
    encode(model)  # refuse a snapshot the native decoder would reject, here and now
    return model, layout
