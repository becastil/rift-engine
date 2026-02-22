"""
Main simulation loop — the core of Rift Engine.

Takes two teams with a draft and simulates a match minute by minute.
Each minute, it calculates income, checks for fights, objectives, and towers,
and records everything to a timeline.

For MVP, probabilities are hand-tuned. In v1, they'll come from ML models.

Usage:
    python -m engine.simulation
"""

import json
import math
import random
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

from engine.game_state import (
    GameState, TeamState, PlayerState, GamePhase, Role, DragonType
)

# ─── DATABASE HELPERS ───
_ROOT = Path(__file__).parent.parent
_DB_PATHS = [
    _ROOT / "data" / "rift_engine.db",
]

def _get_db_path() -> Path | None:
    """
    Find the first working database file.
    Tries each path and verifies the DB is actually readable
    (some filesystems break SQLite's WAL mode).
    """
    for p in _DB_PATHS:
        if p.exists() and p.stat().st_size > 0:
            # Quick check: can we actually read from it?
            try:
                conn = sqlite3.connect(str(p))
                conn.execute("SELECT 1 FROM champions LIMIT 1")
                conn.close()
                return p
            except Exception:
                continue
    return None


def _load_champion_stats(champion_id: str) -> dict | None:
    """
    Look up a champion's base stats and growth stats from the database.
    Returns a dict with 'base_stats', 'stat_growth', 'resource_type', and 'archetype',
    or None if the champion isn't found.
    """
    db_path = _get_db_path()
    if not db_path:
        return None

    try:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT base_stats, stat_growth, resource_type, archetype "
            "FROM champions WHERE champion_id = ? OR display_name = ?",
            (champion_id, champion_id)
        ).fetchone()
        conn.close()

        if not row:
            return None

        return {
            "base_stats": json.loads(row["base_stats"]),
            "stat_growth": json.loads(row["stat_growth"]),
            "resource_type": row["resource_type"],
            "archetype": row["archetype"],
        }
    except Exception:
        return None


def _load_champion_meta(champion_id: str) -> dict | None:
    """
    Look up a champion's meta data (win rate, matchups) from the database.
    Returns a dict with win_rate, tier, matchups etc., or None.
    """
    db_path = _get_db_path()
    if not db_path:
        return None

    try:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT win_rate, matchups FROM champion_meta WHERE champion_id = ?",
            (champion_id,)
        ).fetchone()
        conn.close()

        if not row:
            return None

        return {
            "win_rate": row["win_rate"],
            "matchups": json.loads(row["matchups"]) if row["matchups"] else {},
        }
    except Exception:
        return None


@dataclass
class GameEvent:
    """One thing that happened in the game."""
    time: float          # seconds into the game
    event_type: str      # "KILL", "TOWER", "DRAGON", "BARON", "ITEM_BUY", etc.
    description: str     # Human-readable explanation
    details: dict = field(default_factory=dict)


@dataclass
class SimulationResult:
    """Everything the simulation produces."""
    winner: str                     # "blue" or "red"
    duration_seconds: float
    blue_win_probability: float
    timeline: list[GameEvent]
    gold_curve: list[dict]          # [{time: 0, blue: 0, red: 0}, ...]
    blue_kda: dict                  # {kills: X, deaths: Y, assists: Z}
    red_kda: dict
    champion_reports: dict[str, list[dict]]


# ─── XP TABLE ───
# Cumulative XP needed to reach each level (approximate)
XP_TO_LEVEL = {
    1: 0, 2: 280, 3: 660, 4: 1140, 5: 1720, 6: 2400,
    7: 3180, 8: 4060, 9: 5040, 10: 6120, 11: 7300,
    12: 8580, 13: 9960, 14: 11440, 15: 13020, 16: 14700,
    17: 16480, 18: 18360,
}

# Gold per CS by role (average)
CS_GOLD = {"top": 20, "mid": 20, "adc": 22, "jungle": 18, "support": 10}
# CS per minute by role (average in pro play)
CS_PER_MIN = {"top": 7.0, "mid": 7.5, "adc": 8.0, "jungle": 5.0, "support": 1.2}
# XP per minute by role
XP_PER_MIN = {"top": 450, "mid": 480, "adc": 400, "jungle": 420, "support": 320}

# Passive gold: 1.9 gold/sec after 1:50 = 114 gold/min
PASSIVE_GOLD_PER_MIN = 114.0


def _gold_advantage_for_side(state: GameState, side: str) -> float:
    """Return this side's gold lead (positive = ahead, negative = behind)."""
    return state.gold_diff() if side == "blue" else -state.gold_diff()


def _comeback_pressure(gold_deficit: float) -> float:
    """
    Scale a gold deficit into a 0-1 comeback pressure signal.
    Bigger deficits produce stronger catch-up mechanics.
    """
    if gold_deficit <= 0:
        return 0.0
    return min(1.0, gold_deficit / 9000.0)


def _grant_team_gold(team: TeamState, total_gold: float):
    """Split a lump sum of gold equally across a team."""
    if total_gold <= 0:
        return
    per_player = total_gold / max(1, len(team.players))
    for p in team.players:
        p.gold += per_player


