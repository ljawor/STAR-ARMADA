"""Read-only campaign presentation; timing and camera belong to the view.

Two renderers share this state. `compose`/`draw_gl` are the legacy raster strips (an
overlay layer, still the fallback). `native_model` is the C++ vector briefing card the
window draws itself - see `render.mission_briefing` - and never rasterizes.
"""
from __future__ import annotations
import pygame


class CampaignCinematic:
    def __init__(self, mission, camera, *, reduced_motion=False, outcome=None):
        self.mission_id = mission.get('id')
        self.title = mission.get('name', mission.get('title', 'Mission'))
        objectives = [o.get('text', o.get('description', '')) for o in mission.get('objectives', [])]
        # Structured so the native card can mark and indent each objective; `caption`
        # keeps the legacy concatenation (and therefore compose's output) unchanged.
        self.briefing = str(mission.get('briefing', '') or '')
        self.objectives = [{'text': str(t), 'index': i} for i, t in enumerate(objectives) if t]
        self.caption = '\n'.join([self.briefing] + [entry['text'] for entry in self.objectives])
        self.native_pages = 1
        self.native_page = 0
        self._native_plans = {}
        self.camera = camera
        self.reduced_motion = reduced_motion
        self.outcome = outcome
        self.elapsed = 0.
        self.duration = 10. if outcome is None else 6.
        self.finished = False
        self.saved_view = (list(camera.target), camera.distance, camera.yaw,
                           camera.pitch, camera.follow_id)
        camera.follow_id = None
        camera.distance = max(camera.distance, 2400.)
        camera.pitch = 42.

    def update(self, dt):
        if self.finished:
            return
        self.elapsed += max(0., dt)
        if not self.reduced_motion:
            self.camera.yaw = self.saved_view[2] + min(self.elapsed, self.duration) * 1.5
        if self.elapsed >= self.duration:
            self.finish()

    def compose(self, width, height):
        """Measure every glyph rectangle; page captions rather than clip text."""
        surface = pygame.Surface((width, height), pygame.SRCALPHA)
        font = pygame.font.SysFont('menlo,consolas,monaco', 19)
        title_font = pygame.font.SysFont('menlo,consolas,monaco', 25, bold=True)
        margin = 40
        inner = width - 2 * margin - 40
        self.caption_rects = []

        def wrap(text, face):
            lines = []
            for paragraph in str(text).splitlines():
                line = ''
                # Character fallback makes even modded unbroken tokens total.
                for char in paragraph:
                    if line and face.size(line + char)[0] > inner:
                        split = line.rfind(' ')
                        if split > 0:
                            lines.append(line[:split])
                            line = line[split+1:] + char
                        else:
                            lines.append(line)
                            line = char
                    else:
                        line += char
                if line:
                    lines.append(line)
            return lines

        def text(line, face, y, color=(235,242,255)):
            glyph = face.render(line, True, color)
            rect = surface.blit(glyph, (margin + 20, y))
            self.caption_rects.append(rect)

        pygame.draw.rect(surface, (5,10,20,235), (margin, 24, width-2*margin, 108))
        text(self.outcome or 'CAMPAIGN / DEPLOYMENT', font, 39, (145,195,230))
        titles = wrap(self.title, title_font)
        title = titles[0] if titles else 'Mission'
        if len(titles) > 1:
            while title_font.size(title + '…')[0] > inner:
                title = title[:-1]
            title += '…'
        text(title, title_font, 78)
        panel_y = height - 274
        pygame.draw.rect(surface, (5,10,20,240), (margin,panel_y,width-2*margin,250))
        body = self.caption if self.outcome is None else (
            'Objectives secured. Return to fleet command.' if self.outcome == 'MISSION COMPLETE'
            else 'The operation has ended. Regroup and try again.')
        lines = wrap(body, font)
        rows = 7
        pages = max(1, (len(lines)+rows-1)//rows)
        self.duration = max(self.duration, pages * 5.)
        page = min(pages-1, int(self.elapsed / 5.))
        for i, line in enumerate(lines[page*rows:(page+1)*rows]):
            text(line, font, panel_y + 18 + i*26)
        text(f'Enter / Space / Esc / click to skip   {page+1}/{pages}', font,
             height - 62, (165,205,230))
        return surface

    def native_model(self, width, height):
        """The briefing as a complete C++ vector snapshot: text and geometry only.

        The window draws these ops itself (Noto atlas + bgfx triangles), below its own
        overlays and after the world HUD, so the mission card is crisp at the display
        resolution instead of being a stretched raster strip in `hud.ring`. Pagination
        and the presentation duration follow the same 5 s/page rule as `compose`.
        """
        from render import mission_briefing
        key = (int(width), int(height))
        measured = self._native_plans.get(key)
        if measured is None:
            # Text, wrapping and the card geometry do not change while the briefing
            # runs; measure once per viewport and re-slice the page each frame.
            measured = mission_briefing.plan(
                key[0], key[1], title=self.title, briefing=self.briefing,
                objectives=[entry['text'] for entry in self.objectives],
                outcome=self.outcome)
            self._native_plans[key] = measured
        layout = mission_briefing.page_layout(measured, self.elapsed)
        model = mission_briefing.emit(layout)[0]
        self.duration = max(self.duration, layout['pages'] * mission_briefing.SECONDS_PER_PAGE)
        self.native_pages, self.native_page = layout['pages'], layout['page']
        return model

    def draw_gl(self, width, height):
        from OpenGL import GL
        surface = self.compose(width, height)
        GL.glPushAttrib(GL.GL_ENABLE_BIT | GL.GL_COLOR_BUFFER_BIT |
                        GL.GL_DEPTH_BUFFER_BIT | GL.GL_TEXTURE_BIT | GL.GL_CURRENT_BIT)
        GL.glDisable(GL.GL_DEPTH_TEST)
        GL.glDisable(GL.GL_LIGHTING)
        GL.glDisable(GL.GL_CULL_FACE)
        GL.glDepthMask(GL.GL_FALSE)
        GL.glEnable(GL.GL_BLEND)
        GL.glBlendFunc(GL.GL_SRC_ALPHA, GL.GL_ONE_MINUS_SRC_ALPHA)
        GL.glEnable(GL.GL_TEXTURE_2D)
        texture = GL.glGenTextures(1)
        GL.glBindTexture(GL.GL_TEXTURE_2D, texture)
        GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_MIN_FILTER, GL.GL_LINEAR)
        GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_MAG_FILTER, GL.GL_LINEAR)
        GL.glTexImage2D(GL.GL_TEXTURE_2D,0,GL.GL_RGBA,width,height,0,
                        GL.GL_RGBA,GL.GL_UNSIGNED_BYTE,pygame.image.tobytes(surface,'RGBA',False))
        GL.glMatrixMode(GL.GL_PROJECTION)
        GL.glPushMatrix()
        GL.glLoadIdentity()
        GL.glOrtho(0,width,height,0,-1,1)
        GL.glMatrixMode(GL.GL_MODELVIEW)
        GL.glPushMatrix()
        GL.glLoadIdentity()
        GL.glColor4f(1,1,1,1)
        GL.glBegin(GL.GL_QUADS)
        for uv, pos in (((0,0),(0,0)),((1,0),(width,0)),((1,1),(width,height)),((0,1),(0,height))):
            GL.glTexCoord2f(*uv)
            GL.glVertex2f(*pos)
        GL.glEnd()
        GL.glPopMatrix()
        GL.glMatrixMode(GL.GL_PROJECTION)
        GL.glPopMatrix()
        GL.glMatrixMode(GL.GL_MODELVIEW)
        GL.glDeleteTextures([texture])
        GL.glPopAttrib()

    def handle_event(self, ev):
        if (ev.type == pygame.KEYDOWN and ev.key in
                (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE, pygame.K_ESCAPE)
                or ev.type == pygame.MOUSEBUTTONDOWN):
            self.finish()
        # All input belongs to the presentation until its frame ends.
        return True

    def finish(self):
        if self.finished:
            return
        self.finished = True
        target, distance, yaw, pitch, follow = self.saved_view
        self.camera.target = list(target)
        self.camera.distance, self.camera.yaw = distance, yaw
        self.camera.pitch, self.camera.follow_id = pitch, follow
        self.camera._proj = self.camera._view = None
