"""Clean Classic ancillary screens; presentation only, existing menu actions."""
import pygame
from render.clean_classic import SetupCanvas, ACCENT, BORDER, DONE, INK, MUTED, PANEL


def _button(c, rect, label, action, payload=None, primary=False, focused=False):
    c.button(rect, label, action, payload, selected=focused or _hot(c, rect), primary=primary)


def lan_chooser(menu):
    c = _canvas(menu, 'lan', 'Multiplayer / LAN', 'Connect your fleets on a local network.')
    for x, title, description, label, action, primary in (
        (52, 'Host a game', 'Choose a battlefield and fleet roster. Open a lobby, then launch once everyone is ready.', 'Host game', 'lan_host_setup', True),
        (570, 'Join a game', 'Enter the host address and TCP port. Connect to the lobby and ready your fleet.', 'Join game', 'lan_join_setup', False)):
        c.panel((x, 176, 498, 350))
        c.text(title, (x + 24, 203, 450, 36), 28)
        c.text(description, (x + 24, 267, 450, 120), 20, MUTED, wrap=True)
        _button(c, (x + 24, 443, 450, 44), label, action, primary=primary)
    c.text('Hosting creates a lobby; it does not start a match.', (52, 558, 1016, 30), 18, MUTED)
    _button(c, (32, 650, 180, 36), 'Back', 'goto_main')
    c.finish()


def lan_session(menu):
    joining = menu.screen == 'lan_join'
    c = _canvas(menu, 'lan', 'Join a multiplayer game' if joining else 'Multiplayer lobby',
                'Enter your connection details.' if joining else 'Connected fleets and session status')
    if joining:
        for field, label, y in (('lan_name', 'Nickname', 178), ('lan_port', 'TCP port', 288), ('lan_address', 'Host IPv4 address', 398)):
            c.text(label, (56, y, 614, 28), 18, MUTED)
            _button(c, (56, y + 36, 614, 44), getattr(menu, field) + (' |' if menu.lan_focus == field else ''),
                    'lan_field', field, focused=menu.lan_focus == field)
        c.panel((706, 178, 354, 320))
        c.text('Connection guide', (730, 198, 306, 36), 24)
        c.text('Use the address shown in the host lobby and the same TCP port.\nAsk the host to allow STAR ARMADA through their firewall.',
               (730, 255, 306, 180), 18, MUTED, wrap=True)
        _button(c, (852, 650, 236, 36), 'Connect', 'lan_connect', primary=True)
    elif menu.lan_session is not None:
        snap = menu.lan_session.snapshot
        o = snap.get('options') or menu.lan_options
        c.text(f"{snap.get('status', 'Connecting')} · TCP {snap.get('port', menu.lan_port)}", (56, 170, 1004, 30), 20, ACCENT)
        c.text('Host IPs: ' + ', '.join(snap.get('addresses', [])), (56, 207, 1004, 28), 16, MUTED)
        players = {p['slot']: p for p in snap.get('players', [])}
        for slot in range(o['human_count']):
            p = players.get(slot)
            y = 248 + slot * 64
            c.panel((56, y, 614, 54))
            c.text(f'{slot + 1:02d}', (72, y + 14, 40, 28), 18, MUTED)
            c.text(p['name'] if p else 'Waiting for player…', (122, y + 14, 340, 28), 18, INK if p else MUTED)
            c.text('READY' if p and p['ready'] else 'NOT READY' if p else 'OPEN SLOT', (488, y + 16, 166, 24), 16, ACCENT if p and p['ready'] else MUTED)
        c.panel((706, 248, 354, 282))
        c.text('Match settings', (730, 268, 306, 34), 24)
        for i, line in enumerate((f"Map: {o['map_id']}", f"Humans: {o['human_count']} · AI: {o['ai_count']}",
                f"Difficulty: {o['ai_difficulty']}", 'Humans vs AI' if o['cooperative'] else 'Free for all')):
            c.text(line, (730, 319 + i * 37, 306, 30), 18, MUTED)
        if not snap.get('error'):
            if snap.get('is_host'):
                _button(c, (244, 650, 180, 36), 'Edit setup', 'lan_edit')
            p = players.get(menu.lan_session.local_player)
            if p:
                _button(c, (640, 650, 180, 36), 'Unready' if p['ready'] else 'Ready', 'lan_ready', primary=not snap.get('can_start'))
            if snap.get('is_host') and snap.get('can_start'):
                _button(c, (852, 650, 236, 36), 'Launch game', 'lan_start', primary=True)
            c.text('All humans must connect and ready.' if snap.get('is_host') else 'Waiting for host to launch.', (56, 550, 1004, 26), 16, MUTED)
        else:
            c.text(str(snap['error']), (56, 550, 1004, 26), 16, ACCENT)
            _button(c, (852, 650, 236, 36), 'Reconnect', 'lan_reconnect', primary=True)
    else:
        c.text('Waiting for a session connection…', (56, 180, 1004, 30), 20, MUTED)
    c.text(menu.lan_notice, (56, 582, 1004, 26), 16, MUTED)
    _button(c, (32, 650, 180, 36), 'Back / Esc', 'lan_back')
    c.finish()