def _apply_comeback_team_gold(
    state: GameState,
    team: TeamState,
    side: str,
    timeline: list["GameEvent"],
    source: str,
    threshold: float,
    multiplier: float,
    base_bonus: float,
    cap: float,
):
    """
    Grant objective/tower bounty gold to teams that are meaningfully behind.
    """
    deficit = max(0.0, -_gold_advantage_for_side(state, side))
    if deficit < threshold:
        return

    bonus_gold = min(cap, base_bonus + (deficit - threshold) * multiplier)
    bonus_gold = int(max(0, bonus_gold))
    if bonus_gold <= 0:
        return

    _grant_team_gold(team, bonus_gold)
    timeline.append(GameEvent(
        time=state.game_time,
        event_type="COMEBACK_GOLD",
        description=f"{side.upper()} earns +{bonus_gold} comeback gold from {source}",
        details={"team": side, "source": source, "gold": bonus_gold},
    ))


def _skill_reason(role: str, ability: str, phase: GamePhase) -> str:
    """Why this skill point was invested now (human-readable)."""
    if ability == "R":
        return "Prioritized ultimate spike for all-in and objective fight threat."
    if role == "jungle" and ability == "Q":
        return "Leveled main clear/burst tool to speed camps and improve gank damage."
    if role in {"top", "mid", "adc"} and ability == "Q":
        return "Maxed primary trading spell for stronger lane pressure."
    if role == "support" and ability in {"W", "E"}:
        return "Invested in utility to improve peel/engage windows."
    if phase == GamePhase.EARLY:
        return "Added early skirmish value to contest lane priority."
    if phase == GamePhase.MID:
        return "Shifted skill points into teamfight reliability."
    return "Rounded build for late-game reliability and DPS uptime."


def _combo_reason(role: str, context: str) -> str:
    """Abstract combo-style explanation for combat outcomes."""
    if context == "gank":
        return "Used lane angle + CC chain to force a short burst combo before escape tools reset."
    if context == "counter-gank":
        return "Punished overcommit and flipped the play with faster target focus."
    if context == "lane outplay":
        return "Won cooldown trade timing and converted HP advantage into an all-in."
    if context == "lane fight":
        return "Landed a clean trading pattern and finished in the minion/level window."
    if context == "team fight":
        if role == "support":
            return "Committed engage/peel timing around priority carries in the 5v5."
        if role == "adc":
            return "Played front-to-back spacing and converted sustained DPS safely."
        if role == "jungle":
            return "Entered after key cooldowns, then bursted target line with reset tempo."
        return "Found a priority angle in the skirmish and chained damage during CC uptime."
    return "Executed a favorable ability sequence and target selection window."


def _format_skill_order(skill_history: list[str]) -> str:
    return " > ".join(skill_history) if skill_history else "-"


def _macro_default_action(player: PlayerState) -> tuple[str, str]:
    role = player.role.value
    if not player.alive:
        return (
            "Respawning",
            "Death timer window; next spawn is used to plan next setup and objective path."
        )
    if role == "jungle":
        return (
            "Full clear + lane hover",
            "Maintained camp tempo while tracking lane states for next gank path."
        )
    if role == "support":
        return (
            "Vision + escort duty",
            "Controlled river entrances and shadowed carries for counter-engage."
        )
    return (
        "Wave control + farming",
        "Held lane tempo for XP/CS while waiting for a high-value trade window."
    )


