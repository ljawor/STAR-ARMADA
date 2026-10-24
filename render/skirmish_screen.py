"""Deployment chart: aspect-correct public terrain and collision-free start choices."""
import math
import pygame
from render import i18n
from render.clean_classic import SetupCanvas, INK, MUTED, ACCENT, BORDER
from game.core.skirmish import SKIRMISH_MAP_IDS, PLAYER_COLORS, COLOR_NAMES


def chart(c, data, options):
    preview = pygame.Rect(280, 140, 420, 420)
    c.panel(preview)
    area = preview.inflate(-52, -52)
    scale = area.w / data['bounds']
    def point(pos):
        return (round(area.centerx + pos[0] * scale), round(area.centery + pos[2] * scale))
    old_clip = c.surface.get_clip()
    c.surface.set_clip(preview.inflate(-2, -2))
    # Stable cartographic stars, not random per-frame visual noise.
    for i in range(120):
        x = preview.x + (i * 137 + 23) % preview.w
        y = preview.y + (i * 211 + 61) % preview.h
        pygame.draw.circle(c.surface, (32, 47, 61), (x, y), 1)
    for n in range(9):
        v = round(area.left + n * area.w / 8)
        h = round(area.top + n * area.h / 8)
        pygame.draw.line(c.surface, (29, 46, 58), (v, area.top), (v, area.bottom))
        pygame.draw.line(c.surface, (29, 46, 58), (area.left, h), (area.right, h))
    pygame.draw.rect(c.surface, (57, 79, 91), area, 1)
    for feature in data.get('nebulas', []):
        pos = point(feature['pos'])
        radius = max(5, round(feature.get('radius', 200) * scale))
        for layer in range(5, 0, -1):
            pygame.draw.circle(c.surface, (22 + (5-layer)*3, 25 + (5-layer)*2, 43 + (5-layer)*7), pos, max(2, radius*layer//5))
    for feature in data.get('asteroid_fields', []):
        x, y = point(feature['pos'])
        radius = max(5, round(feature.get('radius', 200)*scale))
        pygame.draw.circle(c.surface, (69, 59, 42), (x, y), radius, 1)
        for i in range(9):
            angle = i * 2.39996
            r = radius * (0.3 + (i % 3) * .25)
            p = (round(x + math.cos(angle)*r), round(y + math.sin(angle)*r))
            pygame.draw.polygon(c.surface, (174,137,76), [(p[0]-2,p[1]),(p[0],p[1]-2),(p[0]+2,p[1]+1),(p[0],p[1]+2)])
    for kind, color in [('gas_giants',(105,131,161)), ('planets',(100,185,160))]:
        for feature in data.get(kind, []):
            x,y = point(feature['pos'])
            r = max(3, round(feature.get('radius',200)*scale))
            pygame.draw.circle(c.surface, (28,53,58), (x,y), r+3, 1)
            pygame.draw.circle(c.surface, color, (x,y), r)
            pygame.draw.circle(c.surface, tuple(min(255,v+35) for v in color), (x-max(1,r//3),y-max(1,r//3)), max(1,r//3))
    for feature in data.get('jump_points', []):
        x,y = point(feature['pos'])
        pygame.draw.polygon(c.surface,(109,160,223),[(x,y-4),(x+4,y),(x,y+4),(x-4,y)],1)
    starts = options.get('spawn_slots', list(range(len(data['players']))))
    active = options['ai_count'] + 1
    for anchor, player in enumerate(data['players']):
        x,y = point(player['start'])
        c.starts.append((x,y))
        owner = starts.index(anchor)
        color = tuple(round(v*255) for v in PLAYER_COLORS[options['colors'][owner]]) if owner < active else (76,86,102)
        pygame.draw.circle(c.surface, (9,18,27), (x,y), 14)
        pygame.draw.circle(c.surface, color, (x,y), 12, 2)
        pygame.draw.circle(c.surface, color, (x,y), 5)
        if owner == 0:
            pygame.draw.circle(c.surface, ACCENT, (x,y), 16, 1)
        c.menu.buttons.append(dict(rect=pygame.Rect(x-16,y-16,32,32), action='skirmish_spawn_point', payload=anchor))
        c.text(str(anchor+1), (x+17,y-9,18,19), 12, color)
    c.surface.set_clip(old_clip)
    return preview


def setup(menu):
    c = SetupCanvas(menu, 'skirmish')
    o = menu.skirmish_options
    data = menu.skirmish_store.maps[o['map_id']]
    capacity = len(data['players'])
    c.text('STAR ARMADA', (32,20,300,30),24)
    c.text('Deploy your fleet', (32,65,780,36),28)
    c.text('BATTLEFIELD', (32,107,224,24),14,MUTED)
    for i,mid in enumerate(SKIRMISH_MAP_IDS):
        row = menu.skirmish_store.maps[mid]
        y = 140+i*49
        c.button((32,y,224,43),'','skirmish_map',mid,mid==o['map_id'])
        c.text(row['name'],(42,y+5,204,19),13)
        c.text(f"{len(row['players'])} PLAYERS / TEAMS OR FFA",(42,y+24,204,17),11,MUTED)
    c.text(data['name'],(280,107,420,24),16)
    preview = chart(c,data,o)
    c.text('Click a start to deploy here.',(280,569,420,20),14,ACCENT)
    c.text('Gold: resources · Teal: worlds · Rings: starts',(280,594,420,20),12,MUTED)
    c.panel((720,107,368,130))
    c.text('Match settings',(734,117,340,28),20)
    c.text(f"AI PLAYERS   {o['ai_count']} / {capacity-1}",(734,151,190,24),14)
    c.button((974,145,44,30),'−','skirmish_ai',-1)
    c.button((1030,145,44,30),'+','skirmish_ai',1)
    c.text('AI DIFFICULTY',(734,190,140,22),12,MUTED)
    c.button((900,183,174,30),o['ai_difficulty'].upper()+' ›','skirmish_difficulty',size=13)
    c.text('FLEET ROSTER',(734,245,340,24),14,MUTED)
    starts = o.get('spawn_slots',list(range(capacity)))
    for slot in range(o['ai_count']+1):
        y = 268+slot*44
        relation = 'Ally' if o['teams'][slot]==o['teams'][0] else 'Enemy'
        c.text('You' if slot==0 else f'AI {slot} · {relation}',(734,y+1,100,18),12)
        c.button((838,y-3,236,22),menu.skirmish_store.factions[o['factions'][slot]].display_name+' ›','skirmish_faction',slot,size=12)
        c.button((734,y+20,112,21),COLOR_NAMES[o['colors'][slot]]+' ›','skirmish_color',slot,size=11)
        # Colour stripe remains visible even at the smallest supported window.
        rgb = tuple(round(v*255) for v in PLAYER_COLORS[o['colors'][slot]])
        pygame.draw.rect(c.surface,rgb,(736,y+23,3,15))
        c.button((852,y+20,108,21),f"Team {o['teams'][slot]+1} ›",'skirmish_team',slot,size=11)
        c.button((966,y+20,108,21),i18n.t('Start {n}', n=starts[slot]+1)+' ›','skirmish_spawn',slot,size=11)
    description_y = 268 + (o['ai_count']+1)*44 + 12
    if description_y < 480:
        c.text(data['description'], (734,description_y,340,610-description_y),12,MUTED,wrap=True)
    c.text(data['description'].split('. ')[0]+'.',(32,542,224,74),12,MUTED,wrap=True)
    c.text(menu.skirmish_notice or 'Same team = allies. AI allies share vision, not control.',(32,618,1056,18),12,MUTED)
    pygame.draw.line(c.surface,BORDER,(32,637),(1088,637))
    c.button((32,650,180,36),'Back','goto_main')
    c.button((852,650,236,36),'Launch skirmish','launch_skirmish',primary=True)
    c.finish(preview)
