"""
Rift Engine API — FastAPI server that runs simulations on demand.

Start the server:
    uvicorn api.main:app --reload

Then open http://localhost:8000/docs to see the interactive API docs.
"""

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from pathlib import Path

from engine.simulation import create_initial_state, simulate_match

app = FastAPI(
    title="Rift Engine",
    description="League of Legends match simulation engine",
    version="0.1.0",
)


# ─── Request / Response Models ───

class ChampionPick(BaseModel):
    champion_id: str    # e.g. "Jinx"
    role: str           # "top", "jungle", "mid", "adc", "support"
    player_name: str = ""

class SimulationRequest(BaseModel):
    blue_team_id: str = "Blue"
    red_team_id: str = "Red"
    blue_draft: list[ChampionPick]    # 5 picks
    red_draft: list[ChampionPick]     # 5 picks
    patch: str = "15.3"
    seed: int | None = None           # optional: for reproducible results

class EventOut(BaseModel):
    time: float
    event_type: str
    description: str

class SimulationResponse(BaseModel):
    winner: str
    duration_minutes: float
    blue_win_probability: float
    blue_kda: dict
    red_kda: dict
    gold_curve: list[dict]
    timeline: list[EventOut]


# ─── Endpoints ───

@app.get("/")
async def root():
    """Serve the UI page."""
    ui_path = Path(__file__).parent.parent / "ui" / "index.html"
    if ui_path.exists():
        return FileResponse(ui_path)
    return {"message": "Rift Engine API is running. Visit /docs for the API explorer."}


@app.get("/health")
async def health():
    return {"status": "ok", "version": "0.1.0"}


@app.post("/simulate", response_model=SimulationResponse)
async def run_simulation(request: SimulationRequest):
    """
    Run a match simulation.

    Send two teams with 5 champion picks each (champion_id + role).
    Returns the full simulation result: winner, gold curves, timeline, KDAs.
    """
    # Convert request to engine format
    blue_champs = [
        {"champion_id": p.champion_id, "role": p.role, "player_name": p.player_name or p.champion_id}
        for p in request.blue_draft
    ]
    red_champs = [
        {"champion_id": p.champion_id, "role": p.role, "player_name": p.player_name or p.champion_id}
        for p in request.red_draft
    ]

    # Create initial state and run simulation
    state = create_initial_state(
        request.blue_team_id, request.red_team_id,
        blue_champs, red_champs,
        patch=request.patch,
    )
    result = simulate_match(state, seed=request.seed)

    # Format response
    return SimulationResponse(
        winner=result.winner,
        duration_minutes=round(result.duration_seconds / 60, 1),
        blue_win_probability=result.blue_win_probability,
        blue_kda=result.blue_kda,
        red_kda=result.red_kda,
        gold_curve=result.gold_curve,
        timeline=[
            EventOut(time=e.time, event_type=e.event_type, description=e.description)
            for e in result.timeline
        ],
    )
