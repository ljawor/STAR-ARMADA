"""Static, read-only Clean Classic replay-library presentation."""
import os
import pygame
from render.clean_classic import SetupCanvas, ACCENT, BORDER, MUTED

BASE = (8, 15, 22)
DANGER = (229, 139, 139)
DANGER_FILL = (55, 27, 33)


def control(c, rect, label, action=None, payload=None, primary=False, danger=False):
    """Inactive controls are visible but never registered as hit targets."""
    rect = pygame.Rect(rect)
    if danger:
        if action:
            c.menu.buttons.append(dict(rect=rect, action=action, payload=payload))
        pygame.draw.rect(c.surface, DANGER_FILL, rect, border_radius=4)
        pygame.draw.rect(c.surface, (104, 53, 62), rect, 1, border_radius=4)
        c.text(label, (rect.x + 10, rect.y + 8, rect.w - 20, rect.h - 10), 14, DANGER)
    elif action:
        c.button(rect, label, action, payload, primary=primary)
    else:
        pygame.draw.rect(c.surface, (12, 21, 29), rect, border_radius=4)
        pygame.draw.rect(c.surface, BORDER, rect, 1, border_radius=4)
        c.text(label, (rect.x + 10, rect.y + 8, rect.w - 20, rect.h - 10), 14, (91, 108, 121))


def replay_library(menu):
    c = SetupCanvas(menu, 'replay')
    # Neither logical content nor aspect-ratio gutters inherit a battle movie.
    c.surface.fill(BASE)
    c.target.fill(BASE)
    c.text('STAR ARMADA', (32, 20, 500, 30), 24)
    c.text('Replay library', (32, 65, 700, 36), 28)
    if menu.replay_confirmation:
        # No underlying list/footer controls or stale hit targets in a modal.
        menu.buttons = []
        c.panel((250, 196, 620, 308))
        all_files = menu.replay_confirmation == 'ALL'
        c.text('DELETE ALL REPLAYS?' if all_files else 'DELETE SELECTED REPLAY?',
               (278, 220, 564, 38), 24)
        c.text('ALL replay JSON files, including files beyond the browser limit.' if all_files
               else os.path.basename(menu.replay_confirmation),
               (278, 278, 564, 56), 16, MUTED, wrap=True)
        c.text('Permanent deletion. This cannot be undone.', (278, 350, 564, 28), 16, DANGER)
        control(c, (278, 426, 270, 42), 'CANCEL / ENTER / ESC', 'replay_cancel_delete', primary=True)
        control(c, (570, 426, 272, 42), 'DELETE PERMANENTLY', 'replay_confirm_delete', danger=True)
        c.finish()
        return
    c.text('READ-ONLY PLAYBACK · newest first', (32, 112, 688, 24), 14, MUTED)
    paths = menu.replay_paths[menu.replay_page * 6:(menu.replay_page + 1) * 6]
    pages = max(1, (len(menu.replay_paths) + 5) // 6)
    c.panel((32, 148, 688, 420))
    if not paths:
        c.text('No replays yet. Finish or leave a match to save one.', (50, 182, 652, 60), 16, MUTED, wrap=True)
    for i, path in enumerate(paths):
        label = menu.replay_metadata[path][1]
        menu.replay_rows.setdefault(path, label)
        y = 160 + i * 66
        rect = pygame.Rect(44, y, 664, 60)
        menu.buttons.append(dict(rect=rect, action='select_replay', payload=path))
        active = path == menu.replay_selected
        pygame.draw.rect(c.surface, (28, 48, 53) if active else (14, 24, 33), rect, border_radius=4)
        pygame.draw.rect(c.surface, ACCENT if active else BORDER, rect, 1, border_radius=4)
        c.text(label, (58, y + 7, 636, 26), 18)
        c.text(os.path.basename(path), (58, y + 34, 636, 22), 14, MUTED)
    c.panel((744, 148, 344, 420))
    c.text('Selected recording', (762, 165, 308, 32), 24)
    selected = menu.replay_selected
    if selected:
        label = menu.replay_metadata.get(selected, (0, 'Unknown time / unavailable', {}))[1]
        c.text(label, (762, 214, 308, 60), 16, wrap=True)
        c.text(os.path.basename(selected), (762, 280, 308, 24), 14, MUTED)
        detail = menu.replay_rows.get(selected, label)
        if detail.startswith(label + ' / '):
            detail = detail[len(label) + 3:]
        c.text(detail, (762, 322, 308, 94), 14, MUTED, wrap=True)
    else:
        c.text('Select a recording to inspect its details.', (762, 214, 308, 70), 16, MUTED, wrap=True)
    control(c, (762, 428, 308, 38), 'PLAY SELECTED', 'play_replay' if selected else None, selected, primary=bool(selected))
    control(c, (762, 478, 308, 38), 'DELETE SELECTED', 'replay_delete' if selected else None, danger=bool(selected))
    c.text('P pause / [ ] speed / Esc exit.', (762, 534, 308, 22), 14, MUTED)
    control(c, (744, 582, 344, 36), 'DELETE ALL REPLAYS', 'replay_delete_all', danger=True)
    c.text(f'Page {menu.replay_page + 1}/{pages} / {len(menu.replay_paths)} files / newest first', (32, 582, 688, 24), 14, MUTED)
    c.text(menu.replay_notice, (32, 608, 688, 24), 14, MUTED)
    pygame.draw.line(c.surface, BORDER, (32, 637), (1088, 637))
    control(c, (32, 650, 156, 36), 'Back / Esc', 'goto_main')
    control(c, (200, 650, 156, 36), 'Refresh', 'replay_refresh')
    control(c, (744, 650, 166, 36), '‹ Previous', 'replay_page' if menu.replay_page else None, -1)
    control(c, (922, 650, 166, 36), 'Next ›', 'replay_page' if menu.replay_page + 1 < pages else None, 1)
    c.finish()
