"""
Main simulation loop — the core of Rift Engine.

Takes two teams with a draft and simulates a match minute by minute.
Each minute, it calculates income, checks for fights, objectives, and towers,
and records everything to a timeline.

For MVP, probabilities are hand-tuned. In v1, they'll come from ML models.

Usage:
    python -m engine.simulation
"""

import random
from dataclasses import dataclass, field

from engine.game_state import (
    GameState, TeamState, PlayerState, GamePhase, Role, DragonType
)


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


def create_initial_state(
    blue_team_id: str,
    red_team_id: str,
    blue_champions: list[dict],    # [{champion_id, role}, ...]
    red_champions: list[dict],
    patch: str = "15.3",
) -> GameState:
    """
    Build the starting game state from a draft.

    Args:
        blue_champions: List of 5 dicts with 'champion_id' and 'role' keys
        red_champions: Same for red side
    """
    def make_players(champs: list[dict]) -> list[PlayerState]:
        return [
            PlayerState(
                champion_id=c["champion_id"],
                role=Role(c["role"]),
                player_name=c.get("player_name", c["champion_id"]),
            )
            for c in champs
        ]

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

    # ─── MAIN LOOP: advance 60 seconds at a time ───
    while not state.game_over and state.game_time < 3600:  # 60 min hard cap
        state.game_time += 60
        state.update_phase()

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
            if next_level <= 18 and player.xp >= XP_TO_LEVEL.get(next_level, 999999):
                player.level = next_level
                # Allocate skill point (simplified: follow standard max order)
                _allocate_skill(player)

        # ─── 2. UPDATE COOLDOWNS ───
        for player in state.all_players():
            player.flash_cd = max(0, player.flash_cd - 60)
            player.tp_cd = max(0, player.tp_cd - 60)

        # ─── 3. UPDATE COMBAT POWER ───
        for player in state.all_players():
            # Simple formula: base power scales with level and gold
            player.combat_power = 80 + (player.level * 12) + (player.gold / 200)

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

    # ─── CALCULATE RESULTS ───
    if not state.game_over:
        # Hit time limit — whoever is ahead wins
        state.winner = "blue" if state.gold_diff() > 0 else "red"

    # Simple win probability: based on how dominant the win was
    gold_lead = abs(state.gold_diff())
    dominance = min(gold_lead / 15000, 0.35)  # cap at 85/15
    if state.winner == "blue":
        blue_wp = 0.50 + dominance
    else:
        blue_wp = 0.50 - dominance

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
    )


def _allocate_skill(player: PlayerState):
    """Simplified skill allocation: R > Q > W > E for most champs."""
    level = player.level
    sp = player.skill_points

    if level in [6, 11, 16] and sp["R"] < 3:
        sp["R"] += 1
    elif sp["Q"] < 5:
        sp["Q"] += 1
    elif sp["W"] < 5:
        sp["W"] += 1
    elif sp["E"] < 5:
        sp["E"] += 1


def _simulate_lane_phase(state: GameState, timeline: list[GameEvent]):
    """Early game: lane-by-lane kill chances."""
    for role in [Role.TOP, Role.MID, Role.ADC]:
        blue_p = state.blue_team.get_player_by_role(role)
        red_p = state.red_team.get_player_by_role(role)
        if not blue_p or not red_p or not blue_p.alive or not red_p.alive:
            continue

        # Base kill probability: ~3% per lane per minute in early game
        kill_prob = 0.03

        # Adjust for combat power difference
        power_diff = blue_p.combat_power - red_p.combat_power
        kill_prob += power_diff / 5000  # slight skew toward stronger player

        # Flash advantage increases kill probability
        if not red_p.is_flash_up() and blue_p.is_flash_up():
            kill_prob += 0.02
        elif not blue_p.is_flash_up() and red_p.is_flash_up():
            kill_prob -= 0.02

        if random.random() < abs(kill_prob):
            if power_diff >= 0:
                _apply_kill(state, blue_p, red_p, timeline, "lane fight")
            else:
                _apply_kill(state, red_p, blue_p, timeline, "lane fight")

    # Jungle ganks
    _simulate_ganks(state, timeline)


def _simulate_ganks(state: GameState, timeline: list[GameEvent]):
    """Jungler ganks a lane."""
    for team, side in [(state.blue_team, "blue"), (state.red_team, "red")]:
        jungler = team.get_player_by_role(Role.JUNGLE)
        if not jungler or not jungler.alive:
            continue

        # ~15% chance the jungler ganks each minute
        if random.random() > 0.15:
            continue

        # Pick a lane to gank
        target_role = random.choice([Role.TOP, Role.MID, Role.ADC])
        opponent_team = state.get_opponent(side)
        target = opponent_team.get_player_by_role(target_role)

        if not target or not target.alive:
            continue

        # Gank success rate: ~40% base, modified by flash
        success_rate = 0.40
        if not target.is_flash_up():
            success_rate += 0.20  # no flash = much easier gank

        if random.random() < success_rate:
            _apply_kill(state, jungler, target, timeline, "gank")
            # Flash blown even on survived ganks sometimes
        elif random.random() < 0.3:
            target.flash_cd = 300  # burned flash but survived
            timeline.append(GameEvent(
                time=state.game_time,
                event_type="FLASH_BURNED",
                description=f"{target.player_name} ({target.champion_id}) burns Flash to escape {side} gank",
            ))


