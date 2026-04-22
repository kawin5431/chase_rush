"""Load gameplay_stats.csv and open the proposal dashboard."""

from chase_rush.dashboard import Dashboard

if __name__ == "__main__":
    Dashboard().load_data().plot_charts().show()
