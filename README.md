# Chase Rush

## Project Description

- **Project by:** kawin kaewparadai
- **Student ID:** 6710545431
- **Game Genre:** Action, Arcade, Infinite Runner

Chase Rush is a top-down infinite car chase game where you drive a Lamborghini through a desert world while evading AI police cars. Survive as long as possible, collect gifts and money, and use nitro boosts to outrun the police. After each run, a full data visualization dashboard is automatically generated showing your stats.

---

## Installation

To clone this project:

```sh
git clone https://github.com/kawin5431/chase_rush.git
cd chase_rush
```

To create and run a Python environment for this project:

**Windows:**

```bat
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

**Mac:**

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

---

## Running Guide

After activating the Python environment, run the game from the project root:

**Windows:**

```bat
python main.py
```

**Mac:**

```sh
python3 main.py
```

> **Important:** Run from the project root directory (where `main.py` is located) so that `assets/` and `data/` paths resolve correctly.

---

## Tutorial / Usage

1. Launch the game with `python3 main.py`
2. Press any key on the start screen to begin
3. Drive using arrow keys or WASD
4. Press **Q** to activate nitro boost (when available)
5. Avoid police cars — collisions drain HP
6. Collect gift boxes for bonus rewards (money, nitro, invincibility, ram)
7. Pick up banknotes on the road to earn money
8. Watch out for cacti (collision damage) and banana peels (loss of control)
9. When HP hits zero, the game ends and the stats dashboard is saved to `data/gameplay_stats_dashboard.png`

**Controls:**

| Key | Action |
|-----|--------|
| ↑ / W | Accelerate |
| ↓ / S | Brake / Reverse |
| ← / A | Turn left |
| → / D | Turn right |
| Q | Activate nitro |
| ESC | Quit |

---

## Game Features

- **Infinite desert world** with procedurally placed obstacles, roads, and pickups
- **Physics-based driving** — acceleration, friction, lateral grip, and knockback
- **AI police cars** with seek-and-chase logic and dynamic difficulty scaling
- **Nitro boost** — press Q to burst to high speed for a few seconds
- **Gift box system** — 4 gift types: money bonus, nitro refill, invincibility, ram boost
- **Banana peels** — cause temporary loss of directional control
- **Cactus obstacles** — stationary hazards that damage the player on collision
- **Persistent wallet** — money balance is saved between sessions
- **Tire skid marks and smoke effects** — visual feedback for drifts and engine damage
- **Auto stats dashboard** — PNG report generated after every run

---

## Known Bugs

- None currently identified.

---

## Unfinished Works

- All planned features have been implemented.

---

## External Sources

1. Lamborghini car sprite — sourced online [player vehicle image]
2. Police car sprite — sourced online [police vehicle image]
3. Background music (`background.mp3`) — sourced online [background audio]
4. Engine sounds (`lamboreal02.mp3`, `slowreal.mp3`, etc.) — sourced online [audio effects]
5. Sound effects (`Hitsound.mp3`, `nitro.mp3`, `driff.mp3`) — sourced online [audio effects]