def _build_champion_minute_report(
    state: GameState,
    player: PlayerState,
    side: str,
    minute_events: list[GameEvent],
    learned_skills: list[str],
    skill_history: list[str],
) -> dict:
    """Create one minute-by-minute deep-dive row for a single champion."""
    actions: list[str] = []
    reasons: list[str] = []
    tags: list[str] = []

    if learned_skills:
        joined = "/".join(learned_skills)
        actions.append(f"Skilled up {joined}")
        for ability in learned_skills:
            reasons.append(_skill_reason(player.role.value, ability, state.phase))
        tags.append("skill_up")

    for event in minute_events:
        details = event.details or {}
        if event.event_type == "KILL":
            if (
                details.get("killer") == player.champion_id
                and details.get("killer_side") == side
            ):
                context = details.get("context", "fight")
                actions.append(f"Secured kill ({context})")
                reasons.append(_combo_reason(player.role.value, context))
                tags.append("kill")
            elif (
                details.get("victim") == player.champion_id
                and details.get("victim_side") == side
            ):
                context = details.get("context", "fight")
                actions.append(f"Died in {context}")
                reasons.append("Was caught during enemy timing window and lost tempo.")
                tags.append("death")
        elif event.event_type == "FLASH_BURNED":
            if (
                details.get("target") == player.champion_id
                and details.get("target_side") == side
            ):
                actions.append("Burned Flash defensively")
                reasons.append("Traded summoner spell to deny kill conversion.")
                tags.append("flash")
        elif event.event_type in {"DRAGON", "BARON", "TOWER"}:
            if details.get("team") == side and player.alive:
                objective = event.event_type.lower()
                actions.append(f"Rotated for {objective}")
                if objective == "dragon":
                    reasons.append("Played objective tempo for stacking map win conditions.")
                elif objective == "baron":
                    reasons.append("Converted pressure into Baron control to force map collapse.")
                else:
                    reasons.append("Converted lane pressure into structural gold and map space.")
                tags.append(objective)
        elif event.event_type == "COMEBACK_GOLD" and details.get("team") == side:
            actions.append("Collected comeback bounty gold")
            reasons.append("Objective bounty reduced deficit and reopened fight options.")
            tags.append("comeback")
        elif event.event_type == "TEAM_FIGHT":
            if details.get("winner") == side and player.alive:
                actions.append("Won teamfight")
                reasons.append("Execution and target focus were cleaner in the engage window.")
                tags.append("teamfight_win")
            elif details.get("loser") == side and player.alive:
                actions.append("Lost teamfight")
                reasons.append("Fight setup was weaker; conceded tempo and map access.")
                tags.append("teamfight_loss")

    if not actions:
        default_action, default_reason = _macro_default_action(player)
        actions.append(default_action)
        reasons.append(default_reason)

    gold_advantage = _gold_advantage_for_side(state, side)
    if gold_advantage >= 2500:
        reasons.append("Played lead-preserving tempo with safer objective setups.")
    elif gold_advantage <= -2500:
        reasons.append("Stayed on comeback script: lower-risk farm and selective fights.")
    else:
        reasons.append("Game state was close; balanced farm, vision, and skirmish readiness.")

    return {
        "time": state.game_time,
        "minute": int(state.game_time / 60),
        "phase": state.phase.value,
        "action": " | ".join(actions),
        "reasoning": " ".join(reasons),
        "level": player.level,
        "gold": round(player.gold, 1),
        "cs": player.cs,
        "kda": f"{player.kills}/{player.deaths}/{player.assists}",
        "alive": player.alive,
        "combat_power": round(player.combat_power, 1),
        "skill_order": _format_skill_order(skill_history),
        "skill_points": dict(player.skill_points),
        "tags": sorted(set(tags)),
    }


def create_initial_state(
    blue_team_id: str,
    red_team_id: str,
    blue_champions: list[dict],    # [{champion_id, role}, ...]
    red_champions: list[dict],
    patch: str = "26.03",
) -> GameState:
    """
    Build the starting game state from a draft.
    Looks up real champion stats from the database when available.

    Args:
        blue_champions: List of 5 dicts with 'champion_id' and 'role' keys
        red_champions: Same for red side
    """
    def make_players(champs: list[dict]) -> list[PlayerState]:
        players = []
        for c in champs:
            champ_id = c["champion_id"]
            player = PlayerState(
                champion_id=champ_id,
                role=Role(c["role"]),
                player_name=c.get("player_name", champ_id),
            )

            # Try to load real stats from the database
            stats = _load_champion_stats(champ_id)
            if stats:
                player.base_stats = stats["base_stats"]
                player.stat_growth = stats["stat_growth"]
                player.resource_type = stats["resource_type"]

            # Try to load meta info (win rate, matchups)
            meta = _load_champion_meta(champ_id)
            if meta:
                player.meta_win_rate = meta["win_rate"]

            players.append(player)
        return players

    return GameState(
        blue_team=TeamState(team_id=blue_team_id, side="blue", players=make_players(blue_champions)),
        red_team=TeamState(team_id=red_team_id, side="red", players=make_players(red_champions)),
        patch=patch,
    )


