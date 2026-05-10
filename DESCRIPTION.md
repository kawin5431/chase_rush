# Project Description

## 1. Project Overview

- **Project Name:** Chase Rush
- **Author:** kawin kaewparadai
- **Student ID:** 6710545431
- **Brief Description:**
  Chase Rush is an infinite top-down car chase game where the player drives a Lamborghini across a desert world while being pursued by AI-controlled police cars. The player must dodge obstacles, collect gifts, earn money, and survive as long as possible as the police difficulty gradually scales up. The game ends when the player's HP reaches zero.

  Every game session is automatically logged to CSV files, and a multi-section data visualization dashboard is generated at the end of each run using Matplotlib and Pandas. The dashboard covers exploratory data analysis, survival statistics, threat analysis, economy tracking, and detailed per-frame charts of the current run.

- **Problem Statement:**
  Games rarely show players meaningful data about their own performance. Chase Rush solves this by recording every frame of gameplay and presenting it as a readable statistical dashboard, letting players understand their playstyle, identify patterns, and improve over time.

- **Target Users:**
  Players who enjoy arcade-style driving games and want to track and analyze their own gameplay data over multiple sessions.

- **Key Features:**
  - Infinite desert world with physics-based driving (acceleration, friction, lateral grip)
  - AI police cars with dynamic difficulty scaling per stage
  - Nitro boost system, gift boxes, banana slips, and cactus obstacles
  - Persistent wallet system saved across sessions (CSV-backed)
  - Per-frame stat logging → CSV → auto-generated PNG dashboard
  - Dashboard with 6 sections: EDA Overview, Survival & Skill, Threats & Combat, Economy & Rewards, Statistical Summary, Current Run Deep Dive

- **Screenshots:**

  Gameplay:

  ![Gameplay](screenshots/gameplay/Screenshot%202026-05-10%20at%2021.15.58.png)

  Dashboard:

  ![Dashboard](screenshots/visualization/Screenshot%202026-05-10%20at%2021.19.21.png)

- **Proposal:** [ChaseRush_Proposal.pdf](ChaseRush_Proposal.pdf)

