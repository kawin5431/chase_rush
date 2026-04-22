"""Shared collision geometry."""

from __future__ import annotations

import math
from typing import List, Optional, Sequence, Tuple

import pygame

Point = Tuple[float, float]
Polygon = Sequence[Point]


def rotated_box(cx: float, cy: float, w: float, h: float, angle: float) -> List[Point]:
    hw, hh = w / 2, h / 2
    rad = math.radians(-angle)
    ca, sa = math.cos(rad), math.sin(rad)
    pts: List[Point] = []
    for ox, oy in [(-hw, -hh), (hw, -hh), (hw, hh), (-hw, hh)]:
        pts.append((cx + ox * ca - oy * sa, cy + ox * sa + oy * ca))
    return pts


def polys_intersect(p1: Polygon, p2: Polygon) -> bool:
    def proj(poly: Polygon, ax: Point) -> Tuple[float, float]:
        dots = [x * ax[0] + y * ax[1] for x, y in poly]
        return min(dots), max(dots)

    for poly in (p1, p2):
        for i in range(len(poly)):
            j = (i + 1) % len(poly)
            edge = (poly[j][0] - poly[i][0], poly[j][1] - poly[i][1])
            ax = (-edge[1], edge[0])
            p1min, p1max = proj(p1, ax)
            p2min, p2max = proj(p2, ax)
            if p1max < p2min or p2max < p1min:
                return False
    return True


def rect_to_poly(rect: pygame.Rect) -> List[Point]:
    return [
        (float(rect.left), float(rect.top)),
        (float(rect.right), float(rect.top)),
        (float(rect.right), float(rect.bottom)),
        (float(rect.left), float(rect.bottom)),
    ]


def poly_hits_any_rect(poly: Polygon, rects: Sequence[pygame.Rect]) -> bool:
    for r in rects:
        if polys_intersect(poly, rect_to_poly(r)):
            return True
    return False


def resolve_push_out_of_rects(
    x: float,
    y: float,
    w: float,
    h: float,
    angle_deg: float,
    rects: Sequence[pygame.Rect],
    max_iter: int = 56,
) -> Tuple[float, float, Optional[Tuple[float, float]]]:
    """
    If the oriented hitbox overlaps any obstacle, step the center outward until clear.
    Returns (new_x, new_y, escape_normal) for optional velocity clipping (normal points out of wall).
    """
    escape_n: Optional[Tuple[float, float]] = None
    for it in range(max_iter):
        poly = rotated_box(x, y, w, h, angle_deg)
        sx, sy = 0.0, 0.0
        hits = 0
        for r in rects:
            if polys_intersect(poly, rect_to_poly(r)):
                hits += 1
                cx, cy = float(r.centerx), float(r.centery)
                dx, dy = x - cx, y - cy
                d = math.hypot(dx, dy)
                if d < 1e-4:
                    dx, dy, d = 1.0, 0.0, 1.0
                sx += dx / d
                sy += dy / d
        if hits == 0:
            return x, y, escape_n
        d = math.hypot(sx, sy)
        if d > 1e-6:
            sx /= d
            sy /= d
        escape_n = (sx, sy)
        step = 3.2 + min(5.0, it * 0.35)
        x += sx * step
        y += sy * step
    return x, y, escape_n


def clip_velocity_into_wall(vx: float, vy: float, nx: float, ny: float, keep_tangent: float = 0.35) -> Tuple[float, float]:
    """Remove inward normal component; nx,ny is escape direction (from wall toward car)."""
    vn = vx * nx + vy * ny
    if vn >= 0:
        return vx, vy
    remove = vn * (1.0 - keep_tangent)
    return vx - nx * remove, vy - ny * remove


def unstick_vehicle_from_rects(ent: object, w: float, h: float, rects: Sequence[pygame.Rect]) -> bool:
    """If hitbox overlaps any rect, push ent out and damp inward speed. Returns True if a fix ran."""
    poly = rotated_box(ent.x, ent.y, w, h, ent.direction)
    if not poly_hits_any_rect(poly, rects):
        return False
    n_final: Optional[Tuple[float, float]] = None
    for _ in range(2):
        ent.x, ent.y, n_final = resolve_push_out_of_rects(ent.x, ent.y, w, h, ent.direction, rects)
        poly = rotated_box(ent.x, ent.y, w, h, ent.direction)
        if not poly_hits_any_rect(poly, rects):
            break
    if n_final is not None:
        ent.vx, ent.vy = clip_velocity_into_wall(ent.vx, ent.vy, n_final[0], n_final[1], keep_tangent=0.42)
    return True


def bounce_oriented_vehicles(
    a: object,
    b: object,
    w1: float,
    h1: float,
    w2: float,
    h2: float,
    restitution: float = 0.78,
) -> bool:
    """If hitboxes overlap, apply impulse + fishtail spin like a real car crash.

    Contact normal is the line between centers. Spin comes from two sources:
      - Tangential relative velocity (sideswipe scrubbing).
      - Off-axis hit: the more the contact normal points toward a car's side
        rather than its nose, the more torque that hit produces.
    """
    box1 = rotated_box(a.x, a.y, w1, h1, a.direction)
    box2 = rotated_box(b.x, b.y, w2, h2, b.direction)
    if not polys_intersect(box1, box2):
        return False

    dx = a.x - b.x
    dy = a.y - b.y
    dist = math.hypot(dx, dy)
    if dist < 1e-6:
        dx, dy, dist = 1.0, 0.0, 1.0
    nx, ny = dx / dist, dy / dist

    rvx = a.vx - b.vx
    rvy = a.vy - b.vy
    vn = rvx * nx + rvy * ny
    tang_x, tang_y = -ny, nx
    vt = rvx * tang_x + rvy * tang_y

    if vn < 0:
        impulse = -(1.0 + restitution) * vn * 0.5
        # Minimum knockback so even a crawl-into-you contact gives a visible jolt.
        min_impulse = 2.2
        if impulse < min_impulse:
            impulse = min_impulse
        a.vx += nx * impulse
        a.vy += ny * impulse
        b.vx -= nx * impulse
        b.vy -= ny * impulse

    friction = 0.28
    jt = -vt * friction * 0.5
    a.vx += tang_x * jt
    a.vy += tang_y * jt
    b.vx -= tang_x * jt
    b.vy -= tang_y * jt

    def _forward(angle_deg: float) -> Tuple[float, float]:
        rad = math.radians(angle_deg)
        return -math.sin(rad), -math.cos(rad)

    fa_x, fa_y = _forward(a.direction)
    fb_x, fb_y = _forward(b.direction)
    off_a = fa_x * ny - fa_y * nx
    off_b = fb_x * ny - fb_y * nx

    approach = max(0.0, -vn)
    slide = vt

    slide_spin = max(-9.0, min(9.0, slide * 0.65))
    impact_spin_a = off_a * approach * 0.9
    impact_spin_b = off_b * approach * 0.9

    a.rotation_speed += slide_spin * 0.9 + impact_spin_a
    b.rotation_speed -= slide_spin * 0.9
    b.rotation_speed -= impact_spin_b

    a.rotation_speed = max(-14.0, min(14.0, a.rotation_speed))
    b.rotation_speed = max(-14.0, min(14.0, b.rotation_speed))

    push = 5.0 + min(8.0, abs(vn) * 0.55)
    a.x += nx * push
    a.y += ny * push
    b.x -= nx * push
    b.y -= ny * push
    return True
