"""Game constants and asset paths (unchanged filenames)."""

SCREEN_WIDTH = 1500
SCREEN_HEIGHT = 850
FPS = 60

WORLD_WIDTH = 5200
WORLD_HEIGHT = 3600

SAND_COLOR = (238, 217, 182)
DOT_COLOR = (222, 196, 142)
DOT_SPACING = 25
DOT_RADIUS = 2

CAR_W = 37
CAR_H = 67
POLICE_W = 43
POLICE_H = 81
# Collision box for police sprite (visual image has transparent margins).
POLICE_HIT_W = 27
POLICE_HIT_H = 66

PLAYER_IMG = "img/lamborghini.png"
POLICE_IMG = "img/Screenshot_2568-05-11_at_02.04.16-removebg-preview.png"

SPAWN_INTERVAL_MS = 2000
DIFFICULTY_INTERVAL_MS = 30_000
GAMEPLAY_STATS_CSV = "gameplay_stats.csv"
# One row per completed run — used by the dashboard for run-to-run comparisons.
GAME_RUNS_CSV = "game_runs.csv"
GIFT_EVENTS_CSV = "gift_events.csv"
WALLET_CSV = "wallet.csv"

# Shop: cost for two extra nitro tanks (full bars) usable this run only.
NITRO_PACK_COST = 10
NITRO_PACK_TANKS = 2

# Gift-box pickup prizes.
GIFT_MONEY_AMOUNT = 100
GIFT_NITRO_TANKS = 2
# Invincibility: player takes no damage from police/cacti.
GIFT_INVINCIBLE_S = 10.0
# Ram mode: any police the player touches instantly explodes.
GIFT_RAM_S = 10.0

PLAYER_MAX_HP = 100
POLICE_MAX_HP = 40
POLICE_HIT_DAMAGE = 5
HIT_INVULN_FRAMES = 45

# Five difficulty stages that gate the police pursuit.
# Each tuple: (start_time_s, cop_count, speed_mult, accel_mult, hp_mult).
# The last stage stays active indefinitely.
POLICE_STAGES = [
    (0,  1, 1.00, 1.00, 1.00),
    (20, 3, 1.06, 1.06, 1.10),
    (40, 5, 1.12, 1.12, 1.25),
    (60, 7, 1.18, 1.18, 1.45),
    (80, 9, 1.25, 1.25, 1.70),
]


def stage_for(elapsed_s: float) -> tuple:
    """Return the POLICE_STAGES entry whose start_time <= elapsed_s."""
    current = POLICE_STAGES[0]
    for s in POLICE_STAGES:
        if elapsed_s >= s[0]:
            current = s
        else:
            break
    return current


def stage_index(elapsed_s: float) -> int:
    """1-based index of the active stage (1..len(POLICE_STAGES))."""
    idx = 1
    for i, s in enumerate(POLICE_STAGES, start=1):
        if elapsed_s >= s[0]:
            idx = i
        else:
            break
    return idx

# If True, hitbox overlay starts on; press H in-game to toggle.
DEBUG_SHOW_HITBOXES = False
