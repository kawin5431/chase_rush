"""Tire skid marks (line strips) + light smoke/drip particles (player & police)."""

from __future__ import annotations

import math
import random
from typing import Any, Callable, List, Optional, Tuple

import pygame


def wheel_contact_points(
    x: float, y: float, direction_deg: float, w: float, h: float
) -> Tuple[Tuple[float, float], Tuple[float, float]]:
    """Left / right contact near the rear axle (behind center, same basis as movement)."""
    return rear_wheel_pair(x, y, direction_deg, w, h, width_frac=0.30, rear_frac=0.38)


def rear_wheel_pair(
    x: float,
    y: float,
    direction_deg: float,
    w: float,
    h: float,
    *,
    width_frac: float,
    rear_frac: float,
) -> Tuple[Tuple[float, float], Tuple[float, float]]:
    """Rear contact points: same basis as Player._forward_unit / DripSmokeFX rear offset."""
    rad = math.radians(direction_deg)
    sin_a = math.sin(rad)
    cos_a = math.cos(rad)
    # Game forward is (-sin, -cos); rear is opposite → (sin, cos).
    bx, by = sin_a, cos_a
    # Right across the car (matches Player._right_unit).
    rx, ry = cos_a, -sin_a
    br = h * rear_frac
    hw = w * width_frac
    lx = x + bx * br - rx * hw
    ly = y + by * br - ry * hw
    r_x = x + bx * br + rx * hw
    r_y = y + by * br + ry * hw
    return (lx, ly), (r_x, r_y)


def add_skid_marks(
    marks: "TireMarkManager",
    x: float,
    y: float,
    direction_deg: float,
    w: float,
    h: float,
) -> None:
    """One rear axle sample per call — avoids zig-zag from two rows in the same frame."""
    l1, r1 = rear_wheel_pair(x, y, direction_deg, w, h, width_frac=0.30, rear_frac=0.46)
    marks.add_wheel_pair(l1[0], l1[1], r1[0], r1[1])


class TireMarkManager:
    """Connected line segments per wheel; break_stroke() starts a new strip."""

    def __init__(self) -> None:
        self.segments: List[List[float]] = []
        self._prev_l: Optional[Tuple[float, float]] = None
        self._prev_r: Optional[Tuple[float, float]] = None
        self._min_gap = 5.5
        self._max_gap = 88.0

    def clear(self) -> None:
        self.segments.clear()
        self._prev_l = None
        self._prev_r = None

    def break_stroke(self) -> None:
        self._prev_l = None
        self._prev_r = None

    def add_wheel_pair(self, lx: float, ly: float, rx: float, ry: float) -> None:
        if self._prev_l is None:
            self._prev_l = (float(lx), float(ly))
            self._prev_r = (float(rx), float(ry))
            return

        for side in ("l", "r"):
            if side == "l":
                px, py, ppx, ppy = lx, ly, self._prev_l[0], self._prev_l[1]
            else:
                px, py, ppx, ppy = rx, ry, self._prev_r[0], self._prev_r[1]
            d = math.hypot(px - ppx, py - ppy)
            if d >= self._max_gap:
                if side == "l":
                    self._prev_l = (float(lx), float(ly))
                else:
                    self._prev_r = (float(rx), float(ry))
            elif d >= self._min_gap:
                self.segments.append([ppx, ppy, float(px), float(py), 240.0])
                if side == "l":
                    self._prev_l = (float(lx), float(ly))
                else:
                    self._prev_r = (float(rx), float(ry))

    def update(self) -> None:
        for s in self.segments:
            s[4] -= 9.5
        self.segments = [s for s in self.segments if s[4] > 0]

    def draw(self, screen: pygame.Surface, cam_x: float, cam_y: float) -> None:
        for x1, y1, x2, y2, a in self.segments:
            al = max(0, min(255, int(a)))
            wline = max(2, int(5 * al / 255))
            shade = 28 + (255 - al) // 6
            col = (shade, shade, min(48, shade + 6))
            pygame.draw.line(
                screen,
                col,
                (int(x1 - cam_x), int(y1 - cam_y)),
                (int(x2 - cam_x), int(y2 - cam_y)),
                width=wline,
            )