def _simulate_skirmishes(state: GameState, timeline: list[GameEvent]):
    """Mid/late game: team fights and skirmishes."""
    # Team fight probability increases through game phases
    fight_prob = 0.08 if state.phase == GamePhase.MID else 0.15

    if random.random() < fight_prob:
        # Calculate total team combat power
        blue_power = sum(p.combat_power for p in state.blue_team.players if p.alive)
        red_power = sum(p.combat_power for p in state.red_team.players if p.alive)

        total = blue_power + red_power
        if total == 0:
            return

        blue_win_chance = blue_power / total
        blue_wins = random.random() < blue_win_chance

        winner_team = state.blue_team if blue_wins else state.red_team
        loser_team = state.red_team if blue_wins else state.blue_team

        # Determine casualties (1-3 kills on losing side, 0-1 on winning side)
        loser_deaths = random.randint(1, min(3, loser_team.alive_count))
        winner_deaths = random.randint(0, 1) if random.random() < 0.4 else 0

        # Apply kills on losing side
        alive_losers = [p for p in loser_team.players if p.alive]
        random.shuffle(alive_losers)
        for i in range(min(loser_deaths, len(alive_losers))):
            killer = random.choice([p for p in winner_team.players if p.alive])
            _apply_kill(state, killer, alive_losers[i], timeline, "team fight")

        # Apply kills on winning side (if any)
        if winner_deaths > 0:
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
        ))


def _simulate_objectives(state: GameState, timeline: list[GameEvent]):
    """Dragon, Herald, Baron logic."""

    # ─── DRAGON ───
    if state.game_time >= 300 and state.next_dragon_spawn <= 0:
        # Which team tries to take it?
        for team, side in [(state.blue_team, "blue"), (state.red_team, "red")]:
            if team.alive_count >= 3 and random.random() < 0.20:
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
                break

    state.next_dragon_spawn = max(0, state.next_dragon_spawn - 60)

    # ─── BARON ───
    if state.game_time >= 1200 and state.next_baron_spawn <= 0:
        for team, side in [(state.blue_team, "blue"), (state.red_team, "red")]:
            opponent = state.get_opponent(side)
            # More likely to take baron if opponent has dead players
            baron_prob = 0.08 + (5 - opponent.alive_count) * 0.04
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
                break

    state.next_baron_spawn = max(0, state.next_baron_spawn - 60)

    # Check baron buff expiry
    for team in [state.blue_team, state.red_team]:
        if team.baron_buff_active and state.game_time >= team.baron_buff_expires:
            team.baron_buff_active = False


def _simulate_towers(state: GameState, timeline: list[GameEvent]):
    """Tower destruction logic."""
    for team, side in [(state.blue_team, "blue"), (state.red_team, "red")]:
        opponent = state.get_opponent(side)
        if opponent.towers_standing <= 0:
            continue

        # Base tower fall probability depends on game phase
        tower_prob = {
            GamePhase.EARLY: 0.03,
            GamePhase.MID: 0.08,
            GamePhase.LATE: 0.12,
        }[state.phase]

        # Baron buff massively increases tower threat
        if team.baron_buff_active:
            tower_prob *= 2.5

        # Gold lead increases tower pressure
        gold_diff = state.gold_diff()
        if side == "blue" and gold_diff > 2000:
            tower_prob += 0.03
        elif side == "red" and gold_diff < -2000:
            tower_prob += 0.03

        if random.random() < tower_prob:
            opponent.towers_standing -= 1
            team_gold_share = 250 + 100  # local + global gold
            for p in team.players:
                p.gold += team_gold_share / 5

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
    if gold_diff > 10000:
        end_prob += 0.10
    if leader.baron_buff_active:
        end_prob += 0.15
    if loser.towers_standing <= 3:
        end_prob += 0.10
    if leader.dragon_soul is not None:
        end_prob += 0.05

    if random.random() < end_prob:
        state.game_over = True
        state.winner = leading_side
        timeline.append(GameEvent(
            time=state.game_time,
            event_type="NEXUS",
            description=f"{leading_side.upper()} team closes out the game!",
        ))


def _apply_kill(state: GameState, killer: PlayerState, victim: PlayerState,
                timeline: list[GameEvent], context: str):
    """Process a kill: gold, death timer, KDA updates."""
    killer.kills += 1
    victim.deaths += 1
    victim.alive = False

    # Death timer scales with level
    death_timer = 10 + (victim.level * 2.5)
    if state.phase == GamePhase.LATE:
        death_timer *= 1.5
    victim.respawn_at = state.game_time + death_timer

    # Kill gold (300 base + bounty)
    bounty = 300
    if killer.kills >= 3:
        bounty += (killer.kills - 2) * 100  # simplified bounty
    killer.gold += bounty

    # Assist gold to nearby allies (simplified: everyone on team gets some)
    killer_team = None
    for team in [state.blue_team, state.red_team]:
        if killer in team.players:
            killer_team = team
            break

    if killer_team:
        for p in killer_team.players:
            if p != killer and p.alive:
                p.assists += 1
                p.gold += 150  # assist gold

    timeline.append(GameEvent(
        time=state.game_time,
        event_type="KILL",
        description=f"{killer.player_name} ({killer.champion_id}) kills {victim.player_name} ({victim.champion_id}) [{context}]",
        details={
            "killer": killer.champion_id,
            "victim": victim.champion_id,
            "context": context,
            "gold_earned": bounty,
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
