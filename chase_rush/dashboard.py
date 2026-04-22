"""Load gameplay_stats.csv and render a scrollable, magazine-style dashboard.

The dashboard is shown from the in-game Stats menu: when a player opens
it we regenerate a tall PNG from the latest CSV and let the pygame UI
vertically scroll through it. The figure is broken into clearly-labelled
sections — KPI cards, spatial analysis, temporal analysis, statistical
summary and gift analytics — each with its own banner so the layout feels
structured and easy to scan.
"""

from __future__ import annotations

import os
from typing import Optional

import matplotlib

matplotlib.use("Agg")  # headless backend; we render to PNG, never a window.
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.gridspec import GridSpec, GridSpecFromSubplotSpec

from . import config


# Dark palette tuned to sit nicely over the game's menu world.
_BG = "#15121c"
_PANEL = "#221f2c"
_PANEL_HI = "#2b2638"
_FG = "#e6e3ef"
_FG_DIM = "#a8a4b8"
_ACCENT = "#ffd35a"  # gold
_ACCENT2 = "#5ac8ff"  # cyan
_ACCENT3 = "#ff7a6b"  # coral
_ACCENT4 = "#9ae66e"  # lime
_ACCENT5 = "#c29bff"  # lavender
_GRID = "#3a3645"

# Distinct shades for the police-stage bands on the timeline plot.
_STAGE_COLORS = ["#2f2a3a", "#363052", "#3d2a55", "#542a4c", "#6b2a3d"]

# Human-readable colours for known gift prizes.
_GIFT_COLORS = {
    "money": _ACCENT,
    "nitro": _ACCENT2,
    "invincible": _ACCENT4,
    "ram_mode": _ACCENT3,
    "ram": _ACCENT3,
}


def _style_ax(ax: plt.Axes, title: str, caption: Optional[str] = None) -> None:
    ax.set_facecolor(_PANEL)
    for spine in ax.spines.values():
        spine.set_color(_GRID)
        spine.set_linewidth(0.9)
    ax.tick_params(colors=_FG_DIM, labelsize=9, length=3)
    ax.xaxis.label.set_color(_FG)
    ax.yaxis.label.set_color(_FG)
    ax.xaxis.label.set_size(10)
    ax.yaxis.label.set_size(10)
    ax.grid(True, color=_GRID, linewidth=0.5, alpha=0.5)
    ax.set_axisbelow(True)
    # Give the title extra pad so the caption (italic subtitle) has room.
    pad = 26 if caption else 10
    ax.set_title(title, color=_ACCENT, fontsize=13, pad=pad, fontweight="bold")
    if caption:
        ax.text(
            0.5,
            1.02,
            caption,
            transform=ax.transAxes,
            ha="center",
            va="bottom",
            color=_FG_DIM,
            fontsize=9,
            style="italic",
        )


