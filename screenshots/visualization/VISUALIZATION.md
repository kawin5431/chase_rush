# Visualization Documentation

This document describes all data visualization components in the Chase Rush statistics dashboard. The dashboard is generated automatically after each game session as a PNG image using Matplotlib and Pandas.

---

## Overall Dashboard

![Overall Dashboard](Screenshot%202026-05-10%20at%2021.19.21.png)

The dashboard is a single-page multi-section visualization generated from two CSV data sources: `game_runs.csv` (one row per run) and `gameplay_stats.csv` (one row per frame of the current run). It is divided into 6 sections covering EDA, survival, threats, economy, statistics, and current run analysis.

---

## Section 01 — EDA Overview

### Distribution Histograms

![EDA Histograms](Screenshot%202026-05-10%20at%2021.19.33.png)

Three histograms showing the frequency distribution of key performance metrics across all runs: `duration_s` (session length), `top_speed` (peak speed reached), and `money_earned` (total money per run). Each histogram displays the shape of the distribution, allowing identification of skewness and central tendency. Right-skewed distributions indicate that most runs are short/slow, with a few exceptional outlier runs.

### Boxplot — Multi-variable Spread

![Boxplot](Screenshot%202026-05-10%20at%2021.19.52.png)

A grouped boxplot comparing the spread and outliers of multiple numeric columns simultaneously. Each box shows the interquartile range (Q1–Q3), median line, whiskers extending to 1.5×IQR, and individual outlier points. This chart reveals which metrics have high variability and which runs deviate significantly from the norm.

### Scatter Plots — Correlation Analysis

![Scatter Plots](Screenshot%202026-05-10%20at%2021.20.18.png)

Two scatter plots examining relationships between variables: (1) `duration_s` vs `money_earned` and (2) `top_speed` vs `total_police_killed`. Each plot includes the Pearson correlation coefficient (ρ) to quantify the linear relationship strength. A positive ρ near 1.0 indicates a strong positive correlation, while ρ near 0 indicates no linear relationship.

---

## Section 05 — Statistical Summary Table

![Stats Table](Screenshot%202026-05-10%20at%2021.20.32.png)

A comprehensive statistics table showing descriptive statistics for all key numeric columns across all recorded runs. Each row represents one metric and each column shows: Mean, Median, Mode, Max, Min, Standard Deviation, and Outlier Count (IQR method). Cells marked with ★ indicate right-skewed distributions where mean > median, meaning the average is pulled up by extreme values.

---

## Section 06 — Current Run Deep Dive

### Speed Over Time with Trend Line

![Speed Chart](Screenshot%202026-05-10%20at%2021.20.41.png)

A time-series line chart of `player_speed` across every frame of the current run. A polynomial degree-3 trend line is overlaid to show the overall speed progression. Stage transitions are shaded in background colors to indicate when police difficulty increased. This chart illustrates player acceleration patterns and the effect of nitro usage and collisions on speed.

### Police Distance Over Time

![Police Distance Chart](Screenshot%202026-05-10%20at%2021.20.50.png)

A time-series line chart showing `dist_nearest_police` (distance to the closest police car) over the run duration. Lower values indicate dangerous moments when police were closing in. Stage transitions are shaded for context. This chart reveals how close the player came to being caught and whether they successfully escaped after dangerous encounters.

### Wallet Balance Over Time

![Wallet Chart](Screenshot%202026-05-10%20at%2021.20.59.png)

A time-series area chart of `wallet_balance` across the run, with gift pickup events marked as scatter points along the line. Each gift point is color-coded by type (money, nitro, invincible, ram). This chart tells the economic story of the run — when money was collected, how gifts were obtained, and how the total balance grew over time.
