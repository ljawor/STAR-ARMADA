"""Clean Classic saved games: timestamp-first library over the menu movie."""
import os
import pygame
from .clean_classic import SetupCanvas, ACCENT, BORDER, MUTED
from .classic_replays import control, DANGER


def saved_games(menu):
    c = SetupCanvas(menu, 'save')
    c.text('STAR ARMADA', (32, 20, 500, 30), 24)
    c.text('Saved games', (32, 65, 700, 36), 28)
    if menu.save_confirmation:
        menu.buttons = []
        c.panel((250, 196, 620, 308))
        all_files = menu.save_confirmation == 'ALL'
        c.text('DELETE ALL SAVED GAMES?' if all_files else 'DELETE SELECTED SAVE?',
               (278, 220, 564, 38), 24)
        c.text('All managed quick/autosaves, including files beyond the browser limit.'
               if all_files else os.path.basename(menu.save_confirmation),
               (278, 278, 564, 56), 16, MUTED, wrap=True)
        c.text('Permanent deletion. Settings and campaign progress are preserved.',
               (278, 346, 564, 60), 16, DANGER, wrap=True)
        control(c, (278, 426, 270, 42), 'CANCEL / ENTER / ESC', 'save_cancel_delete', primary=True)
        control(c, (570, 426, 272, 42), 'DELETE PERMANENTLY', 'save_confirm_delete', danger=True)
        c.finish()
        return
    c.text('CONTINUE A MATCH · newest file time first · UTC', (32, 112, 900, 24), 14, MUTED)
    paths = menu.save_paths[menu.save_page * 6:(menu.save_page + 1) * 6]
    pages = max(1, (len(menu.save_paths) + 5) // 6)
    c.panel((32, 148, 688, 420))
    if not paths:
        c.text('No saved games yet. Use F5 in a match, or enable Autosave.',
               (50, 182, 652, 60), 16, MUTED, wrap=True)
    for i, path in enumerate(paths):
        y = 160 + i * 66
        rect = pygame.Rect(44, y, 664, 60)
        menu.buttons.append(dict(rect=rect, action='select_save', payload=path))
        active = path == menu.save_selected
        pygame.draw.rect(c.surface, (28, 48, 53) if active else (14, 24, 33), rect, border_radius=4)
        pygame.draw.rect(c.surface, ACCENT if active else BORDER, rect, 1, border_radius=4)
        c.text(menu.save_metadata[path][1], (58, y + 7, 636, 26), 18)
        c.text(os.path.basename(path), (58, y + 34, 636, 22), 14, MUTED)
    c.panel((744, 148, 344, 420))
    c.text('Selected save', (762, 165, 308, 32), 24)
    selected = menu.save_selected
    if selected:
        _, label, detail = menu.save_metadata.get(selected, (0, 'Unknown time UTC', 'Unavailable'))
        c.text(label, (762, 214, 308, 60), 16, wrap=True)
        c.text(os.path.basename(selected), (762, 280, 308, 24), 14, MUTED)
        c.text(detail, (762, 322, 308, 94), 14, MUTED, wrap=True)
    else:
        c.text('Select a save to inspect details. Selection never loads a match.',
               (762, 214, 308, 100), 16, MUTED, wrap=True)
    control(c, (762, 428, 308, 38), 'LOAD SELECTED', 'load_save' if selected else None,
            selected, primary=bool(selected))
    control(c, (762, 478, 308, 38), 'DELETE SELECTED', 'save_delete' if selected else None,
            danger=bool(selected))
    c.text('F5 quicksave / F9 quickload in game.', (762, 534, 308, 22), 14, MUTED)
    c.text(f'Page {menu.save_page + 1}/{pages} / {len(menu.save_paths)} managed saves',
           (32, 582, 688, 24), 14, MUTED)
    control(c, (744, 582, 344, 36), 'DELETE ALL SAVES', 'save_delete_all', danger=True)
    c.text(menu.save_notice, (32, 608, 688, 24), 14, MUTED)
    pygame.draw.line(c.surface, BORDER, (32, 637), (1088, 637))
    control(c, (32, 650, 156, 36), 'Back / Esc', 'goto_main')
    control(c, (200, 650, 156, 36), 'Refresh', 'save_refresh')
    control(c, (744, 650, 166, 36), '‹ Previous', 'save_page' if menu.save_page else None, -1)
    control(c, (922, 650, 166, 36), 'Next ›', 'save_page' if menu.save_page + 1 < pages else None, 1)
    c.finish()
