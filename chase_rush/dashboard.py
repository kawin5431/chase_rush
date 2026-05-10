"""Load per-frame stats from ``data/gameplay_stats.csv`` and render a scrollable dashboard.

The dashboard is shown from the in-game Stats menu: when a player opens
it we regenerate a tall PNG from the latest CSV and let the pygame UI
vertically scroll through it. The figure is broken into clearly-labelled
sections — KPI cards, spatial analysis, temporal analysis, statistical
summary and gift analytics — each with its own banner so the layout feels
structured and easy to scan.
"""

from __future__ import annotations

import os
import math
from typing import List, Optional

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
    pad = 22 if caption else 8
    ax.set_title(title, color=_ACCENT, fontsize=13, pad=pad, fontweight="bold")
    if caption:
        ax.text(
            0.5,
            1.01,
            caption,
            transform=ax.transAxes,
            ha="center",
            va="bottom",
            color=_FG_DIM,
            fontsize=8,
            style="italic",
            wrap=True,
            clip_on=False,
        )


class Dashboard:
    """Build and save a multi-section statistics image for the current run."""

    OUTPUT_PATH = config.GAMEPLAY_STATS_DASHBOARD_PNG
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
        key_cols = ["frame", "time_s", "player_x", "player_y", "player_speed"]
        _sub = [c for c in key_cols if c in self.data_frame.columns]
        if _sub:
            self.data_frame = self.data_frame.dropna(subset=_sub)
        gift_path = config.GIFT_EVENTS_CSV
        if os.path.exists(gift_path):
            try:
                self.gift_frame = pd.read_csv(gift_path)
            except (pd.errors.EmptyDataError, OSError):
                self.gift_frame = None
        runs_path = config.GAME_RUNS_CSV
        if os.path.exists(runs_path):
            try:
                self.runs_frame = pd.read_csv(runs_path)
                self.runs_frame = self.runs_frame.fillna(0)
            except (pd.errors.EmptyDataError, OSError):
                self.runs_frame = None
        return self

    def _get_dtype_label(self, col_name: str) -> str:
        """Course-style measurement scale for dashboard EDA labels."""
        nominal = frozenset({"prize", "run_id"})
        ordinal = frozenset({"police_stage", "peak_stage"})
        if col_name in nominal:
            return "Nominal"
        if col_name in ordinal:
            return "Ordinal"
        return "Ratio"

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
        std_v = float(s.std(ddof=0))
        std_s = f"{std_v:.2f}" if np.isfinite(std_v) else "-"
        return [
            f"{s.mean():.2f}",
            f"{s.median():.2f}",
            f"{mode_v:.2f}",
            f"{s.max():.2f}",
            f"{s.min():.2f}",
            std_s,
        ]

    def _iqr_outlier_count_cell(self, series: pd.Series) -> str:
        """Count of IQR outliers; display count if > 0 else '-'."""
        s = series.dropna().astype(float)
        if len(s) == 0:
            return "-"
        q1 = s.quantile(0.25)
        q3 = s.quantile(0.75)
        iqr = float(q3 - q1)
        if not np.isfinite(iqr):
            return "-"
        low = q1 - 1.5 * iqr
        high = q3 + 1.5 * iqr
        mask = (s > high) | (s < low)
        n = int(mask.sum())
        return str(n) if n > 0 else "-"

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
            (0.01, 0.18),
            0.055,
            0.66,
            boxstyle="round,pad=0.02,rounding_size=0.05",
            color=_ACCENT,
            transform=ax.transAxes,
            clip_on=False,
        )
        ax.add_patch(chip)
        ax.text(
            0.0375,
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
            0.085,
            0.5,
            label.upper(),
            color=_ACCENT,
            fontsize=16,
            fontweight="bold",
            ha="left",
            va="center",
            transform=ax.transAxes,
        )
        label_pad = 0.085 + 0.012 * len(label) + 0.04
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
        #   1  KPI strip
        #   2–5  EDA Overview (header, histograms, boxplot, scatter)
        #   6–7  Survival & Skill
        #   8–9  Threats & Combat
        #  10–11 Economy & Rewards
        #  12–13 Statistical Summary (table)
        #  14–15 Current Run Deep Dive
        #  16  footer
        row_ratios = [
            0.75,  # banner
            1.10,  # KPI strip
            0.45,  # header — EDA Overview
            2.85,  # EDA histograms (1×3)
            2.60,  # EDA boxplot
            2.85,  # EDA scatter (1×2)
            0.45,  # header — Survival & Skill
            2.85,  # survival & skill (1×3)
            0.45,  # header — Threats & Combat
            5.70,  # hazards & combat (2×2)
            0.45,  # header — Economy & Rewards
            2.85,  # gifts & economy (1×3)
            0.45,  # header — Statistical Summary
            2.30,  # per-run stats table
            0.45,  # header — Current Run Deep Dive
            2.85,  # current-run charts (1×3)
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
            left=0.07,
            right=0.955,
            top=0.985,
            bottom=0.015,
            hspace=0.85,
            height_ratios=row_ratios,
        )

        # --- Row 0: banner -----------------------------------------------
        self._draw_banner(fig.add_subplot(outer[0]), df, runs)

        # --- Row 1: KPI strip (lifetime totals) --------------------------
        kpi_gs = GridSpecFromSubplotSpec(1, 6, subplot_spec=outer[1], wspace=0.20)
        self._draw_kpi_strip(fig, kpi_gs, df, runs)

        self._section_header(
            fig.add_subplot(outer[2]), "EDA Overview", "01"
        )
        eda_hist_gs = GridSpecFromSubplotSpec(1, 3, subplot_spec=outer[3], wspace=0.32)
        eda_box_ax = fig.add_subplot(outer[4])
        eda_scatter_gs = GridSpecFromSubplotSpec(
            1, 2, subplot_spec=outer[5], wspace=0.32
        )
        self._draw_eda_overview(fig, eda_hist_gs, eda_box_ax, eda_scatter_gs)

        # --- Survival & Skill -------------------------------------------
        self._section_header(
            fig.add_subplot(outer[6]), "Survival & Skill", "02"
        )
        surv_gs = GridSpecFromSubplotSpec(1, 3, subplot_spec=outer[7], wspace=0.32)
        self._draw_survival_charts(fig, surv_gs)

        # --- Threats & Combat -------------------------------------------
        self._section_header(
            fig.add_subplot(outer[8]), "Threats & Combat", "03"
        )
        haz_gs = GridSpecFromSubplotSpec(
            2, 2, subplot_spec=outer[9], wspace=0.26, hspace=0.70
        )
        self._draw_hazard_charts(fig, haz_gs)

        # --- Economy & Rewards -------------------------------------------
        self._section_header(
            fig.add_subplot(outer[10]), "Economy & Rewards", "04"
        )
        econ_gs = GridSpecFromSubplotSpec(1, 3, subplot_spec=outer[11], wspace=0.32)
        self._draw_economy_charts(fig, econ_gs)

        # --- Statistical Summary ----------------------------------------
        self._section_header(
            fig.add_subplot(outer[12]), "Statistical Summary", "05"
        )
        self._draw_runs_stats_table(fig.add_subplot(outer[13]))

        # --- Current Run Deep Dive --------------------------------------
        self._section_header(
            fig.add_subplot(outer[14]), "Current Run Deep Dive", "06"
        )
        cur_gs = GridSpecFromSubplotSpec(1, 3, subplot_spec=outer[15], wspace=0.32)
        self._draw_current_run_charts(fig, cur_gs, df)

        # --- Footer ------------------------------------------------------
        foot = fig.add_subplot(outer[16])
        foot.set_facecolor(_BG)
        foot.axis("off")
        foot.text(
            0.5,
            0.6,
            "— Generated from data/gameplay_stats.csv + data/game_runs.csv  ·  "
            "Chase Rush Analytics —",
            ha="center",
            va="center",
            color=_FG_DIM,
            fontsize=10,
            transform=foot.transAxes,
        )

        config.ensure_parent_dir(self.OUTPUT_PATH)
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
            f"Explore your {n_runs} runs below  ·  "
            f"From distribution analysis to time-series deep dives  ·  "
            f"Latest: {duration:.1f}s  ·  Peak stage {max_stage}"
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
        dtype_info = (
            "DataFrame info — "
            "Ratio: player_speed, duration_s, top_speed, money_earned, wallet_balance  ·  "
            "Ordinal: police_stage, peak_stage  ·  "
            "Nominal: prize (gift type)"
        )
        ax.text(
            0.5,
            0.55,
            dtype_info,
            ha="center",
            va="center",
            color=_FG_DIM,
            fontsize=8,
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

    def _draw_eda_overview(
        self,
        fig: plt.Figure,
        hist_gs: GridSpecFromSubplotSpec,
        box_ax: plt.Axes,
        scatter_gs: GridSpecFromSubplotSpec,
    ) -> None:
        """Topic 2: univariate + normalized comparison + bivariate relationships."""
        runs = self.runs_frame
        _ph = "Finish more runs to see this chart"

        # --- Row A: histograms -----------------------------------------
        def _hist_metric(
            ax: plt.Axes,
            col: str,
            color: str,
            title: str,
            caption: str,
        ) -> None:
            if runs is None or len(runs) < 2 or col not in runs.columns:
                ax.set_facecolor(_PANEL)
                ax.text(
                    0.5, 0.5, _ph, ha="center", va="center",
                    color=_FG_DIM, fontsize=12, transform=ax.transAxes,
                )
                return
            s = pd.to_numeric(runs[col], errors="coerce").dropna()
            if len(s) < 2:
                ax.set_facecolor(_PANEL)
                ax.text(
                    0.5, 0.5, _ph, ha="center", va="center",
                    color=_FG_DIM, fontsize=12, transform=ax.transAxes,
                )
                return
            _style_ax(ax, title, caption)
            ax.hist(s, bins=8, color=color, edgecolor=_BG)
            mean_v = float(s.mean())
            med_v = float(s.median())
            ax.axvline(mean_v, color=_ACCENT3, linestyle="--", label="Mean")
            ax.axvline(med_v, color=_ACCENT2, linestyle=":", label="Median")
            ax.legend(
                loc="upper right",
                fontsize=9,
                frameon=True,
                facecolor=_BG,
                edgecolor=_GRID,
                labelcolor=_FG,
            )
            skew_val = float(s.skew()) if len(s) >= 3 else 0.0
            if skew_val > 0.5:
                shape_label = "Right-skewed"
                shape_color = _ACCENT3
            elif skew_val < -0.5:
                shape_label = "Left-skewed"
                shape_color = _ACCENT2
            else:
                shape_label = "Approx. normal"
                shape_color = _ACCENT4
            ax.text(
                0.97,
                0.95,
                shape_label,
                transform=ax.transAxes,
                ha="right",
                va="top",
                color=shape_color,
                fontsize=9,
                fontweight="bold",
                bbox=dict(
                    boxstyle="round,pad=0.3",
                    facecolor=_PANEL_HI,
                    edgecolor=shape_color,
                    linewidth=1.0,
                ),
            )

        cap_a = "Survival time per run. Dashed = mean, dotted = median."
        cap_b = "Max speed per run. Dashed = mean, dotted = median."
        cap_c = "Money earned per run. Dashed = mean, dotted = median."
        _hist_metric(
            fig.add_subplot(hist_gs[0, 0]),
            "duration_s",
            _ACCENT,
            "Survival Time Distribution",
            cap_a,
        )
        _hist_metric(
            fig.add_subplot(hist_gs[0, 1]),
            "top_speed",
            _ACCENT2,
            "Top Speed Distribution",
            cap_b,
        )
        _hist_metric(
            fig.add_subplot(hist_gs[0, 2]),
            "money_earned",
            _ACCENT4,
            "Money Earned Distribution",
            cap_c,
        )

        # --- Row B: normalized boxplot ----------------------------------
        metrics = {
            "Survival (s)": "duration_s",
            "Top Speed": "top_speed",
            "Banana Slips": "total_banana_slips",
            "Cactus Hits": "total_cactus_hits",
            "Police Kills": "total_police_killed",
        }
        box_colors = [_ACCENT, _ACCENT2, _ACCENT4, _ACCENT3, _ACCENT5]
        cap_box = (
            "Box = Q1–Q3, line = median, whiskers = range, dots = outliers (IQR method). "
            "Outliers: > Q3 + 1.5×IQR or < Q1 − 1.5×IQR. "
            "Values min–max normalized per metric so scales are comparable."
        )
        _style_ax(
            box_ax,
            "Metric Distributions (normalized)",
            cap_box,
        )
        if runs is None or len(runs) < 2:
            box_ax.text(
                0.5, 0.5, _ph, ha="center", va="center",
                color=_FG_DIM, fontsize=12, transform=box_ax.transAxes,
            )
        else:
            data_list: List[np.ndarray] = []
            labels_list: List[str] = []
            for lab, col in metrics.items():
                if col not in runs.columns:
                    continue
                v = pd.to_numeric(runs[col], errors="coerce").fillna(0).values.astype(float)
                if len(v) == 0:
                    continue
                rng = float(np.nanmax(v) - np.nanmin(v))
                if rng <= 0 or not math.isfinite(rng):
                    norm = np.zeros_like(v, dtype=float)
                else:
                    norm = (v - np.nanmin(v)) / rng
                data_list.append(norm)
                labels_list.append(lab)
            if len(data_list) < 1:
                box_ax.text(
                    0.5, 0.5, _ph, ha="center", va="center",
                    color=_FG_DIM, fontsize=12, transform=box_ax.transAxes,
                )
            else:
                try:
                    bp = box_ax.boxplot(
                        data_list,
                        tick_labels=labels_list,
                        patch_artist=True,
                    )
                except TypeError:
                    bp = box_ax.boxplot(
                        data_list,
                        labels=labels_list,
                        patch_artist=True,
                    )
                for patch, c in zip(bp["boxes"], box_colors):
                    patch.set_facecolor(c)
                    patch.set_edgecolor(_BG)
                for med in bp["medians"]:
                    med.set_color("white")
                    med.set_linewidth(1.2)
                for w in bp["whiskers"]:
                    w.set_color(_FG_DIM)
                for fl in bp["fliers"]:
                    fl.set(marker="o", color=_ACCENT3, alpha=0.85)
                box_ax.set_ylabel("Normalized value [0,1]")

        # --- Row C: scatters -------------------------------------------
        ax_s1 = fig.add_subplot(scatter_gs[0, 0])
        if runs is None or len(runs) < 2:
            ax_s1.set_facecolor(_PANEL)
            ax_s1.text(
                0.5, 0.5, _ph, ha="center", va="center",
                color=_FG_DIM, fontsize=12, transform=ax_s1.transAxes,
            )
        elif "duration_s" not in runs.columns or "money_earned" not in runs.columns:
            ax_s1.set_facecolor(_PANEL)
            ax_s1.text(
                0.5, 0.5, _ph, ha="center", va="center",
                color=_FG_DIM, fontsize=12, transform=ax_s1.transAxes,
            )
        else:
            sub = runs[["duration_s", "money_earned"]].apply(
                pd.to_numeric, errors="coerce"
            ).dropna(how="any")
            if len(sub) < 2:
                ax_s1.set_facecolor(_PANEL)
                ax_s1.text(
                    0.5, 0.5, _ph, ha="center", va="center",
                    color=_FG_DIM, fontsize=12, transform=ax_s1.transAxes,
                )
            else:
                x = sub["duration_s"].to_numpy(dtype=float)
                y = sub["money_earned"].to_numpy(dtype=float)
                rho = sub["duration_s"].corr(sub["money_earned"])
                rho_txt = "ρ = —"
                if rho is not None and np.isfinite(float(rho)):
                    rf = float(rho)
                    rho_txt = (
                        f"ρ = {rf:.2f} — "
                        f"{'positive' if rf > 0 else 'negative'} correlation"
                    )
                cap_s1 = (
                    f"{rho_txt}. Variables: {self._get_dtype_label('duration_s')} × "
                    f"{self._get_dtype_label('money_earned')}."
                )
                _style_ax(ax_s1, "Survival vs Money Earned", cap_s1)
                ax_s1.scatter(
                    x, y, color=_ACCENT, s=60, alpha=0.8, edgecolors=_BG,
                )
                x_s = x[np.argsort(x)]
                coeff = np.polyfit(x, y, 1)
                ax_s1.plot(
                    x_s,
                    np.polyval(coeff, x_s),
                    color=_ACCENT3,
                    linewidth=1.5,
                    label="Trend (linear)",
                )
                ax_s1.legend(
                    loc="best",
                    fontsize=9,
                    frameon=True,
                    facecolor=_BG,
                    edgecolor=_GRID,
                    labelcolor=_FG,
                )

        ax_s2 = fig.add_subplot(scatter_gs[0, 1])
        if runs is None or len(runs) < 2:
            ax_s2.set_facecolor(_PANEL)
            ax_s2.text(
                0.5, 0.5, _ph, ha="center", va="center",
                color=_FG_DIM, fontsize=12, transform=ax_s2.transAxes,
            )
        elif not all(
            c in runs.columns for c in ("top_speed", "duration_s", "peak_stage")
        ):
            ax_s2.set_facecolor(_PANEL)
            ax_s2.text(
                0.5, 0.5, _ph, ha="center", va="center",
                color=_FG_DIM, fontsize=12, transform=ax_s2.transAxes,
            )
        else:
            sub2 = runs[["top_speed", "duration_s", "peak_stage"]].apply(
                pd.to_numeric, errors="coerce"
            )
            sub2 = sub2.dropna(subset=["top_speed", "duration_s"])
            if len(sub2) < 2:
                ax_s2.set_facecolor(_PANEL)
                ax_s2.text(
                    0.5, 0.5, _ph, ha="center", va="center",
                    color=_FG_DIM, fontsize=12, transform=ax_s2.transAxes,
                )
            else:
                xs = sub2["top_speed"].to_numpy(dtype=float)
                ys = sub2["duration_s"].to_numpy(dtype=float)
                ps = sub2["peak_stage"].fillna(1).to_numpy(dtype=float)
                rho2 = sub2["top_speed"].corr(sub2["duration_s"])
                rho_txt2 = "ρ = —"
                if rho2 is not None and np.isfinite(float(rho2)):
                    r2f = float(rho2)
                    rho_txt2 = (
                        f"ρ = {r2f:.2f} — "
                        f"{'positive' if r2f > 0 else 'negative'} correlation"
                    )
                cap_s2 = (
                    f"{rho_txt2}. Bubble size = peak police stage "
                    f"({self._get_dtype_label('peak_stage')})."
                )
                _style_ax(ax_s2, "Top Speed vs Survival", cap_s2)
                sizes = np.clip(ps * 30.0, 15.0, 400.0)
                sc = ax_s2.scatter(
                    xs,
                    ys,
                    s=sizes,
                    c=ps,
                    cmap="magma",
                    alpha=0.85,
                    edgecolors=_BG,
                )
                cbar = fig.colorbar(sc, ax=ax_s2, fraction=0.04, pad=0.02)
                cbar.ax.tick_params(colors=_FG_DIM, labelsize=8)
                cbar.set_label("Peak stage", color=_FG_DIM, fontsize=9)
                x_so = xs[np.argsort(xs)]
                coeff2 = np.polyfit(xs, ys, 1)
                ax_s2.plot(
                    x_so,
                    np.polyval(coeff2, x_so),
                    color=_ACCENT3,
                    linewidth=1.5,
                    label="Trend (linear)",
                )
                ax_s2.legend(
                    loc="best",
                    fontsize=9,
                    frameon=True,
                    facecolor=_BG,
                    edgecolor=_GRID,
                    labelcolor=_FG,
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
            "Which run lasted longest? Gold border = personal best.",
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
                "Offensive plays — how many cops did you destroy?",
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
            "Total income per run including banknote + gift money.",
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

        # (c) Lifetime prize haul — pie (distribution substitution) -------
        ax = fig.add_subplot(gs[0, 2])
        _style_ax(
            ax,
            "Gift Prize Breakdown (all runs)",
            "Proportions of each prize type — area represents ratio.",
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

        ax.pie(
            totals,
            labels=labels_p,
            colors=colors,
            autopct="%1.0f%%",
            startangle=90,
            wedgeprops=dict(edgecolor=_BG, linewidth=1.5),
            textprops=dict(color=_FG, fontsize=10),
        )
        ax.axis("equal")

    def _draw_runs_stats_table(self, ax: plt.Axes) -> None:
        """Per-run aggregates: mean/median/mode/max/min/std (ddof=0) + IQR outlier counts."""
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
            ("Avg Speed", "avg_speed", _ACCENT2),
            ("Nitro Frames", "nitro_frames", _ACCENT5),
        ]

        _SKEW_STAR_COLS = frozenset(
            {
                "top_speed",
                "total_police_killed",
                "total_cactus_hits",
                "total_banana_slips",
                "money_earned",
                "nitro_frames",
            }
        )

        col_labels = ["Mean", "Median", "Mode", "Max", "Min", "Std Dev", "Outliers"]
        cell_rows: list[list[str]] = []
        row_labels: list[str] = []
        accent_by_row: list[str] = []
        for label, col, accent in rows:
            if col not in runs.columns:
                continue
            s = runs[col].astype(float)
            disp_label = label
            if col in _SKEW_STAR_COLS:
                sk = s.dropna().astype(float)
                if len(sk) >= 3:
                    sk_val = float(sk.skew())
                    if np.isfinite(sk_val) and sk_val > 0.5:
                        disp_label = f"*{label}"
            row = self._stat_row(s)
            row.append(self._iqr_outlier_count_cell(s))
            cell_rows.append(row)
            row_labels.append(disp_label)
            accent_by_row.append(accent)

        if not cell_rows:
            return

        table = ax.table(
            cellText=cell_rows,
            rowLabels=row_labels,
            colLabels=col_labels,
            bbox=[0.04, 0.10, 0.94, 0.78],
            colWidths=[0.085] * 7,
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

        ax.text(
            0.5,
            0.02,
            "Mode = most frequent value; use median for skewed distributions.  "
            "* right-skewed — median is better representative than mean.",
            ha="center",
            va="bottom",
            color=_FG_DIM,
            fontsize=9,
            style="italic",
            transform=ax.transAxes,
            clip_on=False,
        )

    def _draw_current_run_charts(
        self,
        fig: plt.Figure,
        gs: GridSpecFromSubplotSpec,
        df: pd.DataFrame,
    ) -> None:
        """Topic 3: time-series with trend lines; pickups as highlighted points."""
        # (a) Speed over time + poly trend --------------------------------
        ax = fig.add_subplot(gs[0, 0])
        _style_ax(
            ax,
            "Speed over time (current run)",
            "Raw speed, rolling average, degree-3 polynomial trend; bands = police stage.",
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
            frames_arr = df["frame"].values.astype(float)
            speed_arr = speed.values.astype(float)
            if len(frames_arr) >= 4:
                coeff_p = np.polyfit(frames_arr, speed_arr, 3)
                trend = np.polyval(coeff_p, frames_arr)
                ax.plot(
                    df["frame"],
                    trend,
                    color=_ACCENT3,
                    linewidth=1.5,
                    linestyle="-.",
                    label="Trend (poly-3)",
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

        # (b) Police distance over time ----------------------------------
        ax2 = fig.add_subplot(gs[0, 1])
        _style_ax(
            ax2,
            "Distance to Police (current run)",
            "Lower = more danger. Background bands = police stage.",
        )
        dist = self._col("dist_nearest_police")
        if dist is not None and "time_s" in df.columns and not dist.empty:
            dser = pd.to_numeric(
                dist.replace([np.inf, -np.inf], np.nan),
                errors="coerce",
            )
            tplot = df["time_s"].astype(float)
            self._shade_stages_time(ax2, df)
            ax2.plot(
                tplot,
                dser,
                color=_ACCENT2,
                linewidth=1.0,
                alpha=0.85,
                label="Distance",
            )
            if len(dser) > 30:
                roll_d = dser.rolling(window=30, min_periods=1).mean()
                ax2.plot(
                    tplot,
                    roll_d,
                    color=_ACCENT,
                    linewidth=1.3,
                    label="Rolling avg (30 fr)",
                )
            m = float(np.nanmean(dser.to_numpy(dtype=float)))
            if np.isfinite(m):
                ax2.axhline(
                    m,
                    color=_ACCENT3,
                    linestyle="--",
                    linewidth=1.1,
                    label="Mean distance",
                )
            ax2.set_xlabel("Time (s)")
            ax2.set_ylabel("Distance")
            leg2 = ax2.legend(
                loc="upper right",
                fontsize=9,
                frameon=True,
                facecolor=_BG,
                edgecolor=_GRID,
            )
            for txt in leg2.get_texts():
                txt.set_color(_FG)
        else:
            ax2.text(
                0.5,
                0.5,
                "No distance data",
                ha="center",
                va="center",
                color=_FG_DIM,
                fontsize=12,
                transform=ax2.transAxes,
            )

        # (c) Wallet over time -------------------------------------------
        ax3 = fig.add_subplot(gs[0, 2])
        _style_ax(
            ax3,
            "Wallet Balance over time",
            "Gold dots = money pickup events (Points = individual values).",
        )
        wbal = self._col("wallet_balance")
        if wbal is not None and "time_s" in df.columns and not wbal.empty:
            ax3.plot(
                df["time_s"],
                wbal,
                color=_ACCENT2,
                linewidth=1.2,
                label="Balance",
            )
            if "money_earned_this_frame" in df.columns:
                pickup_mask = df["money_earned_this_frame"].astype(float) > 0
                ax3.scatter(
                    df.loc[pickup_mask, "time_s"],
                    df.loc[pickup_mask, "wallet_balance"],
                    color=_ACCENT,
                    s=25,
                    zorder=5,
                    label="Pickup",
                    edgecolors=_BG,
                )
            ax3.set_xlabel("Time (s)")
            ax3.set_ylabel("Wallet ($)")
            leg3 = ax3.legend(
                loc="upper left",
                fontsize=9,
                frameon=True,
                facecolor=_BG,
                edgecolor=_GRID,
            )
            for txt in leg3.get_texts():
                txt.set_color(_FG)
        else:
            ax3.text(
                0.5,
                0.5,
                "No wallet data",
                ha="center",
                va="center",
                color=_FG_DIM,
                fontsize=12,
                transform=ax3.transAxes,
            )

    # ------------------------------------------------------------------
    # chart helpers
    # ------------------------------------------------------------------
    def _shade_stages_time(self, ax: plt.Axes, df: pd.DataFrame) -> None:
        """Background bands by police stage using ``time_s`` as x."""
        if "police_stage" not in df.columns or "time_s" not in df.columns:
            return
        stages = df["police_stage"].astype(int).values
        times = df["time_s"].astype(float).values
        if len(stages) == 0:
            return
        start_idx = 0
        for i in range(1, len(stages) + 1):
            if i == len(stages) or stages[i] != stages[start_idx]:
                stage_idx = int(stages[start_idx])
                color = _STAGE_COLORS[min(stage_idx - 1, len(_STAGE_COLORS) - 1)]
                t0 = times[start_idx]
                t1 = times[min(i - 1, len(times) - 1)]
                if t1 >= t0:
                    ax.axvspan(t0, t1, facecolor=color, alpha=0.55, zorder=0)
                start_idx = i

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