def _canvas(menu, prefix, title, subtitle):
    c = SetupCanvas(menu, prefix)
    c.text('STAR ARMADA', (32, 20, 1056, 30), 24)
    c.text(title, (32, 65, 1056, 36), 28)
    c.panel((32, 107, 1056, 505))
    c.text(subtitle, (52, 122, 1016, 28), 16, MUTED)
    pygame.draw.line(c.surface, BORDER, (32, 637), (1088, 637))
    return c


def _map_rect(menu, rect):
    scale = min(menu.width / 1120, menu.height / 700)
    ox = (menu.width - round(1120 * scale)) // 2
    oy = (menu.height - round(700 * scale)) // 2
    r = pygame.Rect(rect)
    return pygame.Rect(ox + round(r.x * scale), oy + round(r.y * scale),
                       round(r.w * scale), round(r.h * scale))


def _hot(c, rect):
    return _map_rect(c.menu, rect).collidepoint(pygame.mouse.get_pos())


def briefing(menu):
    missions = menu.campaign.get('missions', [])
    if menu.selected_mission >= len(missions):
        menu.screen = 'campaign'
        return
    mission = missions[menu.selected_mission]
    c = _canvas(menu, 'briefing', mission.get('name', 'Mission'), 'Mission briefing · Review your orders before deploying.')
    c.text('BRIEFING', (56, 176, 572, 26), 16, MUTED)
    c.text(mission.get('briefing', ''), (56, 219, 572, 350), 20, INK, wrap=True)
    pygame.draw.line(c.surface, BORDER, (656, 176), (656, 584))
    c.text('OBJECTIVES', (688, 176, 372, 26), 16, MUTED)
    y = 219
    for objective in mission.get('objectives', []):
        c.text('• ' + objective.get('text', objective.get('type', '?')), (688, y, 372, 84), 18, INK, wrap=True)
        y = c.bounds[-1].bottom + 16
    enemy = mission.get('enemy', {})
    if enemy:
        c.text(f"Enemy: {enemy.get('faction', '?')} force", (688, max(y + 8, 548), 372, 40), 18, ACCENT)
    _button(c, (32, 650, 180, 36), 'Back', 'goto_campaign')
    _button(c, (852, 650, 236, 36), 'Launch mission', 'launch_mission', menu.selected_mission, primary=True)
    c.finish()


