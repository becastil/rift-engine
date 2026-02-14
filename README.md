# Rift Engine

A mechanics-aware League of Legends match simulation engine that recreates realistic matches using historical pro match data.

## What It Does

Given two teams with full 10-champion drafts, Rift Engine simulates a match minute-by-minute and outputs:
- Win probability
- Expected game length
- Gold differential curve over time
- K/D/A distributions
- Objective timeline (dragons, heralds, barons, towers)
- Event timeline with context explanations

## Quick Start

```bash
# 1. Clone and enter the project
cd rift-engine

# 2. Create a virtual environment
python3 -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -e .

# 4. Set up the database
python -m warehouse.schema

# 5. Run a test simulation
python -m engine.simulation

# 6. Start the API server
uvicorn api.main:app --reload
# Then open http://localhost:8000
```

## Project Structure

```
rift-engine/
├── scrapers/          # Data collection from various sources
├── warehouse/         # Database schema + data loading
├── features/          # Derived stats for ML models (v1)
├── models/            # ML model training + inference (v1)
├── engine/            # Core simulation engine
├── api/               # FastAPI web server
├── ui/                # Minimal web UI
├── validation/        # Backtesting + calibration
├── scripts/           # CLI utilities
└── data/              # Local data storage (gitignored)
```

## Data Sources

- **Oracle's Elixir** — Pro match statistics (CSV downloads)
- **CommunityDragon** — Champion/item base stats (JSON API)
- **U.GG** — Meta builds, runes, matchup data (via Firecrawl)
- **Lolalytics** — Win rate curves, item synergies (API)
- **Riot Games API** — Solo queue match timelines

## Build Roadmap

- **MVP** (current): Hand-tuned probability engine with basic simulation loop
- **V1**: LightGBM models trained on real match data
- **V2**: Monte Carlo rollouts with probability distributions

## License

Personal project. Not affiliated with Riot Games.
