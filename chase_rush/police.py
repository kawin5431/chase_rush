"""Police pursuit using player-equivalent driving physics."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Optional, Sequence

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
    from .player import Player
    from .tire_fx import DripSmokeFX, TireMarkManager


class Police:
    """AI driver with the same movement limits as Player."""

    def __init__(self, x: float, y: float) -> None:
        self.x = float(x)
        self.y = float(y)
        self.direction = 0.0
        self.vx = 0.0
        self.vy = 0.0
        self.rotation_speed = 0.0
        self.w = config.POLICE_W
        self.h = config.POLICE_H
        self.hit_w = config.POLICE_HIT_W
        self.hit_h = config.POLICE_HIT_H
        self.image = pygame.transform.scale(
            pygame.image.load(config.POLICE_IMG), (self.w, self.h)
        )
        # Police: higher top speed than player, but only half the acceleration,
        # so it's sluggish off the line / after a crash but out-runs the player
        # on long straights. Drag is lower than player's so the terminal
        # velocity is actually reached (drag_quad governs top speed in practice).
        self._base_max_speed = 46.0
        self._base_engine_accel = 0.57
        self._base_max_hp = config.POLICE_MAX_HP
        self.max_speed = self._base_max_speed
        self.max_back = 10.5
        self.engine_accel = self._base_engine_accel
        self.brake_accel = 0.92
        self.roll_friction = 0.12
        self.drag_quad = 0.00017
        self.lateral_grip_low = 0.97
        self.lateral_grip_high = 0.80
        self.min_turn = 1.2
        self.max_turn = 7.5
        self.steer_ref_speed = 14.0
        self.turn_curve = 1.0
        self.steer_push = 0.055
        self.target: Optional["Player"] = None
        self.speed = 0.0
        self.max_hp = self._base_max_hp
        self.hp = self.max_hp
        self.alive = True
        # Post-crash recovery: stops accelerating for this many frames after
        # ramming the player, letting it skid/coast before resuming pursuit.
        self._stun_frames = 0
        self.stun_on_player_hit = int(config.FPS * 0.5)
        # Cooldown (frames) so a single cactus can't be dinged twice on
        # successive frames while the AI drives through it.
        self._cactus_hit_cd = 0

    @property
    def display_speed(self) -> float:
        return math.hypot(self.vx, self.vy)

    def stun(self, frames: Optional[int] = None) -> None:
        n = self.stun_on_player_hit if frames is None else frames
        if n > self._stun_frames:
            self._stun_frames = n

    def get_hit_poly(self) -> list[tuple[float, float]]:
        return rotated_box(self.x, self.y, self.hit_w, self.hit_h, self.direction)

    def _forward_unit(self, angle_deg: float) -> tuple[float, float]:
        rad = math.radians(angle_deg)
        return -math.sin(rad), -math.cos(rad)

    def _right_unit(self, angle_deg: float) -> tuple[float, float]:
        rad = math.radians(angle_deg)
        return math.cos(rad), -math.sin(rad)

    def _aim_diff(self) -> tuple[float, float]:
        """Returns (signed angle diff in degrees, distance)."""
        if self.target is None:
            return 0.0, 0.0
        dx = self.target.x - self.x
        dy = self.target.y - self.y
        dist = math.hypot(dx, dy)
        desired = math.degrees(math.atan2(-dx, -dy))
        diff = (desired - self.direction + 180) % 360 - 180
        return diff, dist

    def _control_inputs(self, turn_rate: float) -> tuple[bool, bool, bool, bool]:
        if self.target is None:
            return False, False, False, False
        diff, dist = self._aim_diff()
        deadband = max(2.5, turn_rate * 0.7)
        left = diff > deadband
        right = diff < -deadband
        brake = abs(diff) > 115 and dist < 220
        forward = not brake
        # While stunned (just rammed the player), stop throttling — coast.
        if self._stun_frames > 0:
            forward = False
            brake = False
        return forward, brake, left, right

    def draw(self, screen: pygame.Surface, cam_x: float, cam_y: float) -> None:
        rot = pygame.transform.rotate(self.image, self.direction)
        rect = rot.get_rect(center=(int(self.x - cam_x), int(self.y - cam_y)))
        screen.blit(rot, rect)

    def update(
        self,
        obstacles: Sequence[pygame.Rect],
        tire_marks: Optional["TireMarkManager"] = None,
        drip_fx: Optional["DripSmokeFX"] = None,
    ) -> None:
        unstick_vehicle_from_rects(self, self.hit_w, self.hit_h, obstacles)

        if self.alive and self._stun_frames > 0:
            self._stun_frames -= 1

        ux, uy = self._forward_unit(self.direction)
        sx, sy = self._right_unit(self.direction)
        v_forward = self.vx * ux + self.vy * uy
        v_lat = self.vx * sx + self.vy * sy

        spd_ratio = min(1.0, abs(v_forward) / max(self.max_speed, 0.01))
        steer_ratio = min(1.0, abs(v_forward) / max(self.steer_ref_speed, 0.01))
        turn_rate = self.min_turn + (self.max_turn - self.min_turn) * (
            steer_ratio ** self.turn_curve
        )

        if self.alive:
            forward, back, left, right = self._control_inputs(turn_rate)
            steer_dir = (1 if left else 0) - (1 if right else 0)
            if abs(v_forward) >= 0.5 and steer_dir != 0:
                sign = 1.0 if v_forward >= 0 else -1.0
                diff, _ = self._aim_diff()
                step = min(turn_rate, max(0.0, abs(diff) - turn_rate * 0.3))
                self.direction += steer_dir * step * sign
        else:
            # Wreck: no AI, no steering, no throttle. Physics still runs so the
            # car keeps bouncing when rammed and coasts to a stop via drag.
            forward = False
            back = False
            steer_dir = 0

        ux, uy = self._forward_unit(self.direction)
        sx, sy = self._right_unit(self.direction)
        v_forward = self.vx * ux + self.vy * uy
        v_lat = self.vx * sx + self.vy * sy

        if forward:
            if v_forward < self.max_speed:
                headroom = max(0.0, self.max_speed - v_forward)
                v_forward += self.engine_accel * (0.18 + 0.82 * math.sqrt(headroom / max(self.max_speed, 0.01)))
                v_forward = min(self.max_speed, v_forward)
            # Allow over-max from a crash to decay via drag instead of hard clipping.
        elif back:
            if v_forward > 0.4:
                v_forward -= self.brake_accel * 1.25
            else:
                v_forward = max(-self.max_back, v_forward - self.engine_accel * 0.55)
        else:
            if v_forward > 0:
                v_forward = max(0.0, v_forward - self.roll_friction * (0.08 + 0.025 * v_forward))
            elif v_forward < 0:
                v_forward = min(0.0, v_forward + self.roll_friction * (0.12 + 0.035 * abs(v_forward)))

        if steer_dir != 0 and abs(v_forward) >= 0.5:
            v_lat += steer_dir * abs(v_forward) * self.steer_push

        grip = self.lateral_grip_high + (self.lateral_grip_low - self.lateral_grip_high) * (1.0 - spd_ratio)
        v_lat *= grip
        self.vx = v_forward * ux + v_lat * sx
        self.vy = v_forward * uy + v_lat * sy

        vmag2 = self.vx * self.vx + self.vy * self.vy
        if vmag2 > 1e-6:
            drag = self.drag_quad * vmag2
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
            nx_, ny_, escape_n = resolve_push_out_of_rects(
                self.x, self.y, self.hit_w, self.hit_h, self.direction, obstacles
            )
            self.x, self.y = nx_, ny_
            if escape_n is not None:
                enx, eny = escape_n
                vn = pre_vx * enx + pre_vy * eny
                approach = max(0.0, -vn)
                impact_scale = min(1.0, approach / 12.0)
                keep_tangent = 0.72 - 0.22 * impact_scale
                self.vx, self.vy = clip_velocity_into_wall(
                    pre_vx, pre_vy, enx, eny, keep_tangent=keep_tangent
                )
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

        unstick_vehicle_from_rects(self, self.hit_w, self.hit_h, obstacles)

        self.direction += self.rotation_speed
        self.rotation_speed *= 0.92

        unstick_vehicle_from_rects(self, self.hit_w, self.hit_h, obstacles)
        # Wreck acts heavy: extra drag + rotation damping so it reacts to hits
        # but quickly coasts to a stop instead of drifting across the map.
        if not self.alive:
            self.vx *= 0.90
            self.vy *= 0.90
            self.rotation_speed *= 0.88
        self.speed = max(-self.max_back, min(self.max_speed, self.vx * ux + self.vy * uy))

    def apply_difficulty(self, elapsed_s: float) -> None:
        """Scale the cruiser's stats to the current POLICE_STAGES tier.

        Speed/accel multipliers apply immediately; HP cap rises but existing
        damage isn't healed so wounded cars stay wounded into the next stage.
        """
        _, _, speed_mult, accel_mult, hp_mult = config.stage_for(elapsed_s)
        self.max_speed = self._base_max_speed * speed_mult
        self.engine_accel = self._base_engine_accel * accel_mult
        new_max = int(round(self._base_max_hp * hp_mult))
        self.max_hp = new_max
