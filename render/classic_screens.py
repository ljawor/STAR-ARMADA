"""Clean Classic ancillary screens; presentation only, existing menu actions."""
import pygame
from render.clean_classic import SetupCanvas, ACCENT, BORDER, DONE, INK, MUTED, PANEL

#: Number of Settings pages and the index of the Game Balance one (#106). menus.py reads the
#: count for its Page Up / Down clamp and its next-page button, so the two cannot drift.
SETTINGS_PAGE_COUNT = 5
BALANCE_PAGE = 4

#: The Game Balance editor's pages, in tab order, with the rect each tab occupies. The tabs
#: carry their *index* as their payload — a tab is a jump, where every other page control in
#: the menus is a step of ±1 — so this tuple is what both the tabs and `MenuStack`'s clamp
#: read, and the payload of a tab cannot point at a page that does not exist.
BALANCE_PAGES = ('Per-level gains', 'Build levels')
BALANCE_TAB_RECTS = ((440, 150, 300, 34), (756, 150, 332, 34))

#: Human wording for the row each gain edits. The words are the HUD refit block's own where the
#: panel already names a resource, so the screen that tunes a station and the panel that
#: describes it name the same thing; the value column carries the number.
GAIN_LABELS = {
    'hull_bonus': 'hull', 'shield_bonus': 'shields',
    'shield_regen_bonus': 'regen', 'damage_bonus': 'damage',
    'production_bonus': 'output', 'convoy_cargo_bonus': 'cargo',
    'volley_shots_per_level': 'extra shots',
    'convoy_per_two_levels': 'convoys',
}


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
        compact = o['human_count'] > 4
        step = min(64, 280 // o['human_count'])
        for slot in range(o['human_count']):
            p = players.get(slot)
            y = 248 + slot * step
            c.panel((56, y, 614, step - 8 if compact else 54))
            c.text(f'{slot + 1:02d}', (72, y + (4 if compact else 14), 40, 22 if compact else 28), 14 if compact else 18, MUTED)
            c.text(p['name'] if p else 'Waiting for player…', (122, y + (4 if compact else 14), 340, 22 if compact else 28), 14 if compact else 18, INK if p else MUTED)
            c.text('READY' if p and p['ready'] else 'NOT READY' if p else 'OPEN SLOT', (488, y + (5 if compact else 16), 166, 22 if compact else 24), 12 if compact else 16, ACCENT if p and p['ready'] else MUTED)
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
    from render import i18n
    pages = (
        ('Sound & display', (('Music volume', 'music_volume', 'slider'),
            ('SFX volume', 'sfx_volume', 'slider'), ('Fullscreen', 'fullscreen', 'toggle'),
            ('Resolution', 'resolution', 'cycle_resolution'),
            ('Autosave', 'autosave', 'toggle'), ('Ownership markers', 'markers', 'cycle_markers'),
            ('Camera pan speed', 'pan_speed', 'slider')), ()),
        ('Audio & presentation', (('Dynamic range', 'audio_dynamic_range', 'cycle_range'),
            ('Mono audio', 'audio_mono', 'toggle'), ('Cinematics', 'cinematics_enabled', 'toggle'),
            ('Reduced motion', 'reduced_motion', 'toggle'), ('Tutorial hints', 'tutorial_hints', 'toggle')), ()),
        # #160: the renderer, the Blender catalogue and the visual-pack order are no longer choices.
        # The window is the one renderer, the approved catalogue is always on, and the pack list is
        # shipped order. A row for any of them was a switch the player could not use.
        ('Readability & help', (('High contrast panels', 'high_contrast_ui', 'toggle'),),
            ('F1: keyboard and controls help during play.',
             'Changes apply at the next session, never during a battle.')),
        # #93: the language row sits on its own page with the rules it follows, so
        # the fallback behaviour is stated where the choice is made.
        ('Language', (('Language', 'language', 'cycle_language'),),
            ('Menus, panels and data names (ships, stations, factions) are translated.',
             'The pack is chosen from assets/data/lang/; English is the catalogue.',
             'A line a pack does not carry falls back to English.',
             'Presentation only: the language never changes a match or a replay.')),
        # #106: the tuning door sits last on purpose — the language tests and the page
        # walk both count pages, and a page inserted in the middle would renumber them.
        ('Game Balance', (), ()),
    )
    menu.settings_page = min(len(pages) - 1, max(0, getattr(menu, 'settings_page', 0)))
    menu.settings_focus = getattr(menu, 'settings_focus', -1)
    title, rows, notes = pages[menu.settings_page]
    c = _canvas(menu, 'settings', 'Settings',
                i18n.t('{page} · Page {n}/{total}', page=i18n.t(title),
                       n=menu.settings_page + 1, total=len(pages)))
    # Seven sound/display rows plus current-mode information must clear the pinned help footer.
    row_step, row_height = (46, 40) if menu.settings_page == 0 else (61, 48)
    for index, (label, key, action) in enumerate(rows):
        r = pygame.Rect(52, 164 + index * row_step, 1016, row_height)
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
            # The language row names the pack in its own language, never in the active
            # one: "Polski" has to be readable to someone stuck in a pack they cannot read.
            if action == 'cycle_language':
                value = i18n.label(str(value))
            elif action == 'cycle_resolution':
                value = i18n.t('Automatic') if value == 'auto' else str(value).replace('x', ' × ')
            elif action == 'toggle':
                value = 'ON' if value else 'OFF'
            else:
                value = str(value).upper()
            c.text(value + ' ›', (788, r.y + 12, 264, 28), 18, ACCENT)
            payload = {'key': key}
        menu.buttons.append(dict(rect=r, action=action, payload=payload))
    if menu.settings_page == 0:
        # Read the live SDL surface, never the saved preference (which can be pending a restart).
        surface = pygame.display.get_surface()
        width, height = surface.get_size() if surface is not None else (menu.width, menu.height)
        full = bool(surface.get_flags() & pygame.FULLSCREEN) if surface is not None else False
        mode = i18n.t('Fullscreen') if full else i18n.t('Windowed')
        c.text(i18n.t('Current resolution: {width} × {height} · {mode}',
                     width=width, height=height, mode=mode), (68, 491, 968, 24), 16, MUTED)
        c.text('Resolution changes take effect after restarting the game.',
               (68, 519, 968, 24), 16, MUTED)
    notes_top = max(246, 164 + len(rows) * row_step + 15)
    for index, line in enumerate(notes):
        c.text(line, (68, notes_top + index * 40, 968, 30), 18, MUTED)
    if menu.settings_page == BALANCE_PAGE:
        _balance_settings_body(menu, c)
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


def _balance_settings_body(menu, c):
    """The Game Balance page: what is tuned, where the file lives, and the way in (#106)."""
    from render import i18n
    tuned, gated = menu.balance_summary()
    c.text('Station upgrades', (52, 176, 700, 30), 20)
    if tuned or gated:
        c.text(i18n.t('Retuned station types: {tuned}', tuned=tuned) + ' · '
               + i18n.t('Gated hulls: {gated}', gated=gated), (52, 216, 1004, 26), 18, DONE)
    else:
        c.text('Every station uses the shipped balance.', (52, 216, 1004, 26), 18, MUTED)
    c.text('Per station type, a refit level can be made to gain more, and a hull can be held back'
           ' until its station reaches a level.', (52, 258, 1016, 60), 18, MUTED, wrap=True)
    c.text('The tuning is saved the moment it changes and survives application updates: it lives'
           ' beside settings.json in your user data, never inside the application bundle.',
           (52, 320, 1016, 60), 18, MUTED, wrap=True)
    _button(c, (52, 410, 500, 44), 'Station upgrades ›', 'goto_balance', primary=True)
    c.text('A retuned station reads the same numbers in the simulation, in its own panel and in a'
           ' replay recorded with it.', (52, 470, 1016, 60), 18, MUTED)


def balance(menu):
    """Settings → Game Balance → Station upgrades (#106).

    Presentation only, and a draft editor: every press edits `menu.balance_draft`, which the
    menu stack validates and writes once per frame while it is dirty. The screen therefore has
    no half-applied state to leave behind — either the whole config passes the strict reader or
    nothing was written.

    The rows are the station's own (`balance.bonus_rows`, `balance.editable_ships`), so the
    screen can neither offer a gain the simulation would not read nor a hull it would refuse.
    """
    from render import i18n
    from game.data import balance as balance_config
    from game.systems import upgrades
    draft = menu.balance_draft
    station = menu.balance_selected()
    c = _canvas(menu, 'balance', 'Game Balance',
                i18n.t('Station upgrades · what each level gains, and what a hull needs'))
    tuned, gated = menu.balance_summary()
    c.text('FACTION', (52, 150, 368, 24), 16, MUTED)
    faction = menu.skirmish_store.factions[menu.balance_faction]
    _button(c, (52, 176, 368, 36), i18n.name(faction.display_name) + (
        ' ›' if len(menu.balance_factions()) > 1 else ''), 'balance_faction', 1)
    c.text('STATIONS', (52, 226, 368, 24), 16, MUTED)
    for index, station_id in enumerate(menu.balance_stations()):
        row = pygame.Rect(52, 252 + index * 34, 368, 30)
        _button(c, row, '', 'balance_station', station_id, focused=station_id == station)
        edited = (station_id in draft['station_upgrades']
                  or station_id in draft['build_levels'])
        if edited:
            # A dot rather than a word: it needs no translation and it survives the narrow
            # library column at the smallest window.
            pygame.draw.circle(c.surface, DONE, (row.x + 9, row.centery), 3)
        c.text(i18n.name(menu.skirmish_store.stations[station_id].display_name),
               (row.x + 20, row.y + 5, 336, 24), 16)
    for index, label in enumerate(BALANCE_PAGES):
        _button(c, BALANCE_TAB_RECTS[index], label, 'balance_page', index,
                focused=menu.balance_page == index)
    y = 196
    if station is None:
        c.text('No station to retune for this faction.', (440, 200, 648, 26), 18, MUTED)
    elif menu.balance_page == 0:
        gains = draft['station_upgrades'].get(station, {})
        for key in balance_config.bonus_rows(menu.skirmish_store, station):
            value = gains.get(key, upgrades.DEFAULTS[key])
            edited = key in gains
            shown = (i18n.t('+{count} per level', count=int(value))
                     if key in balance_config.COUNT_KEYS
                     else i18n.t('+{percent}% per level', percent=f'{value * 100:g}'))
            c.text(i18n.t(GAIN_LABELS[key]), (456, y + 10, 220, 26), 18)
            if edited:
                c.text('MODIFIED', (682, y + 13, 96, 22), 14, DONE)
            _button(c, (784, y + 4, 40, 34), '−', 'balance_step', {'key': key, 'delta': -1})
            c.text(shown, (830, y + 10, 200, 26), 18, DONE if edited else INK)
            _button(c, (1036, y + 4, 40, 34), '+', 'balance_step', {'key': key, 'delta': 1})
            y += 44
        c.text('The gain each refit level adds, as a share of the shipped value. 100% doubles it.',
               (440, 560, 648, 22), 14, MUTED)
    else:
        hulls = balance_config.editable_ships(menu.skirmish_store, station, menu.balance_faction)
        levels = draft['build_levels'].get(station, {})
        if not hulls:
            c.text('This station lays down no ships.', (440, 200, 648, 26), 18, MUTED)
        for ship_id in hulls:
            level = levels.get(ship_id, balance_config.DEFAULT_BUILD_LEVEL)
            c.text(i18n.name(menu.skirmish_store.ships[ship_id].display_name),
                   (456, y + 10, 320, 26), 18)
            _button(c, (784, y + 4, 40, 34), '−', 'balance_gate_step',
                    {'station': station, 'ship_id': ship_id, 'delta': -1})
            c.text(i18n.t('as shipped') if level <= balance_config.DEFAULT_BUILD_LEVEL
                   else i18n.t('level {level}', level=level), (830, y + 10, 200, 26), 18,
                   DONE if level > balance_config.DEFAULT_BUILD_LEVEL else MUTED)
            _button(c, (1036, y + 4, 40, 34), '+', 'balance_gate_step',
                    {'station': station, 'ship_id': ship_id, 'delta': 1})
            y += 44
        c.text('A hull waits for its station to reach this level — for every player and the AI.',
               (440, 560, 648, 22), 14, MUTED)
    c.text(menu.balance_notice or (i18n.t('Retuned station types: {tuned}', tuned=tuned) + ' · '
                                   + i18n.t('Gated hulls: {gated}', gated=gated)),
           (440, 586, 648, 22), 14, MUTED)
    _button(c, (32, 650, 180, 36), 'Back', 'balance_back')
    _button(c, (612, 650, 224, 36), 'Reset this station', 'balance_reset_station')
    _button(c, (852, 650, 236, 36), 'Reset all tuning', 'balance_reset_all')
    c.finish()
