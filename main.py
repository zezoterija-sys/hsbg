"""Canonical command-line entry point for the HSBG project.

The active experiment CLI lives in ``scripts.run_ai_experiment``.  Keeping the
root entry point as a thin delegate gives the repository one stable command:

    python main.py [experiment options]

Special-purpose data/maintenance tools remain under ``scripts/``.
"""

from scripts.run_ai_experiment import main as run_experiment


def main() -> None:
    """Run the current eight-player MCTS-vs-neural-MCTS experiment CLI."""
    run_experiment()


if __name__ == "__main__":
    main()
