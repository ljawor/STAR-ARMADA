"""LAN Host uses the Skirmish battlefield cards/chart and compact fleet roster."""
import pygame
from game.core.skirmish import PLAYER_COLORS, COLOR_NAMES
from render import i18n
from render.clean_classic import SetupCanvas, INK, MUTED, ACCENT, BORDER
from render.skirmish_screen import battlefield_list, chart


def host_setup(menu):
    c = SetupCanvas(menu, 'lan')
    o = menu.lan_options
    data = menu.skirmish_store.maps[o['map_id']]
    capacity = len(data['players'])
    active = o['human_count'] + o['ai_count']
    starts = o.get('spawn_slots', list(range(capacity)))
    c.text('STAR ARMADA', (32, 20, 300, 30), 24)
    c.text('Host a multiplayer game', (32, 65, 780, 36), 28)
    battlefield_list(c, menu, o, 'lan_map')
    c.text(data['name'], (280, 107, 420, 24), 16)
    preview = chart(c, data, o, human_count=o['human_count'], action='lan_spawn_point')
    c.text('Click a start to deploy here.', (280, 568, 420, 20), 14, ACCENT)
    c.panel((720, 107, 368, 180))
    c.text('Session settings', (734, 117, 340, 28), 20)
    for y, label, action in (
            (151, i18n.t('Humans {count} / {capacity}', count=o['human_count'], capacity=capacity), 'lan_humans'),
            (183, i18n.t('AI {count} / {capacity}', count=o['ai_count'], capacity=capacity-o['human_count']), 'lan_ai')):
        c.text(label, (734, y + 3, 248, 23), 13)
        c.button((1008, y, 28, 26), '−', action, -1, size=13)
        c.button((1046, y, 28, 26), '+', action, 1, size=13)
    c.text('AI DIFFICULTY', (734, 219, 158, 22), 12, MUTED)
    c.button((904, 215, 170, 26), o['ai_difficulty'].upper() + ' ›', 'lan_difficulty', size=12)
    c.button((734, 249, 340, 26), 'Humans vs AI' if o['cooperative'] else 'Free for all', 'lan_cooperative', size=12)
    c.text('FLEET ROSTER', (734, 295, 340, 22), 14, MUTED)
    for slot in range(capacity):
        y = 322 + slot * 38
        role = (i18n.t('Human {n}', n=slot+1) if slot < o['human_count'] else
                i18n.t('AI {n}', n=slot-o['human_count']+1) if slot < active else
                i18n.t('Unused {n}', n=slot+1))
        c.text(role, (734, y + 1, 98, 18), 12, INK if slot < active else MUTED)
        c.button((838, y, 236, 18), menu.skirmish_store.factions[o['factions'][slot]].display_name + ' ›', 'lan_faction', slot, size=12)
        c.button((734, y + 20, 160, 16), COLOR_NAMES[o['colors'][slot]] + ' ›', 'lan_color', slot, size=11)
        rgb = tuple(round(v * 255) for v in PLAYER_COLORS[o['colors'][slot]])
        pygame.draw.rect(c.surface, rgb, (736, y + 22, 3, 14))
        c.button((902, y + 20, 172, 16), i18n.t('Start {n}', n=starts[slot]+1) + ' ›', 'lan_spawn', slot, size=11)
    description_y = 322 + capacity * 38 + 12
    if description_y < 490:
        c.text(data['description'], (734, description_y, 340, 617-description_y), 12, MUTED, wrap=True)
    c.text(menu.lan_notice or data['description'].split('. ')[0] + '.', (32, 542, 224, 62), 12, ACCENT if menu.lan_notice else MUTED, wrap=True)
    for field, label, x, width in (('lan_name', 'Nickname', 280, 256), ('lan_port', 'TCP port', 548, 152)):
        c.text(label, (x, 590, width, 18), 12, MUTED)
        c.button((x, 610, width, 26), getattr(menu, field) + (' |' if menu.lan_focus == field else ''), 'lan_field', field, size=12)
    c.text('Hosting opens a lobby. It does not launch the match.', (32, 608, 224, 28), 10, MUTED, wrap=True)
    pygame.draw.line(c.surface, BORDER, (32, 637), (1088, 637))
    c.button((32, 650, 180, 36), 'Back', 'lan_back')
    c.button((852, 650, 236, 36), 'Apply setup' if menu.lan_session is not None else 'Create lobby', 'lan_connect', primary=True)
    c.finish(preview)