def simulate_match(state: GameState, seed: int | None = None) -> SimulationResult:
    """
    Run a full match simulation from the given starting state.
    Returns a SimulationResult with winner, timeline, gold curves, and KDAs.
    """
    if seed is not None:
        random.seed(seed)

    timeline: list[GameEvent] = []
    gold_curve: list[dict] = []
    champion_reports: dict[str, list[dict]] = {}
    player_meta: dict[int, dict] = {}
    skill_history: dict[int, list[str]] = {}

    for team, side in [(state.blue_team, "blue"), (state.red_team, "red")]:
        for player in team.players:
            key = id(player)
            label = f"{side.upper()} {player.champion_id} ({player.role.value})"
            player_meta[key] = {"side": side, "label": label}
            champion_reports[label] = []
            skill_history[key] = []

    # ─── MAIN LOOP: advance 60 seconds at a time ───
    while not state.game_over and state.game_time < 3600:  # 60 min hard cap
        state.game_time += 60
        state.update_phase()
        minute_start_index = len(timeline)
        skill_ups_this_minute: dict[int, list[str]] = {}

        # ─── 1. INCOME ───
        for player in state.all_players():
            if not player.alive:
                # Check respawn
                if state.game_time >= player.respawn_at:
                    player.alive = True
                continue

            role_name = player.role.value

            # Passive gold (everyone gets this)
            player.gold += PASSIVE_GOLD_PER_MIN

            # CS gold (role-dependent)
            cs_this_min = CS_PER_MIN.get(role_name, 6.0)
            gold_per_cs = CS_GOLD.get(role_name, 18)
            player.gold += cs_this_min * gold_per_cs
            player.cs += int(cs_this_min)

            # XP income
            player.xp += XP_PER_MIN.get(role_name, 400)

            # Level up check
            next_level = player.level + 1
            while next_level <= 18 and player.xp >= XP_TO_LEVEL.get(next_level, 999999):
                player.level = next_level
                # Allocate skill point (simplified: follow standard max order)
                learned_ability = _allocate_skill(player)
                player_key = id(player)
                skill_history[player_key].append(learned_ability)
                skill_ups_this_minute.setdefault(player_key, []).append(learned_ability)
                next_level = player.level + 1

        # ─── 2. UPDATE COOLDOWNS ───
        for player in state.all_players():
            player.flash_cd = max(0, player.flash_cd - 60)
            player.tp_cd = max(0, player.tp_cd - 60)

        # ─── 3. UPDATE COMBAT POWER ───
        # Combat power is based on real champion stats at the player's current level,
        # plus a gold factor (gold = items = more stats in a real game).
        # This is a simplified "effective power" — not perfect, but way better than flat numbers.
        for player in state.all_players():
            ad = player.stat_at_level("attackdamage")       # e.g. 60-120
            hp = player.stat_at_level("hp")                 # e.g. 600-2400
            armor = player.stat_at_level("armor")           # e.g. 25-100
            mr = player.stat_at_level("spellblock")         # e.g. 30-60
            atk_speed = player.stat_at_level("attackspeed") # e.g. 0.6-1.2

            # Effective HP = how much damage you can actually take
            # More armor/MR means each HP point is worth more
            effective_hp = hp * (1 + armor / 100) * (1 + mr / 100)

            # Auto-attack DPS = AD * attacks per second
            auto_dps = ad * atk_speed

            # Combat power = mix of tankiness and damage output
            # Normalize so values land in a reasonable range (roughly 100-500 at level 1-18)
            base_power = (effective_hp / 50) + (auto_dps * 3)

            # Gold factor: gold represents items — roughly 1 point per 400 gold
            gold_bonus = player.gold / 400

            player.combat_power = base_power + gold_bonus

        # ─── 4. LANE EVENTS (kills / trades) ───
        if state.phase == GamePhase.EARLY:
            _simulate_lane_phase(state, timeline)
        else:
            _simulate_skirmishes(state, timeline)

        # ─── 5. OBJECTIVE EVENTS ───
        _simulate_objectives(state, timeline)

        # ─── 6. TOWER EVENTS ───
        _simulate_towers(state, timeline)

        # ─── 7. CHECK WIN CONDITION ───
        for team, side in [(state.blue_team, "blue"), (state.red_team, "red")]:
            opponent = state.get_opponent(side)
            if opponent.towers_standing <= 0:
                state.game_over = True
                state.winner = side
                timeline.append(GameEvent(
                    time=state.game_time,
                    event_type="NEXUS",
                    description=f"{side.upper()} team destroys the nexus!",
                    details={"team": side},
                ))
                break

        # Also end game probabilistically in late game based on gold diff
        if state.phase == GamePhase.LATE and not state.game_over:
            _check_late_game_end(state, timeline)

        # ─── 8. RECORD STATE SNAPSHOT ───
        gold_curve.append({
            "time": state.game_time,
            "blue_gold": state.blue_team.total_gold,
            "red_gold": state.red_team.total_gold,
            "gold_diff": state.gold_diff(),
        })

        minute_events = timeline[minute_start_index:]
        for player in state.all_players():
            key = id(player)
            meta = player_meta[key]
            champion_reports[meta["label"]].append(
                _build_champion_minute_report(
                    state=state,
                    player=player,
                    side=meta["side"],
                    minute_events=minute_events,
                    learned_skills=skill_ups_this_minute.get(key, []),
                    skill_history=skill_history[key],
                )
            )

    # ─── CALCULATE RESULTS ───
    if not state.game_over:
        # Hit time limit — whoever is ahead wins
        state.winner = "blue" if state.gold_diff() > 0 else "red"

    # Win probability model:
    # smoother scoring avoids hard-floor clustering when one side snowballs.
    gold_diff = state.gold_diff()
    kill_diff = state.blue_team.total_kills - state.red_team.total_kills
    tower_diff = state.blue_team.towers_standing - state.red_team.towers_standing
    dragon_diff = len(state.blue_team.dragons_taken) - len(state.red_team.dragons_taken)
    winner_bias = 0.16 if state.winner == "blue" else -0.16

    score = (
        (gold_diff / 4500) * 0.60 +
        (kill_diff / 16) * 0.25 +
        (tower_diff / 5) * 0.28 +
        (dragon_diff / 3) * 0.18 +
        winner_bias
    )

    blue_wp = 0.5 + (0.40 * math.tanh(score))
    blue_wp = max(0.08, min(0.92, blue_wp))

    return SimulationResult(
        winner=state.winner,
        duration_seconds=state.game_time,
        blue_win_probability=round(blue_wp, 3),
        timeline=timeline,
        gold_curve=gold_curve,
        blue_kda={
            "kills": state.blue_team.total_kills,
            "deaths": sum(p.deaths for p in state.blue_team.players),
            "assists": sum(p.assists for p in state.blue_team.players),
        },
        red_kda={
            "kills": state.red_team.total_kills,
            "deaths": sum(p.deaths for p in state.red_team.players),
            "assists": sum(p.assists for p in state.red_team.players),
        },
        champion_reports=champion_reports,
    )


