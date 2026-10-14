"""Clean Classic LAN recovery panel. View-only, one explicit abort action."""
from __future__ import annotations

import math
import pygame
from render.clean_classic import INK, MUTED, ACCENT, BORDER, PANEL
from render.presentation import PresentationOverlay


class RecoveryOverlay(PresentationOverlay):
    def __init__(self, width, height):
        super().__init__(width, height)
        self.rendered_text = []
        self.panel_rect = pygame.Rect(0, 0, 0, 0)
        self.cancel_rect = pygame.Rect(0, 0, 0, 0)

    def handle_event(self, event):
        """True means abort (not merely consumed); the app gates other input."""
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            return not getattr(event, 'repeat', False)
        return (event.type == pygame.MOUSEBUTTONUP and event.button == 1
                and self.cancel_rect.collidepoint(event.pos))

    def draw(self, snapshot, *, width=None, height=None):
        width, height = width or self.width, height or self.height
        if (width, height) != (self.width, self.height):
            self.width, self.height = width, height
            self.surface = pygame.Surface((width, height), pygame.SRCALPHA)
        self.surface.fill((0, 0, 0, 110))
        size = max(16, min(24, round(height / 30)))
        self.font = pygame.font.SysFont('helvetica,arial', size)
        self.title_font = pygame.font.SysFont('helvetica,arial', size + 8, bold=True)
        line = self.font.get_linesize() + 10
        panel_height = line * 6 + 36
        self.panel_rect = pygame.Rect(0, 0, min(740, width - 32), panel_height)
        self.panel_rect.center = (width // 2, height // 2)
        pygame.draw.rect(self.surface, PANEL, self.panel_rect, border_radius=5)
        pygame.draw.rect(self.surface, BORDER, self.panel_rect, 1, border_radius=5)
        self.panel_rects = [self.panel_rect]
        self.rendered_text, self.text_bounds = [], []
        x, y = self.panel_rect.x + 20, self.panel_rect.y + 16

        def text(value, font=None, color=INK):
            nonlocal y
            font = font or self.font
            while font.size(value)[0] > self.panel_rect.w - 40:
                value = value[:-2] + '…'
            glyph = font.render(value, True, color)
            rect = glyph.get_rect(topleft=(x, y))
            self.surface.blit(glyph, rect)
            self.rendered_text.append(value)
            self.text_bounds.append(rect)
            y += line

        text('RECONNECTING LAN', self.title_font)
        missing = snapshot.get('missing', [])
        text('Waiting for: ' + (', '.join(f'Player {int(pid) + 1}' for pid in missing)
                                  if missing else 'peer synchronization'), color=MUTED)
        remaining = snapshot.get('remaining', 0.)
        text(f'Time remaining: {max(0., float(remaining)):.1f}s' if remaining is not None
             else 'Waiting for recovery handshake', color=MUTED)
        phase = str(snapshot.get('phase', 'waiting')).replace('_', ' ').capitalize()
        if snapshot.get('progress') is not None:
            progress = float(snapshot['progress'])
            progress = max(0., min(1., progress)) if math.isfinite(progress) else 0.
            text(f'{phase} · {progress:.0%}')
        else:
            # Backend phase is genuine progress; never invent byte percentages.
            target = snapshot.get('tick')
            text(f'Phase: {phase}' + (f' · barrier tick {target}' if target is not None else ''))
        text('Simulation paused · camera controls remain available', color=MUTED)
        self.cancel_rect = pygame.Rect(x, y, self.panel_rect.w - 40, line)
        pygame.draw.rect(self.surface, ACCENT, self.cancel_rect, border_radius=4)
        text('Cancel reconnect and leave match  ·  Escape', color=(16, 42, 42))