class DripSmokeFX:
    """Short-lived smoke puffs when sliding / hard turn (ดริปควัน).

    On tarmac the puff is grey tire-smoke; on sand (off-road) it turns into
    a tan dust cloud. Pass a `road_check(x, y) -> bool` at construction time
    to route the color decision; without one, every puff is tarmac smoke.
    """

    def __init__(
        self,
        road_check: Optional[Callable[[float, float], bool]] = None,
    ) -> None:
        self._parts: List[dict[str, Any]] = []
        self._road_check = road_check

    def clear(self) -> None:
        self._parts.clear()

    def set_road_check(self, road_check: Callable[[float, float], bool]) -> None:
        self._road_check = road_check

    def burst(self, x: float, y: float, direction_deg: float, strength: float) -> None:
        strength = max(0.0, min(3.5, strength))
        if strength < 0.15:
            return
        rad = math.radians(direction_deg)
        bx = x + self._rear_offset_x(rad, 26.0)
        by = y + self._rear_offset_y(rad, 26.0)
        surface = "road"
        if self._road_check is not None and not self._road_check(bx, by):
            surface = "sand"
        n = 1 + int(strength * 2.2)
        for _ in range(n):
            ang = rad + random.uniform(-0.55, 0.55)
            sp = random.uniform(0.35, 1.15) * strength
            self._parts.append(
                {
                    "x": bx + random.uniform(-4, 4),
                    "y": by + random.uniform(-4, 4),
                    "vx": math.sin(ang) * sp + random.uniform(-0.4, 0.4),
                    "vy": math.cos(ang) * sp + random.uniform(-0.4, 0.4),
                    "life": random.randint(14, 28),
                    "max": 28,
                    "r": random.randint(3, 6),
                    "surface": surface,
                }
            )

    @staticmethod
    def _rear_offset_x(rad: float, dist: float) -> float:
        return dist * math.sin(rad)

    @staticmethod
    def _rear_offset_y(rad: float, dist: float) -> float:
        return dist * math.cos(rad)

    def update(self) -> None:
        for p in self._parts:
            p["life"] -= 1
            p["x"] += p["vx"]
            p["y"] += p["vy"]
            p["vx"] *= 0.92
            p["vy"] *= 0.92
        self._parts = [p for p in self._parts if p["life"] > 0]

    def draw(self, screen: pygame.Surface, cam_x: float, cam_y: float) -> None:
        for p in self._parts:
            t = p["life"] / max(1, p["max"])
            alpha = int(140 * t)
            r = p["r"]
            surf = pygame.Surface((r * 2 + 2, r * 2 + 2), pygame.SRCALPHA)
            if p.get("surface") == "sand":
                # Tan dust: warm yellow that lightens a touch as it fades.
                base = 200 + int(25 * (1 - t))
                color = (base, int(base * 0.82), int(base * 0.52), alpha)
            else:
                g = 110 + int(60 * (1 - t))
                color = (g, g, g, alpha)
            pygame.draw.circle(surf, color, (r + 1, r + 1), r)
            screen.blit(surf, (int(p["x"] - cam_x) - r - 1, int(p["y"] - cam_y) - r - 1))