def _allocate_skill(player: PlayerState) -> str:
    """Simplified skill allocation: R > Q > W > E for most champs."""
    level = player.level
    sp = player.skill_points

    if level in [6, 11, 16] and sp["R"] < 3:
        sp["R"] += 1
        return "R"
    elif sp["Q"] < 5:
        sp["Q"] += 1
        return "Q"
    elif sp["W"] < 5:
        sp["W"] += 1
        return "W"
    elif sp["E"] < 5:
        sp["E"] += 1
        return "E"
    return "Q"


def _simulate_lane_phase(state: GameState, timeline: list[GameEvent]):
    """Early game: lane-by-lane kill chances."""

    # No solo kills before 2:00 — laning doesn't really start until minions meet
    if state.game_time < 120:
        return

    for role in [Role.TOP, Role.MID, Role.ADC]:
        blue_p = state.blue_team.get_player_by_role(role)
        red_p = state.red_team.get_player_by_role(role)
        if not blue_p or not red_p or not blue_p.alive or not red_p.alive:
            continue

        # Base solo kill probability: ~2% per lane per minute
        # (lower than before — solo kills are actually uncommon in early game)
        kill_prob = 0.02

        # Ramp up slightly as early game progresses (more abilities = more kill threat)
        minutes = state.game_time / 60
        if minutes >= 6:
            kill_prob += 0.01  # level 6 power spike

        # Adjust for combat power difference — but only slightly
        # The stronger player is MORE LIKELY to get the kill, not guaranteed
        power_diff = blue_p.combat_power - red_p.combat_power
        avg_power = (blue_p.combat_power + red_p.combat_power) / 2
        if avg_power > 0:
            # Normalize: a 10% power difference shifts kill odds by ~2%
            kill_prob += (power_diff / avg_power) * 0.02

        # Flash advantage increases kill probability
        if not red_p.is_flash_up() and blue_p.is_flash_up():
            kill_prob += 0.015
        elif not blue_p.is_flash_up() and red_p.is_flash_up():
            kill_prob -= 0.015

        if random.random() < abs(kill_prob):
            # Even the weaker player can get the kill ~30% of the time (outplay)
            if power_diff >= 0:
                outplay = random.random() < 0.25
                if outplay:
                    _apply_kill(state, red_p, blue_p, timeline, "lane outplay")
                else:
                    _apply_kill(state, blue_p, red_p, timeline, "lane fight")
            else:
                outplay = random.random() < 0.25
                if outplay:
                    _apply_kill(state, blue_p, red_p, timeline, "lane outplay")
                else:
                    _apply_kill(state, red_p, blue_p, timeline, "lane fight")

    # Jungle ganks — only after ~3:00 (first jungle clear finishes)
    if state.game_time >= 180:
        _simulate_ganks(state, timeline)


def _simulate_ganks(state: GameState, timeline: list[GameEvent]):
    """Jungler ganks a lane. Only called after 3:00 (first clear)."""
    # Defensive guard in case caller changes in future.
    if state.game_time < 180:
        return

    team_order = [(state.blue_team, "blue"), (state.red_team, "red")]
    random.shuffle(team_order)
    for team, side in team_order:
        jungler = team.get_player_by_role(Role.JUNGLE)
        if not jungler or not jungler.alive:
            continue

        # First-clear ganks are possible, but lower frequency before 5:00.
        minutes = state.game_time / 60
        if minutes < 5:
            gank_prob = 0.06
        elif minutes < 10:
            gank_prob = 0.10
        else:
            gank_prob = 0.12

        if jungler.level < 3 or random.random() > gank_prob:
            continue

        # Pick a lane to gank
        target_role = random.choice([Role.TOP, Role.MID, Role.ADC])
        opponent_team = state.get_opponent(side)
        target = opponent_team.get_player_by_role(target_role)

        if not target or not target.alive:
            continue

        # Gank success rate: ~30% base (ganks fail more often than they succeed)
        success_rate = 0.30
        gold_advantage = _gold_advantage_for_side(state, side)
        if gold_advantage < -1200:
            # Teams behind force riskier, higher-payoff plays.
            success_rate += 0.05
        elif gold_advantage > 2500:
            success_rate -= 0.03

        if not target.is_flash_up():
            success_rate += 0.20  # no flash = much easier gank
        success_rate = max(0.20, min(0.55, success_rate))

        if random.random() < success_rate:
            # Sometimes the gank backfires — the laner kills the jungler instead (~15%)
            counter_kill = random.random() < 0.15
            if counter_kill:
                _apply_kill(state, target, jungler, timeline, "counter-gank")
            else:
                _apply_kill(state, jungler, target, timeline, "gank")
        elif random.random() < 0.3:
            target.flash_cd = 300  # burned flash but survived
            timeline.append(GameEvent(
                time=state.game_time,
                event_type="FLASH_BURNED",
                description=f"{target.player_name} ({target.champion_id}) burns Flash to escape {side} gank",
                details={
                    "target": target.champion_id,
                    "target_side": opponent_team.side,
                    "target_role": target.role.value,
                    "gank_side": side,
                },
            ))


