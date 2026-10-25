"""Read-only, bounded help/tutorial panels; never saved or replayed.

Integration: create PresentationOverlay(width, height, settings, local_player).
Route events before InputController; skip world dispatch when consumed. F1 opens
modal help (clear InputController.keys in the caller when opening so a held pan
key cannot stick). Help does not pause simulation by itself. After HUD drawing,
call draw(state, input_controller, width=..., height=...,
blocked_rects=hud.blocked_rects) then draw_gl(). Pass the CURRENT HUD rectangles
before adding overlay.panel_rects to hud.blocked_rects; HUD.render rebuilds its
list each frame. Hints flow around those real rectangles and omit themselves if
no complete panel fits. Help is modal for input but does not pause simulation.
apply_settings(settings) copies and validates view preferences. cleanup()
releases only this overlay's lazily allocated texture, before context teardown.
"""
from __future__ import annotations

import pygame
from render.menus import validate_presentation_settings

HELP_PAGES = (
    ('KEYBOARD & CONTROLS', (
        'Select: left click or left drag. Shift adds to selection.',
        'Orders: right click a location to move or a detected enemy to attack.',
        'Camera: arrows or W A S D pan the view (S pans too, even with units selected).',
        'Mouse wheel: zoom. Q / E: rotate. Minimap click: recenter.',
        'Space: focus selection. H: follow selected unit. M: toggle follow.',
        'X: tactical overview. P: pause. F10: toggle mouse grab.',
        'Ctrl/Cmd + 1-9: assign control group. 1-9: recall; Shift: add.',
        'F: fleet panel. G then 1-9: create fleet. J: jump destination.',
        'Backspace: stop selected units. Esc: cancel; Esc twice: leave match.',
        'F1 / Esc: close help. Page Up/Down: help pages.',
    )),
    ('RECOVERY & SUPPORT', (
        'Board: select an operating boarding-capable ship, press B, then click a detected enemy hull.',
        'All target shields must be down. Approach boarding range; your party travels in a physical craft.',
        'Load passengers: select an operating crew transport near a friendly recovery base, then press L.',
        'Deliver passengers: with cargo loaded, press R and click an owned hull missing crew.',
        'Life support must meet the recovery threshold; see contextual drill hints for its current value.',
        'Equipment repair does NOT replace crew. Select an operating constructor and use its Repair button, then click an owned hull.',
        'The drill begins with healthy life support on both abandoned targets; do not build a constructor unless repairs become necessary.',
        'Settings: tutorial hints, high contrast panels and reduced motion are optional. These are targeted panels, not whole-game scaling.',
        'F1 / Esc: close help. Page Up/Down: help pages.',
    )),
)