class EngineSmokeFX:
    """Hood vent smoke / fire when a vehicle is damaged.

    Particles are emitted from the front-left and front-right of the vehicle
    (the hood) and drift outward with the same physics as DripSmokeFX. When
    `mode='fire'` the color palette swaps to a hot orange/red gradient so
    low-HP vehicles trail flames instead of grey smoke.
    """

    def __init__(self) -> None:
        self._parts: List[dict[str, Any]] = []

    def clear(self) -> None:
        self._parts.clear()

    def emit(
        self,
        x: float,
        y: float,
        direction_deg: float,
        w: float,
        h: float,
        mode: str = "smoke",
        intensity: float = 1.0,
    ) -> None:
        """Spawn a pair of hood puffs. Call once per frame while damaged."""
        rad = math.radians(direction_deg)
        fx_, fy_ = -math.sin(rad), -math.cos(rad)
        rx_, ry_ = math.cos(rad), -math.sin(rad)
        front_dist = h * 0.32
        side_dist = w * 0.32
        n_per_side = 1 if intensity < 1.2 else 2
        for side in (-1, 1):
            bx = x + fx_ * front_dist + rx_ * side_dist * side
            by = y + fy_ * front_dist + ry_ * side_dist * side
            for _ in range(n_per_side):
                ox = rx_ * side + random.uniform(-0.25, 0.25)
                oy = ry_ * side + random.uniform(-0.25, 0.25)
                sp = random.uniform(0.55, 1.3) * intensity
                vx = ox * sp + random.uniform(-0.3, 0.3)
                vy = oy * sp + random.uniform(-0.3, 0.3)
                life = random.randint(14, 24)
                self._parts.append(
                    {
                        "x": bx + random.uniform(-3, 3),
                        "y": by + random.uniform(-3, 3),
                        "vx": vx,
                        "vy": vy,
                        "life": life,
                        "max": life,
                        "r": float(random.randint(4, 7)),
                        "mode": mode,
                    }
                )

    def emit_nitro(
        self,
        x: float,
        y: float,
        direction_deg: float,
        w: float,
        h: float,
        intensity: float = 1.0,
    ) -> None:
        """Spawn small jet-flame particles shooting out the rear of the car.

        Particles start blue/white and fade through cyan → orange → red so the
        exhaust reads as a hot nitrous burn.
        """
        rad = math.radians(direction_deg)
        # Forward vector points where the car's nose is; rear is the opposite.
        fx_, fy_ = -math.sin(rad), -math.cos(rad)
        rx_, ry_ = math.cos(rad), -math.sin(rad)
        rear_dist = h * 0.50
        side_dist = w * 0.22
        for side in (-1, 1):
            bx = x - fx_ * rear_dist + rx_ * side_dist * side
            by = y - fy_ * rear_dist + ry_ * side_dist * side
            n = 4 if intensity >= 1.0 else 3
            for _ in range(n):
                sp = random.uniform(1.4, 2.6) * intensity
                # Blow backward (opposite of forward) with slight spread.
                vx = -fx_ * sp + random.uniform(-0.35, 0.35)
                vy = -fy_ * sp + random.uniform(-0.35, 0.35)
                life = random.randint(4, 8)
                self._parts.append(
                    {
                        "x": bx + random.uniform(-2, 2),
                        "y": by + random.uniform(-2, 2),
                        "vx": vx,
                        "vy": vy,
                        "life": life,
                        "max": life,
                        "r": float(random.randint(2, 4)),
                        "mode": "nitro",
                    }
                )

    def explode(self, x: float, y: float) -> None:
        """Radial blast: mix of fire + dark smoke radiating in all directions."""
        big_count = 38
        for _ in range(big_count):
            ang = random.uniform(0.0, math.tau)
            sp = random.uniform(1.6, 4.8)
            mode = "fire" if random.random() < 0.55 else "dark_smoke"
            life = random.randint(32, 55)
            self._parts.append(
                {
                    "x": x + random.uniform(-6, 6),
                    "y": y + random.uniform(-6, 6),
                    "vx": math.cos(ang) * sp + random.uniform(-0.4, 0.4),
                    "vy": math.sin(ang) * sp + random.uniform(-0.4, 0.4),
                    "life": life,
                    "max": life,
                    "r": float(random.randint(5, 10)),
                    "mode": mode,
                }
            )
        # A few bright hot-cores spawning at center
        for _ in range(10):
            ang = random.uniform(0.0, math.tau)
            sp = random.uniform(0.3, 1.3)
            life = random.randint(12, 22)
            self._parts.append(
                {
                    "x": x + random.uniform(-3, 3),
                    "y": y + random.uniform(-3, 3),
                    "vx": math.cos(ang) * sp,
                    "vy": math.sin(ang) * sp,
                    "life": life,
                    "max": life,
                    "r": float(random.randint(7, 12)),
                    "mode": "fire",
                }
            )

    def update(self) -> None:
        for p in self._parts:
            p["life"] -= 1
            p["x"] += p["vx"]
            p["y"] += p["vy"]
            p["vx"] *= 0.88
            p["vy"] *= 0.88
            p["r"] += 0.12

        self._parts = [p for p in self._parts if p["life"] > 0]

    def draw(self, screen: pygame.Surface, cam_x: float, cam_y: float) -> None:
        for p in self._parts:
            t = p["life"] / max(1, p["max"])
            r = max(1, int(p["r"]))
            alpha = int(180 * t)
            if p["mode"] == "fire":
                if t > 0.889:
                    col = (255, 110, 30, alpha)
                elif t > 0.667:
                    col = (225, 20, 10, alpha)
                else:
                    k = t / 0.667
                    g = int(30 * k)
                    col = (g, g, g, alpha)
            elif p["mode"] == "dark_smoke":
                g = 30 + int(35 * (1 - t))
                col = (g, g, g, alpha)
            elif p["mode"] == "nitro":
                # Deep blue → dark purple → deep red ramp across the short life.
                if t > 0.75:
                    col = (25, 45, 190, alpha)
                elif t > 0.50:
                    col = (60, 30, 170, alpha)
                elif t > 0.25:
                    col = (130, 25, 90, alpha)
                else:
                    col = (175, 20, 25, alpha)
            else:
                g = 235 + int(20 * t)
                col = (min(255, g), min(255, g), min(255, g), alpha)
            surf = pygame.Surface((r * 2 + 2, r * 2 + 2), pygame.SRCALPHA)
            pygame.draw.circle(surf, col, (r + 1, r + 1), r)
            screen.blit(surf, (int(p["x"] - cam_x) - r - 1, int(p["y"] - cam_y) - r - 1))