def _simulate_skirmishes(state: GameState, timeline: list[GameEvent]):
    """Mid/late game: team fights and skirmishes."""
    # Team fight probability increases through game phases
    fight_prob = 0.08 if state.phase == GamePhase.MID else 0.12

    if random.random() < fight_prob:
        # Calculate total team combat power
        blue_power = sum(p.combat_power for p in state.blue_team.players if p.alive)
        red_power = sum(p.combat_power for p in state.red_team.players if p.alive)

        total = blue_power + red_power
        if total == 0:
            return

        # Execution variance and catch-up pressure create swings in mid/late game.
        gold_deficit = abs(state.gold_diff())
        pressure = _comeback_pressure(gold_deficit)
        execution_swing = random.gauss(0, total * (0.15 + (pressure * 0.08)))
        blue_effective = blue_power + execution_swing

        # If one side is far behind in gold, give them a small upset boost.
        comeback_shift = total * (0.06 * pressure)
        if state.gold_diff() > 0:      # blue ahead, red behind
            blue_effective -= comeback_shift
        elif state.gold_diff() < 0:    # red ahead, blue behind
            blue_effective += comeback_shift

        blue_win_chance = max(0.25, min(0.75, blue_effective / total))
        blue_wins = random.random() < blue_win_chance

        winner_team = state.blue_team if blue_wins else state.red_team
        loser_team = state.red_team if blue_wins else state.blue_team

        # Determine casualties — close fights have more even kill counts
        power_ratio = max(blue_power, red_power) / total if total > 0 else 0.5
        is_stomp = power_ratio > 0.58  # one team is significantly stronger

        if is_stomp:
            loser_deaths = random.randint(2, min(4, loser_team.alive_count))
            winner_deaths = 1 if random.random() < 0.3 else 0
        else:
            # Close fight — both sides lose people
            loser_deaths = random.randint(1, min(3, loser_team.alive_count))
            winner_deaths = random.randint(1, 2) if random.random() < 0.6 else 0

        # Apply kills on losing side
        alive_losers = [p for p in loser_team.players if p.alive]
        random.shuffle(alive_losers)
        for i in range(min(loser_deaths, len(alive_losers))):
            alive_winners = [p for p in winner_team.players if p.alive]
            if alive_winners:
                killer = random.choice(alive_winners)
                _apply_kill(state, killer, alive_losers[i], timeline, "team fight")

        # Apply kills on winning side (if any)
        for _ in range(winner_deaths):
            alive_winners = [p for p in winner_team.players if p.alive]
            alive_losers_remaining = [p for p in loser_team.players if p.alive]
            if alive_winners and alive_losers_remaining:
                victim = random.choice(alive_winners)
                killer = random.choice(alive_losers_remaining)
                _apply_kill(state, killer, victim, timeline, "team fight")

        side = "Blue" if blue_wins else "Red"
        timeline.append(GameEvent(
            time=state.game_time,
            event_type="TEAM_FIGHT",
            description=f"{side} wins team fight ({loser_deaths} kills to {winner_deaths})",
            details={
                "winner": "blue" if blue_wins else "red",
                "loser": "red" if blue_wins else "blue",
                "loser_deaths": loser_deaths,
                "winner_deaths": winner_deaths,
            },
        ))


