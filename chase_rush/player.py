"""Player vehicle — velocity-based movement with drag and lateral grip."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any, Optional, Sequence

import pygame

from . import config
from .collision import (
    clip_velocity_into_wall,
    poly_hits_any_rect,
    resolve_push_out_of_rects,
    rotated_box,
    unstick_vehicle_from_rects,
)
from .tire_fx import add_skid_marks

if TYPE_CHECKING:
    from .tire_fx import DripSmokeFX, TireMarkManager


class _NoInput:
    """Stand-in for pygame.key.get_pressed() that reports nothing held."""

    def __getitem__(self, _key: int) -> bool:
        return False


_NO_KEYS = _NoInput()


class Player:
    def __init__(self, x: float, y: float) -> None:
        self.x = float(x)
        self.y = float(y)
        self.direction = 0.0
        self.vx = 0.0
        self.vy = 0.0
        self.rotation_speed = 0.0
        self.w = config.CAR_W
        self.h = config.CAR_H
        self.image = pygame.transform.scale(
            pygame.image.load(config.PLAYER_IMG), (self.w, self.h)
        )
        self.max_speed = 39.0
        self.max_back = 10.5
        self.engine_accel = 1.14
        self.brake_accel = 0.92
        self.roll_friction = 0.12
        self.drag_quad = 0.00085
        # Grip reacts to speed: more slip at high speed, tighter at low speed.
        self.lateral_grip_low = 0.97
        self.lateral_grip_high = 0.80
        # Turn rate grows with speed (arcade feel): parked car barely turns,
        # full-throttle car swings its heading fast. The rate caps out once
        # the car is at its practical top speed (steer_ref_speed) so we get
        # the full range of turning within normal play, not only near max_speed.
        self.min_turn = 1.2
        self.max_turn = 7.5
        self.steer_ref_speed = 11.0
        self.turn_curve = 1.0
        # Wheelbase governs how much lateral push the steering induces.
        self.steer_push = 0.055
        self._last_eff_speed = 0.0
        self.hp = config.PLAYER_MAX_HP
        # Nitrous boost: Q button floods extra power and raises the speed cap
        # until the bar is drained. The bar refills slowly when not in use.
        self.nitro_max = 100.0
        self.nitro = self.nitro_max
        self.nitro_drain_per_s = 45.0
        self.nitro_regen_per_s = 12.0
        self.nitro_active = False
        # Tuned so actual terminal speed (drag-limited) lands near 16.
        # Drag is cut during nitro because the base drag_quad is tuned for a
        # ~10.5 top speed; without that cut the boost caps out around 12.
        self.nitro_speed_mult = 1.8
        self.nitro_accel_mult = 3.5
        self.nitro_drag_mult = 0.55
        self._nitro_requested = False
        # Frames during which the throttle is ignored (set after a banana
        # peel slip so the driver can't just mash gas through the spin).
        self._throttle_lock_frames = 0
        # Extra nitro tanks bought from the menu. Each tank auto-refills the
        # main bar when it empties; the count resets every new game.
        self.nitro_tanks = 0

    def _forward_unit(self, angle_deg: float) -> tuple[float, float]:
        rad = math.radians(angle_deg)
        return -math.sin(rad), -math.cos(rad)

    def _right_unit(self, angle_deg: float) -> tuple[float, float]:
        rad = math.radians(angle_deg)
        return math.cos(rad), -math.sin(rad)

    def _forward_pressed(self, keys: Any) -> bool:
        # Throttle lock (e.g. right after a banana slip) suppresses the
        # accelerator for a short window; steering/reverse still work.
        if self._throttle_lock_frames > 0:
            return False
        return keys[pygame.K_UP] or keys[pygame.K_w]

    def _back_pressed(self, keys: Any) -> bool:
        return keys[pygame.K_DOWN] or keys[pygame.K_s]

    def _left_pressed(self, keys: Any) -> bool:
        return keys[pygame.K_LEFT] or keys[pygame.K_a]

    def _right_pressed(self, keys: Any) -> bool:
        return keys[pygame.K_RIGHT] or keys[pygame.K_d]

    def set_nitro_input(self, pressed: bool) -> None:
        """Record whether the nitrous button (Q) is currently held."""
        self._nitro_requested = bool(pressed)

    def get_hit_poly(self) -> list[tuple[float, float]]:
        return rotated_box(self.x, self.y, self.w, self.h, self.direction)

    def get_rect(self) -> pygame.Rect:
        poly = self.get_hit_poly()
        xs = [p[0] for p in poly]
        ys = [p[1] for p in poly]
        return pygame.Rect(int(min(xs)), int(min(ys)), int(max(xs) - min(xs)), int(max(ys) - min(ys)))

    def move(
        self,
        keys: Any,
        obstacles: Sequence[pygame.Rect],
        tire_marks: Optional["TireMarkManager"] = None,
        drip_fx: Optional["DripSmokeFX"] = None,
    ) -> float:
        unstick_vehicle_from_rects(self, self.w, self.h, obstacles)
        if self._throttle_lock_frames > 0:
            self._throttle_lock_frames -= 1

        ux, uy = self._forward_unit(self.direction)
        sx, sy = self._right_unit(self.direction)

        v_forward = self.vx * ux + self.vy * uy
        v_lat = self.vx * sx + self.vy * sy

        spd_ratio = min(1.0, abs(v_forward) / max(self.max_speed, 0.01))
        steer_ratio = min(1.0, abs(v_forward) / max(self.steer_ref_speed, 0.01))
        turn_rate = self.min_turn + (self.max_turn - self.min_turn) * (
            steer_ratio ** self.turn_curve
        )

        # Need a bit of forward motion before steering engages (wheels rolling).
        steer_dir = 0
        if self._left_pressed(keys):
            steer_dir += 1
        if self._right_pressed(keys):
            steer_dir -= 1

        if abs(v_forward) >= 0.5 and steer_dir != 0:
            # Reverse inverts steering direction (like real cars).
            sign = 1.0 if v_forward >= 0 else -1.0
            self.direction += steer_dir * turn_rate * sign

        ux, uy = self._forward_unit(self.direction)
        sx, sy = self._right_unit(self.direction)
        v_forward = self.vx * ux + self.vy * uy
        v_lat = self.vx * sx + self.vy * sy

        # Nitrous: active only while requested AND bar has charge.
        self.nitro_active = self._nitro_requested and self.nitro > 0.0
        dt = 1.0 / config.FPS
        if self.nitro_active:
            self.nitro = max(0.0, self.nitro - self.nitro_drain_per_s * dt)
            # Auto-consume a purchased tank to refill the bar on empty so the
            # bought nitro feels seamless.
            if self.nitro <= 0.0 and self.nitro_tanks > 0:
                self.nitro_tanks -= 1
                self.nitro = self.nitro_max
        else:
            self.nitro = min(
                self.nitro_max, self.nitro + self.nitro_regen_per_s * dt
            )
        eff_max_speed = (
            self.max_speed * self.nitro_speed_mult if self.nitro_active else self.max_speed
        )
        eff_engine_accel = (
            self.engine_accel * self.nitro_accel_mult
            if self.nitro_active
            else self.engine_accel
        )

        if self._forward_pressed(keys):
            if v_forward < eff_max_speed:
                headroom = max(0.0, eff_max_speed - v_forward)
                v_forward += eff_engine_accel * (
                    0.18 + 0.82 * math.sqrt(headroom / max(eff_max_speed, 0.01))
                )
                v_forward = min(eff_max_speed, v_forward)
            # If already over max_speed (rammed from behind), coast — drag decays it.
        elif self._back_pressed(keys):
            if v_forward > 0.4:
                v_forward -= self.brake_accel * 1.25
            else:
                v_forward = max(-self.max_back, v_forward - self.engine_accel * 0.55)
        else:
            if v_forward > 0:
                v_forward = max(0.0, v_forward - self.roll_friction * (0.08 + 0.025 * v_forward))
            elif v_forward < 0:
                v_forward = min(0.0, v_forward + self.roll_friction * (0.12 + 0.035 * abs(v_forward)))

        # Steering pushes the rear out: lateral push grows with forward speed.
        if steer_dir != 0 and abs(v_forward) >= 0.5:
            v_lat += steer_dir * abs(v_forward) * self.steer_push

        # Grip: less grip at high speed means more slide through turns.
        grip = self.lateral_grip_high + (self.lateral_grip_low - self.lateral_grip_high) * (1.0 - spd_ratio)
        v_lat *= grip

        self.vx = v_forward * ux + v_lat * sx
        self.vy = v_forward * uy + v_lat * sy

        vmag2 = self.vx * self.vx + self.vy * self.vy
        if vmag2 > 1e-6:
            drag_q = (
                self.drag_quad * self.nitro_drag_mult
                if self.nitro_active
                else self.drag_quad
            )
            drag = drag_q * vmag2
            scale = max(0.0, 1.0 - drag)
            self.vx *= scale
            self.vy *= scale
            vmag2 = self.vx * self.vx + self.vy * self.vy

        if drip_fx is not None and vmag2 > 14.0:
            slip = abs(self.vx * sx + self.vy * sy)
            if slip > 2.4:
                drip_fx.burst(self.x, self.y, self.direction, slip * 0.11)

        dx = self.vx
        dy = self.vy
        pre_vx, pre_vy = self.vx, self.vy
        hit_obstacle = False
        self.x += dx
        self.y += dy
        if poly_hits_any_rect(self.get_hit_poly(), obstacles):
            hit_obstacle = True
            nx_, ny_, escape_n = self.x, self.y, None
            nx_, ny_, escape_n = resolve_push_out_of_rects(
                self.x, self.y, self.w, self.h, self.direction, obstacles
            )
            self.x, self.y = nx_, ny_
            if escape_n is not None:
                enx, eny = escape_n
                vn = pre_vx * enx + pre_vy * eny
                # Head-on (deep inward) absorbs more, glancing hit keeps more tangential speed.
                approach = max(0.0, -vn)
                impact_scale = min(1.0, approach / 12.0)
                keep_tangent = 0.72 - 0.22 * impact_scale
                self.vx, self.vy = clip_velocity_into_wall(
                    pre_vx, pre_vy, enx, eny, keep_tangent=keep_tangent
                )
                # Energy loss + small rotational kick proportional to glancing component.
                self.vx *= 0.78
                self.vy *= 0.78
                tang_x, tang_y = -eny, enx
                tang = pre_vx * tang_x + pre_vy * tang_y
                self.rotation_speed += max(-3.2, min(3.2, tang * 0.22))
            else:
                self.vx *= 0.42
                self.vy *= 0.42
        if hit_obstacle and tire_marks is not None:
            tire_marks.break_stroke()
        unstick_vehicle_from_rects(self, self.w, self.h, obstacles)

        self.direction += self.rotation_speed
        self.rotation_speed *= 0.92

        unstick_vehicle_from_rects(self, self.w, self.h, obstacles)

        vmag2 = self.vx * self.vx + self.vy * self.vy
        self._last_eff_speed = math.sqrt(vmag2) if vmag2 > 1e-8 else 0.0
        return self._last_eff_speed

    def coast(
        self,
        obstacles: Sequence[pygame.Rect],
        tire_marks: Optional["TireMarkManager"] = None,
        drip_fx: Optional["DripSmokeFX"] = None,
    ) -> float:
        """Run the physics step with no driver input (post-death wreck).

        The wreck feels heavy: extra linear + rotational damping bleeds speed
        fast so the car bounces on impact but doesn't slide forever.
        """
        spd = self.move(_NO_KEYS, obstacles, tire_marks, drip_fx)
        self.vx *= 0.90
        self.vy *= 0.90
        self.rotation_speed *= 0.88
        return spd

    def draw(self, screen: pygame.Surface, cam_x: float, cam_y: float) -> None:
        rot = pygame.transform.rotate(self.image, self.direction)
        rect = rot.get_rect(center=(int(self.x - cam_x), int(self.y - cam_y)))
        screen.blit(rot, rect)

    @property
    def display_speed(self) -> float:
        return self._last_eff_speed
