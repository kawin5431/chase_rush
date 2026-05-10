"""Entry point + optional dashboard launcher."""

import sys

import pygame

from chase_rush.game import Game


def main() -> None:
    # Match CD-quality decode paths used by the asset MP3s; a smaller power-of-2
    # buffer cuts input→speaker latency vs SDL_mixer defaults (noticeable on macOS).
    pygame.mixer.pre_init(44100, -16, 2, 256)
    pygame.init()
    pygame.mixer.set_num_channels(32)
    try:
        Game().run()
    except FileNotFoundError as e:
        print("Missing asset file:", e, file=sys.stderr)
        sys.exit(1)


def show_dashboard() -> None:
    """Open gameplay dashboard manually when needed."""
    from chase_rush.dashboard import Dashboard

    dash = Dashboard()
    dash.load_data().plot_charts()
    dash.show()


if __name__ == "__main__":
    main()