def _simulate_objectives(state: GameState, timeline: list[GameEvent]):
    """Dragon, Herald, Baron logic."""

    # ─── DRAGON ───
    if state.game_time >= 300 and state.next_dragon_spawn <= 0:
        # Which team tries to take it?
        team_order = [(state.blue_team, "blue"), (state.red_team, "red")]
        random.shuffle(team_order)
        for team, side in team_order:
            dragon_prob = 0.20
            gold_advantage = _gold_advantage_for_side(state, side)
            if gold_advantage < -1500:
                dragon_prob += 0.06
            elif gold_advantage > 3000:
                dragon_prob -= 0.04

            if team.alive_count >= 3 and random.random() < dragon_prob:
                dragon_type = random.choice(list(DragonType)[:6])  # not elder
                team.dragons_taken.append(dragon_type)
                state.next_dragon_spawn = 300  # 5 min respawn
                state.dragons_spawned += 1

                # Check for soul
                if len(team.dragons_taken) >= state.soul_point:
                    team.dragon_soul = team.dragons_taken[-1]

                timeline.append(GameEvent(
                    time=state.game_time,
                    event_type="DRAGON",
                    description=f"{side.upper()} takes {dragon_type.value} dragon (#{len(team.dragons_taken)})",
                    details={"dragon_type": dragon_type.value, "team": side},
                ))
                _apply_comeback_team_gold(
                    state=state,
                    team=team,
                    side=side,
                    timeline=timeline,
                    source="dragon",
                    threshold=1600,
                    multiplier=0.05,
                    base_bonus=120,
                    cap=500,
                )
                break

    state.next_dragon_spawn = max(0, state.next_dragon_spawn - 60)

    # ─── BARON ───
    if state.game_time >= 1200 and state.next_baron_spawn <= 0:
        team_order = [(state.blue_team, "blue"), (state.red_team, "red")]
        random.shuffle(team_order)
        for team, side in team_order:
            opponent = state.get_opponent(side)
            # More likely to take baron if opponent has dead players
            baron_prob = 0.08 + (5 - opponent.alive_count) * 0.04
            gold_advantage = _gold_advantage_for_side(state, side)
            if gold_advantage < -2000:
                baron_prob += 0.03
            elif gold_advantage > 5000:
                baron_prob -= 0.02

            if team.alive_count >= 4 and random.random() < baron_prob:
                team.barons_taken += 1
                team.baron_buff_active = True
                team.baron_buff_expires = state.game_time + 180  # 3 min buff
                state.next_baron_spawn = 360  # 6 min respawn

                timeline.append(GameEvent(
                    time=state.game_time,
                    event_type="BARON",
                    description=f"{side.upper()} secures Baron Nashor!",
                    details={"team": side},
                ))
                _apply_comeback_team_gold(
                    state=state,
                    team=team,
                    side=side,
                    timeline=timeline,
                    source="baron",
                    threshold=2200,
                    multiplier=0.08,
                    base_bonus=180,
                    cap=800,
                )
                break

    state.next_baron_spawn = max(0, state.next_baron_spawn - 60)

    # Check baron buff expiry
    for team in [state.blue_team, state.red_team]:
        if team.baron_buff_active and state.game_time >= team.baron_buff_expires:
            team.baron_buff_active = False


def _simulate_towers(state: GameState, timeline: list[GameEvent]):
    """Tower destruction logic."""

    # Towers don't fall before ~8 minutes in real games (plates + tower HP)
    if state.game_time < 480:
        return

    team_order = [(state.blue_team, "blue"), (state.red_team, "red")]
    random.shuffle(team_order)
    for team, side in team_order:
        opponent = state.get_opponent(side)
        if opponent.towers_standing <= 0:
            continue

        # Base tower fall probability depends on game phase
        # Reduced early game rate — first tower usually falls around 10-14 min
        tower_prob = {
            GamePhase.EARLY: 0.02,
            GamePhase.MID: 0.06,
            GamePhase.LATE: 0.10,
        }[state.phase]

        # Baron buff massively increases tower threat
        if team.baron_buff_active:
            tower_prob *= 2.5

        # Gold lead increases tower pressure
        gold_advantage = _gold_advantage_for_side(state, side)
        if gold_advantage > 2000:
            tower_prob += 0.02
        elif gold_advantage < -1800:
            # Trailing teams can still find map trades.
            tower_prob += 0.01

        if random.random() < tower_prob:
            opponent.towers_standing -= 1
            team_gold_share = 250 + 100  # local + global gold
            for p in team.players:
                p.gold += team_gold_share / 5
            _apply_comeback_team_gold(
                state=state,
                team=team,
                side=side,
                timeline=timeline,
                source="tower",
                threshold=1400,
                multiplier=0.04,
                base_bonus=90,
                cap=350,
            )

            timeline.append(GameEvent(
                time=state.game_time,
                event_type="TOWER",
                description=f"{side.upper()} destroys a tower ({opponent.towers_standing} remaining)",
                details={"team": side, "remaining": opponent.towers_standing},
            ))


def _check_late_game_end(state: GameState, timeline: list[GameEvent]):
    """In late game, large advantages can end the game faster."""
    gold_diff = abs(state.gold_diff())
    leading_side = "blue" if state.gold_diff() > 0 else "red"
    leader = state.get_team(leading_side)
    loser = state.get_opponent(leading_side)

    # If one team has a massive lead and baron buff, game likely ends
    end_prob = 0.0
    if gold_diff > 12000:
        end_prob += 0.08
    if leader.baron_buff_active:
        end_prob += 0.10
    if loser.towers_standing <= 2:
        end_prob += 0.08
    if leader.dragon_soul is not None:
        end_prob += 0.04

    if random.random() < end_prob:
        state.game_over = True
        state.winner = leading_side
        timeline.append(GameEvent(
            time=state.game_time,
            event_type="NEXUS",
            description=f"{leading_side.upper()} team closes out the game!",
            details={"team": leading_side},
        ))


