"""
CLI tool to run a single simulation.
Usage: python -m scripts.run_simulation
"""

from engine.simulation import create_initial_state, simulate_match, main

if __name__ == "__main__":
    main()
