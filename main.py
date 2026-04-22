"""Entry point + optional dashboard launcher."""

import sys

import pygame

from chase_rush.dashboard import Dashboard
from chase_rush.game import Game


def main() -> None:
    pygame.init()
    pygame.mixer.init()
    pygame.mixer.set_num_channels(32)
    try:
        Game().run()
    except FileNotFoundError as e:
        print("Missing asset file:", e, file=sys.stderr)
        sys.exit(1)


def show_dashboard() -> None:
    """Open gameplay dashboard manually when needed."""
    dash = Dashboard()
    dash.load_data().plot_charts()
    dash.show()


if __name__ == "__main__":
    main()