def _apply_kill(state: GameState, killer: PlayerState, victim: PlayerState,
                timeline: list[GameEvent], context: str):
    """
    Process a kill: gold, death timer, KDA updates.
    Includes shutdown bounties — killing a fed player gives extra gold,
    which is League's main comeback mechanic.
    """
    killer.kills += 1
    victim.deaths += 1
    victim.alive = False

    killer_team = None
    for team in [state.blue_team, state.red_team]:
        if killer in team.players:
            killer_team = team
            break

    victim_team = None
    if killer_team:
        victim_team = state.get_opponent(killer_team.side)

    # Death timer scales with level (Riot's actual formula is close to this)
    death_timer = 6 + (victim.level * 2)
    if state.phase == GamePhase.LATE:
        death_timer *= 1.5
    victim.respawn_at = state.game_time + death_timer

    # ── BOUNTY SYSTEM (League's comeback mechanic) ──
    # Base kill gold
    base_gold = 300

    # Shutdown bounty: if the VICTIM has a kill streak, the killer gets bonus gold
    # This is how losing teams catch up — they get rewarded for killing fed players
    victim_streak = victim.kills - victim.deaths  # net "fed-ness"
    shutdown_bonus = 0
    if victim_streak >= 2:
        shutdown_bonus = 150 * min(victim_streak - 1, 5)  # 150-750 bonus gold

    # Consecutive death penalty: if the victim has died a lot without kills,
    # they're worth LESS gold (prevents farming a weak player)
    if victim.deaths > victim.kills + 3:
        base_gold = max(100, base_gold - 50 * (victim.deaths - victim.kills - 3))

    # Catch-up bonus: teams that are behind get extra kill rewards.
    comeback_bonus = 0
    gold_deficit = 0.0
    if killer_team and victim_team:
        gold_deficit = max(0.0, victim_team.total_gold - killer_team.total_gold)
        if gold_deficit >= 1200:
            comeback_bonus = min(250, int(40 + (gold_deficit - 1200) * 0.03))

    bounty = base_gold + shutdown_bonus + comeback_bonus
    killer.gold += bounty

    # Assist gold to nearby allies (simplified)
    if killer_team:
        assist_gold = 100
        if gold_deficit >= 2000:
            assist_gold = 115
        for p in killer_team.players:
            if p != killer and p.alive:
                p.assists += 1
                p.gold += assist_gold

    # ── CATCH-UP XP ──
    # In real League, killing a higher-level player gives bonus XP
    if victim.level > killer.level:
        xp_bonus = (victim.level - killer.level) * 60
        killer.xp += xp_bonus

    shutdown_text = f" [SHUTDOWN +{shutdown_bonus}g]" if shutdown_bonus > 0 else ""
    comeback_text = f" [COMEBACK +{comeback_bonus}g]" if comeback_bonus > 0 else ""
    timeline.append(GameEvent(
        time=state.game_time,
        event_type="KILL",
        description=f"{killer.player_name} ({killer.champion_id}) kills {victim.player_name} ({victim.champion_id}) [{context}]{shutdown_text}{comeback_text}",
        details={
            "killer": killer.champion_id,
            "killer_side": killer_team.side if killer_team else "",
            "killer_role": killer.role.value,
            "victim": victim.champion_id,
            "victim_side": victim_team.side if victim_team else "",
            "victim_role": victim.role.value,
            "context": context,
            "gold_earned": bounty,
            "shutdown_bonus": shutdown_bonus,
            "comeback_bonus": comeback_bonus,
        },
    ))


# ─── CLI Entry Point ───
def main():
    """Run a quick test simulation."""
    print("=== RIFT ENGINE — Test Simulation ===\n")

    # Example draft
    blue_champs = [
        {"champion_id": "Renekton", "role": "top"},
        {"champion_id": "LeeSin", "role": "jungle"},
        {"champion_id": "Ahri", "role": "mid"},
        {"champion_id": "Jinx", "role": "adc"},
        {"champion_id": "Thresh", "role": "support"},
    ]
    red_champs = [
        {"champion_id": "Gnar", "role": "top"},
        {"champion_id": "Viego", "role": "jungle"},
        {"champion_id": "Syndra", "role": "mid"},
        {"champion_id": "Kaisa", "role": "adc"},
        {"champion_id": "Nautilus", "role": "support"},
    ]

    state = create_initial_state("T1", "GenG", blue_champs, red_champs)
    result = simulate_match(state, seed=42)

    print(f"Winner: {result.winner.upper()}")
    print(f"Game Length: {result.duration_seconds / 60:.1f} minutes")
    print(f"Blue Win Probability: {result.blue_win_probability:.1%}")
    print(f"\nBlue KDA: {result.blue_kda}")
    print(f"Red KDA: {result.red_kda}")

    print(f"\n--- Timeline ({len(result.timeline)} events) ---")
    for event in result.timeline[:20]:  # Show first 20 events
        minutes = event.time / 60
        print(f"  [{minutes:5.1f}m] {event.event_type:12s} | {event.description}")

    if len(result.timeline) > 20:
        print(f"  ... and {len(result.timeline) - 20} more events")

    print(f"\n--- Gold Curve (every 5 min) ---")
    for snapshot in result.gold_curve:
        if snapshot["time"] % 300 == 0:  # every 5 minutes
            minutes = snapshot["time"] / 60
            diff = snapshot["gold_diff"]
            bar = "=" * int(abs(diff) / 500)
            side = "BLUE+" if diff > 0 else "RED+"
            print(f"  {minutes:5.1f}m | {side}{abs(diff):,.0f}g {'>' if diff > 0 else '<'}{bar}")


if __name__ == "__main__":
    main()
