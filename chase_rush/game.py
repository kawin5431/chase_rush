"""Main game loop."""

from __future__ import annotations

import math
import random
from typing import Any, List, Optional

import pygame

from . import config
from .collision import bounce_oriented_vehicles, polys_intersect, unstick_vehicle_from_rects
from .map import Map
from .player import Player
from .police import Police
from .sound_manager import SoundManager
from .stats_tracker import StatsTracker, nearest_police_distance
from .tire_fx import DripSmokeFX, EngineSmokeFX, TireMarkManager
from .wallet import Wallet


class Game:
    def __init__(self) -> None:
        self.screen = pygame.display.set_mode((config.SCREEN_WIDTH, config.SCREEN_HEIGHT))
        pygame.display.set_caption("Chase Rush")
        self.clock = pygame.time.Clock()
        self.map = Map()
        self.player = Player(config.WORLD_WIDTH / 2, config.WORLD_HEIGHT / 2)
        self.map.generate(self.player.x, self.player.y)
        self.police: List[Police] = []
        self.stats = StatsTracker()
        self.snd = SoundManager()
        self.snd.start_game_ambient()
        self.font = pygame.font.SysFont(None, 48)
        self.frame = 0
        self.start_ticks = 0
        self.last_spawn = 0
        self.playing = False
        self.keys = None
        self._prev_forward = False
        # Edge-detect Q so the nitro whoosh fires exactly once per press.
        self._prev_q_pressed = False
        self._hit_invuln_frames = 0
        self._cactus_hit_cd = 0
        self._death_frames = 0
        # Throttle the crash SFX so sustained-contact collisions don't silence
        # new impacts. A few frames is enough to keep each distinct hit
        # audible without letting the sound overlap into a continuous buzz.
        self._crash_sfx_cd = 0
        # Gift-box power-ups: separate invincibility (no damage taken) and
        # ram-mode (police explode on contact) windows, plus a transient
        # banner shown after pickup.
        self._invincible_frames = 0
        self._ram_frames = 0
        self._gift_msg = ""
        self._gift_msg_frames = 0
        # Session counters exposed to stats/HUD/dashboard.
        self._count_cactus_hits = 0
        self._count_banana_slips = 0
        self._count_player_police_collisions = 0
        self._count_police_killed = 0
        self._count_gifts_collected = 0
        # Money earned during the current frame (reset at start of update).
        self._money_earned_this_frame = 0
        self.tire_marks = TireMarkManager()
        self.drip_fx = DripSmokeFX(road_check=self.map.is_point_on_road)
        self.engine_fx = EngineSmokeFX()
        self._show_hitboxes = config.DEBUG_SHOW_HITBOXES
        self.wallet = Wallet()
        # Tanks the player has bought in the shop for the next game only.
        # Consumed by _start_session, which copies them onto the player.
        self.pending_nitro_tanks = 0

    def handle_events(self) -> bool:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return False
            if event.type == pygame.KEYDOWN and event.key == pygame.K_h:
                self._show_hitboxes = not self._show_hitboxes
        self.keys = pygame.key.get_pressed()
        return True

    def _elapsed_s(self) -> float:
        return (pygame.time.get_ticks() - self.start_ticks) / 1000.0

    def _camera(self) -> tuple[float, float]:
        cam_x = self.player.x - config.SCREEN_WIDTH / 2
        cam_y = self.player.y - config.SCREEN_HEIGHT / 2
        return cam_x, cam_y

    def _random_edge_spawn(self) -> tuple[float, float]:
        w, h = config.WORLD_WIDTH, config.WORLD_HEIGHT
        obstacles = self.map.get_obstacles()
        pad = 90.0
        for _ in range(50):
            side = random.randint(0, 3)
            if side == 0:
                x, y = random.uniform(pad, w - pad), random.uniform(pad, pad + 70)
            elif side == 1:
                x, y = random.uniform(pad, w - pad), random.uniform(h - pad - 70, h - pad)
            elif side == 2:
                x, y = random.uniform(pad, pad + 70), random.uniform(pad, h - pad)
            else:
                x, y = random.uniform(w - pad - 70, w - pad), random.uniform(pad, h - pad)
            test = pygame.Rect(
                int(x - config.POLICE_W / 2),
                int(y - config.POLICE_H / 2),
                config.POLICE_W,
                config.POLICE_H,
            )
            if not any(test.colliderect(o) for o in obstacles):
                return x, y
        return pad + 40, pad + 40

    def _spawn_police(self) -> None:
        elapsed_s = self._elapsed_s()
        target = config.stage_for(elapsed_s)[1]
        now = pygame.time.get_ticks()
        alive_count = sum(1 for p in self.police if p.alive)
        if alive_count >= target:
            return
        if now - self.last_spawn < config.SPAWN_INTERVAL_MS:
            return
        x, y = self._random_edge_spawn()
        unit = Police(x, y)
        unit.target = self.player
        unit.apply_difficulty(elapsed_s)
        # Newly spawned car enters at the current stage's full HP cap.
        unit.hp = unit.max_hp
        self.police.append(unit)
        self.last_spawn = now

    def _emit_vehicle_damage_fx(
        self,
        ratio: float,
        x: float,
        y: float,
        direction: float,
        w: float,
        h: float,
    ) -> None:
        """Emit hood smoke / fire appropriate to the vehicle's HP ratio."""
        if ratio >= 0.60:
            return
        if ratio < 0.30:
            mode = "fire"
            intensity = 1.35
        elif ratio < 0.40:
            mode = "dark_smoke"
            intensity = 1.2
        else:
            mode = "smoke"
            intensity = 0.8 + (0.60 - ratio) * 2.0
        self.engine_fx.emit(x, y, direction, w, h, mode=mode, intensity=intensity)

    def _emit_damage_fx(self) -> None:
        """Hood smoke/fire for the player and every police car with low HP."""
        player_ratio = self.player.hp / max(1, config.PLAYER_MAX_HP)
        self._emit_vehicle_damage_fx(
            player_ratio,
            self.player.x,
            self.player.y,
            self.player.direction,
            config.CAR_W,
            config.CAR_H,
        )
        max_police_hp = max(1, config.POLICE_MAX_HP)
        for p in self.police:
            # Dead wrecks keep burning (hp=0 → fire mode) until respawned out.
            self._emit_vehicle_damage_fx(
                p.hp / max_police_hp,
                p.x,
                p.y,
                p.direction,
                config.POLICE_W,
                config.POLICE_H,
            )

    def _apply_random_gift(self) -> None:
        """Roll one of four prizes when the player picks up a gift box."""
        prize = random.choice(("money", "nitro", "invincible", "ram"))
        if prize == "money":
            self.wallet.add(config.GIFT_MONEY_AMOUNT)
            self._money_earned_this_frame += config.GIFT_MONEY_AMOUNT
            self._gift_msg = f"+${config.GIFT_MONEY_AMOUNT}!"
        elif prize == "nitro":
            self.player.nitro_tanks += config.GIFT_NITRO_TANKS
            self._gift_msg = f"+{config.GIFT_NITRO_TANKS} NITRO TANKS!"
        elif prize == "invincible":
            self._invincible_frames = int(config.GIFT_INVINCIBLE_S * config.FPS)
            self._gift_msg = "INVINCIBLE!"
        else:  # ram
            self._ram_frames = int(config.GIFT_RAM_S * config.FPS)
            self._gift_msg = "RAM MODE!"
        self._gift_msg_frames = int(2.0 * config.FPS)
        self._count_gifts_collected += 1
        # Log the prize tagged with the current difficulty stage so the
        # summary can report the most-frequent reward per stage.
        self.stats.log_gift(
            stage=config.stage_index(self._elapsed_s()),
            prize=prize,
            time_s=self._elapsed_s(),
        )

    def _apply_banana_slip(self) -> None:
        """Step-on-peel: car keeps sliding the way it was already going but
        the body starts spinning independently — classic slip-on-ice effect.

        The faster the car was travelling, the harder the spin.
        """
        p = self.player
        vmag = math.hypot(p.vx, p.vy)
        # Kick the car forward along its current velocity so the slide feels
        # like the peel flings it across the road. Low-speed cases still get
        # a small shove so stepping on a peel never feels weak.
        if vmag > 0.1:
            boost = 1.6
            p.vx *= boost
            p.vy *= boost
        else:
            # Coasting to a stop? Give it a kick along the heading direction.
            ux, uy = math.cos(math.radians(p.direction)), -math.sin(
                math.radians(p.direction)
            )
            p.vx += ux * 4.0
            p.vy += uy * 4.0
        # Angular kick: direction random, magnitude scales with post-boost
        # speed so high-speed peels cause a dramatic pirouette.
        vmag2 = math.hypot(p.vx, p.vy)
        spin_dir = random.choice((-1.0, 1.0))
        spin = spin_dir * (3.0 + min(10.0, vmag2 * 1.1)) * random.uniform(0.85, 1.2)
        p.rotation_speed += spin
        self._count_banana_slips += 1
        # Lock the throttle for 0.5 s so the driver has to ride out the slide.
        p._throttle_lock_frames = max(
            p._throttle_lock_frames, int(0.5 * config.FPS)
        )
        # Treat the slip like an automatic gas release: silence the lambo
        # engine track and play the slow-down cue in its place.
        self.snd.stop_music()
        self.snd.play_once("release")
        # Force the forward-edge tracker to "released" so the engine track
        # doesn't immediately re-trigger while the key is still held down;
        # lambo will only resume after the player actually taps forward
        # again once the lock expires.
        self._prev_forward = False
        self.snd.play_once("slip")

    def _play_crash_sfx(self) -> None:
        """Fire the crash sound, but rate-limit so sustained contact doesn't loop."""
        if self._crash_sfx_cd <= 0:
            self.snd.play_once("crash")
            self._crash_sfx_cd = 5  # ~83 ms at 60 fps

    def _police_hits_player(self) -> bool:
        pb = self.player.get_hit_poly()
        for p in self.police:
            if polys_intersect(pb, p.get_hit_poly()):
                return True
        return False

    def _log_frame(self) -> None:
        elapsed = self._elapsed_s()
        dist = nearest_police_distance(self.player.x, self.player.y, self.police)
        if math.isinf(dist):
            dist = math.hypot(config.WORLD_WIDTH, config.WORLD_HEIGHT)
        active_police = sum(1 for p in self.police if p.alive)
        self.stats.log_event(
            frame=self.frame,
            time_s=elapsed,
            player_x=self.player.x,
            player_y=self.player.y,
            player_speed=self.player.display_speed,
            dist_nearest_police=dist,
            num_active_police=active_police,
            player_direction=self.player.direction,
            player_hp=self.player.hp,
            nitro_level=self.player.nitro,
            nitro_active=self.player.nitro_active,
            wallet_balance=self.wallet.balance,
            money_earned_this_frame=self._money_earned_this_frame,
            police_stage=config.stage_index(elapsed),
            total_cactus_hits=self._count_cactus_hits,
            total_banana_slips=self._count_banana_slips,
            total_collisions_player_police=self._count_player_police_collisions,
            total_police_killed=self._count_police_killed,
            total_gifts_collected=self._count_gifts_collected,
        )
        self._money_earned_this_frame = 0

    def _trigger_player_death(self) -> None:
        """Explode, cut input, run a short boom animation while the wreck coasts."""
        self.engine_fx.explode(self.player.x, self.player.y)
        # Cut engine/crash/music loops then fire the slow-down cue so the
        # explosion is punctuated by the "gas release" sound on top of the
        # background music loop.
        self.snd.silence_gameplay()
        self.snd.play_once("release")
        self.player.hp = 0
        self._add_explosion_impulse(self.player)
        self._log_frame()
        self.frame += 1
        self._death_frames = int(config.FPS * 1.5)

    def _kill_police(self, p: "Police") -> None:
        """Blow up a police car and convert it to a coasting wreck; queue a respawn.

        Velocity is NOT zeroed: the wreck keeps its current momentum so it can
        slide, bounce off other cars, and coast to a stop via drag/friction.
        """
        if not p.alive:
            return
        self.engine_fx.explode(p.x, p.y)
        p.alive = False
        p.hp = 0
        p._stun_frames = 0
        self._count_police_killed += 1
        self._add_explosion_impulse(p)
        # Queue an immediate respawn so live count matches current difficulty.
        self.last_spawn = pygame.time.get_ticks() - config.SPAWN_INTERVAL_MS

    @staticmethod
    def _add_explosion_impulse(vehicle: Any) -> None:
        """Small kick + spin so the blast is visible on a heavy wreck.

        Kept modest because wrecks apply extra damping each frame; a big
        impulse would read as a slide, not a recoil.
        """
        speed = math.hypot(vehicle.vx, vehicle.vy)
        if speed > 0.01:
            boost = 1.0 + 1.2 / speed
            vehicle.vx *= boost
            vehicle.vy *= boost
        spin_sign = 1.0 if (vehicle.rotation_speed >= 0) else -1.0
        vehicle.rotation_speed += spin_sign * 2.2

    def update(self, _dt: int) -> None:
        player_dead = self._death_frames > 0
        if not player_dead and (not self.playing or self.keys is None):
            return

        if player_dead:
            self._death_frames -= 1
            self.player.set_nitro_input(False)
        else:
            # Treat the throttle as released whenever the player can't
            # actually accelerate (e.g. during a banana-peel slide) so the
            # engine-track edge stays aligned with the physics.
            forward = bool(
                self.keys[pygame.K_UP] or self.keys[pygame.K_w]
            ) and self.player._throttle_lock_frames == 0
            if forward and not self._prev_forward:
                # Cut off any lingering slow-down cue the moment the player
                # hits the throttle again — the release sound only makes
                # sense while the car is coasting.
                self.snd.stop_sound("release")
                self.snd.music("lambo", 1.0)
            if self._prev_forward and not forward:
                # Stop the engine track and fire a single release cue; this
                # is a one-shot, not a looping track, so the road goes quiet
                # after the sound finishes.
                self.snd.stop_music()
                self.snd.play_once("release")
            self._prev_forward = forward
            q_pressed = bool(self.keys[pygame.K_q])
            # Fire the nitro whoosh exactly once on the Q key-down edge,
            # regardless of whether the bar has any charge to burn.
            if q_pressed and not self._prev_q_pressed:
                self.snd.play_once("nitro")
            self._prev_q_pressed = q_pressed
            self.player.set_nitro_input(q_pressed)

        obstacles = self.map.get_obstacles()
        self.map.update()
        self.tire_marks.update()
        self.drip_fx.update()
        self.engine_fx.update()
        self._emit_damage_fx()
        if player_dead:
            # Wreck keeps sliding: no steering/throttle, just drag + collisions.
            self.player.coast(obstacles, self.tire_marks, self.drip_fx)
        else:
            self.player.move(self.keys, obstacles, self.tire_marks, self.drip_fx)
            if self.player.nitro_active:
                self.engine_fx.emit_nitro(
                    self.player.x,
                    self.player.y,
                    self.player.direction,
                    config.CAR_W,
                    config.CAR_H,
                    intensity=1.0,
                )
        self._spawn_police()
        if self._crash_sfx_cd > 0:
            self._crash_sfx_cd -= 1
        for p in self.police:
            if bounce_oriented_vehicles(
                self.player,
                p,
                config.CAR_W,
                config.CAR_H,
                p.hit_w,
                p.hit_h,
            ):
                if p.alive and p._stun_frames == 0:
                    p.hp = max(0, p.hp - config.POLICE_HIT_DAMAGE)
                if p.alive:
                    p.stun()
                    if p.hp <= 0:
                        self._kill_police(p)
        for i in range(len(self.police)):
            for j in range(i + 1, len(self.police)):
                pi, pj = self.police[i], self.police[j]
                if bounce_oriented_vehicles(
                    pi, pj, pi.hit_w, pi.hit_h, pj.hit_w, pj.hit_h
                ):
                    # If one side is a wreck, the alive car ramming it takes
                    # damage (same rule as ramming a cruiser).
                    for alive_one, other in ((pi, pj), (pj, pi)):
                        if alive_one.alive and not other.alive:
                            if alive_one._stun_frames == 0:
                                alive_one.hp = max(
                                    0, alive_one.hp - config.POLICE_HIT_DAMAGE
                                )
                            alive_one.stun()
                            if alive_one.hp <= 0:
                                self._kill_police(alive_one)
        unstick_vehicle_from_rects(self.player, config.CAR_W, config.CAR_H, obstacles)
        for p in self.police:
            unstick_vehicle_from_rects(p, p.hit_w, p.hit_h, obstacles)
        elapsed_s = self._elapsed_s()
        for p in self.police:
            p.target = self.player
            p.apply_difficulty(elapsed_s)
            p.update(obstacles, self.tire_marks, self.drip_fx)
            if p._cactus_hit_cd > 0:
                p._cactus_hit_cd -= 1
            if p.alive and p._cactus_hit_cd == 0:
                hit, _ = self.map.pop_cactus_hit(p.get_hit_poly())
                if hit:
                    p.hp = max(0, p.hp - 1)
                    p._cactus_hit_cd = 8
                    if p.hp <= 0:
                        self._kill_police(p)

        if player_dead:
            if self._death_frames == 0:
                self.playing = False
            return

        if self._hit_invuln_frames > 0:
            self._hit_invuln_frames -= 1
        if self._cactus_hit_cd > 0:
            self._cactus_hit_cd -= 1

        hit_cactus, _ = self.map.pop_cactus_hit(self.player.get_hit_poly())
        if hit_cactus and self._cactus_hit_cd == 0:
            self._count_cactus_hits += 1
            if self._invincible_frames == 0:
                self.player.hp -= 1
                if self.player.hp <= 0:
                    self._trigger_player_death()
                    return
            self._cactus_hit_cd = 8

        # Pick up every banknote the player touches this frame (loop until
        # no more are intersecting so two overlapping notes can't be missed).
        while True:
            value = self.map.pop_banknote_hit(self.player.get_hit_poly())
            if not value:
                break
            self.wallet.add(value)
            self._money_earned_this_frame += value

        # Gift boxes: random prize on contact.
        while self.map.pop_gift_hit(self.player.get_hit_poly()):
            self._apply_random_gift()

        # Banana peel: step on one and the car slides in a random direction,
        # with a wobble proportional to current speed. Hit sound fires once.
        while self.map.pop_banana_hit(self.player.get_hit_poly()):
            self._apply_banana_slip()

        # Tick power-up timers.
        if self._invincible_frames > 0:
            self._invincible_frames -= 1
        if self._ram_frames > 0:
            self._ram_frames -= 1
            # Any police the player touches while ram is active explodes.
            pb = self.player.get_hit_poly()
            for p in self.police:
                if p.alive and polys_intersect(pb, p.get_hit_poly()):
                    p.hp = 0
                    self._kill_police(p)
        if self._gift_msg_frames > 0:
            self._gift_msg_frames -= 1

        if self._police_hits_player():
            # Sound fires on every contact; damage still gated by the
            # invulnerability window so ramming can't shred the player.
            self._play_crash_sfx()
            # Every distinct contact counts for the session tally, even if
            # the player is still invulnerable (we want raw encounter stats).
            if self._hit_invuln_frames == 0:
                self._count_player_police_collisions += 1
            if self._hit_invuln_frames == 0 and self._invincible_frames == 0:
                self.player.hp -= config.POLICE_HIT_DAMAGE
                self._hit_invuln_frames = config.HIT_INVULN_FRAMES
                if self.player.hp <= 0:
                    self._trigger_player_death()
                    return

        self._log_frame()
        self.frame += 1

    def _draw_hitboxes(self, cam_x: float, cam_y: float) -> None:
        """Wireframe collision: obstacles as rects, vehicles as rotated_box polys."""
        for r in self.map.get_obstacles():
            pygame.draw.rect(
                self.screen,
                (140, 70, 30),
                (int(r.x - cam_x), int(r.y - cam_y), r.w, r.h),
                width=2,
            )
        pl = self.player.get_hit_poly()
        pts_p = [(int(x - cam_x), int(y - cam_y)) for x, y in pl]
        if len(pts_p) >= 2:
            pygame.draw.lines(self.screen, (0, 200, 90), True, pts_p, width=2)
        for p in self.police:
            poly = p.get_hit_poly()
            pts = [(int(x - cam_x), int(y - cam_y)) for x, y in poly]
            if len(pts) >= 2:
                pygame.draw.lines(self.screen, (70, 130, 255), True, pts, width=2)

    def render(self) -> None:
        cam_x, cam_y = self._camera()
        self.map.draw(self.screen, cam_x, cam_y)
        self.tire_marks.draw(self.screen, cam_x, cam_y)
        self.drip_fx.draw(self.screen, cam_x, cam_y)
        for p in self.police:
            p.draw(self.screen, cam_x, cam_y)
        self.player.draw(self.screen, cam_x, cam_y)
        self.engine_fx.draw(self.screen, cam_x, cam_y)
        if self.playing and self._show_hitboxes:
            self._draw_hitboxes(cam_x, cam_y)

        elapsed = self._elapsed_s()
        score = int(elapsed) if self.playing or self.frame > 0 else 0
        stage_idx = config.stage_index(elapsed)
        total_stages = len(config.POLICE_STAGES)
        score_txt = self.font.render(f"Score (survival s): {score}", True, (20, 20, 20))
        stage_txt = self.font.render(
            f"Stage: {stage_idx}/{total_stages}", True, (120, 40, 20)
        )
        pol_txt = self.font.render(f"Police: {len(self.police)}", True, (20, 20, 120))
        hp_col = (180, 30, 30) if self.player.hp <= 25 else (20, 100, 20)
        hp_txt = self.font.render(f"HP: {self.player.hp}", True, hp_col)
        spd_txt = self.font.render(
            f"Speed: {self.player.display_speed:5.1f}", True, (20, 20, 20)
        )
        police_spd = max((p.display_speed for p in self.police), default=0.0)
        pol_spd_txt = self.font.render(
            f"Police spd: {police_spd:5.1f}", True, (20, 20, 120)
        )
        hint = self.font.render(
            "WASD / arrows — evade the police   |   H: hitboxes (on)" if self._show_hitboxes
            else "WASD / arrows — evade the police   |   H: hitboxes",
            True,
            (40, 40, 40),
        )
        self.screen.blit(score_txt, (20, 20))
        self.screen.blit(stage_txt, (20, 60))
        self.screen.blit(hp_txt, (20, 100))
        self.screen.blit(pol_txt, (20, 140))
        self.screen.blit(spd_txt, (20, 180))
        self.screen.blit(pol_spd_txt, (20, 220))
        self._draw_stage_stars(stage_idx)
        self._draw_nitro_bar()
        self._draw_wallet_hud()
        self._draw_powerups_hud()
        if self.playing:
            self.screen.blit(hint, (20, config.SCREEN_HEIGHT - 40))
        pygame.display.flip()

    def _draw_nitro_bar(self) -> None:
        """Bottom-right NITRO bar: fills cyan, flashes orange while burning."""
        w, h = 240, 22
        x = config.SCREEN_WIDTH - w - 24
        y = config.SCREEN_HEIGHT - h - 24
        ratio = max(0.0, min(1.0, self.player.nitro / self.player.nitro_max))
        # Back panel with subtle shadow.
        shadow = pygame.Rect(x + 2, y + 3, w, h)
        pygame.draw.rect(self.screen, (0, 0, 0, 80), shadow, border_radius=6)
        panel = pygame.Rect(x, y, w, h)
        pygame.draw.rect(self.screen, (34, 34, 42), panel, border_radius=6)
        pygame.draw.rect(self.screen, (12, 12, 18), panel, 2, border_radius=6)
        # Fill: cyan idle, flashing orange/yellow when the boost is active.
        fill_w = int((w - 6) * ratio)
        if fill_w > 0:
            fill = pygame.Rect(x + 3, y + 3, fill_w, h - 6)
            if self.player.nitro_active:
                flash = (self.frame // 3) % 2
                fill_col = (255, 188, 40) if flash else (255, 120, 20)
            else:
                fill_col = (60, 210, 240) if ratio > 0.25 else (230, 80, 60)
            pygame.draw.rect(self.screen, fill_col, fill, border_radius=4)
        # Label and hotkey hint sit above the bar.
        label = self.font.render("NITRO  (Q)", True, (235, 235, 245))
        self.screen.blit(label, (x, y - 30))
        # Extra tank icons under the bar (mini bottles, one per remaining tank).
        tanks = getattr(self.player, "nitro_tanks", 0)
        if tanks > 0:
            bx = x + w
            by = y + h + 6
            for i in range(tanks):
                rx = bx - (i + 1) * 18
                ry = by
                bottle = pygame.Rect(rx, ry, 12, 18)
                pygame.draw.rect(self.screen, (34, 34, 42), bottle, border_radius=3)
                pygame.draw.rect(self.screen, (60, 210, 240), bottle.inflate(-4, -6), border_radius=2)
                pygame.draw.rect(self.screen, (12, 12, 18), bottle, 1, border_radius=3)

    def _draw_wallet_hud(self) -> None:
        """Top-right wallet badge showing current balance."""
        font_s = pygame.font.SysFont(None, 32, bold=True)
        text = f"${self.wallet.balance}"
        tsurf = font_s.render(text, True, (30, 30, 30))
        pad = 10
        w = tsurf.get_width() + pad * 2 + 22
        h = tsurf.get_height() + pad
        x = config.SCREEN_WIDTH - w - 24
        y = 20
        panel = pygame.Rect(x, y, w, h)
        pygame.draw.rect(self.screen, (230, 200, 90), panel, border_radius=8)
        pygame.draw.rect(self.screen, (120, 90, 20), panel, 2, border_radius=8)
        # Coin circle on the left.
        pygame.draw.circle(self.screen, (245, 225, 120), (x + 14, y + h // 2), 8)
        pygame.draw.circle(self.screen, (120, 90, 20), (x + 14, y + h // 2), 8, 1)
        self.screen.blit(tsurf, (x + 26, y + pad // 2))

    def _draw_powerups_hud(self) -> None:
        """Active-power banners under the wallet + center banner on pickup."""
        font_s = pygame.font.SysFont(None, 28, bold=True)
        font_big = pygame.font.SysFont(None, 64, bold=True)

        # Stacked power-up pills under the wallet badge (top-right).
        y = 72
        pills: list[tuple[str, tuple[int, int, int]]] = []
        if self._invincible_frames > 0:
            secs = self._invincible_frames / config.FPS
            pills.append((f"INVINCIBLE  {secs:0.1f}s", (120, 200, 255)))
        if self._ram_frames > 0:
            secs = self._ram_frames / config.FPS
            pills.append((f"RAM MODE  {secs:0.1f}s", (255, 150, 70)))
        for text, col in pills:
            tsurf = font_s.render(text, True, (20, 20, 20))
            pad = 10
            w = tsurf.get_width() + pad * 2
            h = tsurf.get_height() + pad
            x = config.SCREEN_WIDTH - w - 24
            rect = pygame.Rect(x, y, w, h)
            pygame.draw.rect(self.screen, col, rect, border_radius=8)
            pygame.draw.rect(self.screen, (30, 30, 30), rect, 2, border_radius=8)
            self.screen.blit(tsurf, (x + pad, y + pad // 2))
            y += h + 8

        # Big transient banner when a gift has just been opened.
        if self._gift_msg_frames > 0 and self._gift_msg:
            # Fade alpha in the last 20 frames.
            alpha = 255
            if self._gift_msg_frames < 20:
                alpha = int(255 * self._gift_msg_frames / 20)
            tsurf = font_big.render(self._gift_msg, True, (255, 230, 80))
            shadow = font_big.render(self._gift_msg, True, (0, 0, 0))
            tsurf.set_alpha(alpha)
            shadow.set_alpha(alpha)
            cx = config.SCREEN_WIDTH // 2
            cy = 150
            self.screen.blit(shadow, shadow.get_rect(center=(cx + 3, cy + 3)))
            self.screen.blit(tsurf, tsurf.get_rect(center=(cx, cy)))

    def _draw_stage_stars(self, stage_idx: int) -> None:
        """Render `stage_idx` sheriff-badge stars across the top-center of the screen."""
        if stage_idx <= 0:
            return
        star_r = 22
        gap = 14
        total_w = stage_idx * (star_r * 2) + (stage_idx - 1) * gap
        start_x = config.SCREEN_WIDTH // 2 - total_w // 2 + star_r
        y = 42
        for i in range(stage_idx):
            cx = start_x + i * (star_r * 2 + gap)
            self._draw_sheriff_star(cx, y, star_r)

    def _draw_sheriff_star(self, cx: int, cy: int, r_outer: int) -> None:
        """Six-point gold badge with a small center dot, stroked in black."""
        r_inner = int(r_outer * 0.46)
        pts: list[tuple[int, int]] = []
        for i in range(12):
            r = r_outer if i % 2 == 0 else r_inner
            ang = math.radians(-90 + i * 30)
            pts.append((int(cx + r * math.cos(ang)), int(cy + r * math.sin(ang))))
        shadow = [(x + 2, y + 3) for (x, y) in pts]
        pygame.draw.polygon(self.screen, (0, 0, 0, 80), shadow)
        pygame.draw.polygon(self.screen, (245, 196, 60), pts)
        pygame.draw.polygon(self.screen, (40, 30, 10), pts, 2)
        pygame.draw.circle(self.screen, (210, 150, 30), (cx, cy), max(3, r_outer // 5))
        pygame.draw.circle(
            self.screen, (40, 30, 10), (cx, cy), max(3, r_outer // 5), 1
        )

    def _start_session(self) -> None:
        # Restart the engine loop/music that game_over_screen silenced.
        self.snd.resume_gameplay()
        # Carry over position/direction/velocity from the menu demo car so
        # hitting Start feels like a smooth hand-off: the same car keeps
        # rolling, just with fresh stats (HP/speed caps/etc.) and real input.
        start_x = self.player.x
        start_y = self.player.y
        start_dir = self.player.direction
        start_vx = self.player.vx
        start_vy = self.player.vy
        self.player = Player(start_x, start_y)
        self.player.direction = start_dir
        self.player.vx = start_vx
        self.player.vy = start_vy
        self.player.nitro_tanks = self.pending_nitro_tanks
        # Bought nitro only lives for this run; clear it so the next game
        # requires a new purchase.
        self.pending_nitro_tanks = 0
        # Regenerate with a safe zone around the new start so cacti don't
        # spawn directly in front of the player on kickoff.
        self.map.generate(self.player.x, self.player.y)
        self.police.clear()
        self.stats = StatsTracker()
        self.frame = 0
        self.start_ticks = pygame.time.get_ticks()
        self.last_spawn = self.start_ticks - config.SPAWN_INTERVAL_MS
        self._prev_forward = False
        self._prev_q_pressed = False
        self._hit_invuln_frames = 0
        self._cactus_hit_cd = 0
        self._death_frames = 0
        self._crash_sfx_cd = 0
        self._invincible_frames = 0
        self._ram_frames = 0
        self._gift_msg = ""
        self._gift_msg_frames = 0
        self._count_cactus_hits = 0
        self._count_banana_slips = 0
        self._count_player_police_collisions = 0
        self._count_police_killed = 0
        self._count_gifts_collected = 0
        self._money_earned_this_frame = 0
        self.tire_marks.clear()
        self.drip_fx.clear()
        self.engine_fx.clear()
        self._show_hitboxes = config.DEBUG_SHOW_HITBOXES
        self.playing = True

    # ------------------------------------------------------------------
    # Menu demo: a living background where the player car cruises along
    # the top road slowly. Police aren't spawned until the real game starts.
    # ------------------------------------------------------------------
    def _init_menu_demo(self) -> None:
        """Set up a slow cruising demo used as the menu background."""
        # Top horizontal road is centered at world_height/2 - gap (gap=120
        # in Map.generate). Place the demo car on it facing east.
        top_road_y = config.WORLD_HEIGHT // 2 - 120
        self.player = Player(config.WORLD_WIDTH * 0.3, top_road_y)
        self.player.direction = -90.0  # face right (east)
        # Calm, slow cruise so the background is chill, not a race.
        self.player.max_speed = 4.5
        self.player.engine_accel = 0.35
        self.player.nitro_tanks = 0
        self.map.generate(self.player.x, self.player.y, safe_radius=220.0)
        self.police.clear()
        self.tire_marks.clear()
        self.drip_fx.clear()
        self.engine_fx.clear()
        self._prev_forward = False

    class _ForwardOnlyKeys:
        """Stub keys dict that reports only W/UP held (steady throttle)."""

        def __getitem__(self, key: int) -> bool:
            return key in (pygame.K_w, pygame.K_UP)

    _FORWARD_KEYS = _ForwardOnlyKeys()

    def _step_menu_demo(self) -> None:
        """Advance the demo player forward one frame."""
        self.player.set_nitro_input(False)
        self.player.move(self._FORWARD_KEYS, self.map.get_obstacles(),
                         self.tire_marks, self.drip_fx)

    def _render_menu_scene(self) -> None:
        """Draw the world + demo car (no HUD) behind the menu UI."""
        cam_x, cam_y = self._camera()
        self.map.draw(self.screen, cam_x, cam_y)
        self.tire_marks.draw(self.screen, cam_x, cam_y)
        self.drip_fx.draw(self.screen, cam_x, cam_y)
        self.player.draw(self.screen, cam_x, cam_y)
        self.engine_fx.draw(self.screen, cam_x, cam_y)

    def start_screen(self) -> bool:
        """Menu: live world behind, wallet, Buy Nitro, and Start buttons."""
        big = pygame.font.SysFont(None, 96, bold=True)
        med = pygame.font.SysFont(None, 44)
        small = pygame.font.SysFont(None, 28)
        tiny = pygame.font.SysFont(None, 24)

        sw, sh = config.SCREEN_WIDTH, config.SCREEN_HEIGHT
        # Layout: title at top, action buttons at bottom — leaves the whole
        # middle band free so the demo car/road is never obscured.
        buy_btn = pygame.Rect(0, 0, 360, 60)
        buy_btn.center = (sw // 2, sh - 240)
        stats_btn = pygame.Rect(0, 0, 360, 60)
        stats_btn.center = (sw // 2, sh - 160)
        start_btn = pygame.Rect(0, 0, 360, 60)
        start_btn.center = (sw // 2, sh - 80)

        self._init_menu_demo()

        msg = ""
        msg_timer = 0

        while True:
            mouse = pygame.mouse.get_pos()
            clicked = False
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    return False
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_RETURN or event.key == pygame.K_SPACE:
                        return True
                    if event.key == pygame.K_b:
                        msg, msg_timer = self._try_buy_nitro_pack(), 90
                    if event.key == pygame.K_s:
                        self.stats_screen()
                if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    clicked = True

            if clicked:
                if buy_btn.collidepoint(mouse):
                    msg, msg_timer = self._try_buy_nitro_pack(), 90
                elif stats_btn.collidepoint(mouse):
                    self.stats_screen()
                elif start_btn.collidepoint(mouse):
                    return True

            # Animated game-world background — no dimming overlays.
            self._step_menu_demo()
            self._render_menu_scene()

            # --- Top: title + subtitle + wallet inline ---
            title = big.render("Chase Rush", True, (255, 210, 80))
            tshadow = big.render("Chase Rush", True, (0, 0, 0))
            self.screen.blit(tshadow, tshadow.get_rect(center=(sw // 2 + 4, 64)))
            self.screen.blit(title, title.get_rect(center=(sw // 2, 60)))
            sub = small.render("Outrun the law. Grab the cash.", True, (240, 220, 180))
            self.screen.blit(sub, sub.get_rect(center=(sw // 2, 120)))

            # --- Bottom: compact wallet pill above the three buttons ---
            pill = pygame.Rect(0, 0, 460, 42)
            pill.center = (sw // 2, sh - 320)
            pill_surf = pygame.Surface(pill.size, pygame.SRCALPHA)
            pygame.draw.rect(pill_surf, (40, 30, 22, 210), pill_surf.get_rect(), border_radius=10)
            pygame.draw.rect(pill_surf, (200, 160, 60, 255), pill_surf.get_rect(), 2, border_radius=10)
            self.screen.blit(pill_surf, pill.topleft)
            wtxt = small.render(
                f"Wallet: ${self.wallet.balance}    Extra Tanks: x{self.pending_nitro_tanks}",
                True,
                (240, 220, 140),
            )
            self.screen.blit(wtxt, wtxt.get_rect(center=pill.center))

            # Shop (Buy) button.
            hover_buy = buy_btn.collidepoint(mouse)
            btn_col = (80, 40, 40) if not hover_buy else (120, 60, 60)
            pygame.draw.rect(self.screen, btn_col, buy_btn, border_radius=12)
            pygame.draw.rect(self.screen, (230, 90, 90), buy_btn, 2, border_radius=12)
            btxt = med.render(
                f"Buy Nitro Pack  (+{config.NITRO_PACK_TANKS})  ${config.NITRO_PACK_COST}",
                True,
                (255, 230, 230),
            )
            self.screen.blit(btxt, btxt.get_rect(center=buy_btn.center))
            hint = tiny.render("Click or press B", True, (220, 180, 180))
            self.screen.blit(hint, hint.get_rect(center=(buy_btn.centerx, buy_btn.bottom + 14)))

            # Stats button.
            hover_stats = stats_btn.collidepoint(mouse)
            sc_s = (40, 40, 90) if not hover_stats else (60, 60, 130)
            pygame.draw.rect(self.screen, sc_s, stats_btn, border_radius=12)
            pygame.draw.rect(self.screen, (140, 160, 230), stats_btn, 2, border_radius=12)
            st_text = med.render("Stats", True, (220, 230, 255))
            self.screen.blit(st_text, st_text.get_rect(center=stats_btn.center))
            hint_st = tiny.render("Click or press S", True, (180, 200, 230))
            self.screen.blit(hint_st, hint_st.get_rect(center=(stats_btn.centerx, stats_btn.bottom + 14)))

            # Start button.
            hover_start = start_btn.collidepoint(mouse)
            sc = (40, 90, 40) if not hover_start else (60, 130, 60)
            pygame.draw.rect(self.screen, sc, start_btn, border_radius=12)
            pygame.draw.rect(self.screen, (140, 220, 140), start_btn, 2, border_radius=12)
            stext = med.render("Start Game", True, (230, 255, 230))
            self.screen.blit(stext, stext.get_rect(center=start_btn.center))
            hint2 = tiny.render("Click or press ENTER", True, (180, 220, 180))
            self.screen.blit(hint2, hint2.get_rect(center=(start_btn.centerx, start_btn.bottom + 14)))

            # Transient feedback from a purchase attempt.
            if msg_timer > 0 and msg:
                col = (240, 220, 120) if "Bought" in msg else (240, 120, 120)
                mtxt = small.render(msg, True, col)
                self.screen.blit(mtxt, mtxt.get_rect(center=(sw // 2, sh - 60)))
                msg_timer -= 1

            pygame.display.flip()
            self.clock.tick(config.FPS)

    def stats_screen(self) -> None:
        """Full-dashboard Stats screen with vertical scrolling.

        Matplotlib renders a tall multi-section PNG to disk; pygame
        then shows a scrollable viewport over that image with a sticky
        header bar (``Back`` + scroll hints) and a custom scrollbar
        along the right edge.
        """
        import os

        big = pygame.font.SysFont(None, 54, bold=True)
        med = pygame.font.SysFont(None, 30, bold=True)
        tiny = pygame.font.SysFont(None, 22)

        sw, sh = config.SCREEN_WIDTH, config.SCREEN_HEIGHT
        header_h = 80
        back_btn = pygame.Rect(30, header_h // 2 - 22, 120, 44)

        # --- loading splash ---------------------------------------------
        self.screen.fill((20, 18, 26))
        loading = med.render("Rendering dashboard…", True, (230, 200, 160))
        self.screen.blit(loading, loading.get_rect(center=(sw // 2, sh // 2)))
        pygame.display.flip()

        chart_surface: Optional[pygame.Surface] = None
        error_text: Optional[str] = None
        if os.path.exists(config.GAMEPLAY_STATS_CSV):
            try:
                from .dashboard import Dashboard

                Dashboard().load_data().plot_charts()
                if os.path.exists(Dashboard.OUTPUT_PATH):
                    raw = pygame.image.load(Dashboard.OUTPUT_PATH).convert()
                    chart_surface = self._fit_width(raw, sw - 40)
            except Exception as exc:  # pragma: no cover — visual feedback
                error_text = f"Could not render charts: {exc}"
        else:
            error_text = "No games played yet — finish a run to see your stats."

        # --- scroll state -----------------------------------------------
        viewport = pygame.Rect(20, header_h + 10, sw - 40, sh - header_h - 20)
        if chart_surface is not None:
            content_h = chart_surface.get_height()
        else:
            content_h = viewport.height
        max_scroll = max(0, content_h - viewport.height)
        scroll_y = 0
        step = 60
        page_step = viewport.height - 60

        dragging_bar = False
        drag_offset_y = 0

        def bar_rect() -> pygame.Rect:
            if max_scroll <= 0:
                return pygame.Rect(sw - 14, viewport.top, 8, viewport.height)
            track_h = viewport.height
            bar_h = max(40, int(track_h * viewport.height / content_h))
            bar_y = viewport.top + int(
                (track_h - bar_h) * (scroll_y / max_scroll)
            )
            return pygame.Rect(sw - 14, bar_y, 8, bar_h)

        while True:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    return
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        return
                    if event.key in (pygame.K_DOWN, pygame.K_j):
                        scroll_y = min(max_scroll, scroll_y + step)
                    elif event.key in (pygame.K_UP, pygame.K_k):
                        scroll_y = max(0, scroll_y - step)
                    elif event.key == pygame.K_PAGEDOWN or event.key == pygame.K_SPACE:
                        scroll_y = min(max_scroll, scroll_y + page_step)
                    elif event.key == pygame.K_PAGEUP:
                        scroll_y = max(0, scroll_y - page_step)
                    elif event.key == pygame.K_HOME:
                        scroll_y = 0
                    elif event.key == pygame.K_END:
                        scroll_y = max_scroll
                if event.type == pygame.MOUSEWHEEL:
                    scroll_y = max(
                        0, min(max_scroll, scroll_y - event.y * step)
                    )
                if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    mp = pygame.mouse.get_pos()
                    if back_btn.collidepoint(mp):
                        return
                    br = bar_rect()
                    if br.collidepoint(mp):
                        dragging_bar = True
                        drag_offset_y = mp[1] - br.top
                    elif (
                        max_scroll > 0
                        and sw - 18 <= mp[0] <= sw - 2
                        and viewport.top <= mp[1] <= viewport.bottom
                    ):
                        # Click-on-track jumps one page in that direction.
                        if mp[1] < br.top:
                            scroll_y = max(0, scroll_y - page_step)
                        else:
                            scroll_y = min(max_scroll, scroll_y + page_step)
                if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                    dragging_bar = False
                if event.type == pygame.MOUSEMOTION and dragging_bar and max_scroll > 0:
                    br = bar_rect()
                    track_top = viewport.top
                    track_h = viewport.height - br.height
                    new_top = event.pos[1] - drag_offset_y
                    t = max(0.0, min(1.0, (new_top - track_top) / max(1, track_h)))
                    scroll_y = int(t * max_scroll)

            # --- draw --------------------------------------------------
            self.screen.fill((20, 18, 26))

            # Viewport content (clipped chart).
            if chart_surface is not None:
                src_rect = pygame.Rect(
                    0,
                    scroll_y,
                    chart_surface.get_width(),
                    min(viewport.height, content_h - scroll_y),
                )
                dest = (
                    viewport.left + (viewport.width - chart_surface.get_width()) // 2,
                    viewport.top,
                )
                self.screen.blit(chart_surface, dest, src_rect)
            else:
                msg = med.render(
                    error_text or "No data.", True, (230, 200, 160)
                )
                self.screen.blit(msg, msg.get_rect(center=viewport.center))

            # Header bar (sits above the viewport — opaque).
            header_rect = pygame.Rect(0, 0, sw, header_h)
            pygame.draw.rect(self.screen, (26, 22, 34), header_rect)
            pygame.draw.line(
                self.screen, (90, 80, 120), (0, header_h), (sw, header_h), 2
            )

            # Back button.
            mp = pygame.mouse.get_pos()
            hover = back_btn.collidepoint(mp)
            col = (70, 70, 100) if not hover else (100, 100, 140)
            pygame.draw.rect(self.screen, col, back_btn, border_radius=10)
            pygame.draw.rect(self.screen, (180, 180, 220), back_btn, 2, border_radius=10)
            bt = med.render("◄ Back", True, (230, 230, 255))
            self.screen.blit(bt, bt.get_rect(center=back_btn.center))

            # Title.
            title = big.render("Run Dashboard", True, (255, 215, 90))
            self.screen.blit(title, title.get_rect(center=(sw // 2, header_h // 2)))

            # Hint on the right.
            hint = tiny.render(
                "Scroll / ↑↓ / PgUp-PgDn   ·   ESC to close",
                True,
                (170, 170, 200),
            )
            self.screen.blit(hint, hint.get_rect(midright=(sw - 24, header_h // 2)))

            # Scrollbar.
            if chart_surface is not None and max_scroll > 0:
                track = pygame.Rect(sw - 16, viewport.top, 12, viewport.height)
                pygame.draw.rect(self.screen, (38, 34, 48), track, border_radius=6)
                br = bar_rect()
                pygame.draw.rect(self.screen, (140, 130, 170), br, border_radius=4)
                pygame.draw.rect(self.screen, (200, 190, 230), br, 1, border_radius=4)

            pygame.display.flip()
            self.clock.tick(config.FPS)

    def _fit_width(self, surf: pygame.Surface, target_w: int) -> pygame.Surface:
        """Scale ``surf`` so that its width == ``target_w`` (aspect-preserving)."""
        w, h = surf.get_size()
        if w == target_w:
            return surf
        new_h = max(1, int(h * target_w / w))
        return pygame.transform.smoothscale(surf, (target_w, new_h))

    def _try_buy_nitro_pack(self) -> str:
        """Attempt to buy a nitro pack; return a short status string."""
        if self.wallet.spend(config.NITRO_PACK_COST):
            self.pending_nitro_tanks += config.NITRO_PACK_TANKS
            return f"Bought +{config.NITRO_PACK_TANKS} nitro tanks!"
        return "Not enough money."

    def _grayscale_snapshot(self) -> pygame.Surface:
        """Return a desaturated copy of the current screen for a noir freeze-frame."""
        snap = self.screen.copy()
        try:
            import numpy as np
            import pygame.surfarray as sa
            arr = sa.pixels3d(snap)
            # Luminance weights (BT.601) give a natural-looking grayscale.
            gray = (
                arr[:, :, 0] * 0.299
                + arr[:, :, 1] * 0.587
                + arr[:, :, 2] * 0.114
            ).astype(np.uint8)
            arr[:, :, 0] = gray
            arr[:, :, 1] = gray
            arr[:, :, 2] = gray
            del arr
        except Exception:
            # Fallback: simple dark overlay if numpy/surfarray is unavailable.
            dim = pygame.Surface(snap.get_size())
            dim.fill((40, 40, 40))
            dim.set_alpha(180)
            snap.blit(dim, (0, 0))
        return snap

    def game_over_screen(self) -> bool:
        # Only the background music should keep playing from here on out.
        self.snd.silence_gameplay()

        big = pygame.font.SysFont(None, 110, bold=True)
        small = pygame.font.SysFont(None, 40)
        tiny = pygame.font.SysFont(None, 28)

        bg = self._grayscale_snapshot()
        vignette = pygame.Surface(
            (config.SCREEN_WIDTH, config.SCREEN_HEIGHT), pygame.SRCALPHA
        )
        vignette.fill((0, 0, 0, 120))

        survived = int(self._elapsed_s())
        pulse = 0

        while True:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    return False
                if event.type == pygame.KEYDOWN and event.key in (
                    pygame.K_ESCAPE,
                    pygame.K_RETURN,
                    pygame.K_SPACE,
                ):
                    return True
                if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    return True

            self.screen.blit(bg, (0, 0))
            self.screen.blit(vignette, (0, 0))

            t1 = big.render("GAME OVER", True, (230, 40, 40))
            t1_shadow = big.render("GAME OVER", True, (0, 0, 0))
            cx = config.SCREEN_WIDTH // 2
            cy = config.SCREEN_HEIGHT // 2 - 40
            self.screen.blit(t1_shadow, t1_shadow.get_rect(center=(cx + 4, cy + 4)))
            self.screen.blit(t1, t1.get_rect(center=(cx, cy)))

            t2 = small.render(f"Survived {survived} s", True, (230, 230, 230))
            t3 = small.render(f"Wallet: ${self.wallet.balance}", True, (240, 220, 120))
            self.screen.blit(t2, t2.get_rect(center=(cx, cy + 80)))
            self.screen.blit(t3, t3.get_rect(center=(cx, cy + 120)))

            # Gently pulsing "press any key" prompt.
            pulse = (pulse + 1) % 120
            alpha = 160 + int(80 * abs(math.sin(pulse / 120.0 * math.pi * 2)))
            hint = tiny.render(
                "Press ENTER / SPACE / ESC to return to menu", True, (220, 220, 220)
            )
            hint.set_alpha(alpha)
            self.screen.blit(hint, hint.get_rect(center=(cx, cy + 190)))

            pygame.display.flip()
            self.clock.tick(config.FPS)

    def run(self) -> None:
        alive = True
        while alive:
            if not self.start_screen():
                break
            self._start_session()
            while alive and self.playing:
                alive = self.handle_events()
                if not alive:
                    break
                dt = self.clock.tick(config.FPS)
                self.update(dt)
                self.render()

            had_logs = bool(self.stats.session_data)
            if had_logs:
                self.stats.save_csv()
                # Also append a one-row summary so the dashboard can plot
                # run-to-run comparisons over the player's history.
                try:
                    self.stats.append_run_summary()
                except Exception:
                    pass
            if not alive:
                break
            alive = self.game_over_screen()
        pygame.quit()
