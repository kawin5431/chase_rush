# 📄 DESCRIPTION.md

## 🎮 Overview
This is a car chase game named **"Catch me if you can"**, where the player drives a car to avoid police vehicles while collecting nitro boosts and leaving tire marks on the sand. The game is developed using Pygame and structured with Object-Oriented Programming for modularity and scalability.

## 📦 Class Descriptions

### `Game`
The central controller of the game. It manages the main game loop, object spawning, collisions, and updates.

- **Attributes**:
  - Manages screen, player, police cars, tire marks, nitro flame, background, sounds, statistics, etc.
  - Keeps track of time, distance, nitro count, milestones, and visual effects like screen shake.
- **Methods**:
  - `start_screen()`, `game_over()`, `spawn_police()`, `collision_response(...)`, `run()`

### `PlayerCar` (inherits from `CarBase`)
Represents the player’s car with controls, physics, and nitro management.

- **Attributes**:
  - Speed, acceleration, friction, turning limits, total distance, nitro fading
- **Methods**:
  - `control(...)` - responds to key input
  - `hitbox()` - returns collision box

### `PoliceCar` (inherits from `CarBase`)
An AI-controlled car that chases the player.

- **Attributes**:
  - Speed, acceleration, friction, turn angles, HP
- **Methods**:
  - `update(tx, ty)` - update movement toward target
  - `hitbox()` - returns collision box

### `CarBase`
Base class for all car objects (e.g., player, police), handling shared properties and rendering.

- **Attributes**:
  - Position, angle, velocity, image, dimensions
- **Methods**:
  - `move()`, `draw(...)`

### `Background`
Handles the drawing of the infinite sand map.

- **Method**:
  - `draw(screen, cx, cy)` - draws map centered around the player

### `TireMarkManager`
Keeps track of and displays the tire marks left by the player.

- **Attributes**:
  - `marks` - list of tire mark positions
- **Methods**:
  - `add(x, y)`, `update()`, `draw(...)`

### `NitroFlame`
Handles nitro effects (flame visual) and logic for boosting.

- **Attributes**:
  - `active`, `end`, `fade`, `fade_rate`
- **Methods**:
  - `start()`, `update(...)`, `draw(...)`

### `SoundManager`
Plays and manages all game sounds and music.

- **Attributes**:
  - `channels`, `sounds`, `current_music`
- **Methods**:
  - `play_loop()`, `play_once()`, `music(...)`

### `StatsManager`
Saves and visualizes game statistics.

- **Methods**:
  - `save(dist, t, avg, nitro, police)`
  - `plot()` - generates charts using matplotlib

## 🔁 Game Loop Responsibilities
- Process input
- Move player/police
- Handle collisions
- Update visuals (background, nitro flame, tire marks)
- Track and display stats
- Save end-game data

## 🛠 Technologies
- **Python 3**
- **Pygame**
- **Matplotlib**
- **Pandas**
- **CSV file I/O**
