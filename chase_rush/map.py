"""Game world: roads plus cactus hazards and break effects."""

from __future__ import annotations

import math
import random
from typing import Any, List, Tuple

import pygame

from . import config
from .collision import Polygon, polys_intersect, rect_to_poly


class Map:
    # Banknote tiers: (label, value, color, rim color).
    BANKNOTE_TIERS = [
        ("green",  1, (70, 160, 80),  (30, 90, 40)),
        ("purple", 3, (140, 70, 180), (80, 30, 120)),
        ("gold",   5, (230, 190, 50), (150, 110, 20)),
    ]
    # Relative spawn weights (green is common, gold is rare).
    BANKNOTE_WEIGHTS = [60, 28, 12]

    def __init__(self) -> None:
        self.width = config.WORLD_WIDTH
        self.height = config.WORLD_HEIGHT
        self.tiles: tuple[int, int] = (self.width // config.DOT_SPACING, self.height // config.DOT_SPACING)
        self.obstacles: List[pygame.Rect] = []
        self._roads_h: List[pygame.Rect] = []
        self._cacti: List[pygame.Rect] = []
        self._cactus_fx: List[dict[str, Any]] = []
        # Each banknote: {"rect": pygame.Rect, "tier": int (0..2)}
        self._banknotes: List[dict[str, Any]] = []
        # Gift boxes that award a random prize when touched.
        self._gift_boxes: List[pygame.Rect] = []
        # Banana peels: stepping on one sends the stepping vehicle into a slide.
        self._banana_peels: List[pygame.Rect] = []
        self._rng = random.Random()

    def generate(self, safe_x: float, safe_y: float, safe_radius: float = 200.0) -> None:
        self.obstacles.clear()
        self._roads_h.clear()
        self._cacti.clear()
        self._cactus_fx.clear()
        lane_w = 52
        road_w = lane_w * 2
        y_center = self.height // 2
        gap = 120
        self._roads_h.append(pygame.Rect(0, int(y_center - gap - road_w // 2), self.width, road_w))
        self._roads_h.append(pygame.Rect(0, int(y_center + gap - road_w // 2), self.width, road_w))
        # One world-tile worth of cacti; the draw/collision code tiles them
        # across infinite world copies, so the same population re-appears
        # forever as the player drives (just like the roads).
        target_count = 130
        placed = 0
        attempts = 0
        max_attempts = target_count * 8
        while placed < target_count and attempts < max_attempts:
            attempts += 1
            if self._spawn_cactus_anywhere(safe_x, safe_y, safe_radius=safe_radius):
                placed += 1
        # Banknotes: scattered through the base tile and redrawn across the
        # world via tile offsets just like cacti.
        self._banknotes.clear()
        bank_target = 50
        placed_b = 0
        attempts_b = 0
        while placed_b < bank_target and attempts_b < bank_target * 8:
            attempts_b += 1
            if self._spawn_banknote_anywhere(safe_x, safe_y, safe_radius=safe_radius):
                placed_b += 1
        # Gift boxes: rare pickups that give a random boost on contact.
        self._gift_boxes.clear()
        gift_target = 12
        placed_g = 0
        attempts_g = 0
        while placed_g < gift_target and attempts_g < gift_target * 10:
            attempts_g += 1
            if self._spawn_gift_anywhere(safe_x, safe_y, safe_radius=safe_radius):
                placed_g += 1
        # Load the banana sprite lazily (once per Map instance) so we only
        # touch the disk after pygame's display is ready.
        if not hasattr(self, "_banana_img"):
            try:
                raw = pygame.image.load(config.BANANA_IMG).convert_alpha()
                # Preserve the sprite's native wide aspect ratio (~1.77:1)
                # so the peel looks chunky instead of squished.
                self._banana_img = pygame.transform.smoothscale(raw, (44, 25))
            except (pygame.error, FileNotFoundError):
                self._banana_img = None
        # Banana peels: sprinkled around the world; stepping on one causes a
        # random-direction slide.
        self._banana_peels.clear()
        banana_target = 35
        placed_bn = 0
        attempts_bn = 0
        while placed_bn < banana_target and attempts_bn < banana_target * 8:
            attempts_bn += 1
            if self._spawn_banana_anywhere(safe_x, safe_y, safe_radius=safe_radius):
                placed_bn += 1

    def _spawn_cactus_anywhere(
        self, safe_x: float, safe_y: float, safe_radius: float
    ) -> bool:
        """Pick a random point anywhere in the world, skipping the spawn bubble."""
        safe_r2 = safe_radius * safe_radius
        for _ in range(40):
            x = self._rng.uniform(40.0, self.width - 40.0)
            y = self._rng.uniform(40.0, self.height - 40.0)
            dx = x - safe_x
            dy = y - safe_y
            if dx * dx + dy * dy < safe_r2:
                continue
            sz = self._rng.randint(26, 40)
            r = pygame.Rect(int(x - sz / 2), int(y - sz / 2), sz, sz)
            if self._is_on_road(r):
                continue
            if any(r.colliderect(c.inflate(8, 8)) for c in self._cacti):
                continue
            self._cacti.append(r)
            return True
        return False

    def get_obstacles(self) -> List[pygame.Rect]:
        return self.obstacles

    def _is_on_road(self, r: pygame.Rect) -> bool:
        return any(r.colliderect(road.inflate(20, 14)) for road in self._roads_h)

    def is_point_on_road(self, x: float, y: float) -> bool:
        """True iff a world-space point lies inside one of the road strips.

        Roads tile across the world, so the coordinate is wrapped into the
        base tile before testing; otherwise a player past the tile edge
        would read as off-road even when visually on tarmac.
        """
        wx = int(x) % self.width
        wy = int(y) % self.height
        return any(road.collidepoint(wx, wy) for road in self._roads_h)

    def _spawn_cactus_near(self, cx: float, cy: float, min_dist: float = 120.0, max_dist: float = 1450.0) -> bool:
        for _ in range(26):
            a = self._rng.uniform(0.0, 6.283185307)
            d = self._rng.uniform(min_dist, max_dist)
            x = cx + math.cos(a) * d
            y = cy + math.sin(a) * d
            sz = self._rng.randint(26, 40)
            r = pygame.Rect(int(x - sz / 2), int(y - sz / 2), sz, sz)
            if self._is_on_road(r):
                continue
            if any(r.colliderect(c.inflate(8, 8)) for c in self._cacti):
                continue
            self._cacti.append(r)
            return True
        return False

    def update(self) -> None:
        for p in self._cactus_fx:
            p["life"] -= 1
            p["x"] += p["vx"]
            p["y"] += p["vy"]
            p["vx"] *= 0.9
            p["vy"] *= 0.9
        self._cactus_fx = [p for p in self._cactus_fx if p["life"] > 0]

    def _spawn_banknote_anywhere(
        self, safe_x: float, safe_y: float, safe_radius: float
    ) -> bool:
        """Place a single banknote in a random, unblocked spot in the base tile."""
        safe_r2 = safe_radius * safe_radius
        for _ in range(24):
            x = self._rng.uniform(60.0, self.width - 60.0)
            y = self._rng.uniform(60.0, self.height - 60.0)
            dx = x - safe_x
            dy = y - safe_y
            if dx * dx + dy * dy < safe_r2:
                continue
            w = 30
            h = 18
            r = pygame.Rect(int(x - w / 2), int(y - h / 2), w, h)
            if self._is_on_road(r):
                continue
            if any(r.colliderect(c.inflate(6, 6)) for c in self._cacti):
                continue
            if any(r.colliderect(b["rect"].inflate(10, 10)) for b in self._banknotes):
                continue
            tier = self._rng.choices(
                range(len(self.BANKNOTE_TIERS)),
                weights=self.BANKNOTE_WEIGHTS,
                k=1,
            )[0]
            self._banknotes.append({"rect": r, "tier": tier})
            return True
        return False

    def _spawn_gift_anywhere(
        self, safe_x: float, safe_y: float, safe_radius: float
    ) -> bool:
        """Place a single gift box in a random, unblocked spot in the base tile."""
        safe_r2 = safe_radius * safe_radius
        for _ in range(24):
            x = self._rng.uniform(80.0, self.width - 80.0)
            y = self._rng.uniform(80.0, self.height - 80.0)
            dx = x - safe_x
            dy = y - safe_y
            if dx * dx + dy * dy < safe_r2:
                continue
            w = 30
            h = 30
            r = pygame.Rect(int(x - w / 2), int(y - h / 2), w, h)
            if self._is_on_road(r):
                continue
            if any(r.colliderect(c.inflate(10, 10)) for c in self._cacti):
                continue
            if any(r.colliderect(b["rect"].inflate(12, 12)) for b in self._banknotes):
                continue
            if any(r.colliderect(g.inflate(20, 20)) for g in self._gift_boxes):
                continue
            self._gift_boxes.append(r)
            return True
        return False

    def pop_gift_hit(self, poly: Polygon) -> bool:
        """Remove any gift box touching the poly; return True on collect."""
        cx = sum(p[0] for p in poly) / len(poly)
        cy = sum(p[1] for p in poly) / len(poly)
        offsets = self._tile_offsets_near(cx, cy)
        for i, g in enumerate(self._gift_boxes):
            for ox, oy in offsets:
                tr = pygame.Rect(
                    g.x + ox * self.width,
                    g.y + oy * self.height,
                    g.w,
                    g.h,
                )
                if polys_intersect(poly, rect_to_poly(tr)):
                    self._gift_boxes.pop(i)
                    return True
        return False

    def _spawn_banana_anywhere(
        self, safe_x: float, safe_y: float, safe_radius: float
    ) -> bool:
        """Drop a single banana peel somewhere in the tile, off road and clear."""
        safe_r2 = safe_radius * safe_radius
        for _ in range(20):
            x = self._rng.uniform(40.0, self.width - 40.0)
            y = self._rng.uniform(40.0, self.height - 40.0)
            dx = x - safe_x
            dy = y - safe_y
            if dx * dx + dy * dy < safe_r2:
                continue
            w = 32
            h = 22
            r = pygame.Rect(int(x - w / 2), int(y - h / 2), w, h)
            # Peels can sit on road *or* dirt, but avoid other pickups/obstacles.
            if any(r.colliderect(c.inflate(6, 6)) for c in self._cacti):
                continue
            if any(r.colliderect(b["rect"].inflate(6, 6)) for b in self._banknotes):
                continue
            if any(r.colliderect(g.inflate(10, 10)) for g in self._gift_boxes):
                continue
            if any(r.colliderect(p.inflate(8, 8)) for p in self._banana_peels):
                continue
            self._banana_peels.append(r)
            return True
        return False

    def pop_banana_hit(self, poly: Polygon) -> bool:
        """Remove any banana peel touching the poly; return True on hit."""
        cx = sum(p[0] for p in poly) / len(poly)
        cy = sum(p[1] for p in poly) / len(poly)
        offsets = self._tile_offsets_near(cx, cy)
        for i, pl in enumerate(self._banana_peels):
            for ox, oy in offsets:
                tr = pygame.Rect(
                    pl.x + ox * self.width,
                    pl.y + oy * self.height,
                    pl.w,
                    pl.h,
                )
                if polys_intersect(poly, rect_to_poly(tr)):
                    self._banana_peels.pop(i)
                    return True
        return False

    def pop_banknote_hit(self, poly: Polygon) -> int:
        """If the poly touches a banknote (any tile), remove it and return its value."""
        cx = sum(p[0] for p in poly) / len(poly)
        cy = sum(p[1] for p in poly) / len(poly)
        offsets = self._tile_offsets_near(cx, cy)
        for i, b in enumerate(self._banknotes):
            r = b["rect"]
            for ox, oy in offsets:
                tr = pygame.Rect(
                    r.x + ox * self.width,
                    r.y + oy * self.height,
                    r.w,
                    r.h,
                )
                if polys_intersect(poly, rect_to_poly(tr)):
                    value = self.BANKNOTE_TIERS[b["tier"]][1]
                    self._banknotes.pop(i)
                    return value
        return 0

    def _tile_offsets_near(self, x: float, y: float) -> List[Tuple[int, int]]:
        """Tile coordinates to scan around a world-space point (3x3 wrap)."""
        ox_c = int(x // self.width)
        oy_c = int(y // self.height)
        return [
            (ox, oy)
            for ox in (ox_c - 1, ox_c, ox_c + 1)
            for oy in (oy_c - 1, oy_c, oy_c + 1)
        ]

    def pop_cactus_hit(self, poly: Polygon) -> Tuple[bool, Tuple[float, float]]:
        # Treat cacti as tiled across world copies; test every nearby tile
        # offset so collisions work anywhere the player roams.
        cx = sum(p[0] for p in poly) / len(poly)
        cy = sum(p[1] for p in poly) / len(poly)
        offsets = self._tile_offsets_near(cx, cy)
        for i, c in enumerate(self._cacti):
            for ox, oy in offsets:
                cr = pygame.Rect(
                    c.x + ox * self.width, c.y + oy * self.height, c.w, c.h
                )
                if polys_intersect(poly, rect_to_poly(cr)):
                    self._cacti.pop(i)
                    self._burst_cactus(cr.centerx, cr.centery)
                    return True, (float(cr.centerx), float(cr.centery))
        return False, (0.0, 0.0)

    def _draw_cactus(
        self, screen: pygame.Surface, cx: int, cy: int, cw: int, ch: int
    ) -> None:
        """Draw one cactus at screen coords (cx, cy), size (cw, ch)."""
        trunk_h = max(14, int(ch * 0.78))
        trunk_w = max(10, int(cw * 0.5))
        trunk = pygame.Rect(cx - trunk_w // 2, cy - trunk_h // 2 + 2, trunk_w, trunk_h)
        pygame.draw.rect(screen, (33, 120, 56), trunk, border_radius=max(3, trunk_w // 3))
        hi = trunk.inflate(-max(2, trunk_w // 3), -max(2, trunk_h // 3))
        pygame.draw.rect(screen, (68, 170, 92), hi, border_radius=max(2, hi.w // 3))

        arm_w = max(5, trunk_w // 2)
        arm_h = max(8, int(trunk_h * 0.55))
        left_arm = pygame.Rect(trunk.left - arm_h + 2, trunk.top + trunk_h // 4, arm_h, arm_w)
        right_arm = pygame.Rect(trunk.right - 2, trunk.top + trunk_h // 3, arm_h, arm_w)
        pygame.draw.rect(screen, (33, 120, 56), left_arm, border_radius=max(2, arm_w // 2))
        pygame.draw.rect(screen, (33, 120, 56), right_arm, border_radius=max(2, arm_w // 2))

        for arm in (left_arm, right_arm):
            tip = pygame.Rect(arm.right - arm_w // 2, arm.top - arm_w // 2, arm_w, arm_w)
            pygame.draw.circle(screen, (68, 170, 92), tip.center, max(2, arm_w // 2))

        for _ in range(8):
            sx = self._rng.randint(trunk.left, trunk.right)
            sy = self._rng.randint(trunk.top, trunk.bottom)
            pygame.draw.line(screen, (208, 236, 198), (sx, sy), (sx + 1, sy - 2), 1)

    def _burst_cactus(self, x: float, y: float) -> None:
        for _ in range(self._rng.randint(12, 18)):
            ang = self._rng.uniform(0.0, 6.283185307)
            sp = self._rng.uniform(1.6, 4.8)
            self._cactus_fx.append(
                {
                    "x": x + self._rng.uniform(-4, 4),
                    "y": y + self._rng.uniform(-4, 4),
                    "vx": math.cos(ang) * sp,
                    "vy": math.sin(ang) * sp,
                    "life": self._rng.randint(10, 22),
                    "r": self._rng.randint(2, 4),
                    "col": self._rng.choice([(42, 138, 64), (70, 162, 82), (34, 115, 50)]),
                }
            )

    def draw(self, screen: pygame.Surface, cam_x: float, cam_y: float) -> None:
        screen.fill(config.SAND_COLOR)
        for sx in range(0, config.SCREEN_WIDTH + config.DOT_SPACING, config.DOT_SPACING):
            for sy in range(0, config.SCREEN_HEIGHT + config.DOT_SPACING, config.DOT_SPACING):
                wx = sx + cam_x
                wy = sy + cam_y
                seed = (int(wx) // config.DOT_SPACING, int(wy) // config.DOT_SPACING)
                if (hash(seed) % 100) / 100 < 0.3:
                    pygame.draw.circle(screen, config.DOT_COLOR, (sx, sy), config.DOT_RADIUS)

        road = (95, 95, 96)
        edge = (125, 125, 126)
        lane = (230, 208, 105)
        screen_rect = screen.get_rect()
        tile_x0 = int(cam_x // self.width) - 1
        tile_x1 = int((cam_x + config.SCREEN_WIDTH) // self.width) + 1
        tile_y0 = int(cam_y // self.height) - 1
        tile_y1 = int((cam_y + config.SCREEN_HEIGHT) // self.height) + 1
        for rect in self._roads_h:
            for ox in range(tile_x0, tile_x1 + 1):
                for oy in range(tile_y0, tile_y1 + 1):
                    dr = pygame.Rect(
                        int(rect.x + ox * self.width - cam_x),
                        int(rect.y + oy * self.height - cam_y),
                        rect.width,
                        rect.height,
                    )
                    if dr.colliderect(screen_rect):
                        pygame.draw.rect(screen, road, dr)
                        pygame.draw.rect(screen, edge, dr, 2)

        dash_len = 32
        dash_gap = 20
        for r in self._roads_h:
            for ox in range(tile_x0, tile_x1 + 1):
                for oy in range(tile_y0, tile_y1 + 1):
                    start = int(r.x + ox * self.width - cam_x)
                    end = int(r.right + ox * self.width - cam_x)
                    y_mid = int(r.centery + oy * self.height - cam_y)
                    x = start
                    while x < end:
                        pygame.draw.line(screen, lane, (x, y_mid), (min(x + dash_len, end), y_mid), 3)
                        x += dash_len + dash_gap

        for c in self._cacti:
            for ox in range(tile_x0, tile_x1 + 1):
                for oy in range(tile_y0, tile_y1 + 1):
                    cx = int(c.centerx + ox * self.width - cam_x)
                    cy = int(c.centery + oy * self.height - cam_y)
                    if not (
                        -40 <= cx <= config.SCREEN_WIDTH + 40
                        and -40 <= cy <= config.SCREEN_HEIGHT + 40
                    ):
                        continue
                    self._draw_cactus(screen, cx, cy, c.w, c.h)

        for p in self._cactus_fx:
            pygame.draw.circle(
                screen,
                p["col"],
                (int(p["x"] - cam_x), int(p["y"] - cam_y)),
                p["r"],
            )

        for b in self._banknotes:
            r = b["rect"]
            label, value, fill, rim = self.BANKNOTE_TIERS[b["tier"]]
            for ox in range(tile_x0, tile_x1 + 1):
                for oy in range(tile_y0, tile_y1 + 1):
                    sx = int(r.x + ox * self.width - cam_x)
                    sy = int(r.y + oy * self.height - cam_y)
                    if not (
                        -40 <= sx <= config.SCREEN_WIDTH + 40
                        and -40 <= sy <= config.SCREEN_HEIGHT + 40
                    ):
                        continue
                    self._draw_banknote(screen, sx, sy, r.w, r.h, fill, rim, value)

        for g in self._gift_boxes:
            for ox in range(tile_x0, tile_x1 + 1):
                for oy in range(tile_y0, tile_y1 + 1):
                    sx = int(g.x + ox * self.width - cam_x)
                    sy = int(g.y + oy * self.height - cam_y)
                    if not (
                        -40 <= sx <= config.SCREEN_WIDTH + 40
                        and -40 <= sy <= config.SCREEN_HEIGHT + 40
                    ):
                        continue
                    self._draw_gift_box(screen, sx, sy, g.w, g.h)

        for pl in self._banana_peels:
            for ox in range(tile_x0, tile_x1 + 1):
                for oy in range(tile_y0, tile_y1 + 1):
                    sx = int(pl.x + ox * self.width - cam_x)
                    sy = int(pl.y + oy * self.height - cam_y)
                    if not (
                        -40 <= sx <= config.SCREEN_WIDTH + 40
                        and -40 <= sy <= config.SCREEN_HEIGHT + 40
                    ):
                        continue
                    self._draw_banana_peel(screen, sx, sy, pl.w, pl.h)

    def _draw_banana_peel(
        self, screen: pygame.Surface, x: int, y: int, w: int, h: int
    ) -> None:
        """Blit the banana-peel sprite; fall back to a simple crescent."""
        img = getattr(self, "_banana_img", None)
        if img is not None:
            iw, ih = img.get_size()
            # Sprite sits slightly larger than the hitbox so the peel looks
            # chunky; center it on the hitbox rectangle.
            dst = img.get_rect(center=(x + w // 2, y + h // 2))
            screen.blit(img, dst)
            return
        cx = x + w // 2
        cy = y + h // 2
        body = pygame.Rect(x, y, w, h)
        pygame.draw.ellipse(screen, (245, 215, 60), body)
        pygame.draw.ellipse(screen, (160, 120, 20), body, 2)
        pygame.draw.circle(screen, (110, 80, 20), (x + w - 3, cy), 2)

    def _draw_gift_box(
        self, screen: pygame.Surface, x: int, y: int, w: int, h: int
    ) -> None:
        """Draw a wrapped present: box + cross ribbon + bow on top."""
        shadow = pygame.Rect(x + 2, y + 3, w, h)
        pygame.draw.rect(screen, (0, 0, 0, 70), shadow, border_radius=4)
        body = pygame.Rect(x, y, w, h)
        pygame.draw.rect(screen, (210, 60, 70), body, border_radius=4)
        pygame.draw.rect(screen, (140, 20, 30), body, 2, border_radius=4)
        # Cross ribbon (gold).
        cy = y + h // 2
        cx = x + w // 2
        pygame.draw.rect(screen, (255, 210, 70), pygame.Rect(x, cy - 3, w, 6))
        pygame.draw.rect(screen, (255, 210, 70), pygame.Rect(cx - 3, y, 6, h))
        # Bow on top.
        pygame.draw.circle(screen, (255, 210, 70), (cx - 4, y + 1), 4)
        pygame.draw.circle(screen, (255, 210, 70), (cx + 4, y + 1), 4)
        pygame.draw.circle(screen, (160, 120, 20), (cx - 4, y + 1), 4, 1)
        pygame.draw.circle(screen, (160, 120, 20), (cx + 4, y + 1), 4, 1)

    def _draw_banknote(
        self,
        screen: pygame.Surface,
        x: int,
        y: int,
        w: int,
        h: int,
        fill: tuple,
        rim: tuple,
        value: int,
    ) -> None:
        """Draw one banknote at screen (x, y) size (w, h) with a '$N' label."""
        shadow = pygame.Rect(x + 2, y + 3, w, h)
        pygame.draw.rect(screen, (0, 0, 0, 70), shadow, border_radius=3)
        body = pygame.Rect(x, y, w, h)
        pygame.draw.rect(screen, fill, body, border_radius=3)
        pygame.draw.rect(screen, rim, body, 2, border_radius=3)
        cx = x + w // 2
        cy = y + h // 2
        pygame.draw.circle(screen, rim, (cx, cy), max(5, h // 3), 1)
        if not hasattr(self, "_bank_font"):
            self._bank_font = pygame.font.SysFont(None, 18, bold=True)
        txt = self._bank_font.render(f"${value}", True, (250, 250, 250))
        screen.blit(txt, txt.get_rect(center=(cx, cy)))
