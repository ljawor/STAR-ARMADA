"""Read-only Clean classic menu presentation; gameplay actions stay in menus."""
from functools import lru_cache
import pygame

from render import i18n

INK = (229, 235, 236)
MUTED = (152, 168, 183)
ACCENT = (184, 220, 215)
BORDER = (43, 57, 69)
PANEL = (17, 28, 38)
#: Finished-work colour, kept distinct from both the seaglass accent and the
#: muted grey so a completed campaign row cannot read as merely "available".
DONE = (226, 197, 121)


@lru_cache(maxsize=32)
def font(size, bold=False):
    return pygame.font.SysFont('helvetica,arial', size, bold=bold)


def main_menu(menu):
    surface = menu._surface
    scale = min(menu.width / 800, menu.height / 600)
    cx = menu.width // 2
    title = font(round(46 * scale), True).render('STAR ARMADA', True, INK)
    surface.blit(title, title.get_rect(center=(cx, round(menu.height * .20))))
    subtitle = font(round(13 * scale)).render(
        i18n.t('FLEET COMMAND  ·  OUTER ARMADA'), True, MUTED)
    surface.blit(subtitle, subtitle.get_rect(center=(cx, round(menu.height * .27))))
    drawn = []
    width, height = round(310 * scale), round(40 * scale)
    y = round(menu.height * .35)
    mouse = pygame.mouse.get_pos()
    for i, (label, action) in enumerate((('Skirmish', 'start_skirmish'),
            ('Multiplayer / LAN', 'goto_lan'), ('Campaign', 'goto_campaign'),
            ('Saved Games', 'goto_saved_games'), ('Replays', 'goto_replays'),
            ('Settings', 'goto_settings'), ('Quit', 'exit'))):
        rect = pygame.Rect(cx - width // 2, y + i * round(48 * scale), width, height)
        menu.buttons.append(dict(rect=rect, action=action, payload=None))
        # This screen draws its own labels rather than going through the canvas, so the
        # lookup happens here — and the drawn text is recorded for the same reason the
        # canvas records its own.
        label = i18n.t(label)
        drawn.append(label)
        primary = i == 0
        pygame.draw.rect(surface, ACCENT if primary else (25, 39, 49) if rect.collidepoint(mouse) else (13, 23, 32), rect, border_radius=4)
        if not primary:
            pygame.draw.rect(surface, BORDER, rect, 1, border_radius=4)
        glyph = font(round(17 * scale), primary).render(label, True, (16, 42, 42) if primary else INK)
        surface.blit(glyph, glyph.get_rect(center=rect.center))
    notice = menu.replay_notice
    f = font(round(12 * scale))
    while notice and f.size(notice)[0] > menu.width - 40:
        notice = notice[:-2] + '…'
    if notice:
        glyph = f.render(notice, True, MUTED)
        surface.blit(glyph, glyph.get_rect(center=(cx, menu.height - 20)))
    menu.main_rendered_text = drawn

class SetupCanvas:
    """One cached logical surface, measured glyphs, and mapped hit targets."""
    def __init__(self, menu, prefix):
        self.menu, self.prefix = menu, prefix
        self.target = menu._surface
        cache = getattr(menu, '_classic_surfaces', None)
        if cache is None:
            cache = menu._classic_surfaces = {}
        if prefix not in cache:
            cache[prefix] = pygame.Surface((1120, 700))
        self.surface = cache[prefix]
        # Carry the aspect-preserving backdrop into the logical UI canvas.
        # An opaque full-canvas fill would hide the movie behind setup screens.
        scale = min(menu.width / 1120, menu.height / 700)
        size = (round(1120 * scale), round(700 * scale))
        crop = pygame.Rect((menu.width - size[0]) // 2,
                           (menu.height - size[1]) // 2, *size)
        pygame.transform.smoothscale(self.target.subsurface(crop), (1120, 700), self.surface)
        self.texts, self.bounds, self.starts = [], [], []

    def text(self, value, rect, size=16, color=INK, wrap=False):
        # Drawing edge (#93): every classic-screen label, value and note is looked up
        # here, so the whole menu surface is translated without touching a call site.
        value = i18n.t(value)
        rect = pygame.Rect(rect)
        f = font(size, size >= 24)
        lines, line = [], ''
        for word in str(value).split():
            candidate = (line + ' ' + word).strip()
            if wrap and line and f.size(candidate)[0] > rect.w:
                lines.append(line)
                line = word
            else:
                line = candidate
        lines.append(line)
        line_height = max(f.get_linesize(), f.get_height()) + 1
        limit = max(1, rect.h // line_height)
        for i, line in enumerate(lines[:limit]):
            truncated = i == limit - 1 and len(lines) > limit
            while line and f.size(line + ('…' if truncated else ''))[0] > rect.w:
                line = line[:-1]
                truncated = True
            value = line + ('…' if truncated else '')
            self.texts.append(value)
            glyph = f.render(value, True, color)
            bounds = glyph.get_rect(topleft=(rect.x, rect.y + i * line_height))
            self.surface.blit(glyph, bounds)
            self.bounds.append(bounds)

    def button(self, rect, label, action, payload=None, selected=False, swatch=None, primary=False, size=14):
        from game.core.skirmish import PLAYER_COLORS
        # Drawing edge (#93): these labels arrive already suffixed ("Blue ›", "Team 2 ›") so
        # that the row reads as click-to-cycle. The suffix is not part of any msgid, so look
        # up the name alone and put the affordance back — dropping it would silently remove
        # the only cue that the row cycles.
        suffix = ' ›' if label.endswith(' ›') else ''
        label = i18n.t(label[:-len(suffix)] if suffix else label) + suffix
        rect = pygame.Rect(rect)
        self.menu.buttons.append(dict(rect=rect, action=action, payload=payload))
        pygame.draw.rect(self.surface, ACCENT if primary else (28, 48, 53) if selected else (14, 24, 33), rect, border_radius=4)
        pygame.draw.rect(self.surface, ACCENT if selected else BORDER, rect, 1, border_radius=4)
        inset = 10
        if swatch:
            rgb = tuple(round(c * 255) for c in PLAYER_COLORS[swatch])
            pygame.draw.rect(self.surface, rgb, (rect.x + 9, rect.y + 10, 14, 14), border_radius=2)
            inset = 30
        self.text(label, (rect.x + inset, rect.y + 8, rect.w - inset - 6, rect.h - 10), size,
                  (16, 42, 42) if primary else INK)

    def panel(self, rect):
        pygame.draw.rect(self.surface, PANEL, rect, border_radius=5)
        pygame.draw.rect(self.surface, BORDER, rect, 1, border_radius=5)

    def finish(self, preview=None):
        menu = self.menu
        scale = min(menu.width / 1120, menu.height / 700)
        size = (round(1120 * scale), round(700 * scale))
        ox, oy = (menu.width - size[0]) // 2, (menu.height - size[1]) // 2
        self.target.blit(pygame.transform.smoothscale(self.surface, size), (ox, oy))
        def transform(r):
            return pygame.Rect(ox + round(r.x * scale), oy + round(r.y * scale), round(r.w * scale), round(r.h * scale))
        for b in menu.buttons:
            b['rect'] = transform(b['rect'])
        setattr(menu, self.prefix + '_rendered_text', self.texts)
        setattr(menu, self.prefix + '_text_bounds', [transform(r) for r in self.bounds])
        if preview:
            setattr(menu, self.prefix + '_preview_rect', transform(preview))
            setattr(menu, self.prefix + '_preview_starts', [(ox + round(x * scale), oy + round(y * scale)) for x, y in self.starts])


def battlefield(c, options, active_count, action):
    from game.core.skirmish import SKIRMISH_MAP_IDS, PLAYER_COLORS
    m = c.menu
    c.text('BATTLEFIELD', (32, 107, 224, 24), 14, MUTED)
    for i, mid in enumerate(SKIRMISH_MAP_IDS):
        y = 140 + i * 88
        data = m.skirmish_store.maps[mid]
        c.button((32, y, 224, 76), '', action, mid, mid == options['map_id'])
        c.text(data['name'], (44, y + 10, 200, 38), 16, wrap=True)
        c.text(f"{m.skirmish_capacity(mid)} PLAYERS / TEAMS OR FFA", (44, y + 51, 200, 20), 14, MUTED)
    data = m.skirmish_store.maps[options['map_id']]
    preview = pygame.Rect(280, 140, 548, 155)
    c.panel(preview)
    bounds = float(data['bounds'])
    def point(pos):
        return (round(preview.x + 18 + (pos[0] / bounds + .5) * (preview.w - 36)),
                round(preview.y + 18 + (pos[2] / bounds + .5) * (preview.h - 36)))
    old_clip = c.surface.get_clip()
    c.surface.set_clip(preview.inflate(-4, -4))
    for x in range(preview.x + 20, preview.right, 40):
        pygame.draw.line(c.surface, (25, 39, 49), (x, preview.y), (x, preview.bottom))
    for y in range(preview.y + 20, preview.bottom, 40):
        pygame.draw.line(c.surface, (25, 39, 49), (preview.x, y), (preview.right, y))
    for kind, color in (('nebulas', (54, 40, 86)), ('gas_giants', (105, 131, 161)),
                        ('asteroid_fields', (174, 137, 76)), ('planets', (100, 185, 160)),
                        ('jump_points', (109, 160, 223))):
        for feature in data.get(kind, []):
            radius = max(3, round(feature.get('radius', 200) / bounds * preview.h))
            pygame.draw.circle(c.surface, color, point(feature['pos']), radius,
                               1 if kind in ('gas_giants', 'jump_points') else 0)
    for i, player in enumerate(data['players']):
        pos = point(player['start'])
        c.starts.append(pos)
        color = tuple(round(v * 255) for v in PLAYER_COLORS[options['colors'][i]])
        pygame.draw.circle(c.surface, color if i < active_count else (76, 86, 102), pos, 7)
        c.text(str(i + 1), (pos[0] + 10, pos[1] - 9, 20, 20), 14)
    c.surface.set_clip(old_clip)
    c.text('PUBLIC MAP · numbered starts / gold resources / teal worlds', (280, 302, 548, 22), 14, MUTED)
    return data, preview


def skirmish_setup(menu):
    from game.core.skirmish import COLOR_NAMES
    c = SetupCanvas(menu, 'skirmish')
    o = menu.skirmish_options
    c.text('STAR ARMADA', (32, 20, 300, 30), 24)
    c.text('Deploy your fleet', (32, 65, 780, 36), 28)
    c.text('Choose a battlefield, configure your fleet, then launch.', (280, 107, 548, 24), 14, MUTED)
    data, preview = battlefield(c, o, o['ai_count'] + 1, 'skirmish_map')
    c.text('FLEET ROSTER', (280, 330, 548, 24), 16, MUTED)
    for slot in range(o['ai_count'] + 1):
        y = 364 + slot * 42
        relation = 'Ally' if o['teams'][slot] == o['teams'][0] else 'Enemy'
        c.text('You' if slot == 0 else f'AI {slot} · {relation}', (280, y + 8, 92, 24), 14)
        color = o['colors'][slot]
        c.button((376, y, 114, 34), COLOR_NAMES[color] + ' ›', 'skirmish_color', slot, swatch=color)
        c.button((498, y, 220, 34), menu.skirmish_store.factions[o['factions'][slot]].display_name + ' ›', 'skirmish_faction', slot)
        c.button((726, y, 102, 34), f"Team {o['teams'][slot] + 1} ›", 'skirmish_team', slot)
    c.panel((852, 107, 236, 423))
    c.text('Match settings', (866, 122, 208, 30), 24)
    c.text(f"AI PLAYERS   {o['ai_count']} / {menu.skirmish_capacity(o['map_id']) - 1}", (866, 169, 208, 26), 16)
    c.button((866, 201, 48, 34), '−', 'skirmish_ai', -1)
    c.button((922, 201, 48, 34), '+', 'skirmish_ai', 1)
    c.text('AI DIFFICULTY', (866, 255, 208, 24), 14, MUTED)
    c.button((866, 283, 208, 34), o['ai_difficulty'].upper() + ' ›', 'skirmish_difficulty')
    c.text('Same team = allies. AI allies share vision, not control. Keep at least two different teams.', (866, 340, 208, 100), 14, MUTED, wrap=True)
    c.text('Distinct colors are kept automatically. Click to cycle.', (866, 449, 208, 60), 14, MUTED, wrap=True)
    c.text(data['description'], (32, 544, 1056, 60), 14, MUTED, wrap=True)
    c.text(menu.skirmish_notice or 'Unused fleet choices are retained when reducing AI players.', (32, 608, 1056, 22), 14, MUTED)
    pygame.draw.line(c.surface, BORDER, (32, 637), (1088, 637))
    c.button((32, 650, 180, 36), 'Back', 'goto_main')
    c.button((852, 650, 236, 36), 'Launch skirmish', 'launch_skirmish', primary=True)
    c.finish(preview)


def host_setup(menu):
    from game.core.skirmish import COLOR_NAMES
    c = SetupCanvas(menu, 'lan')
    o = menu.lan_options
    c.text('STAR ARMADA', (32, 20, 300, 30), 24)
    c.text('Host a multiplayer game', (32, 65, 780, 36), 28)
    c.text('Hosting opens a lobby. It does not launch the match.', (280, 107, 548, 24), 14, MUTED)
    data, preview = battlefield(c, o, o['human_count'] + o['ai_count'], 'lan_map')
    c.text('FLEET ROSTER', (280, 330, 548, 24), 16, MUTED)
    for slot in range(4):
        y = 364 + slot * 42
        role = 'HUMAN' if slot < o['human_count'] else 'AI' if slot < o['human_count'] + o['ai_count'] else 'UNUSED'
        c.text(f'{slot + 1} {role}', (280, y + 8, 92, 24), 14, MUTED if role == 'UNUSED' else INK)
        color = o['colors'][slot]
        c.button((376, y, 114, 34), COLOR_NAMES[color] + ' ›', 'lan_color', slot, swatch=color)
        c.button((498, y, 330, 34), menu.skirmish_store.factions[o['factions'][slot]].display_name + ' ›', 'lan_faction', slot)
    c.panel((852, 107, 236, 423))
    c.text('Session settings', (866, 122, 208, 30), 24)
    c.text(f"Humans {o['human_count']} / capacity {menu.skirmish_capacity(o['map_id'])}", (866, 165, 208, 24), 14)
    c.button((866, 188, 48, 34), '−', 'lan_humans', -1)
    c.button((922, 188, 48, 34), '+', 'lan_humans', 1)
    c.text(f"AI {o['ai_count']} (0–2)", (866, 233, 208, 24), 14)
    c.button((866, 256, 48, 34), '−', 'lan_ai', -1)
    c.button((922, 256, 48, 34), '+', 'lan_ai', 1)
    c.button((866, 300, 208, 34), 'Difficulty: ' + o['ai_difficulty'], 'lan_difficulty')
    c.button((866, 344, 208, 34), 'Humans vs AI' if o['cooperative'] else 'Free for all', 'lan_cooperative')
    for field, label, y in (('lan_name', 'Nickname', 390), ('lan_port', 'TCP port', 456)):
        c.text(label, (866, y, 208, 24), 14, MUTED)
        c.button((866, y + 23, 208, 34), getattr(menu, field) + (' |' if menu.lan_focus == field else ''), 'lan_field', field)
    c.text(data['description'], (32, 544, 1056, 60), 14, MUTED, wrap=True)
    c.text(menu.lan_notice or 'Distinct colors. Unused slot choices are retained. Click to cycle.', (32, 608, 1056, 22), 14, MUTED)
    pygame.draw.line(c.surface, BORDER, (32, 637), (1088, 637))
    c.button((32, 650, 180, 36), 'Back', 'lan_back')
    c.button((852, 650, 236, 36), 'Apply setup' if menu.lan_session is not None else 'Create lobby', 'lan_connect', primary=True)
    c.finish(preview)
