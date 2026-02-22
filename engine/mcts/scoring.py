"""
Scoring Function — how the MCTS judges whether a 20-second outcome was good or bad.

Think of it like a report card for each simulated play:
  +points for good stuff (got gold, gained XP, good wave position)
  -points for bad stuff (died, lost CS, burned flash, bad wave position)

The total score tells the MCTS engine "this action led to a good outcome."
"""

from engine.mcts.lane_state import LaneState, Position, WavePosition


def score_state(before: LaneState, after: LaneState) -> float:
    """
    Score the transition from 'before' to 'after' state.
    Positive = good for you. Negative = bad for you.
    
    Returns a float roughly in the range [-100, +100].
    """
    score = 0.0

    # ── SURVIVAL (most important) ──
    # Dying is the worst thing that can happen. Massive penalty.
    if after.my_hp <= 0:
        score -= 80.0
        # Extra penalty if you had flash up (wasted escape tool)
        if before.has_flash:
            score -= 10.0
        return score  # Dead = done, no other scoring matters

    # ── GOLD GAINED ──
    # Every 100 gold gained is worth ~5 points
    gold_diff = after.my_gold - before.my_gold
    score += gold_diff * 0.05

    # Kill gold is extra valuable (means enemy is also dead = tempo)
    if after.enemy_hp <= 0 and before.enemy_hp > 0:
        score += 25.0  # Kill bonus on top of gold

    # ── XP / LEVEL ──
    level_diff = after.my_level - before.my_level
    if level_diff > 0:
        score += 8.0 * level_diff  # Level up is very valuable

    # ── HP TRADING ──
    # If you traded HP, was it worth it?
    my_hp_lost_pct = (before.my_hp - after.my_hp) / before.my_hp_max * 100
    enemy_hp_lost_pct = (before.enemy_hp - after.enemy_hp) / before.enemy_hp_max * 100

    # Good trade: enemy lost more HP% than you
    trade_diff = enemy_hp_lost_pct - my_hp_lost_pct
    score += trade_diff * 0.3

    # ── SUMMONER SPELLS ──
    # Burning flash is bad (-15) unless you got a kill
    if before.has_flash and not after.has_flash:
        if after.enemy_hp <= 0:
            score -= 3.0   # Flash for kill = acceptable
        else:
            score -= 15.0  # Flash for nothing = terrible

    # Enemy burning flash is good for us
    if before.enemy_flash_cd_est <= 0 and after.enemy_flash_cd_est > 0:
        score += 12.0

    # ── WAVE POSITION ──
    # Good positions: frozen near you, or crashed (roam/recall window)
    wave_scores = {
        WavePosition.FROZEN_NEAR_ME: 5.0,       # Best — safe CS, enemy overextends
        WavePosition.PUSHING_TO_ME: 2.0,         # Decent — wave coming to safe spot
        WavePosition.MIDDLE: 0.0,                # Neutral
        WavePosition.SLOW_PUSH_TO_THEM: 1.0,     # Setting up a crash = good
        WavePosition.CRASHED: 3.0,               # Crash = recall/roam window
    }
    wave_before = wave_scores.get(before.wave_position, 0)
    wave_after = wave_scores.get(after.wave_position, 0)
    score += (wave_after - wave_before) * 2.0

    # ── CS DIFFERENCE ──
    # More of your minions dying (fewer enemy minions) means you're getting CS
    cs_gained_est = max(0, before.enemy_minions - after.enemy_minions)
    score += cs_gained_est * 1.5

    # ── POSITION SAFETY ──
    pos_safety = {
        Position.UNDER_TOWER: 3.0,
        Position.SAFE: 2.0,
        Position.MIDDLE: 0.0,
        Position.EXTENDED: -3.0,
        Position.RIVER: -2.0,
    }
    # Only penalize being extended if gank risk is high
    if after.gank_risk > 0.4 and after.my_position in (Position.EXTENDED, Position.RIVER):
        score -= 8.0 * after.gank_risk

    # ── MANA MANAGEMENT ──
    # Running out of mana is bad
    if after.my_mana_pct < 15 and before.my_mana_pct >= 15:
        score -= 5.0  # Went OOM

    # ── TOWER DAMAGE ──
    # Dealing tower damage is great (permanent advantage)
    tower_dmg = before.enemy_tower_hp - after.enemy_tower_hp
    if tower_dmg > 0:
        score += tower_dmg * 0.5

    return score


def quick_evaluate(state: LaneState) -> float:
    """
    Quick static evaluation of a state (no before/after comparison).
    Used for leaf-node evaluation in MCTS when we don't want to simulate further.
    
    Returns rough score: positive = good position, negative = bad.
    """
    score = 0.0

    # HP advantage
    hp_ratio = state.my_hp_pct - state.enemy_hp_pct
    score += hp_ratio * 0.3

    # Level advantage
    score += (state.my_level - state.enemy_level) * 8.0

    # Gold advantage (rough item advantage)
    score += state.my_gold * 0.01

    # Cooldown advantage (more abilities ready = more threat)
    my_ready = sum(1 for cd in [state.my_q_cd, state.my_w_cd, state.my_e_cd, state.my_r_cd] if cd <= 0)
    enemy_ready = sum(1 for cd in [state.enemy_q_cd_est, state.enemy_w_cd_est, state.enemy_e_cd_est, state.enemy_r_cd_est] if cd <= 0)
    score += (my_ready - enemy_ready) * 3.0

    # Flash advantage
    if state.has_flash and state.enemy_flash_cd_est > 0:
        score += 8.0
    elif not state.has_flash and state.enemy_flash_cd_est <= 0:
        score -= 8.0

    # Wave position
    if state.wave_position == WavePosition.FROZEN_NEAR_ME:
        score += 6.0
    elif state.wave_position == WavePosition.CRASHED:
        score += 3.0

    # Gank risk penalty
    score -= state.gank_risk * 10.0

    return score
