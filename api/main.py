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
from engine.mcts.lane_state import LaneState
from engine.mcts.tree import run_mcts
from engine.mcts.explainer import explain_recommendation

app = FastAPI(
    title="Rift Engine",
    description="League of Legends match simulation engine",
    version="0.1.0",
)


# ─── Request / Response Models ───

# ─── Patch Decoder Models ───

class PatchDecodeRequest(BaseModel):
    url: str | None = None  # Optional: decode specific URL. Omit for latest.

class PatchChangeOut(BaseModel):
    change_type: str
    target_name: str
    ability: str = ""
    description: str = ""
    roles_affected: list[str] = []
    impact_score: float = 0.0

class PatchOut(BaseModel):
    patch_version: str
    url: str = ""
    extracted_at: str = ""
    changes: list[PatchChangeOut] = []

class RoleSummaryOut(BaseModel):
    role: str
    patch: str
    buffs: list[dict] = []
    nerfs: list[dict] = []
    item_changes: list[dict] = []
    system_changes: list[dict] = []
    tldr: str = ""


# ─── MCTS Models ───

class MCTSRequest(BaseModel):
    state: dict  # LaneState as dict
    iterations: int = 1000
    enemy_model: str = "average"  # "average", "optimal", "passive"

class MCTSRecommendation(BaseModel):
    do_this: str
    why: str
    watch_for: str
    plan_changes_if: str
    confidence: str
    next_2_min: str
    position_advice: str
    action_scores: dict = {}

class MCTSPlanRequest(BaseModel):
    state: dict
    steps: int = 6  # How many 20-sec steps to plan (6 = 2 minutes)
    enemy_model: str = "average"
    iterations_per_step: int = 500


# ─── Simulation Models ───

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
    champion_reports: dict[str, list[dict]]


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
        champion_reports=result.champion_reports,
    )


# ─── Patch Decoder Endpoints ───

@app.get("/patches")
async def list_patches():
    """List all decoded patches."""
    try:
        from scrapers.patch_decoder import PatchDecoder
        decoder = PatchDecoder()
        return decoder.get_stored_patches()
    except Exception as e:
        return {"error": str(e)}


@app.get("/patches/{version}")
async def get_patch(version: str):
    """Get all changes for a specific patch."""
    try:
        from scrapers.patch_decoder import PatchDecoder
        decoder = PatchDecoder()
        changes = decoder.get_stored_changes(version)
        return {"patch_version": version, "changes": changes}
    except Exception as e:
        return {"error": str(e)}


@app.get("/patches/{version}/role/{role}")
async def get_patch_by_role(version: str, role: str):
    """Get role-specific patch summary."""
    try:
        from scrapers.patch_decoder import PatchDecoder
        decoder = PatchDecoder()
        return decoder.summarize_by_role(version, role)
    except Exception as e:
        return {"error": str(e)}


@app.post("/patches/decode")
async def decode_patch(request: PatchDecodeRequest = PatchDecodeRequest()):
    """Trigger a patch note decode. Optionally specify a URL."""
    try:
        from scrapers.patch_decoder import PatchDecoder
        decoder = PatchDecoder()
        if request.url:
            result = decoder.decode_url(request.url)
        else:
            result = decoder.decode_latest()
        return {
            "patch_version": result.version,
            "url": result.url,
            "changes_count": len(result.changes),
            "extracted_at": result.extracted_at,
        }
    except Exception as e:
        return {"error": str(e)}


# ─── MCTS Endpoints ───

@app.post("/mcts/recommend", response_model=MCTSRecommendation)
async def mcts_recommend(request: MCTSRequest):
    """
    Get a recommendation for the next 20 seconds.
    Send your current lane state, get back plain-English advice.
    """
    state = LaneState.from_dict(request.state)
    result = run_mcts(
        state,
        iterations=min(request.iterations, 5000),  # Cap at 5000
        enemy_model=request.enemy_model,
    )
    explanation = explain_recommendation(state, result)
    explanation["action_scores"] = result.action_scores
    return MCTSRecommendation(**explanation)


@app.post("/mcts/plan")
async def mcts_plan(request: MCTSPlanRequest):
    """
    Chain multiple 20-second decisions into a multi-step plan.
    Returns a sequence of recommendations.
    """
    from engine.mcts.simulator import simulate_step

    state = LaneState.from_dict(request.state)
    steps = min(request.steps, 18)  # Cap at 6 minutes
    plan = []

    for i in range(steps):
        result = run_mcts(
            state,
            iterations=min(request.iterations_per_step, 2000),
            enemy_model=request.enemy_model,
        )
        explanation = explain_recommendation(state, result)
        explanation["step"] = i + 1
        explanation["game_time"] = state.game_time
        explanation["action_scores"] = result.action_scores
        plan.append(explanation)

        # Advance state by taking the recommended action
        state = simulate_step(state, result.best_action, request.enemy_model)

        # Stop if dead
        if state.my_hp <= 0:
            plan.append({"step": i + 2, "do_this": "You died — respawning", "game_time": state.game_time})
            break

    return {"plan": plan, "total_steps": len(plan)}


# ─── Static files for UI ───
ui_dir = Path(__file__).parent.parent / "ui"
if ui_dir.exists():
    app.mount("/ui", StaticFiles(directory=str(ui_dir)), name="ui")