class Dashboard:
    """Build and save a multi-section statistics image for the current run."""

    OUTPUT_PATH = "gameplay_stats_dashboard.png"
    # Width of the rendered PNG in inches × dpi. Kept close to the game's
    # playable area (screen width minus a scrollbar gutter) so no ugly
    # rescaling happens in pygame.
    FIG_WIDTH_IN = 14.0
    DPI = 100

    def __init__(self) -> None:
        self.data_frame: Optional[pd.DataFrame] = None
        self.gift_frame: Optional[pd.DataFrame] = None
        self.runs_frame: Optional[pd.DataFrame] = None

    def load_data(self, path: Optional[str] = None) -> "Dashboard":
        fn = path or config.GAMEPLAY_STATS_CSV
        self.data_frame = pd.read_csv(fn)
        gift_path = getattr(config, "GIFT_EVENTS_CSV", "gift_events.csv")
        if os.path.exists(gift_path):
            try:
                self.gift_frame = pd.read_csv(gift_path)
            except (pd.errors.EmptyDataError, OSError):
                self.gift_frame = None
        runs_path = getattr(config, "GAME_RUNS_CSV", "game_runs.csv")
        if os.path.exists(runs_path):
            try:
                self.runs_frame = pd.read_csv(runs_path)
            except (pd.errors.EmptyDataError, OSError):
                self.runs_frame = None
        return self

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------
    def _col(self, name: str) -> Optional[pd.Series]:
        if self.data_frame is None or name not in self.data_frame.columns:
            return None
        return self.data_frame[name]

    def _stat_row(self, series: pd.Series) -> list[str]:
        s = series.dropna()
        if s.empty:
            return ["-"] * 6
        mode_val = s.mode()
        mode_v = float(mode_val.iloc[0]) if not mode_val.empty else float("nan")
        return [
            f"{s.mean():.2f}",
            f"{s.median():.2f}",
            f"{mode_v:.2f}",
            f"{s.max():.2f}",
            f"{s.min():.2f}",
            f"{s.std():.2f}",
        ]

    def _kpi_card(
        self,
        ax: plt.Axes,
        label: str,
        value: str,
        accent: str,
        sub: Optional[str] = None,
    ) -> None:
        """Render a single KPI card with coloured accent bar + big number."""
        ax.set_xticks([])
        ax.set_yticks([])
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        ax.set_facecolor(_PANEL)
        for spine in ax.spines.values():
            spine.set_color(_GRID)
            spine.set_linewidth(0.9)

        ax.add_patch(
            mpatches.Rectangle(
                (0, 0), 0.045, 1, color=accent, transform=ax.transAxes, clip_on=False
            )
        )
        ax.text(
            0.10,
            0.75,
            label.upper(),
            color=_FG_DIM,
            fontsize=10,
            fontweight="bold",
            transform=ax.transAxes,
            va="center",
            ha="left",
        )
        ax.text(
            0.10,
            0.40,
            value,
            color=_FG,
            fontsize=28,
            fontweight="bold",
            transform=ax.transAxes,
            va="center",
            ha="left",
        )
        if sub:
            ax.text(
                0.10,
                0.13,
                sub,
                color=accent,
                fontsize=10,
                fontweight="bold",
                transform=ax.transAxes,
                va="center",
                ha="left",
            )

    def _section_header(self, ax: plt.Axes, label: str, badge: str) -> None:
        """Render a section banner: numbered badge + bold title + divider."""
        ax.set_facecolor(_BG)
        ax.set_xticks([])
        ax.set_yticks([])
        for spine in ax.spines.values():
            spine.set_visible(False)
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)

        # Numbered chip on the left.
        chip = mpatches.FancyBboxPatch(
            (0.0, 0.18),
            0.055,
            0.66,
            boxstyle="round,pad=0.02,rounding_size=0.05",
            color=_ACCENT,
            transform=ax.transAxes,
            clip_on=False,
        )
        ax.add_patch(chip)
        ax.text(
            0.0275,
            0.5,
            badge,
            color=_BG,
            fontsize=14,
            fontweight="bold",
            ha="center",
            va="center",
            transform=ax.transAxes,
        )
        ax.text(
            0.075,
            0.5,
            label.upper(),
            color=_ACCENT,
            fontsize=16,
            fontweight="bold",
            ha="left",
            va="center",
            transform=ax.transAxes,
        )
        label_pad = 0.075 + 0.012 * len(label) + 0.04
        ax.plot(
            [label_pad, 1.0],
            [0.5, 0.5],
            color=_GRID,
            linewidth=1.1,
            alpha=0.9,
            transform=ax.transAxes,
            clip_on=False,
        )

    # ------------------------------------------------------------------
    # main render
    # ------------------------------------------------------------------
    def plot_charts(self) -> "Dashboard":
        if self.data_frame is None or self.data_frame.empty:
            return self
        df = self.data_frame
        runs = self.runs_frame

        # --- figure layout -------------------------------------------------
        # The dashboard is now run-to-run first: almost every chart is a
        # per-run comparison bar. A smaller "Current run highlights" section
        # at the bottom preserves the most useful per-frame views.
        #
        # Rows:
        #   0  banner
        #   1  KPI strip (lifetime / cross-run totals)
        #   2  header — Survival & skill per run
        #   3  survival / skill charts (1x3)
        #   4  header — Hazards & combat per run
        #   5  hazards charts (2x2)
        #   6  header — Gifts & economy per run
        #   7  economy charts (1x3)
        #   8  header — Per-run statistical summary
        #   9  per-run stats table
        #  10  header — Current run highlights
        #  11  current-run charts (1x3)
        #  12  footer
        row_ratios = [
            0.55,  # banner
            1.10,  # KPI strip
            0.45,  # header
            2.85,  # survival & skill (1x3)
            0.45,  # header
            5.70,  # hazards & combat (2x2)
            0.45,  # header
            2.85,  # gifts & economy (1x3)
            0.45,  # header
            2.30,  # per-run stats table
            0.45,  # header
            2.85,  # current-run charts (1x3)
            0.40,  # footer
        ]
        total = sum(row_ratios)
        fig_height = 3.4 * total / 2.60
        fig = plt.figure(
            figsize=(self.FIG_WIDTH_IN, fig_height), facecolor=_BG
        )
        outer = GridSpec(
            len(row_ratios),
            1,
            figure=fig,
            left=0.055,
            right=0.965,
            top=0.985,
            bottom=0.015,
            hspace=0.70,
            height_ratios=row_ratios,
        )

        # --- Row 0: banner -----------------------------------------------
        self._draw_banner(fig.add_subplot(outer[0]), df, runs)

        # --- Row 1: KPI strip (lifetime totals) --------------------------
        kpi_gs = GridSpecFromSubplotSpec(1, 6, subplot_spec=outer[1], wspace=0.20)
        self._draw_kpi_strip(fig, kpi_gs, df, runs)

        # --- Row 2+3: Survival & skill per run ---------------------------
        self._section_header(
            fig.add_subplot(outer[2]), "Survival & skill per run", "01"
        )
        surv_gs = GridSpecFromSubplotSpec(1, 3, subplot_spec=outer[3], wspace=0.32)
        self._draw_survival_charts(fig, surv_gs)

        # --- Row 4+5: Hazards & combat per run ---------------------------
        self._section_header(
            fig.add_subplot(outer[4]), "Hazards & combat per run", "02"
        )
        haz_gs = GridSpecFromSubplotSpec(
            2, 2, subplot_spec=outer[5], wspace=0.26, hspace=0.70
        )
        self._draw_hazard_charts(fig, haz_gs)

        # --- Row 6+7: Gifts & economy per run ----------------------------
        self._section_header(
            fig.add_subplot(outer[6]), "Gifts & economy per run", "03"
        )
        econ_gs = GridSpecFromSubplotSpec(1, 3, subplot_spec=outer[7], wspace=0.32)
        self._draw_economy_charts(fig, econ_gs)

        # --- Row 8+9: per-run statistical summary ------------------------
        self._section_header(
            fig.add_subplot(outer[8]), "Per-run statistical summary", "04"
        )
        self._draw_runs_stats_table(fig.add_subplot(outer[9]))

        # --- Row 10+11: Current run highlights ---------------------------
        self._section_header(
            fig.add_subplot(outer[10]), "Current run highlights", "05"
        )
        cur_gs = GridSpecFromSubplotSpec(1, 3, subplot_spec=outer[11], wspace=0.32)
        self._draw_current_run_charts(fig, cur_gs, df)

        # --- Row 12: footer ---------------------------------------------
        foot = fig.add_subplot(outer[12])
        foot.set_facecolor(_BG)
        foot.axis("off")
        foot.text(
            0.5,
            0.6,
            "— Generated from gameplay_stats.csv + game_runs.csv  ·  "
            "Chase Rush Analytics —",
            ha="center",
            va="center",
            color=_FG_DIM,
            fontsize=10,
            transform=foot.transAxes,
        )

        fig.savefig(self.OUTPUT_PATH, dpi=self.DPI, facecolor=_BG)
        plt.close(fig)
        return self

    # ------------------------------------------------------------------
    # Banner + KPI
    # ------------------------------------------------------------------
    def _draw_banner(
        self,
        ax: plt.Axes,
        df: pd.DataFrame,
        runs: Optional[pd.DataFrame],
    ) -> None:
        ax.set_facecolor(_BG)
        ax.set_xticks([])
        ax.set_yticks([])
        for spine in ax.spines.values():
            spine.set_visible(False)
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)

        duration = (
            float(df["time_s"].iloc[-1]) if "time_s" in df.columns else 0.0
        )
        max_stage = (
            int(df["police_stage"].max()) if "police_stage" in df.columns else 1
        )
        n_runs = 0 if runs is None else len(runs)

        ax.text(
            0.5,
            0.72,
            "Chase Rush  —  Run Dashboard",
            color=_ACCENT,
            fontsize=26,
            fontweight="bold",
            ha="center",
            va="center",
            transform=ax.transAxes,
        )
        sub = (
            f"{n_runs} runs logged"
            f"   ·   latest run {duration:.1f}s"
            f"   ·   peak stage {max_stage}"
        )
        ax.text(
            0.5,
            0.30,
            sub,
            ha="center",
            va="center",
            color=_FG_DIM,
            fontsize=13,
            transform=ax.transAxes,
        )
        ax.plot(
            [0.0, 1.0],
            [0.04, 0.04],
            color=_ACCENT,
            linewidth=1.4,
            alpha=0.65,
            transform=ax.transAxes,
            clip_on=False,
        )

    def _draw_kpi_strip(
        self,
        fig: plt.Figure,
        kpi_gs: GridSpecFromSubplotSpec,
        df: pd.DataFrame,
        runs: Optional[pd.DataFrame],
    ) -> None:
        """Six cards summarising the player's career across every saved run."""

        latest_duration = (
            float(df["time_s"].iloc[-1]) if "time_s" in df.columns else 0.0
        )

        if runs is None or runs.empty:
            # No history yet — fall back to the current-run values so the
            # strip stays populated on a first playthrough.
            speed = self._col("player_speed")
            kills = self._col("total_police_killed")
            wallet = self._col("wallet_balance")
            defs = [
                ("Runs logged", "1", _ACCENT, "first run"),
                ("Best survival", f"{latest_duration:.1f}s", _ACCENT3, "current"),
                (
                    "Best top speed",
                    f"{speed.max():.1f}" if speed is not None else "-",
                    _ACCENT2,
                    "current",
                ),
                (
                    "Police wrecked",
                    f"{int(kills.iloc[-1])}" if kills is not None else "-",
                    _ACCENT5,
                    "current",
                ),
                ("Gifts opened", "0", _ACCENT4, "all runs"),
                (
                    "Top wallet",
                    f"${int(wallet.iloc[-1])}" if wallet is not None else "-",
                    _ACCENT,
                    "current",
                ),
            ]
        else:
            n = len(runs)
            best_surv = float(runs["duration_s"].max()) if "duration_s" in runs else 0.0
            best_speed = (
                float(runs["top_speed"].max()) if "top_speed" in runs else 0.0
            )
            total_kills = (
                int(runs["total_police_killed"].sum())
                if "total_police_killed" in runs
                else 0
            )
            total_gifts = (
                int(runs["total_gifts_collected"].sum())
                if "total_gifts_collected" in runs
                else 0
            )
            top_wallet = (
                int(runs["final_wallet"].max()) if "final_wallet" in runs else 0
            )
            avg_surv = (
                float(runs["duration_s"].mean()) if "duration_s" in runs else 0.0
            )

            defs = [
                ("Runs logged", f"{n}", _ACCENT, f"avg {avg_surv:.1f}s"),
                ("Best survival", f"{best_surv:.1f}s", _ACCENT3, "any run"),
                ("Best top speed", f"{best_speed:.1f}", _ACCENT2, "any run"),
                ("Police wrecked", f"{total_kills}", _ACCENT5, "all runs"),
                ("Gifts opened", f"{total_gifts}", _ACCENT4, "all runs"),
                ("Top wallet", f"${top_wallet}", _ACCENT, "any run"),
            ]

        for i, (label, value, accent, sub) in enumerate(defs):
            ax = fig.add_subplot(kpi_gs[0, i])
            self._kpi_card(ax, label, value, accent, sub)

    # ------------------------------------------------------------------
    # Run-to-run comparison (main content)
    # ------------------------------------------------------------------
    def _per_run_bar(
        self,
        ax: plt.Axes,
        metric: str,
        color: str,
        title: str,
        caption: str,
        ylabel: str,
        value_fmt: str = "{:.0f}",
        as_float: bool = False,
    ) -> None:
        """Render a single per-run bar chart with avg line + best highlight."""
        _style_ax(ax, title, caption)
        runs = self.runs_frame
        if runs is None or runs.empty or metric not in runs.columns:
            ax.text(
                0.5,
                0.5,
                "Finish more runs to compare",
                ha="center",
                va="center",
                color=_FG_DIM,
                fontsize=12,
                transform=ax.transAxes,
            )
            return

        series = runs[metric].fillna(0)
        vals = series.astype(float).values if as_float else series.astype(int).values
        labels = [f"#{i + 1}" for i in range(len(vals))]
        bars = ax.bar(labels, vals, color=color, edgecolor=_BG, linewidth=0.7)

        mean_val = float(np.mean(vals)) if len(vals) else 0.0
        avg_label = f"avg {mean_val:.2f}" if as_float else f"avg {mean_val:.1f}"
        ax.axhline(
            mean_val,
            color=_ACCENT,
            linewidth=1.1,
            linestyle="--",
            alpha=0.8,
            label=avg_label,
        )
        if len(vals):
            best_idx = int(np.argmax(vals))
            bars[best_idx].set_edgecolor(_ACCENT)
            bars[best_idx].set_linewidth(1.8)

        for b, v in zip(bars, vals):
            if v == 0:
                continue
            ax.text(
                b.get_x() + b.get_width() / 2,
                b.get_height(),
                value_fmt.format(v),
                ha="center",
                va="bottom",
                color=_FG,
                fontsize=9,
                fontweight="bold",
            )

        ax.set_xlabel("Run")
        ax.set_ylabel(ylabel)
        if len(labels) > 12:
            step = max(1, len(labels) // 12)
            ax.set_xticks(range(0, len(labels), step))
            ax.set_xticklabels(labels[::step], rotation=0)
        leg = ax.legend(
            loc="upper left",
            fontsize=9,
            frameon=True,
            facecolor=_BG,
            edgecolor=_GRID,
        )
        for txt in leg.get_texts():
            txt.set_color(_FG)

    def _draw_survival_charts(
        self, fig: plt.Figure, gs: GridSpecFromSubplotSpec
    ) -> None:
        """Row of three per-run bars: survival time, top speed, peak stage."""
        self._per_run_bar(
            fig.add_subplot(gs[0, 0]),
            "duration_s",
            _ACCENT,
            "Survival time per run",
            "How many seconds you stayed alive in every completed run.",
            "Seconds",
            value_fmt="{:.0f}",
            as_float=True,
        )
        self._per_run_bar(
            fig.add_subplot(gs[0, 1]),
            "top_speed",
            _ACCENT2,
            "Top speed per run",
            "Maximum speed reached during each completed run.",
            "Speed (px/frame)",
            value_fmt="{:.1f}",
            as_float=True,
        )
        self._per_run_bar(
            fig.add_subplot(gs[0, 2]),
            "peak_stage",
            _ACCENT3,
            "Peak police stage per run",
            "Highest difficulty stage reached in every completed run.",
            "Stage",
            value_fmt="{:.0f}",
        )

    def _draw_hazard_charts(
        self, fig: plt.Figure, gs: GridSpecFromSubplotSpec
    ) -> None:
        """2×2 grid of per-run hazard/combat counters."""
        specs = [
            (
                0, 0,
                "total_banana_slips",
                _ACCENT4,
                "Banana peels per run",
                "Number of banana peels the player slipped on in every completed run.",
                "Slips",
            ),
            (
                0, 1,
                "total_cactus_hits",
                _ACCENT3,
                "Cactus hits per run",
                "Times the player's car crashed into a cactus across every completed run.",
                "Hits",
            ),
            (
                1, 0,
                "total_police_killed",
                _ACCENT5,
                "Police wrecked per run",
                "Patrol cars destroyed by the player in every completed run.",
                "Wrecks",
            ),
            (
                1, 1,
                "total_collisions_player_police",
                _ACCENT2,
                "Police collisions per run",
                "How many times a cop rammed into the player each completed run.",
                "Collisions",
            ),
        ]
        for row, col, metric, color, title, caption, ylabel in specs:
            self._per_run_bar(
                fig.add_subplot(gs[row, col]),
                metric,
                color,
                title,
                caption,
                ylabel,
            )

    def _draw_economy_charts(
        self, fig: plt.Figure, gs: GridSpecFromSubplotSpec
    ) -> None:
        """Row of three per-run economy/gift charts."""
        runs = self.runs_frame

        # (a) Money earned per run --------------------------------------
        ax = fig.add_subplot(gs[0, 0])
        self._per_run_bar(
            ax,
            "money_earned",
            _ACCENT,
            "Money earned per run",
            "Sum of banknotes + gift rewards collected during each run.",
            "Money ($)",
        )

        # (b) Gifts collected per run (stacked by type) -----------------
        ax = fig.add_subplot(gs[0, 1])
        _style_ax(
            ax,
            "Gifts collected per run",
            "Breakdown of gift-box prizes rolled in every completed run.",
        )
        if runs is None or runs.empty:
            ax.text(
                0.5,
                0.5,
                "Finish more runs to compare",
                ha="center",
                va="center",
                color=_FG_DIM,
                fontsize=12,
                transform=ax.transAxes,
            )
        else:
            prize_cols = [
                ("gift_money", "money"),
                ("gift_nitro", "nitro"),
                ("gift_invincible", "invincible"),
                ("gift_ram", "ram"),
            ]
            labels = [f"#{i + 1}" for i in range(len(runs))]
            bottom = np.zeros(len(runs))
            plotted = False
            for col, prize in prize_cols:
                if col not in runs.columns:
                    continue
                vals = runs[col].fillna(0).astype(int).values
                if not vals.any():
                    continue
                color = _GIFT_COLORS.get(prize, _ACCENT2)
                ax.bar(
                    labels,
                    vals,
                    bottom=bottom,
                    color=color,
                    edgecolor=_BG,
                    linewidth=0.6,
                    label=prize,
                )
                bottom += vals
                plotted = True
            ax.set_xlabel("Run")
            ax.set_ylabel("Pickups")
            if len(labels) > 12:
                step = max(1, len(labels) // 12)
                ax.set_xticks(range(0, len(labels), step))
                ax.set_xticklabels(labels[::step])
            if plotted:
                leg = ax.legend(
                    loc="upper left",
                    fontsize=9,
                    frameon=True,
                    facecolor=_BG,
                    edgecolor=_GRID,
                )
                for txt in leg.get_texts():
                    txt.set_color(_FG)
            else:
                ax.text(
                    0.5,
                    0.5,
                    "No gifts opened yet",
                    ha="center",
                    va="center",
                    color=_FG_DIM,
                    fontsize=12,
                    transform=ax.transAxes,
                )

        # (c) Lifetime prize haul ---------------------------------------
        ax = fig.add_subplot(gs[0, 2])
        _style_ax(
            ax,
            "Gift prizes — all runs",
            "Total count of each prize type opened across every completed run.",
        )
        prize_cols = [
            ("gift_money", "money"),
            ("gift_nitro", "nitro"),
            ("gift_invincible", "invincible"),
            ("gift_ram", "ram"),
        ]
        if runs is None or runs.empty:
            ax.text(
                0.5,
                0.5,
                "Finish more runs to compare",
                ha="center",
                va="center",
                color=_FG_DIM,
                fontsize=12,
                transform=ax.transAxes,
            )
            return

        labels_p: list[str] = []
        totals: list[int] = []
        colors: list[str] = []
        for col, prize in prize_cols:
            if col not in runs.columns:
                continue
            total = int(runs[col].fillna(0).sum())
            labels_p.append(prize)
            totals.append(total)
            colors.append(_GIFT_COLORS.get(prize, _ACCENT2))

        if not totals or sum(totals) == 0:
            ax.text(
                0.5,
                0.5,
                "No gifts opened yet",
                ha="center",
                va="center",
                color=_FG_DIM,
                fontsize=12,
                transform=ax.transAxes,
            )
            return

        bars = ax.bar(
            labels_p, totals, color=colors, edgecolor=_BG, linewidth=0.7
        )
        for b, v in zip(bars, totals):
            ax.text(
                b.get_x() + b.get_width() / 2,
                b.get_height(),
                f"{v}",
                ha="center",
                va="bottom",
                color=_FG,
                fontsize=11,
                fontweight="bold",
            )
        ax.set_xlabel("Prize")
        ax.set_ylabel("Pickups (all runs)")
        ax.tick_params(axis="x", labelsize=10)

    def _draw_runs_stats_table(self, ax: plt.Axes) -> None:
        """Per-run aggregates in a mean/median/max/min/std table."""
        ax.set_facecolor(_BG)
        ax.axis("off")
        ax.text(
            0.5,
            1.03,
            "Per-run aggregate statistics across every completed game.",
            ha="center",
            va="bottom",
            color=_FG_DIM,
            fontsize=10,
            style="italic",
            transform=ax.transAxes,
            clip_on=False,
        )

        runs = self.runs_frame
        if runs is None or runs.empty:
            ax.text(
                0.5,
                0.45,
                "Finish more runs to see the comparison table.",
                ha="center",
                va="center",
                color=_FG_DIM,
                fontsize=12,
                transform=ax.transAxes,
            )
            return

        rows = [
            ("Survival (s)", "duration_s", _ACCENT),
            ("Top speed", "top_speed", _ACCENT2),
            ("Peak stage", "peak_stage", _ACCENT3),
            ("Police wrecked", "total_police_killed", _ACCENT5),
            ("Cactus hits", "total_cactus_hits", _ACCENT3),
            ("Banana slips", "total_banana_slips", _ACCENT4),
            ("Money earned", "money_earned", _ACCENT),
        ]

        col_labels = ["Mean", "Median", "Max", "Min", "Std Dev"]
        cell_rows: list[list[str]] = []
        row_labels: list[str] = []
        accent_by_row: list[str] = []
        for label, col, accent in rows:
            if col not in runs.columns:
                continue
            s = runs[col].astype(float).dropna()
            if s.empty:
                cell_rows.append(["-"] * 5)
            else:
                cell_rows.append(
                    [
                        f"{s.mean():.2f}",
                        f"{s.median():.2f}",
                        f"{s.max():.2f}",
                        f"{s.min():.2f}",
                        f"{s.std(ddof=0):.2f}",
                    ]
                )
            row_labels.append(label)
            accent_by_row.append(accent)

        if not cell_rows:
            return

        table = ax.table(
            cellText=cell_rows,
            rowLabels=row_labels,
            colLabels=col_labels,
            bbox=[0.22, 0.05, 0.72, 0.85],
            colWidths=[0.14] * 5,
            cellLoc="center",
            rowLoc="center",
        )
        table.auto_set_font_size(False)
        table.set_fontsize(11)
        table.scale(1.0, 1.5)
        for (r, c), cell in table.get_celld().items():
            cell.set_edgecolor(_GRID)
            cell.set_linewidth(0.8)
            if r == 0:
                cell.set_facecolor(_PANEL_HI)
                cell.get_text().set_color(_ACCENT)
                cell.get_text().set_fontweight("bold")
            elif c == -1:
                row_accent = accent_by_row[r - 1]
                cell.set_facecolor(_PANEL_HI)
                cell.get_text().set_color(row_accent)
                cell.get_text().set_fontweight("bold")
            else:
                cell.set_facecolor(_PANEL if r % 2 else "#1d1a26")
                cell.get_text().set_color(_FG)

    def _draw_current_run_charts(
        self,
        fig: plt.Figure,
        gs: GridSpecFromSubplotSpec,
        df: pd.DataFrame,
    ) -> None:
        """Keep the three most informative per-frame charts for the latest run."""
        # (a) Speed over time (stage-shaded) -----------------------------
        ax = fig.add_subplot(gs[0, 0])
        _style_ax(
            ax,
            "Speed over time (current run)",
            "Raw speed plus a rolling average; background bands mark stages.",
        )
        speed = self._col("player_speed")
        if speed is not None and "frame" in df.columns and not speed.empty:
            self._shade_stages(ax, df)
            ax.plot(
                df["frame"],
                speed,
                color=_ACCENT2,
                linewidth=1.1,
                alpha=0.9,
                label="Speed",
            )
            if len(speed) > 24:
                rolling = speed.rolling(window=24, min_periods=1).mean()
                ax.plot(
                    df["frame"],
                    rolling,
                    color=_ACCENT,
                    linewidth=1.4,
                    label="Rolling avg (24 fr)",
                )
            ax.set_xlabel("Frame")
            ax.set_ylabel("Speed")
            leg = ax.legend(
                loc="upper right",
                fontsize=9,
                frameon=True,
                facecolor=_BG,
                edgecolor=_GRID,
            )
            for txt in leg.get_texts():
                txt.set_color(_FG)
        else:
            ax.text(
                0.5,
                0.5,
                "No speed data",
                ha="center",
                va="center",
                color=_FG_DIM,
                fontsize=12,
                transform=ax.transAxes,
            )

        # (b) Driving direction rose ------------------------------------
        ax = fig.add_subplot(gs[0, 1], projection="polar")
        ax.set_facecolor(_PANEL)
        ax.set_title(
            "Direction rose (current run)",
            color=_ACCENT,
            fontsize=13,
            pad=30,
            fontweight="bold",
        )
        ax.annotate(
            "How often the player drove toward each compass direction.",
            xy=(0.5, 1.08),
            xycoords="axes fraction",
            ha="center",
            va="bottom",
            color=_FG_DIM,
            fontsize=9,
            style="italic",
        )
        dir_col = self._col("player_direction_deg")
        if dir_col is not None and not dir_col.empty:
            bins = np.linspace(0, 2 * np.pi, 25)
            theta = np.deg2rad(dir_col.values)
            hist, edges = np.histogram(theta, bins=bins)
            width = np.diff(edges)
            centers = edges[:-1] + width / 2
            max_h = hist.max() if hist.max() > 0 else 1
            cmap = plt.get_cmap("magma")
            bar_colors = [cmap(0.25 + 0.65 * (h / max_h)) for h in hist]
            ax.bar(
                centers,
                hist,
                width=width,
                bottom=0.0,
                color=bar_colors,
                edgecolor=_BG,
                linewidth=0.4,
                align="center",
            )
            ax.tick_params(colors=_FG_DIM, labelsize=8)
            for spine in ax.spines.values():
                spine.set_color(_GRID)

        # (c) Position heatmap ------------------------------------------
        ax = fig.add_subplot(gs[0, 2])
        _style_ax(
            ax,
            "Position heatmap (current run)",
            "Density of the player's location across the map, with start & end.",
        )
        px, py = self._col("player_x"), self._col("player_y")
        if px is not None and py is not None and not px.empty:
            hb = ax.hexbin(
                px,
                py,
                gridsize=28,
                cmap="magma",
                mincnt=1,
                linewidths=0.2,
                edgecolors=_BG,
            )
            ax.plot(px, py, color=_ACCENT5, linewidth=0.8, alpha=0.5)
            ax.scatter(
                px.iloc[0],
                py.iloc[0],
                color=_ACCENT4,
                s=40,
                label="Start",
                zorder=5,
            )
            ax.scatter(
                px.iloc[-1],
                py.iloc[-1],
                color=_ACCENT3,
                s=80,
                marker="X",
                label="End",
                zorder=5,
            )
            ax.set_xlabel("World X")
            ax.set_ylabel("World Y")
            ax.invert_yaxis()
            cbar = fig.colorbar(hb, ax=ax, fraction=0.04, pad=0.02)
            cbar.ax.tick_params(colors=_FG_DIM, labelsize=8)
            cbar.set_label("Frames", color=_FG_DIM, fontsize=9)
            leg = ax.legend(
                loc="upper right",
                fontsize=9,
                frameon=True,
                facecolor=_BG,
                edgecolor=_GRID,
            )
            for txt in leg.get_texts():
                txt.set_color(_FG)
        else:
            ax.text(
                0.5,
                0.5,
                "No position data",
                ha="center",
                va="center",
                color=_FG_DIM,
                fontsize=12,
                transform=ax.transAxes,
            )

    # ------------------------------------------------------------------
    # chart helpers
    # ------------------------------------------------------------------
    def _shade_stages(self, ax: plt.Axes, df: pd.DataFrame) -> None:
        if "police_stage" not in df.columns or "frame" not in df.columns:
            return
        stages = df["police_stage"].astype(int).values
        frames = df["frame"].values
        if len(stages) == 0:
            return
        start_idx = 0
        for i in range(1, len(stages) + 1):
            if i == len(stages) or stages[i] != stages[start_idx]:
                stage_idx = int(stages[start_idx])
                color = _STAGE_COLORS[min(stage_idx - 1, len(_STAGE_COLORS) - 1)]
                ax.axvspan(
                    frames[start_idx],
                    frames[min(i, len(frames) - 1)],
                    facecolor=color,
                    alpha=0.55,
                    zorder=0,
                )
                if start_idx == 0 or stages[start_idx] != stages[start_idx - 1]:
                    ax.text(
                        frames[start_idx],
                        ax.get_ylim()[1] if ax.get_ylim()[1] > 0 else 1,
                        f" S{stage_idx}",
                        color=_ACCENT,
                        fontsize=8,
                        fontweight="bold",
                        va="top",
                        ha="left",
                        alpha=0.9,
                    )
                start_idx = i

    def show(self) -> None:
        """Open the rendered PNG with the system default image viewer."""
        if not os.path.exists(self.OUTPUT_PATH):
            return
        try:
            import subprocess
            import sys

            if sys.platform == "darwin":
                subprocess.run(["open", self.OUTPUT_PATH], check=False)
            elif sys.platform.startswith("win"):
                os.startfile(self.OUTPUT_PATH)  # type: ignore[attr-defined]
            else:
                subprocess.run(["xdg-open", self.OUTPUT_PATH], check=False)
        except Exception:
            pass