class PresentationOverlay:
    def __init__(self, width: int, height: int, settings: dict | None = None,
                 local_player: int = 0):
        pygame.font.init()
        self.font = pygame.font.SysFont('helvetica,arial', 18)
        self.title_font = pygame.font.SysFont('helvetica,arial', 24, bold=True)
        self.width, self.height = width, height
        self.surface = pygame.Surface((width, height), pygame.SRCALPHA)
        self.local_player = local_player
        self.help_visible = False
        self.help_page = 0
        self.panel_rects = []
        self.text_bounds = []
        self.overlay_tex = None
        self.apply_settings(settings or {})

    def apply_settings(self, settings: dict) -> None:
        self.settings = validate_presentation_settings(settings)

    def handle_event(self, event) -> bool:
        if event.type == pygame.KEYDOWN and event.key == pygame.K_F1:
            if not getattr(event, 'repeat', False):
                self.help_visible = not self.help_visible
            return True
        if event.type == pygame.KEYUP and event.key == pygame.K_F1:
            return True
        if self.help_visible:
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    self.help_visible = False
                elif event.key in (pygame.K_PAGEDOWN, pygame.K_RIGHT):
                    self.help_page = min(len(HELP_PAGES) - 1, self.help_page + 1)
                elif event.key in (pygame.K_PAGEUP, pygame.K_LEFT):
                    self.help_page = max(0, self.help_page - 1)
            return event.type in (pygame.KEYDOWN, pygame.KEYUP, pygame.TEXTINPUT,
                                  pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP,
                                  pygame.MOUSEMOTION, pygame.MOUSEWHEEL)
        if event.type in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP, pygame.MOUSEMOTION):
            return any(rect.collidepoint(event.pos) for rect in self.panel_rects)
        if event.type == pygame.MOUSEWHEEL:
            pos = getattr(event, 'pos', None)
            if pos is None and pygame.display.get_init():
                pos = pygame.mouse.get_pos()
            return pos is not None and any(rect.collidepoint(pos) for rect in self.panel_rects)
        return False

    def _wrap(self, text: str, font, width: int) -> list[str]:
        # Character fallback bounds long mod tokens as well as ordinary words.
        lines, line = [], ''
        for word in text.split():
            candidate = (line + ' ' + word).strip()
            if font.size(candidate)[0] <= width:
                line = candidate
                continue
            if line:
                lines.append(line)
                line = ''
            for char in word:
                if line and font.size(line + char)[0] > width:
                    lines.append(line)
                    line = ''
                line += char
        if line:
            lines.append(line)
        return lines

    def _panel(self, title: str, paragraphs: list[str], rect, font=None):
        font = font or self.font
        high = self.settings['high_contrast_ui']
        foreground = (255, 255, 255) if high else (232, 239, 255)
        pygame.draw.rect(self.surface, (0, 0, 0, 255) if high else (10, 16, 30, 245), rect, border_radius=8)
        pygame.draw.rect(self.surface, foreground, rect, 2, border_radius=8)
        self.panel_rects.append(rect)
        y = rect.y + 16
        for text, face in [(title, self.title_font)] + [(p, font) for p in paragraphs]:
            for line in self._wrap(text, face, rect.w - 32):
                rendered = face.render(line, True, foreground)
                bounds = rendered.get_rect(topleft=(rect.x + 16, y))
                if bounds.bottom > rect.bottom - 16:
                    raise ValueError('presentation panel exceeds its measured layout')
                self.surface.blit(rendered, bounds)
                self.text_bounds.append((line, bounds))
                y += face.get_linesize() + 3
            y += 5

    def tutorial_paragraphs(self, state, selection) -> list[str]:
        """Read the drill's current objective and knowledge-limited selection."""
        if state is None:
            return []
        mission = getattr(state, '_mission_system', None)
        snapshot = getattr(state, 'mission_state', None) or {}
        definition = (mission.mission if mission else snapshot.get('definition')) or {}
        if (state.mission_id or definition.get('id')) != 'm00_recovery_drill':
            return []
        objectives = mission.objectives if mission else snapshot.get('objectives', [])
        completed = mission.completed if mission else snapshot.get('completed', False)
        failed = mission.failed if mission else snapshot.get('failed', False)
        if failed:
            return ['Status: DRILL FAILED. Esc: leave match.']
        if completed:
            return ['Status: DRILL COMPLETE. Esc: leave match.']
        objective = next((o for o in objectives if o.get('active', True) and not o.get('done')), None)
        if objective is None:
            return []
        from game.data.store import DataStore
        from game.systems.crew_recovery import recovery_rules
        from game.systems.boarding import boarding_capable
        threshold = recovery_rules()['support_threshold']
        selected = []
        for ident in sorted(set(selection or ())):
            entity = state.entity(ident)
            if entity is not None and (entity.owner == self.local_player or state.can_see(self.local_player, ident)):
                if entity.alive:
                    selected.append(entity)
        owned = [e for e in selected if e.owner == self.local_player]
        full_recovery = objective.get('type') == 'recover_crew' and objective.get('full_complement')
        goal = ('Goal: restore the captured corvette to 100% onboard crew.' if full_recovery
                else 'Goal: deliver ' + str(objective.get('count', 4)) + ' personnel.'
                if objective.get('type') == 'recover_crew' else 'Goal: board and capture the hull.')
        recovery_hint = ('Automatic recruitment near a friendly recovery base OR crew transport delivery both count. '
                         'Equipment repair does NOT replace crew.')
        if not selected:
            return [goal, recovery_hint if full_recovery else
                    'Select your cruiser to board (B), or crew transport to load (L). F1: controls.']
        transport = next((e for e in owned if (DataStore.get().ships.get(e.data_id) is not None
                          and DataStore.get().ships[e.data_id].crew_capacity > 0)), None)
        entity = transport or next(iter(owned), selected[0])
        support = entity.subsystem_fraction('life_support')
        if entity.owner != self.local_player:
            if (not state.is_enemy(self.local_player, entity.owner) or entity.is_planet
                    or not (entity.is_ship or entity.is_squadron or entity.is_station)):
                return [goal, 'Select your cruiser to board (B), or crew transport to load (L). F1: controls.']
            shields = 'UP - lower all shields' if entity.total_shield() > 0 else 'DOWN'
            return [goal, 'Detected target shields: ' + shields + '.',
                    'Select your cruiser; B then click this detected hull.']
        status = f'Crew: {entity.crew}/{entity.max_crew}. Life support: {support:.0%}.'
        if support < threshold:
            instruction = f'Repair life support to {threshold:.0%} first. Equipment repair does NOT replace crew.'
        elif full_recovery and transport is None:
            instruction = recovery_hint
        elif entity.crew == 0:
            instruction = 'Deliver passengers from a crew transport. Equipment repair does NOT replace crew.'
        elif transport is not None:
            status += f' Passengers: {entity.crew_cargo}.'
            instruction = ('L: load near a friendly recovery base.' if entity.crew_cargo <= 0
                           else 'R: deliver to the owned hull missing crew; click target.')
        elif boarding_capable(entity):
            instruction = 'B: board a detected enemy. All shields must be DOWN; approach boarding range.'
        else:
            instruction = 'Select your cruiser (B) or crew transport (L / R). F1: controls.'
        return [goal, status, instruction]

    def draw(self, state, input_controller=None, *, width=None, height=None,
             selection=None, local_player=None, blocked_rects=(),
             mission_managed_by_hud=False) -> pygame.Surface:
        """Paint to a transparent Surface; draw_gl uploads it after the HUD.

        selection may be an iterable of IDs or an InputController (second arg).
        Only owned/currently detected selected entities may contribute hints.
        """
        width, height = width or self.width, height or self.height
        if (width, height) != (self.width, self.height):
            self.width, self.height = width, height
            self.surface = pygame.Surface((width, height), pygame.SRCALPHA)
        self.surface.fill((0, 0, 0, 0))
        self.panel_rects, self.text_bounds = [], []
        if self.help_visible:
            title, paragraphs = HELP_PAGES[self.help_page]
            rect = pygame.Rect((width - min(800, width - 64)) // 2, 72,
                               min(800, width - 64), height - 144)
            self._panel(f'{title} - {self.help_page + 1}/{len(HELP_PAGES)}', list(paragraphs), rect)
        elif self.settings['tutorial_hints'] and not mission_managed_by_hud:
            if local_player is not None:
                self.local_player = local_player
            if selection is None:
                selection = getattr(input_controller, 'selection', input_controller)
                if hasattr(input_controller, 'local_player'):
                    self.local_player = input_controller.local_player
            paragraphs = self.tutorial_paragraphs(state, selection)
            if paragraphs:
                panel_width = min(400, width - 680)
                lines = len(self._wrap('RECOVERY DRILL', self.title_font, panel_width - 32))
                panel_height = 32 + lines * (self.title_font.get_linesize() + 3) + 5
                panel_height += sum(len(self._wrap(p, self.font, panel_width - 32)) *
                                    (self.font.get_linesize() + 3) + 5 for p in paragraphs)
                rect = pygame.Rect((width - panel_width) // 2, 46, panel_width, panel_height)
                # Flow below real mission/controls geometry, not a fixed y.
                # If the HUD fills the available corridor, omit optional hints
                # rather than cover controls or render a clipped instruction.
                occupied = [pygame.Rect(r).inflate(0, 12) for r in blocked_rects]
                for candidate_y in sorted({46} | {r.bottom for r in occupied}):
                    rect.y = candidate_y
                    if rect.bottom <= height - 110 and not any(rect.colliderect(r) for r in occupied):
                        self._panel('RECOVERY DRILL', paragraphs, rect)
                        break
        return self.surface

    def draw_gl(self) -> None:
        """Empty overlays are safe without an SDL/GL context."""
        if not self.panel_rects:
            return
        display = pygame.display.get_surface()
        if display is None or not display.get_flags() & pygame.OPENGL:
            raise RuntimeError('presentation draw_gl requires a real SDL OpenGL context')
        from OpenGL import GL as gl
        # Save before allocation/upload: first draw must be as state-neutral as
        # subsequent draws. Texture ownership is local, never the HUD's texture.
        active = int(gl.glGetIntegerv(gl.GL_ACTIVE_TEXTURE))
        mode = int(gl.glGetIntegerv(gl.GL_MATRIX_MODE))
        program = int(gl.glGetIntegerv(gl.GL_CURRENT_PROGRAM))
        unpack_keys = (gl.GL_UNPACK_ALIGNMENT, gl.GL_UNPACK_ROW_LENGTH,
                       gl.GL_UNPACK_SKIP_ROWS, gl.GL_UNPACK_SKIP_PIXELS)
        unpack = [int(gl.glGetIntegerv(key)) for key in unpack_keys]
        gl.glActiveTexture(gl.GL_TEXTURE0)
        gl.glPushAttrib(gl.GL_ENABLE_BIT | gl.GL_COLOR_BUFFER_BIT |
                        gl.GL_DEPTH_BUFFER_BIT | gl.GL_TEXTURE_BIT |
                        gl.GL_CURRENT_BIT | gl.GL_TRANSFORM_BIT)
        matrices = []
        try:
            gl.glUseProgram(0)
            # Fixed-function multitexturing otherwise tints UI with the last
            # world's material on another unit. GL_TEXTURE_BIT/ENABLE_BIT
            # preserve all units, not just the upload unit.
            for unit in range(int(gl.glGetIntegerv(gl.GL_MAX_TEXTURE_UNITS))):
                gl.glActiveTexture(gl.GL_TEXTURE0 + unit)
                for target in (gl.GL_TEXTURE_1D, gl.GL_TEXTURE_2D,
                               gl.GL_TEXTURE_3D, gl.GL_TEXTURE_CUBE_MAP):
                    gl.glDisable(target)
            gl.glActiveTexture(gl.GL_TEXTURE0)
            for key, value in zip(unpack_keys, (1, 0, 0, 0)):
                gl.glPixelStorei(key, value)
            if self.overlay_tex is None:
                self.overlay_tex = int(gl.glGenTextures(1))
            gl.glBindTexture(gl.GL_TEXTURE_2D, self.overlay_tex)
            for key in (gl.GL_TEXTURE_MIN_FILTER, gl.GL_TEXTURE_MAG_FILTER):
                gl.glTexParameteri(gl.GL_TEXTURE_2D, key, gl.GL_LINEAR)
            for key in (gl.GL_TEXTURE_WRAP_S, gl.GL_TEXTURE_WRAP_T):
                gl.glTexParameteri(gl.GL_TEXTURE_2D, key, gl.GL_CLAMP_TO_EDGE)
            gl.glTexImage2D(gl.GL_TEXTURE_2D, 0, gl.GL_RGBA, self.width, self.height,
                            0, gl.GL_RGBA, gl.GL_UNSIGNED_BYTE,
                            pygame.image.tobytes(self.surface, 'RGBA'))
            for matrix in (gl.GL_PROJECTION, gl.GL_MODELVIEW, gl.GL_TEXTURE):
                gl.glMatrixMode(matrix)
                gl.glPushMatrix()
                matrices.append(matrix)
                gl.glLoadIdentity()
                if matrix == gl.GL_PROJECTION:
                    gl.glOrtho(0, self.width, self.height, 0, -1, 1)
            for capability in (gl.GL_LIGHTING, gl.GL_DEPTH_TEST, gl.GL_CULL_FACE,
                               gl.GL_SCISSOR_TEST, gl.GL_STENCIL_TEST,
                               gl.GL_ALPHA_TEST, gl.GL_FOG):
                gl.glDisable(capability)
            gl.glDepthMask(gl.GL_FALSE)
            gl.glEnable(gl.GL_TEXTURE_2D)
            gl.glTexEnvi(gl.GL_TEXTURE_ENV, gl.GL_TEXTURE_ENV_MODE, gl.GL_MODULATE)
            gl.glEnable(gl.GL_BLEND)
            gl.glBlendEquation(gl.GL_FUNC_ADD)
            gl.glBlendFunc(gl.GL_SRC_ALPHA, gl.GL_ONE_MINUS_SRC_ALPHA)
            gl.glColor4f(1, 1, 1, 1)
            gl.glBegin(gl.GL_QUADS)
            # Verbatim HUD UV convention: unflipped SDL bytes, t=0 at top.
            gl.glTexCoord2f(0, 0); gl.glVertex2f(0, 0)
            gl.glTexCoord2f(1, 0); gl.glVertex2f(self.width, 0)
            gl.glTexCoord2f(1, 1); gl.glVertex2f(self.width, self.height)
            gl.glTexCoord2f(0, 1); gl.glVertex2f(0, self.height)
            gl.glEnd()
        finally:
            for matrix in reversed(matrices):
                gl.glMatrixMode(matrix)
                gl.glPopMatrix()
            gl.glPopAttrib()
            for key, value in zip(unpack_keys, unpack):
                gl.glPixelStorei(key, value)
            gl.glUseProgram(program)
            gl.glActiveTexture(active)
            gl.glMatrixMode(mode)

    def cleanup(self) -> None:
        """Call before context teardown; unused overlays own no GL resources."""
        if self.overlay_tex is not None:
            from OpenGL.GL import glDeleteTextures
            glDeleteTextures([self.overlay_tex])
            self.overlay_tex = None


