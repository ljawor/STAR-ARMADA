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
        self.drag_cur: tuple | None = None      # live drag corner (box-select)
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
        if ev.type == pygame.WINDOWFOCUSLOST:
            self.keys.clear()
            self.dragging = False
            self.drag_start = self.drag_cur = self.right_drag = None
            return
        if ev.type == pygame.KEYDOWN:
            if ev.key in self.keys:
                return                         # ignore OS key-repeat for toggles
            self.keys.add(ev.key)
            if ev.key == pygame.K_F10:
                self.grab_mouse = not self.grab_mouse
                pygame.event.set_grab(self.grab_mouse)
                pygame.mouse.set_visible(not self.grab_mouse)
            elif ev.key == pygame.K_ESCAPE:
                if self.hud.placement:
                    self.hud.placement = None       # cancel placement first
                elif self.hud.fleet_panel:
                    self.hud.fleet_panel = False
                    self._pending_fleet = None
                elif self._pending_fleet:
                    self._pending_fleet = None
                    self.app.flash("fleet creation cancelled")
                else:
                    self.keys.clear()
                    self.app.request_exit()
            elif pygame.K_1 <= ev.key <= pygame.K_9:
                num = ev.key - pygame.K_0
                if self._pending_fleet:
                    self._create_fleet(self._pending_fleet, formation="line")
                    self._control_group(num, assign=True)
                else:
                    self._control_group(num, assign=self._ctrl_down(ev))
            elif ev.key == pygame.K_g and self.selection:
                self._pending_fleet = sorted(self.selection)
                self.app.flash("press 1-9 to form fleet, or F for formation")
            elif ev.key == pygame.K_f:
                self.hud.fleet_panel = not self.hud.fleet_panel
                self._pending_fleet = None
                if self.hud.fleet_panel:
                    self.hud.placement = None
                    self.app.flash("fleet panel: choose formation and commander")
            elif ev.key == pygame.K_j and self.selection:
                self._queue_jump()
            elif ev.key == pygame.K_s and self.selection:
                st.queue_command(StopCommand(self.local_player,
                                             sorted(self.selection)))
            elif ev.key == pygame.K_h and self.selection:
                self.camera.follow_id = sorted(self.selection)[0]
            elif ev.key == pygame.K_p:
                self.app.toggle_pause()
            elif ev.key == pygame.K_SPACE:
                self._follow_selection()
            elif ev.key == pygame.K_x:
                self.camera.follow_id = None
                self.camera.target = [0.0, 0.0, 0.0]
                self.camera.distance = self.camera.zoom_limits[1]
                self.camera.pitch = 89.0
                self.app.flash("tactical overview")
            elif ev.key == pygame.K_m:
                if self.camera.follow_id is None:
                    self._follow_selection()
                else:
                    self.camera.follow_id = None
                    self.app.flash("free camera")
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
                self.drag_start = None
                self.drag_cur = None
            elif ev.button == 3:
                self._right_click(ev.pos)
                self.right_drag = None
        elif ev.type == pygame.MOUSEMOTION:
            if self.dragging:
                # live corner so the HUD can draw the selection rectangle
                self.drag_cur = ev.pos
            if self.right_drag is not None:
                # rotate camera on right-drag (macOS sensitivity per skill)
                dx, dy = ev.rel
                self.camera.rotate(-dx * 0.25, -dy * 0.18)

    def _camera_keys(self, dt: float) -> None:
        """Pan with arrows/WASD via event-tracked key set (skill: event-based)."""
        dt = max(0.0, dt)
        pan_speed = dt * 30.0
        pan_down = (pygame.K_DOWN in self.keys or
                    (pygame.K_s in self.keys and not self.selection))
        if self.keys & {pygame.K_LEFT, pygame.K_RIGHT, pygame.K_UP,
                        pygame.K_a, pygame.K_d, pygame.K_w} or pan_down:
            self.camera.follow_id = None
        if pygame.K_q in self.keys:
            self.camera.rotate(-60.0 * dt, 0)
        if pygame.K_e in self.keys:
            self.camera.rotate(60.0 * dt, 0)
        if pygame.K_LEFT in self.keys or pygame.K_a in self.keys:
            self.camera.pan(-14 * pan_speed, 0)
        if pygame.K_RIGHT in self.keys or pygame.K_d in self.keys:
            self.camera.pan(14 * pan_speed, 0)
        if pygame.K_UP in self.keys or pygame.K_w in self.keys:
            self.camera.pan(0, -14 * pan_speed)
        if pan_down:
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
    def _follow_selection(self) -> None:
        """Follow the first live selected unit without changing simulation time."""
        entity = next((e for i in sorted(self.selection)
                       if (e := self.state.entity(i)) is not None), None)
        if entity is None:
            self.app.flash("select a unit to follow")
            return
        self.camera.follow_id = entity.id
        self.camera.target[0] = entity.pos.x
        self.camera.target[2] = entity.pos.z
        self.app.flash("following selection")

    def update(self, dt: float = 1.0 / 30.0) -> None:
        """Per-frame held-key motion and follow camera, not event-rate motion."""
        self._camera_keys(dt)
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
                if kind in {"fleet_formation", "fleet_commander",
                            "fleet_create", "fleet_close"} and not self.hud.fleet_panel:
                    # Buttons remain from the last render until the next frame.
                    # Consume stale controls without acting or selecting the scene.
                    return True
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
                elif kind == "fleet_formation":
                    self.hud.fleet_formation = pl["formation"]
                elif kind == "fleet_commander":
                    self.hud.fleet_commander = pl["commander"]
                elif kind == "fleet_create":
                    ids = [i for i in pl["unit_ids"]
                           if (e := st.entity(i)) is not None
                           and e.owner == lp and e.is_ship]
                    if ids:
                        self._create_fleet(ids, self.hud.fleet_formation,
                                           self.hud.fleet_commander)
                        self.hud.fleet_panel = False
                    else:
                        self.app.flash("select your ships to form a fleet")
                elif kind == "fleet_close":
                    self.hud.fleet_panel = False
                elif kind == "ability":
                    st.queue_command(self._ability_cmd(pl))
                return True
        return False

    # ------------------------------------------------------------- placement mode
    def update_placement(self) -> None:
        """Per-frame ghost position + validity for station placement.

        Uses the SAME validator as the sim (ConstructionSystem.check_site) so
        a green ghost always means the build will be accepted — plus a reason
        string for the red case.
        """
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
        b = self.state.entity(pl["builder_id"])
        valid, reason = True, ""
        if b is None:
            valid, reason = False, "no builder selected"
        else:
            from game.systems.construction import ConstructionSystem
            # reach manager via state-free instantiation: check_site needs
            # only state+ds; grab the live system from the manager if present
            cs = getattr(self.state, "_construction_system", None)
            if cs is None:
                cs = ConstructionSystem(self.state)
            valid, reason = cs.check_site(pl["station_kind"], w, b)
            # Proximity is enforced at order time (start_station), not by
            # check_site — surfaced here so the ghost goes red and says why
            # instead of the click being silently rejected.
            if valid and hasattr(cs, "too_far_to_build"):
                far, d, lim = cs.too_far_to_build(w, b)
                if far:
                    valid = False
                    reason = (f"constructor {d - lim:,.0f}u out of range "
                              f"({d:,.0f}u, max {lim:,.0f}u)")
        pl["ghost"] = {"sx": mx, "sy": my, "valid": valid, "reason": reason,
                       "radius": rad, "world": w}

    def _confirm_placement(self, pos: tuple) -> bool:
        pl = self.hud.placement
        if not pl:
            return False
        self.hud.placement = None       # exit mode regardless of outcome
        w = self.camera.screen_to_world(*pos)
        if w is None:
            self.app.flash("cannot place there")
            return True
        b = self.state.entity(pl["builder_id"])
        if b is None:
            self.app.flash("no builder selected")
            return True
        from game.systems.construction import ConstructionSystem
        cs = getattr(self.state, "_construction_system", None)
        if cs is None:
            cs = ConstructionSystem(self.state)
        valid, reason = cs.check_site(pl["station_kind"], w, b)
        if not valid:
            # tell the player WHY in language, not just a red circle
            self.app.flash(f"cannot build {pl['station_kind'].replace('_', ' ')}: "
                           f"{reason}")
            return True
        self.state.queue_command(BuildStationCommand(
            self.local_player, pl["builder_id"], pl["station_kind"],
            _vec3(w[0], 0.0, w[2])))
        self.app.flash(f"constructing {pl['station_kind'].replace('_', ' ')}")
        return True

    def _ability_cmd(self, pl: dict):
        from game.core.commands import AbilityCommand
        tgt = None
        if pl.get("targeted"):
            tgt = self.camera.screen_to_world(*pygame.mouse.get_pos())
        return AbilityCommand(self.local_player, pl["unit_ids"],
                              pl["ability_id"], target=tgt)

    def _build_spot(self, builder, station_kind: str):
        """Place near builder, first spot that passes the FULL sim validator."""
        from game.core.vectors import Vec3
        cs = getattr(self.state, "_construction_system", None)
        for dist in (260.0, 380.0, 520.0, 700.0):
            for ang in (0.0, 1.0, 2.1, 3.1, 4.2, 5.2):
                x = builder.pos.x + dist * _cos(ang)
                z = builder.pos.z + dist * _sin(ang)
                if cs is not None and cs.check_site(
                        station_kind, (x, 0.0, z), builder)[0]:
                    return Vec3(x, 0.0, z)
                if cs is None and self._spot_clear(x, z, station_kind):
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

    def _ctrl_down(self, ev=None) -> bool:
        """Is Ctrl (or Cmd on macOS) held?

        Read the live modifier state from the event, falling back to the
        event-tracked key set. Never uses key.get_pressed() (macOS skill).
        """
        mods = getattr(ev, "mod", 0) if ev is not None else 0
        if mods & (pygame.KMOD_CTRL | pygame.KMOD_LMETA | pygame.KMOD_RMETA):
            return True
        return bool(self.keys & {pygame.K_LCTRL, pygame.K_RCTRL,
                                 pygame.K_LGUI, pygame.K_RGUI})

    def _control_group(self, num: int, assign: bool | None = None) -> None:
        """Ctrl/Shift+<n> assigns the selection to group `n`; <n> alone recalls.

        Previously EVERY number key assigned, so Ctrl+1..9 never worked —
        pressing Ctrl+2 overwrote group 2 with the current selection and left
        the selection unchanged, instead of recalling the group.
        """
        if assign is None:
            assign = bool(self.keys & {pygame.K_LCTRL, pygame.K_RCTRL,
                                       pygame.K_LGUI, pygame.K_RGUI})
        if assign:
            self.groups[num] = set(self.selection)
            self.app.flash(f"group {num} set ({len(self.selection)} units)")
        elif pygame.K_LSHIFT in self.keys or pygame.K_RSHIFT in self.keys:
            cur = self.groups.get(num, set())
            self.selection = set(self.selection) | cur
        else:
            self.selection = set(self.groups.get(num, set()))
            if self.selection:
                self.app.flash(f"group {num} ({len(self.selection)} units)")

    def _create_fleet(self, ids: list, formation: str = "line",
                      commander: str | None = None) -> None:
        self.state.queue_command(FleetCreateCommand(
            self.local_player, ids, name=f"Fleet {len(self.state.fleets) + 1}",
            formation=formation, commander=commander))
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