- **YouTube Presentation:** [https://youtu.be/eWoHkiGRkuY](https://youtu.be/eWoHkiGRkuY)

---

## 2. Concept

### 2.1 Background

This project was inspired by classic top-down police chase games and the idea of combining gameplay with real data analysis. Most arcade games treat each session as disposable — Chase Rush treats every run as a data point worth examining.

The core problem the game highlights is survival under pressure: how does a player's speed, decision-making, and resource management change as the threat level increases? By recording per-frame data and visualizing it, the game transforms a fun experience into a data story.

### 2.2 Objectives

- Build a fully playable top-down infinite driving game using Pygame and OOP principles
- Record meaningful gameplay metrics every frame and persist them to CSV
- Generate a multi-section data visualization dashboard automatically after each run
- Apply data processing concepts: data cleaning, EDA, distribution analysis, correlation, and data storytelling
- Demonstrate clear relationships between game events (police stage, gifts, collisions) and outcome metrics (money, survival time, speed)

---

## 3. UML Class Diagram

The UML class diagram shows all 12 classes, their attributes, methods, and relationships (association, composition).

**Attached:** [UML.pdf](UML.pdf)

---

## 4. Object-Oriented Programming Implementation

- **Game:** Central game controller. Manages the main loop, event handling, collision resolution, spawning, and rendering. Owns Player, Police list, Map, StatsTracker, SoundManager, and visual effects.
- **Player:** Physics-based player car with keyboard input, nitro management, HP tracking, and polygon hitbox.
- **Police:** AI-controlled police car that seeks the player. Supports stun, dynamic difficulty scaling, and the same physics model as Player.
- **Map:** Generates and manages the infinite world: road tiles, cactus obstacles, banknotes, banana peels, and gift boxes. Handles all pickup collision detection.
- **Wallet:** Persistent money balance stored in CSV. Tracks `balance` and `total_earned`. Every change is flushed to disk immediately.
- **StatsTracker:** Logs per-frame gameplay events and per-run summaries to CSV. Also tracks gift pickup events by stage.
- **Dashboard:** Reads CSV data and generates a multi-section PNG visualization using Matplotlib and Pandas. Covers EDA, survival, threats, economy, statistics, and current run analysis.
- **SoundManager:** Manages all audio channels: background music, engine sound, crash SFX, nitro, and drift sounds.
- **TireMarkManager:** Renders connected skid mark trails from both rear wheels of the player car.
- **DripSmokeFX:** Emits short-lived particle puffs (smoke on tarmac, dust on sand) during hard slides or turns.
- **EngineSmokeFX:** Emits hood smoke or fire particles from damaged vehicles. Switches to fire palette at low HP.
- **_NoInput:** Internal sentinel object that returns `False` for any key query — used as a safe fallback before input is available.

---

## 5. Statistical Data

### 5.1 Data Recording Method

Data is recorded at two levels:

**Per-frame** (`data/gameplay_stats.csv`): Every game frame, `StatsTracker.log_event()` appends one row capturing player position, speed, distance to nearest police, HP, nitro level, wallet balance, and cumulative counters. This file is saved at game over via `save_csv()`.

**Per-run** (`data/game_runs.csv`): At the end of each run, `StatsTracker.append_run_summary()` appends one row summarizing the entire session. This file accumulates across all sessions and is the primary source for cross-run analysis in the dashboard.

Gift events are separately logged to `data/gift_events.csv` to track which prizes were collected in which stage.

### 5.2 Data Features

**game_runs.csv** (one row per run):

| Column | Type | Description |
|--------|------|-------------|
| run_id | int | Sequential run number |
| timestamp | str | Date and time of the run |
| duration_s | float | Total survival time in seconds |
| frames | int | Total frames in the run |
| peak_stage | int | Highest police difficulty stage reached |
| top_speed | float | Maximum speed recorded (km/h) |
| avg_speed | float | Average speed across the run |
| min_police_dist | float | Closest police approach distance |
| nitro_frames | int | Total frames spent in nitro boost |
| total_banana_slips | int | Number of banana peel hits |
| total_cactus_hits | int | Number of cactus collisions |
| total_police_killed | int | Number of police cars destroyed |
| total_collisions_player_police | int | Total player–police collision events |
| total_gifts_collected | int | Total gift boxes collected |
| gift_money / gift_nitro / gift_invincible / gift_ram | int | Count of each gift type |
| money_earned | int | Money earned from banknotes this run |
| final_wallet | int | Total persistent wallet balance at run end |

**gameplay_stats.csv** (one row per frame of current run):

| Column | Type | Description |
|--------|------|-------------|
| frame | int | Frame number |
| time_s | float | Time elapsed in seconds |
| player_x / player_y | float | Player world position |
| player_speed | float | Current speed (km/h) |
| dist_nearest_police | float | Distance to nearest police car |
| player_hp | int | Remaining HP |
| nitro_level | float | Current nitro charge |
| wallet_balance | int | Current persistent wallet balance |
| police_stage | int | Current difficulty stage |

---

## 6. Changed Proposed Features

The original proposal described a simpler statistics screen with basic bar charts. The final implementation significantly expanded the data component to include:

- Full EDA pipeline (histograms, boxplots, scatter plots with correlation coefficients)
- Statistical summary table with mean, median, mode, std dev, and IQR outlier detection
- Per-frame time-series charts with trend lines, rolling averages, and stage shading
- Persistent wallet system that was not in the original proposal
- Gift event logging by stage to analyze reward distribution

---

## 7. External Sources

The following external assets were used in this project:

- **Lamborghini sprite** — sourced online, used for player car visual
- **Police car sprite** — sourced online, used for police car visual
- **Background music** (`background.mp3`) — sourced online
- **Engine sounds** (`lamboreal02.mp3`, `slowreal.mp3`, `slow03.mp3`, `reverselambo.mp3`) — sourced online
- **Sound effects** (`Hitsound.mp3`, `nitro.mp3`, `driff.mp3`) — sourced online

*(If you have specific source URLs or license info, add them here.)*