def campaign(menu, unlocked_ids, completed_ids: set[str] | frozenset[str] = frozenset()):
    missions = menu.campaign.get('missions', [])
    completed_ids = set(completed_ids)
    page_size = 7
    pages = max(1, (len(missions) + page_size - 1) // page_size)
    menu.campaign_page = min(pages - 1, max(0, getattr(menu, 'campaign_page', 0)))
    c = _canvas(menu, 'campaign', menu.campaign.get('campaign', 'Campaign'),
                f'Choose your next mission · Page {menu.campaign_page + 1}/{pages}')
    menu.campaign_rows = {}
    if not missions:
        c.text('No missions defined.', (56, 180, 1004, 30), 20, MUTED)
    start = menu.campaign_page * page_size
    for i in range(start, min(len(missions), start + page_size)):
        mission = missions[i]
        r = pygame.Rect(52, 164 + (i - start) * 60, 1016, 50)
        unlocked = mission.get('id') in unlocked_ids
        # A won mission stays selectable (replays are the review loop) but reads
        # as finished: gold row, gold status, distinct from available/locked.
        done = mission.get('id') in completed_ids
        if done:
            fill = (26, 54, 46) if _hot(c, r) else (18, 42, 37)
            edge = DONE
        elif unlocked:
            fill = (28, 48, 53) if _hot(c, r) else (14, 24, 33)
            edge = ACCENT if _hot(c, r) else BORDER
        else:
            fill, edge = (12, 20, 27), BORDER
        pygame.draw.rect(c.surface, fill, r, border_radius=4)
        pygame.draw.rect(c.surface, edge, r, 1, border_radius=4)
        c.text(f'{i + 1:02d}', (r.x + 16, r.y + 13, 46, 28), 18,
               DONE if done else ACCENT if unlocked else MUTED)
        c.text(mission.get('name', mission.get('id', '?')), (r.x + 78, r.y + 13, 708, 28), 18,
               INK if unlocked else MUTED)
        status = 'COMPLETE' if done else 'AVAILABLE' if unlocked else 'LOCKED'
        c.text(status, (r.right - 184, r.y + 15, 166, 26), 16,
               DONE if done else ACCENT if unlocked else MUTED)
        menu.campaign_rows[mission.get('id')] = _map_rect(menu, r)
        if unlocked:
            menu.buttons.append(dict(rect=r, action='select_mission', payload=i))
    c.text('COMPLETE missions stay playable · finish a mission to unlock the next chapter.',
           (52, 586, 1016, 26), 16, MUTED)
    _button(c, (32, 650, 180, 36), 'Back', 'goto_main')
    if menu.campaign_page > 0:
        _button(c, (684, 650, 192, 36), 'Previous page', 'campaign_page', -1)
    if menu.campaign_page < pages - 1:
        _button(c, (896, 650, 192, 36), 'Next page', 'campaign_page', 1)
    c.finish()


def settings(menu):
    pages = (
        ('Sound & display', (('Music volume', 'music_volume', 'slider'),
            ('SFX volume', 'sfx_volume', 'slider'), ('Fullscreen', 'fullscreen', 'toggle'),
            ('Autosave', 'autosave', 'toggle'), ('Ownership markers', 'markers', 'cycle_markers'),
            ('Camera pan speed', 'pan_speed', 'slider'))),
        ('Audio & presentation', (('Dynamic range', 'audio_dynamic_range', 'cycle_range'),
            ('Mono audio', 'audio_mono', 'toggle'), ('Cinematics', 'cinematics_enabled', 'toggle'),
            ('Reduced motion', 'reduced_motion', 'toggle'), ('Tutorial hints', 'tutorial_hints', 'toggle'))),
        ('Readability & help', (('High contrast panels', 'high_contrast_ui', 'toggle'),)),
    )
    menu.settings_page = min(2, max(0, getattr(menu, 'settings_page', 0)))
    menu.settings_focus = getattr(menu, 'settings_focus', -1)
    title, rows = pages[menu.settings_page]
    c = _canvas(menu, 'settings', 'Settings', f'{title} · Page {menu.settings_page + 1}/3')
    for index, (label, key, action) in enumerate(rows):
        r = pygame.Rect(52, 164 + index * 61, 1016, 48)
        hot = menu.settings_focus == index or _hot(c, r)
        pygame.draw.rect(c.surface, (28, 48, 53) if hot else (14, 24, 33), r, border_radius=4)
        pygame.draw.rect(c.surface, ACCENT if hot else BORDER, r, 2 if hot else 1, border_radius=4)
        c.text(label, (r.x + 16, r.y + 12, 530, 28), 18)
        value = menu.settings.get(key)
        if action == 'slider':
            value = min(1., max(0., float(value)))
            bar = pygame.Rect(788, r.y + 20, 184, 10)
            pygame.draw.rect(c.surface, BORDER, bar, border_radius=3)
            pygame.draw.rect(c.surface, ACCENT, (bar.x, bar.y, round(bar.w * value), bar.h), border_radius=3)
            c.text(f'{int(value * 100)}%', (988, r.y + 12, 64, 28), 18)
            payload = {'key': key, 'rect': bar}
        else:
            value = ('ON' if value else 'OFF') if action == 'toggle' else str(value).upper()
            c.text(value + ' ›', (788, r.y + 12, 264, 28), 18, ACCENT)
            payload = {'key': key}
        menu.buttons.append(dict(rect=r, action=action, payload=payload))
    if menu.settings_page == 2:
        for index, line in enumerate(('F1: keyboard and controls help during play.',
            'High contrast applies to help / hint panels only.',
            'Reduced motion disables menu drift and cinematic motion.',
            'Not whole-game scaling or full colorblind compliance.')):
            c.text(line, (68, 246 + index * 40, 968, 30), 18, MUTED)
    c.text('Tab / Up / Down: focus · Enter: toggle · Left / Right: volume', (52, 552, 1016, 24), 16, MUTED)
    c.text('Page Up / Down: pages · Esc: back', (52, 581, 1016, 24), 16, MUTED)
    c.button((32, 650, 180, 36), 'Back', 'goto_main')
    c.button((684, 650, 192, 36), 'Previous page', 'settings_page', -1)
    c.button((896, 650, 192, 36), 'Next page', 'settings_page', 1)
    c.finish()
    menu.settings_text_bounds = list(zip(menu.settings_rendered_text, menu.settings_text_bounds))
    for b in menu.buttons:
        if b['action'] == 'slider':
            b['payload']['rect'] = _map_rect(menu, b['payload']['rect'])
