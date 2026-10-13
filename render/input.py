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
    CancelBuildCommand, ColonizeCommand, FleetCreateCommand, MoveCommand,
    ResearchCommand, StopCommand, UpgradeStationCommand,
)
from game.data.store import DataStore

# #69: Escape aborts whatever the player is doing. A second Escape press inside
# this window opens the previous screen, so one stray press cannot end a match.
MENU_ARM_SECONDS = 2.5


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
        self.camera.bind_scene(state, lambda: self.local_player)
        self._pending_jump: tuple[int, ...] | None = None
        self._pending_ability: dict | None = None
        self._pending_fleet: list[int] | None = None   # after G, awaiting number key
        self._menu_armed = False                # #69: first Escape armed the menu
        self._menu_arm_left = 0.0
        # right-panel scroll context (set by HUD each frame)
        self._right_panel_rect = None
        self._panel_scroll_key = None

    # ------------------------------------------------------------------ events
    def handle_event(self, ev) -> None:
        self.camera.refresh_scene()
        st = self.state
        self._prune_contacts()
        if ev.type == pygame.WINDOWFOCUSLOST:
            self._cancel_jump()
            self._cancel_ability()
            self.keys.clear()
            self._disarm_menu()
            self.dragging = False
            self.drag_start = self.drag_cur = self.right_drag = None
            return
        if ev.type == pygame.KEYDOWN:
            if ev.key in self.keys:
                return                         # ignore OS key-repeat for toggles
            self.keys.add(ev.key)
            if ev.key != pygame.K_ESCAPE:
                # #69: only Escape itself arms the menu; any other press means
                # the player has moved on, so a later Escape must abort again.
                self._disarm_menu()
            if ev.key == pygame.K_F10:
                self.grab_mouse = not self.grab_mouse
                pygame.event.set_grab(self.grab_mouse)
                pygame.mouse.set_visible(not self.grab_mouse)
            elif ev.key == pygame.K_ESCAPE:
                self._escape()
            elif pygame.K_1 <= ev.key <= pygame.K_9:
                self._cancel_jump()
                num = ev.key - pygame.K_0
                if self._pending_fleet:
                    self._create_fleet(self._pending_fleet, formation="line")
                    self._control_group(num, assign=True)
                else:
                    self._control_group(num, assign=self._ctrl_down(ev))
            elif ev.key == pygame.K_g and self.selection:
                self._cancel_jump()
                self._pending_fleet = sorted(self.selection)
                self.app.flash("press 1-9 to form fleet, or F for formation")
            elif ev.key == pygame.K_f:
                self._cancel_jump()
                self.hud.fleet_panel = not self.hud.fleet_panel
                self._pending_fleet = None
                if self.hud.fleet_panel:
                    self.hud.placement = None
                    self.app.flash("fleet panel: choose formation and commander")
            elif ev.key == pygame.K_j and self.selection:
                self._queue_jump()
            elif ev.key == pygame.K_l and self.selection:
                self._queue_crew('crew_load')
            elif ev.key == pygame.K_r and self.selection:
                self._queue_crew('crew_deliver')
            elif ev.key == pygame.K_b and self.selection:
                self._queue_board()
            elif ev.key == pygame.K_BACKSPACE:
                # #48: Stop moved off S so WASD panning cannot break; S now
                # pans the camera like the other pan keys, selection or not.
                self._cancel_jump()
                self._cancel_ability()
                self.hud.placement = None
                self._pending_fleet = None
                if self.selection:
                    st.queue_command(StopCommand(self.local_player,
                                                 sorted(self.selection)))
                    self.app.flash("stop")
                else:
                    self.app.flash("backspace: nothing selected to stop")
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
        elif ev.type == pygame.MOUSEWHEEL:
            if not self._scroll_panel(-ev.y):
                self.camera.zoom(0.88 ** ev.y)
        elif ev.type == pygame.MOUSEBUTTONDOWN:
            self._disarm_menu()      # a click is the player moving on, not a menu press
            if ev.button == 1:
                if self._pending_ability is not None:
                    self._confirm_ability(ev.pos)
                    return
                if self._pending_jump is not None:
                    self._confirm_jump(ev.pos)
                    return
                if self.hud.placement:
                    self._confirm_placement(ev.pos)
                    return
                if self._click_button(ev.pos):
                    return
                if any(r.collidepoint(ev.pos) for r in getattr(self.hud, 'blocked_rects', [])):
                    return
                if self.hud.minimap_rect and \
                        self.hud.minimap_rect.collidepoint(ev.pos):
                    self._minimap_jump(ev.pos)
                else:
                    self.drag_start = ev.pos
                    self.dragging = True
            elif ev.button == 3:
                if self._pending_ability is not None:
                    self._cancel_ability()
                    return
                if self._pending_jump is not None:
                    self._cancel_jump()
                    return
                if self.hud.placement:
                    self.hud.placement = None       # right-click cancels
                    return
                if any(r.collidepoint(ev.pos) for r in getattr(self.hud, 'blocked_rects', [])):
                    self.right_drag = None
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
            if any(r.collidepoint(ev.pos) for r in getattr(self.hud, 'blocked_rects', [])):
                if ev.button == 1:
                    self.dragging = False
                    self.drag_start = self.drag_cur = None
                elif ev.button == 3:
                    self.right_drag = None
                return
            if ev.button == 1 and self.dragging:
                self._finish_box_select(ev.pos)
                self.dragging = False
                self.drag_start = None
                self.drag_cur = None
            elif ev.button == 3 and self.right_drag is not None:
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
        # #48: S pans down like the rest of WASD, with or without a selection
        # (Stop is on Backspace), so the pan scheme never looks dead.
        pan_keys = {pygame.K_LEFT, pygame.K_RIGHT, pygame.K_UP, pygame.K_DOWN,
                    pygame.K_a, pygame.K_d, pygame.K_w, pygame.K_s}
        if self.keys & pan_keys:
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
        if pygame.K_DOWN in self.keys or pygame.K_s in self.keys:
            self.camera.pan(0, 14 * pan_speed)

    # ------------------------------------------------------------- panel scroll
    def _scroll_panel(self, direction: int) -> bool:
        """Wheel over a HUD scrollable list scrolls it; True if consumed."""
        mp = pygame.mouse.get_pos()
        for rect, key in self.hud.scroll_rects:
            if rect.collidepoint(mp):
                panel = getattr(self.hud, 'scroll_panels', {}).get(key)
                if panel and self.hud.minimized[panel]:
                    return True  # stale event batch: neither scroll nor world zoom
                cur = self.hud.scroll.get(key, 0)
                self.hud.scroll[key] = max(0, cur + direction)
                return True
        return False

    # ------------------------------------------------------------- helpers
    def _escape(self) -> None:
        """#69: abort the current operation; Escape again opens the previous screen.

        Escape used to leave the match whenever nothing was pending, so one
        stray press dropped the player out of a running game. It now only
        aborts, and that abort press arms the menu, so the next Escape press
        (inside MENU_ARM_SECONDS) opens the previous screen.
        """
        if self._abort_current_operation():
            self._arm_menu()
        elif self._menu_armed:
            self._disarm_menu()
            self.keys.clear()
            self.app.request_exit()
        else:
            self._arm_menu()
            self.app.flash("nothing to cancel - press Esc again for the main menu")

    def _abort_current_operation(self) -> bool:
        """Cancel targeting/placement/fleet intent. True if anything was active."""
        if self._pending_ability is not None:
            self._cancel_ability()
        elif self._pending_jump is not None:
            self._cancel_jump()
        elif self.hud.placement:
            self.hud.placement = None       # cancel placement first
        elif self.hud.fleet_panel:
            self.hud.fleet_panel = False
            self._pending_fleet = None
        elif self._pending_fleet:
            self._pending_fleet = None
            self.app.flash("fleet creation cancelled")
        else:
            return False
        return True

    def _arm_menu(self) -> None:
        self._menu_armed = True
        self._menu_arm_left = MENU_ARM_SECONDS

    def _disarm_menu(self) -> None:
        self._menu_armed = False
        self._menu_arm_left = 0.0

    def _prune_contacts(self) -> None:
        """UI memory must never keep following an unseen live enemy."""
        self.selection.intersection_update(
            eid for eid in tuple(self.selection)
            if self.state.can_see(self.local_player, eid))
        # A hull in hyperspace transit renders nowhere on the strategic view:
        # drop it from selection too, or the HUD would describe a ghost (#92).
        self.selection.intersection_update(
            eid for eid in tuple(self.selection)
            if (e := self.state.entity(eid)) is not None and not e.jump_travelling)
        if self.camera.follow_id is not None and not self.state.can_see(
                self.local_player, self.camera.follow_id):
            self.camera.follow_id = None

    def _follow_selection(self) -> None:
        """Follow the first live selected unit without changing simulation time."""
        self._prune_contacts()
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
        self._prune_contacts()
        if (self._pending_ability is not None
                and not self._ability_cmd(self._pending_ability).unit_ids):
            self._cancel_ability()
            self.app.flash("ability cancelled: no eligible ships remain")
        if self._pending_jump is not None and not self._jump_units(self._pending_jump):
            self._cancel_jump()
            self.app.flash("jump cancelled: no eligible ships remain")
        if self._menu_armed:
            # #69: the second Escape press has to follow the first closely, so a
            # prompt from a minute ago cannot end the match later.
            self._menu_arm_left -= max(0.0, dt)
            if self._menu_arm_left <= 0.0:
                self._disarm_menu()
        self._camera_keys(dt)
        if self.camera.follow_id is not None:
            e = self.state.entity(self.camera.follow_id)
            if e is None:
                self.camera.follow_id = None
            else:
                self.camera.target[0] = e.pos.x
                self.camera.target[2] = e.pos.z
        self.camera.refresh_scene()

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
            if not e.alive or (e.owner == -1 and not e.is_planet) or not self.state.can_see(self.local_player, e.id):
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

    def _ship_pick_distance(self, e, sp, mouse, floor):
        """Keep the small-contact affordance, also accept projected visual hulls.

        Eight actual all-role bounds corners are projected with the renderer's
        shared LOD rule. Simulation/collision radius never enters picking.
        """
        import math
        from itertools import product
        from render.ship_sizes import readable_size, _bounds
        d = math.hypot(sp[0]-mouse[0], sp[1]-mouse[1])
        if not (e.is_station or e.is_ship or e.is_squadron):
            return d
        if e.is_station and (e.planet_building_slot is not None or e.satellite_slot is not None):
            from render.planet_building_geometry import station_pick_distance
            return station_pick_distance(self.state, e, self.camera, mouse, floor)
        eye = self.camera.eye_position()
        _, _, forward = self.camera.basis()
        depth = sum((v-eye[i])*forward[i] for i,v in enumerate((e.pos.x,e.pos.y,e.pos.z)))
        if depth <= 0: return d
        ppw = self.camera.height/(2*depth*math.tan(math.radians(self.camera.fov/2)))
        from render.faction_visuals import owner_faction, normalize_station_key
        faction = owner_faction(self.state, e.owner)
        if e.is_station:
            faction, _ = normalize_station_key(e.data_id, faction)
            if faction == "imperial":
                return d  # keep protected legacy station affordance
            from render.camera_geometry import station_bounds
            lo, hi = station_bounds(e.data_id, faction)
            scale = e.radius / 50.
            yaw = self.camera._station_angle()
        else:
            size = readable_size(DataStore.get(), e.data_id, ppw, faction)
            lo, hi, _ = _bounds(size.shape)
            scale, yaw = size.scale, e.yaw
        ca, sa = math.cos(yaw), math.sin(yaw)
        points = []
        for x,y,z in product(*zip(lo,hi)):
            x,y,z = x*scale,y*scale,z*scale
            p = self.camera.world_to_screen(e.pos.x+x*ca+z*sa,e.pos.y+y,e.pos.z+z*ca-x*sa)
            if p is not None: points.append(p)
        if not points: return d
        dx = max(min(p[0] for p in points)-mouse[0],0.,mouse[0]-max(p[0] for p in points))
        dy = max(min(p[1] for p in points)-mouse[1],0.,mouse[1]-max(p[1] for p in points))
        return min(d, math.hypot(dx,dy)+floor*.5)

    def _single_select(self, mx: float, my: float) -> None:
        best, best_d = None, 28.0
        for e in self.state.entities.values():
            if not e.alive or (e.owner == -1 and not e.is_planet) or not self.state.can_see(self.local_player, e.id):
                continue
            sp = self.camera.world_to_screen(e.pos.x, e.pos.y, e.pos.z)
            if sp is None:
                continue
            d = self._ship_pick_distance(e, sp, (mx, my), 28.)
            if d < best_d:
                best, best_d = e, d
        self.selection = {best.id} if best else set()

    def _click_button(self, pos: tuple) -> bool:
        """HUD buttons -> queued PlayerCommands. True if a button consumed click."""
        for btn in self.hud.buttons:
            if btn["rect"].collidepoint(pos):
                kind, pl = btn["kind"], btn["payload"]
                st, lp = self.state, self.local_player
                if kind == 'hud_panel':
                    self.hud.minimized[pl['panel']] = pl['minimized']
                    return True
                if btn.get('panel') and self.hud.minimized[btn['panel']]:
                    return True
                if kind in {"fleet_formation", "fleet_commander",
                            "fleet_create", "fleet_close"} and not self.hud.fleet_panel:
                    # Buttons remain from the last render until the next frame.
                    # Consume stale controls without acting or selecting the scene.
                    return True
                if kind == "hud_scroll":
                    key = pl["key"]
                    self.hud.scroll[key] = max(0, self.hud.scroll.get(key, 0) + pl["delta"])
                elif kind == "build_station_place":
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
                elif kind == 'hud_planet_page':
                    self.hud.planet_page = pl['page']
                elif kind in ('build_satellite', 'build_planet_building'):
                    from game.systems.colonies import eligible_planet
                    planet = st.entity(pl['planet_id'])
                    page = 'surface' if kind == 'build_planet_building' else 'orbit'
                    if (eligible_planet(planet) and planet.id in self.selection
                            and planet.colonized_by == lp and st.can_see(lp, planet.id)
                            and self.hud.planet_page == page):
                        from game.core.commands import PlayerCommand
                        st.queue_command(PlayerCommand(kind, lp,
                            target_id=planet.id, station_kind=pl['station_kind']))
                elif kind == "build_ship":
                    st.queue_command(BuildShipCommand(
                        lp, pl["shipyard_id"], pl["ship_id"], 1))
                elif kind == "cancel_build":
                    # Payload names the queue holder (station/constructor or
                    # colony planet) and the index inside its build_queue. A row
                    # left over from another selection or planet page is inert:
                    # the target must still be selected and the page unchanged.
                    raw_id = pl.get("target_id")
                    target = st.entity(raw_id) if type(raw_id) is int else None
                    index = pl.get("index")
                    page = pl.get("page")
                    owner = None
                    if target is not None:
                        owner = target.colonized_by if target.is_planet else target.owner
                    if (target is not None and owner == lp and target.id in self.selection
                            and (page is None or page == self.hud.planet_page)
                            and type(index) is int
                            and 0 <= index < len(target.build_queue)):
                        st.queue_command(CancelBuildCommand(lp, target.id, index))
                elif kind == "upgrade_station":
                    # #77: the row names the station it was drawn for. A row left
                    # over from another selection is inert; ownership and eligibility
                    # are re-checked by the simulation, which also refuses an
                    # unaffordable step with a float text.
                    raw_id = pl.get("target_id")
                    target = st.entity(raw_id) if type(raw_id) is int else None
                    if (target is not None and target.is_station and target.alive
                            and target.owner == lp and target.id in self.selection):
                        st.queue_command(UpgradeStationCommand(lp, target.id))
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
                elif kind == 'explore':
                    from game.core.commands import PlayerCommand
                    from game.systems.exploration import exploration_capable
                    ids = tuple(i for i in sorted(set(pl.get('unit_ids', ())) & self.selection)
                                if (e := st.entity(i)) is not None and e.owner == lp
                                and e.operational and exploration_capable(e))
                    if ids:
                        self._cancel_jump()
                        self._cancel_ability()
                        self.hud.placement = None
                        self.hud.fleet_panel = False
                        self._pending_fleet = None
                        st.queue_command(PlayerCommand('explore', lp, unit_ids=ids))
                elif kind == 'repair':
                    self._queue_repair(pl)
                elif kind in ('crew_load', 'crew_deliver', 'crew_cancel'):
                    self._queue_crew(kind)
                elif kind == 'board':
                    self._queue_board()
                elif kind == "ability":
                    cmd = self._ability_cmd(pl)
                    if cmd.unit_ids:
                        if pl["ability_id"] == "tractor_beam":
                            self._cancel_jump()
                            self.hud.placement = None
                            self._pending_ability = dict(pl, unit_ids=list(cmd.unit_ids))
                            self.hud.ability_prompt = "TRACTOR BEAM: click a detected enemy · Esc / right-click cancel"
                        else:
                            st.queue_command(cmd)
                return True
        return False

    # ------------------------------------------------------------- placement mode
    def update_placement(self) -> None:
        """Per-frame ghost position + validity for station placement.

        Preview uses only current player knowledge; the sim rechecks physical
        legality when the order executes.
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
            valid, reason = cs.check_site(pl["station_kind"], w, b,
                                          viewer=self.local_player)
        from render.faction_visuals import owner_faction
        pl["ghost"] = {"sx": mx, "sy": my, "valid": valid, "reason": reason,
                       "radius": rad, "world": w, "station_kind": pl["station_kind"],
                       "builder_id": pl["builder_id"],
                       "faction": owner_faction(self.state, self.local_player)}

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
        valid, reason = cs.check_site(pl["station_kind"], w, b,
                                      viewer=self.local_player)
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

    def _cancel_ability(self):
        self._pending_ability = None
        self.hud.ability_prompt = ""
        self.dragging = False
        self.drag_start = self.drag_cur = self.right_drag = None

    def _queue_repair(self, payload):
        from game.systems.repairs import builder_capable
        ids = [i for i in sorted(set(payload.get('unit_ids', ())) & self.selection)
               if (e := self.state.entity(i)) is not None
               and e.owner == self.local_player and builder_capable(self.state, e)
               and e.jump_charge <= 0 and e.jump_target is None]
        if not ids:
            self.app.flash('select your operating constructor')
            return
        self._cancel_jump()
        self._cancel_ability()
        self.hud.placement = None
        self.hud.fleet_panel = False
        self._pending_fleet = None
        self._pending_ability = {'ability_id': '_repair', 'unit_ids': ids}
        self.hud.ability_prompt = 'REPAIR: click owned damaged hull · paid CR / MT · Esc / right-click cancel'

    def _queue_crew(self, kind):
        from game.core.commands import PlayerCommand
        recovery = self.state._crew_recovery_system
        ids = tuple(i for i in sorted(self.selection) if (e := self.state.entity(i)) is not None
                    and e.owner == self.local_player and e.operational and recovery.capacity(e)
                    and not e.boarding and e.jump_charge <= 0)
        if not ids:
            self.app.flash('select your operating crew transport')
            return
        if kind != 'crew_deliver':
            self.state.queue_command(PlayerCommand(kind, self.local_player, unit_ids=ids))
            return
        ids = tuple(i for i in ids if self.state.entity(i).crew_cargo > 0)
        if not ids:
            self.app.flash('load passengers at a friendly base first')
            return
        self._cancel_jump()
        self._cancel_ability()
        self.hud.placement = None
        self.hud.fleet_panel = False
        self._pending_fleet = None
        self._pending_ability = {'ability_id': '_crew_deliver', 'unit_ids': list(ids)}
        self.hud.ability_prompt = 'CREW: click an owned hull · life support >=50% · Esc / right-click cancel'

    def _queue_board(self):
        from game.systems.boarding import boarding_capable
        ids = [i for i in sorted(self.selection) if (e := self.state.entity(i)) is not None
               and e.owner == self.local_player and boarding_capable(e) and e.crew >= 2
               and e.jump_charge <= 0
               and not any(c.boarding.get('source') == i for c in self.state.entities.values())]
        if not ids:
            self.app.flash('select own boarding-capable ships with crew and no deployed party')
            return
        self._cancel_jump()
        self._cancel_ability()
        self.hud.placement = None
        self.hud.fleet_panel = False
        self._pending_fleet = None
        self._pending_ability = {'ability_id': '_board', 'unit_ids': ids}
        self.hud.ability_prompt = 'BOARD: detected enemy hull · all shields down · Esc / right-click cancel'

    def _confirm_ability(self, pos):
        if any(r.collidepoint(pos) for r in self.hud.blocked_rects):
            return
        target = self._pick_target(pos)
        cmd = self._ability_cmd(self._pending_ability)
        if cmd.type == 'repair':
            from game.systems.repairs import repair_reason
            if target is None or target.owner != self.local_player:
                self.app.flash('choose an owned damaged hull')
                return
            reasons = [(i, repair_reason(self.state, self.state.entity(i), target)) for i in cmd.unit_ids]
            cmd.unit_ids = tuple(i for i, reason in reasons if not reason)
            if not cmd.unit_ids:
                self.app.flash('cannot repair: ' + (reasons[0][1] if reasons else 'no eligible constructors'))
                return
        elif cmd.type == 'crew_deliver':
            if target is None or target.owner != self.local_player:
                self.app.flash('choose an owned hull')
                return
            recovery = self.state._crew_recovery_system
            reasons = [(i, recovery.reason(self.state.entity(i), 'deliver', target)) for i in cmd.unit_ids]
            cmd.unit_ids = tuple(i for i, reason in reasons if not reason)
            if not cmd.unit_ids:
                self.app.flash('cannot deliver: ' + (reasons[0][1] if reasons else 'no eligible transports'))
                return
        elif target is None or not self.state.is_enemy(self.local_player, target.owner):
            self.app.flash("choose a detected enemy")
            return
        if cmd.type == 'board':
            from game.systems.boarding import boarding_reason
            reasons = [(i, boarding_reason(self.state, self.state.entity(i), target))
                       for i in cmd.unit_ids]
            cmd.unit_ids = tuple(i for i, reason in reasons if not reason)
            if not cmd.unit_ids:
                self.app.flash('cannot board: ' + (reasons[0][1] if reasons else 'no eligible ships'))
                return
        if cmd.unit_ids:
            cmd.target_id = target.id
            self.state.queue_command(cmd)
        self._cancel_ability()

    def _ability_cmd(self, pl: dict):
        from game.core.commands import AbilityCommand
        if pl['ability_id'] == '_repair':
            from game.core.commands import PlayerCommand
            from game.systems.repairs import builder_capable
            ids = tuple(i for i in sorted(set(pl['unit_ids']) & self.selection)
                        if (e := self.state.entity(i)) is not None
                        and e.owner == self.local_player and builder_capable(self.state, e)
                        and e.jump_charge <= 0 and e.jump_target is None)
            return PlayerCommand('repair', self.local_player, unit_ids=ids)
        if pl['ability_id'] == '_crew_deliver':
            from game.core.commands import PlayerCommand
            recovery = self.state._crew_recovery_system
            ids = tuple(i for i in sorted(set(pl['unit_ids']) & self.selection)
                        if (e := self.state.entity(i)) is not None and e.owner == self.local_player
                        and e.operational and recovery.capacity(e) and e.crew_cargo > 0
                        and not e.boarding and e.jump_charge <= 0)
            return PlayerCommand('crew_deliver', self.local_player, unit_ids=ids)
        if pl['ability_id'] == '_board':
            from game.core.commands import PlayerCommand
            from game.systems.boarding import boarding_capable
            ids = tuple(i for i in sorted(set(pl['unit_ids']) & self.selection)
                        if (e := self.state.entity(i)) is not None and e.owner == self.local_player
                        and boarding_capable(e) and e.crew >= 2 and e.jump_charge <= 0
                        and not any(c.boarding.get('source') == i for c in self.state.entities.values()))
            return PlayerCommand('board', self.local_player, unit_ids=ids)
        tgt = None
        if pl.get("targeted"):
            tgt = self.camera.screen_to_world(*pygame.mouse.get_pos())
        from render.hud import selected_ability_data
        ids = set(pl['unit_ids']) & self.selection
        rows = selected_ability_data(self.state, ids, self.local_player)
        eligible = next((r['unit_ids'] for r in rows if r['ability_id'] == pl['ability_id']), [])
        return AbilityCommand(self.local_player, eligible,
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
        self._prune_contacts()
        if not self.selection:
            return
        st, lp = self.state, self.local_player
        ids = sorted(self.selection)
        # Resolve hardware targets before querying the ground GL matrices.
        # target priority: enemy unit > colonizable planet > ground move
        target = self._pick_target(pos)
        if target is not None:
            e = target
            from game.systems.colonies import eligible_planet
            if eligible_planet(e) and (e.colonized_by is None or st.is_enemy(lp, e.colonized_by)):
                colonizers = [i for i in ids
                              if (sd := _ship_data(st.entity(i))) is not None
                              and sd.can_colonize]
                if colonizers:
                    st.queue_command(ColonizeCommand(lp, colonizers, e.id))
                    self.app.flash("colonization ordered")
                    return
            st.queue_command(AttackCommand(lp, ids, e.id))
            self.app.flash(f"attack {DataStore.get().unit_name(e)}")
        elif (w := self.camera.screen_to_world(*pos)) is not None:
            st.queue_command(AttackMoveCommand(lp, ids, w))
            self.app.flash("attack-move")

    def _pick_target(self, pos: tuple):
        best, best_d = None, 30.0
        for e in self.state.entities.values():
            from game.systems.colonies import eligible_planet
            if (not e.alive or (e.owner == -1 and not eligible_planet(e))
                    or not self.state.can_see(self.local_player, e.id)):
                continue
            sp = self.camera.world_to_screen(e.pos.x, e.pos.y, e.pos.z)
            if sp is None:
                continue
            d = self._ship_pick_distance(e, sp, pos, 30.)
            if d < best_d:
                best, best_d = e, d
        return best

    def _cancel_jump(self) -> None:
        if self._pending_jump is not None:
            self._pending_jump = None
            self.hud.jump_prompt = False
            self.dragging = False
            self.drag_start = self.drag_cur = self.right_drag = None
            self.app.flash("jump destination selection cancelled")

    def _jump_units(self, ids) -> tuple[int, ...]:
        """Inspect only snapshotted own units, never destination entities."""
        return tuple(i for i in sorted(ids)
                     if (e := self.state.entity(i)) is not None
                     and e.owner == self.local_player and e.alive and e.hull > 0
                     and e.is_ship and not e.is_squadron
                     and not e.is_station and not e.is_planet
                     and (sd := _ship_data(e)) is not None and not sd.is_squadron
                     and e.jump_charge <= 0 and e.jump_target is None
                     and e.ability_cooldowns.get("_jump_cd", 0) <= 0)

    def _queue_jump(self) -> None:
        if self._pending_jump is not None:
            return
        ids = self._jump_units(self.selection)
        if not ids:
            self.app.flash("select eligible own ships ready to jump")
            return
        self._cancel_ability()
        self._pending_jump = ids
        self.hud.jump_prompt = True
        self.hud.placement = None
        self.hud.fleet_panel = False
        self._pending_fleet = None
        self.dragging = False
        self.drag_start = self.drag_cur = self.right_drag = None
        self.app.flash("jump: click destination on ground or minimap; Esc cancels")

    def _confirm_jump(self, pos: tuple) -> None:
        from game.core.commands import JumpCommand
        ids = self._jump_units(self._pending_jump or ())
        if not ids:
            self._cancel_jump()
            self.app.flash("jump cancelled: no eligible ships remain")
            return
        width, height = self.camera.width, self.camera.height
        if not (0 <= pos[0] < width and 0 <= pos[1] < height):
            self.app.flash("cannot jump there: click inside battlefield or minimap")
            return
        r = self.hud.minimap_rect
        if r is not None and r.collidepoint(pos):
            if not r.inflate(-8, -8).collidepoint(pos):
                self.app.flash("cannot jump there: click inside minimap content")
                return
            w = self._minimap_world(pos)
        else:
            if (any(b["rect"].collidepoint(pos) for b in self.hud.buttons)
                    or any(r.collidepoint(pos) for r in
                           getattr(self.hud, "blocked_rects", []))):
                self.app.flash("cannot jump through HUD: click ground or minimap")
                return
            w = self.camera.screen_to_world(*pos)
        if w is None:
            self.app.flash("cannot jump there: choose battlefield ground")
            return
        from math import isfinite
        target = _vec3(w[0], 0.0, w[2])
        half = self.state.map_info.bounds / 2.0
        if not all(isfinite(v) and abs(v) <= half for v in (target.x, target.z)):
            self.app.flash("cannot jump there: outside map bounds")
            return
        self.state.queue_command(JumpCommand(
            self.local_player, ids, target))
        self._cancel_jump()
        self.app.flash("hyperspace jump ordered")

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
        self._prune_contacts()

    def _create_fleet(self, ids: list, formation: str = "line",
                      commander: str | None = None) -> None:
        self.state.queue_command(FleetCreateCommand(
            self.local_player, ids, name=f"Fleet {len(self.state.fleets) + 1}",
            formation=formation, commander=commander))
        self._pending_fleet = None
        self.app.flash(f"fleet formed ({formation})")

    def _minimap_world(self, pos: tuple) -> tuple:
        """Inverse of HUD._minimap px(): four-pixel content inset."""
        r = self.hud.minimap_rect
        bounds = max(1.0, self.state.map_info.bounds)
        half = bounds / 2.0
        wx = (pos[0] - r.centerx) / (r.width / 2 - 4) * half
        wz = (pos[1] - r.centery) / (r.height / 2 - 4) * half
        return wx, 0.0, wz

    def _minimap_jump(self, pos: tuple) -> None:
        wx, _, wz = self._minimap_world(pos)
        self.camera.follow_id = None
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