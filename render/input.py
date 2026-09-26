"""Input: translates mouse/keyboard into queued PlayerCommands + camera motion.

Follows the macOS pygame skill rules:
  - event-based key tracking (KEYDOWN/KEYUP sets), never key.get_pressed()
  - F10 toggles mouse grab
  - click window / pump handled by main loop
Player intent ALWAYS becomes a PlayerCommand on state.command_queue — the sim
layer owns all mutation (multiplayer-ready seam, spec §31).
"""
from __future__ import annotations

import pygame

from game.core.commands import (
    AttackCommand, AttackMoveCommand, BuildShipCommand, BuildStationCommand,
    ColonizeCommand, FleetCreateCommand, MoveCommand, ResearchCommand,
    StopCommand,
)
from game.data.store import DataStore


class InputController:
    def __init__(self, state, camera, hud, app):
        self.state = state
        self.camera = camera
        self.hud = hud
        self.app = app                      # app provides local_player, pause, exit
        self.keys: set[int] = set()         # event-tracked keys (macOS)
        self.selection: set[int] = set()
        self.groups: dict[int, set[int]] = {}   # control groups 1-9
        self.drag_start: tuple | None = None
        self.dragging = False
        self.right_drag: tuple | None = None
        self.grab_mouse = False
        self.local_player = 0
        self._pending_fleet: list[int] | None = None   # after G, awaiting number key
        # right-panel scroll context (set by HUD each frame)
        self._right_panel_rect = None
        self._panel_scroll_key = None

    # ------------------------------------------------------------------ events
    def handle_event(self, ev) -> None:
        st = self.state
        if ev.type == pygame.KEYDOWN:
            self.keys.add(ev.key)
            if ev.key == pygame.K_F10:
                self.grab_mouse = not self.grab_mouse
                pygame.event.set_grab(self.grab_mouse)
                pygame.mouse.set_visible(not self.grab_mouse)
            elif ev.key == pygame.K_ESCAPE:
                if self.hud.placement:
                    self.hud.placement = None       # cancel placement first
                elif st.game_over:
                    self.app.request_exit()
                else:
                    self.selection.clear()
                    self._pending_fleet = None
            elif pygame.K_1 <= ev.key <= pygame.K_9:
                if self._pending_fleet:
                    self._create_fleet(self._pending_fleet, formation="line")
                    self._control_group(ev.key - pygame.K_0)
                else:
                    self._control_group(ev.key - pygame.K_0)
            elif ev.key == pygame.K_g and self.selection:
                self._pending_fleet = sorted(self.selection)
                self.app.flash("press 1-9 to form fleet, or F for formation")
            elif ev.key == pygame.K_f and self._pending_fleet:
                self._create_fleet(self._pending_fleet, formation="line")
            elif ev.key == pygame.K_j and self.selection:
                self._queue_jump()
            elif ev.key == pygame.K_s and self.selection:
                st.queue_command(StopCommand(self.local_player,
                                             sorted(self.selection)))
            elif ev.key == pygame.K_h and self.selection:
                self.camera.follow_id = sorted(self.selection)[0]
            elif ev.key == pygame.K_SPACE:
                self.app.toggle_pause()
        elif ev.type == pygame.KEYUP:
            self.keys.discard(ev.key)
        elif ev.type == pygame.MOUSEBUTTONDOWN:
            if ev.button == 1:
                if self.hud.placement:
                    self._confirm_placement(ev.pos)
                    return
                if self._click_button(ev.pos):
                    return
                if self.hud.minimap_rect and \
                        self.hud.minimap_rect.collidepoint(ev.pos):
                    self._minimap_jump(ev.pos)
                else:
                    self.drag_start = ev.pos
                    self.dragging = True
            elif ev.button == 3:
                if self.hud.placement:
                    self.hud.placement = None       # right-click cancels
                    return
                self.right_drag = ev.pos
            elif ev.button == 4:
                if self._scroll_panel(-1):
                    return
                self.camera.zoom(0.88)
            elif ev.button == 5:
                if self._scroll_panel(1):
                    return
                self.camera.zoom(1.14)
        elif ev.type == pygame.MOUSEBUTTONUP:
            if ev.button == 1 and self.dragging:
                self._finish_box_select(ev.pos)
                self.dragging = False
            elif ev.button == 3:
                self._right_click(ev.pos)
                self.right_drag = None
        elif ev.type == pygame.MOUSEMOTION:
            if self.right_drag is not None:
                # rotate camera on right-drag (macOS sensitivity per skill)
                dx, dy = ev.rel
                self.camera.rotate(-dx * 0.25, -dy * 0.18)
        self._camera_keys()

    def _camera_keys(self) -> None:
        """Pan with arrows/WASD via event-tracked key set (skill: event-based)."""
        pan_speed = 1.0
        if pygame.K_LEFT in self.keys or pygame.K_a in self.keys:
            self.camera.pan(-14 * pan_speed, 0)
        if pygame.K_RIGHT in self.keys or pygame.K_d in self.keys:
            self.camera.pan(14 * pan_speed, 0)
        if pygame.K_UP in self.keys or pygame.K_w in self.keys:
            self.camera.pan(0, -14 * pan_speed)
        if pygame.K_DOWN in self.keys or pygame.K_s in self.keys:
            self.camera.pan(0, 14 * pan_speed)

    # ------------------------------------------------------------- panel scroll
    def _scroll_panel(self, direction: int) -> bool:
        """Wheel over a HUD scrollable list scrolls it; True if consumed."""
        mp = pygame.mouse.get_pos()
        for rect, key in self.hud.scroll_rects:
            if rect.collidepoint(mp):
                cur = self.hud.scroll.get(key, 0)
                self.hud.scroll[key] = max(0, cur + direction)
                return True
        return False

    # ------------------------------------------------------------- helpers
    def update(self) -> None:
        """Per-frame: follow camera."""
        if self.camera.follow_id is not None:
            e = self.state.entity(self.camera.follow_id)
            if e is None:
                self.camera.follow_id = None
            else:
                self.camera.target[0] = e.pos.x
                self.camera.target[2] = e.pos.z

    def _finish_box_select(self, end: tuple) -> None:
        assert self.drag_start is not None
        x0, y0 = self.drag_start
        x1, y1 = end
        if abs(x1 - x0) < 6 and abs(y1 - y0) < 6:
            self._single_select(x1, y1)
            return
        lo_x, hi_x = sorted((x0, x1))
        lo_y, hi_y = sorted((y0, y1))
        picked = set()
        for e in self.state.entities.values():
            if not e.alive or e.owner == -1:
                continue
            sp = self.camera.world_to_screen(e.pos.x, e.pos.y, e.pos.z)
            if sp is None:
                continue
            if lo_x <= sp[0] <= hi_x and lo_y <= sp[1] <= hi_y:
                picked.add(e.id)
        if picked:
            self.selection = picked
        else:
            self.selection.clear()

    def _single_select(self, mx: float, my: float) -> None:
        best, best_d = None, 28.0
        for e in self.state.entities.values():
            if not e.alive or e.owner == -1:
                continue
            sp = self.camera.world_to_screen(e.pos.x, e.pos.y, e.pos.z)
            if sp is None:
                continue
            d = ((sp[0] - mx) ** 2 + (sp[1] - my) ** 2) ** 0.5
            if d < best_d:
                best, best_d = e, d
        self.selection = {best.id} if best else set()

    def _click_button(self, pos: tuple) -> bool:
        """HUD buttons -> queued PlayerCommands. True if a button consumed click."""
        for btn in self.hud.buttons:
            if btn["rect"].collidepoint(pos):
                kind, pl = btn["kind"], btn["payload"]
                st, lp = self.state, self.local_player
                if kind == "build_station_place":
                    # arm placement mode: click on the field positions it
                    self.hud.placement = {
                        "builder_id": pl["builder_id"],
                        "station_kind": pl["station_kind"],
                        "ghost": None,
                    }
                    self.app.flash(f"select a position for {pl['station_kind']}")
                elif kind == "build_station":
                    b = st.entity(pl["builder_id"])
                    if b is None:
                        return True
                    pos3 = self._build_spot(b, pl["station_kind"])
                    st.queue_command(BuildStationCommand(
                        lp, pl["builder_id"], pl["station_kind"], pos3))
                    self.app.flash(f"constructing {pl['station_kind']}")
                elif kind == "build_ship":
                    st.queue_command(BuildShipCommand(
                        lp, pl["shipyard_id"], pl["ship_id"], 1))
                elif kind == "research":
                    st.queue_command(ResearchCommand(
                        lp, pl["station_id"], pl["tech_id"]))
                elif kind == "ability":
                    st.queue_command(self._ability_cmd(pl))
                return True
        return False

    # ------------------------------------------------------------- placement mode
    def update_placement(self) -> None:
        """Per-frame ghost position + validity for station placement."""
        pl = self.hud.placement
        if not pl:
            return
        mx, my = pygame.mouse.get_pos()
        w = self.camera.screen_to_world(mx, my)
        if w is None:
            pl["ghost"] = None
            return
        ds = DataStore.get()
        std = ds.stations.get(pl["station_kind"])
        rad = std.radius if std else 120.0
        valid = self._spot_clear(w[0], w[2], pl["station_kind"])
        # also show builder reach: too far -> invalid
        b = self.state.entity(pl["builder_id"])
        if b is not None:
            d2 = (b.pos.x - w[0]) ** 2 + (b.pos.z - w[2]) ** 2
            if d2 > 3500.0 ** 2:
                valid = False
        pl["ghost"] = {"sx": mx, "sy": my, "valid": valid, "radius": rad,
                       "world": w}

    def _confirm_placement(self, pos: tuple) -> bool:
        pl = self.hud.placement
        if not pl:
            return False
        self.hud.placement = None       # exit mode regardless of outcome
        w = self.camera.screen_to_world(*pos)
        if w is None:
            self.app.flash("cannot place there")
            return True
        valid = self._spot_clear(w[0], w[2], pl["station_kind"])
        if not valid:
            self.app.flash("position blocked")
            return True
        self.state.queue_command(BuildStationCommand(
            self.local_player, pl["builder_id"], pl["station_kind"],
            _vec3(w[0], 0.0, w[2])))
        self.app.flash(f"constructing {pl['station_kind']}")
        return True

    def _ability_cmd(self, pl: dict):
        from game.core.commands import AbilityCommand
        tgt = None
        if pl.get("targeted"):
            tgt = self.camera.screen_to_world(*pygame.mouse.get_pos())
        return AbilityCommand(self.local_player, pl["unit_ids"],
                              pl["ability_id"], target=tgt)

    def _build_spot(self, builder, station_kind: str):
        """Place near builder, clear of planets (simple probe)."""
        from game.core.vectors import Vec3
        for dist in (260.0, 380.0, 520.0, 700.0):
            for ang in (0.0, 1.0, 2.1, 3.1, 4.2, 5.2):
                x = builder.pos.x + dist * _cos(ang)
                z = builder.pos.z + dist * _sin(ang)
                if self._spot_clear(x, z, station_kind):
                    return Vec3(x, 0.0, z)
        return Vec3(builder.pos.x + 260.0, 0.0, builder.pos.z)

    def _spot_clear(self, x: float, z: float, station_kind: str) -> bool:
        ds = DataStore.get()
        std = ds.stations.get(station_kind)
        r = std.radius if std else 120.0
        for e in self.state.entities.values():
            if not e.alive or not (e.is_station or e.is_planet):
                continue
            d2 = (e.pos.x - x) ** 2 + (e.pos.z - z) ** 2
            if d2 < (e.radius + r + 80.0) ** 2:
                return False
        return True

    def _right_click(self, pos: tuple) -> None:
        if not self.selection:
            return
        st, lp = self.state, self.local_player
        ids = sorted(self.selection)
        w = self.camera.screen_to_world(*pos)
        # target priority: enemy unit > colonizable planet > ground move
        target = self._pick_target(pos)
        if target is not None:
            e = target
            if e.is_planet and e.colonized_by is None:
                colonizers = [i for i in ids
                              if (sd := _ship_data(st.entity(i))) is not None
                              and sd.can_colonize]
                if colonizers:
                    st.queue_command(ColonizeCommand(lp, colonizers, e.id))
                    self.app.flash("colonization ordered")
                    return
            st.queue_command(AttackCommand(lp, ids, e.id))
            self.app.flash(f"attack {DataStore.get().unit_name(e)}")
        elif w is not None:
            st.queue_command(AttackMoveCommand(lp, ids, w))
            self.app.flash("attack-move")

    def _pick_target(self, pos: tuple):
        best, best_d = None, 30.0
        for e in self.state.entities.values():
            if not e.alive or e.owner == -1 or e.is_planet and e.colonized_by is not None:
                continue
            sp = self.camera.world_to_screen(e.pos.x, e.pos.y, e.pos.z)
            if sp is None:
                continue
            d = ((sp[0] - pos[0]) ** 2 + (sp[1] - pos[1]) ** 2) ** 0.5
            if d < best_d:
                best, best_d = e, d
        return best

    def _queue_jump(self) -> None:
        from game.core.commands import JumpCommand
        from game.core.vectors import Vec3
        ids = sorted(self.selection)
        if not ids:
            return
        # jump toward the map center by default (prototype: no jump-point UI yet)
        tgt = Vec3(0.0, 0.0, 0.0)
        self.state.queue_command(JumpCommand(self.local_player, ids, tgt))
        self.app.flash("hyperspace jump charging")

    def _control_group(self, num: int) -> None:
        if pygame.K_LSHIFT in self.keys or pygame.K_RSHIFT in self.keys:
            cur = self.groups.get(num, set())
            self.selection = set(self.selection) | cur
        else:
            self.groups[num] = set(self.selection)
            self.selection = set(self.groups[num])

    def _create_fleet(self, ids: list, formation: str = "line") -> None:
        self.state.queue_command(FleetCreateCommand(
            self.local_player, ids, name=f"Fleet {len(self.state.fleets) + 1}",
            formation=formation))
        self._pending_fleet = None
        self.app.flash(f"fleet formed ({formation})")

    def _minimap_jump(self, pos: tuple) -> None:
        r = self.hud.minimap_rect
        bounds = max(1.0, self.state.map_info.bounds)
        half = bounds / 2.0
        wx = (pos[0] - r.centerx) / (r.width / 2 - 4) * half
        wz = (pos[1] - r.centery) / (r.height / 2 - 4) * half
        self.camera.target[0] = wx
        self.camera.target[2] = wz
        self.camera.clamp_target()


def _ship_data(e):
    if e is None:
        return None
    return DataStore.get().ships.get(e.data_id)


def _vec3(x, y, z):
    from game.core.vectors import Vec3
    return Vec3(x, y, z)


def _cos(a):
    import math
    return math.cos(a)


def _sin(a):
    import math
    return math.sin(a)