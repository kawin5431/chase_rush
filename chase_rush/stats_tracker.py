"""Per-frame gameplay statistics → CSV."""

from __future__ import annotations

import csv
import math
import os
import time
from collections import Counter
from typing import Any, Dict, List, Optional

from . import config


class StatsTracker:
    def __init__(self) -> None:
        self.session_data: List[Dict[str, Any]] = []
        self.records: List[Dict[str, Any]] = self.session_data
        # Separate log of gift-box pickups: one row per pickup, tagged with the
        # stage it happened in so we can compute the favourite prize per stage
        # afterwards.
        self.gift_events: List[Dict[str, Any]] = []

    def log_event(
        self,
        frame: int,
        time_s: float,
        player_x: float,
        player_y: float,
        player_speed: float,
        dist_nearest_police: float,
        num_active_police: int,
        player_direction: float,
        player_hp: int,
        nitro_level: float,
        nitro_active: bool,
        wallet_balance: int,
        money_earned_this_frame: int,
        police_stage: int,
        total_cactus_hits: int,
        total_banana_slips: int,
        total_collisions_player_police: int,
        total_police_killed: int,
        total_gifts_collected: int,
    ) -> None:
        row = {
            "frame": frame,
            "time_s": round(time_s, 6),
            "player_x": round(player_x, 4),
            "player_y": round(player_y, 4),
            "player_speed": round(player_speed, 6),
            "dist_nearest_police": round(dist_nearest_police, 4),
            "num_active_police": num_active_police,
            "player_direction_deg": round(player_direction % 360.0, 4),
            "player_hp": int(player_hp),
            "nitro_level": round(float(nitro_level), 4),
            "nitro_active": 1 if nitro_active else 0,
            "wallet_balance": int(wallet_balance),
            "money_earned_this_frame": int(money_earned_this_frame),
            "police_stage": int(police_stage),
            "total_cactus_hits": int(total_cactus_hits),
            "total_banana_slips": int(total_banana_slips),
            "total_collisions_player_police": int(total_collisions_player_police),
            "total_police_killed": int(total_police_killed),
            "total_gifts_collected": int(total_gifts_collected),
        }
        self.session_data.append(row)

    def log_gift(self, stage: int, prize: str, time_s: float) -> None:
        """Record that a gift-box prize was rolled during a stage."""
        self.gift_events.append(
            {
                "time_s": round(time_s, 6),
                "stage": int(stage),
                "prize": str(prize),
            }
        )

    def save_csv(self, path: Optional[str] = None) -> None:
        fn = path or config.GAMEPLAY_STATS_CSV
        if not self.session_data:
            return
        fieldnames = list(self.session_data[0].keys())
        with open(fn, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames)
            w.writeheader()
            w.writerows(self.session_data)
        # Write gift events to a sibling CSV so the favourite-prize-per-stage
        # lookup is reproducible from disk too.
        gift_path = getattr(config, "GIFT_EVENTS_CSV", "gift_events.csv")
        if self.gift_events:
            with open(gift_path, "w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=["time_s", "stage", "prize"])
                w.writeheader()
                w.writerows(self.gift_events)

    def append_run_summary(self, path: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Append one row to the cross-run summary CSV and return it.

        The CSV has a row per completed run with the aggregated numbers we
        want to compare across games (survival, speeds, damage, hazards,
        gifts, money).  Returns ``None`` if the run had no data.
        """
        if not self.session_data:
            return None

        fn = path or getattr(config, "GAME_RUNS_CSV", "game_runs.csv")
        last = self.session_data[-1]

        def _last(col: str, default: int = 0) -> int:
            return int(last.get(col, default))

        # Count prize types from the gift events log.
        prize_counter: Counter = Counter(ev["prize"] for ev in self.gift_events)

        # Derived per-run aggregates from the session timeline.
        speeds = [float(r.get("player_speed", 0.0)) for r in self.session_data]
        dists = [
            float(r.get("dist_nearest_police", float("inf")))
            for r in self.session_data
            if r.get("dist_nearest_police") not in (None, "")
        ]
        dists = [d for d in dists if math.isfinite(d)]
        money_earned = sum(
            int(r.get("money_earned_this_frame", 0)) for r in self.session_data
        )
        nitro_frames = sum(
            1 for r in self.session_data if int(r.get("nitro_active", 0))
        )

        row = {
            "run_id": int(time.time()),
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()),
            "duration_s": round(float(last.get("time_s", 0.0)), 2),
            "frames": len(self.session_data),
            "peak_stage": max(
                (int(r.get("police_stage", 1)) for r in self.session_data), default=1
            ),
            "top_speed": round(max(speeds) if speeds else 0.0, 3),
            "avg_speed": round(sum(speeds) / len(speeds) if speeds else 0.0, 3),
            "min_police_dist": round(min(dists) if dists else 0.0, 2),
            "nitro_frames": nitro_frames,
            "total_banana_slips": _last("total_banana_slips"),
            "total_cactus_hits": _last("total_cactus_hits"),
            "total_police_killed": _last("total_police_killed"),
            "total_collisions_player_police": _last("total_collisions_player_police"),
            "total_gifts_collected": _last("total_gifts_collected"),
            "gift_money": int(prize_counter.get("money", 0)),
            "gift_nitro": int(prize_counter.get("nitro", 0)),
            "gift_invincible": int(prize_counter.get("invincible", 0)),
            "gift_ram": int(prize_counter.get("ram", 0)),
            "money_earned": int(money_earned),
            "final_wallet": _last("wallet_balance"),
        }

        fieldnames = list(row.keys())
        file_exists = os.path.exists(fn)
        with open(fn, "a", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames)
            if not file_exists:
                w.writeheader()
            w.writerow(row)
        return row

    def favourite_gift_per_stage(self) -> Dict[int, str]:
        """Return {stage_index: most-common prize name} across all pickups."""
        by_stage: Dict[int, Counter] = {}
        for ev in self.gift_events:
            by_stage.setdefault(ev["stage"], Counter())[ev["prize"]] += 1
        out: Dict[int, str] = {}
        for stage, ctr in by_stage.items():
            prize, _ = ctr.most_common(1)[0]
            out[stage] = prize
        return out

    def get_summary(self) -> Dict[str, Any]:
        if not self.session_data:
            return {}
        import pandas as pd

        df = pd.DataFrame(self.session_data)
        summary: Dict[str, Any] = {
            "rows": len(df),
            "duration_s": float(df["time_s"].iloc[-1]) if len(df) else 0.0,
        }
        for col in ("player_speed", "dist_nearest_police", "num_active_police"):
            if col in df.columns:
                summary[col] = {
                    "mean": float(df[col].mean()),
                    "median": float(df[col].median()),
                    "std": float(df[col].std(ddof=0)),
                    "min": float(df[col].min()),
                    "max": float(df[col].max()),
                }
        # Final counters (already monotonic) just need the last value.
        for col in (
            "total_cactus_hits",
            "total_banana_slips",
            "total_collisions_player_police",
            "total_police_killed",
            "total_gifts_collected",
            "wallet_balance",
        ):
            if col in df.columns:
                summary[col] = int(df[col].iloc[-1])
        summary["favourite_gift_per_stage"] = self.favourite_gift_per_stage()
        return summary


def nearest_police_distance(px: float, py: float, police_units: list) -> float:
    if not police_units:
        return float("inf")
    best = math.inf
    for p in police_units:
        d = math.hypot(p.x - px, p.y - py)
        if d < best:
            best = d
    return best
