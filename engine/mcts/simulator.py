"""
Fast 20-Second Forward Simulator — predicts what happens after you take an action.

Takes a LaneState + an action → produces a new LaneState 20 seconds later.
This is simplified physics — we're not modeling every auto-attack, just the
broad strokes: did HP change? Did cooldowns tick? Did the wave move?

The enemy's behavior is modeled simply (v1 = random/average play).
"""

import random
from engine.mcts.lane_state import LaneState, Position, WavePosition, EnemyJgLocation
from engine.mcts.actions import LaneAction

# ── Constants ──
TICK_SECONDS = 20.0
GOLD_PER_SECOND = 1.9  # Passive gold after 1:50
CS_GOLD_AVG = 20.0     # Average gold per CS
MANA_REGEN_PER_SEC = 1.5  # Rough average mana regen


def simulate_step(state: LaneState, action: LaneAction, enemy_model: str = "average") -> LaneState:
    """
    Given a state and an action, simulate 20 seconds and return the new state.
    
    enemy_model:
        "average" — enemy plays safely, trades occasionally
        "optimal" — enemy punishes every mistake
        "passive" — enemy mostly farms (Iron/Bronze behavior)
    """
    s = state.clone()

    # ── 1. PASSIVE TICKS (happen regardless of action) ──
    s.game_time += TICK_SECONDS

    # Passive gold
    if s.game_time > 110:  # Gold starts at 1:50
        s.my_gold += GOLD_PER_SECOND * TICK_SECONDS

    # Mana regen
    s.my_mana = min(s.my_mana_max, s.my_mana + MANA_REGEN_PER_SEC * TICK_SECONDS)
    s.enemy_mana_est = min(300, s.enemy_mana_est + MANA_REGEN_PER_SEC * TICK_SECONDS)

    # Cooldown ticks
    s.my_q_cd = max(0, s.my_q_cd - TICK_SECONDS)
    s.my_w_cd = max(0, s.my_w_cd - TICK_SECONDS)
    s.my_e_cd = max(0, s.my_e_cd - TICK_SECONDS)
    s.my_r_cd = max(0, s.my_r_cd - TICK_SECONDS)
    s.my_flash_cd = max(0, s.my_flash_cd - TICK_SECONDS)
    s.my_summ2_cd = max(0, s.my_summ2_cd - TICK_SECONDS)
    s.enemy_q_cd_est = max(0, s.enemy_q_cd_est - TICK_SECONDS)
    s.enemy_w_cd_est = max(0, s.enemy_w_cd_est - TICK_SECONDS)
    s.enemy_e_cd_est = max(0, s.enemy_e_cd_est - TICK_SECONDS)
    s.enemy_r_cd_est = max(0, s.enemy_r_cd_est - TICK_SECONDS)
    s.enemy_flash_cd_est = max(0, s.enemy_flash_cd_est - TICK_SECONDS)

    # Jungler tracking decays
    s.enemy_jg_last_seen += TICK_SECONDS

    # Objective timers tick
    s.dragon_timer = max(0, s.dragon_timer - TICK_SECONDS)
    s.herald_timer = max(0, s.herald_timer - TICK_SECONDS)

    # ── 2. ACTION-SPECIFIC EFFECTS ──
    if action == LaneAction.FARM_SAFE:
        _do_farm_safe(s)
    elif action == LaneAction.FARM_PUSH:
        _do_farm_push(s)
    elif action == LaneAction.FREEZE:
        _do_freeze(s)
    elif action == LaneAction.THIN_WAVE:
        _do_thin_wave(s)
    elif action == LaneAction.RESET_WAVE:
        _do_reset_wave(s)
    elif action == LaneAction.SHORT_TRADE:
        _do_short_trade(s, enemy_model)
    elif action == LaneAction.EXTENDED_TRADE:
        _do_extended_trade(s, enemy_model)
    elif action == LaneAction.ALL_IN:
        _do_all_in(s, enemy_model)
    elif action == LaneAction.WARD_RIVER:
        _do_ward(s)
    elif action == LaneAction.RECALL:
        _do_recall(s)
    elif action in (LaneAction.ROAM_TOP, LaneAction.ROAM_BOT):
        _do_roam(s)
    elif action in (LaneAction.ROAM_DRAGON, LaneAction.ROAM_HERALD):
        _do_roam_objective(s)

    # ── 3. GANK CHECK ──
    # Random chance of getting ganked (higher if extended, no flash, no wards)
    _check_gank(s, enemy_model)

    # ── 4. PHASE UPDATE ──
    if s.game_time >= 1500:
        s.phase = "late"
    elif s.game_time >= 840:
        s.phase = "mid"

    return s


# ── Action Implementations ──

def _do_farm_safe(s: LaneState):
    """Last-hit carefully, stay near tower."""
    cs_gained = random.randint(2, 4)  # ~3 CS in 20 sec
    s.my_gold += cs_gained * CS_GOLD_AVG
    s.enemy_minions = max(0, s.enemy_minions - cs_gained)
    s.my_position = Position.SAFE
    # Wave slowly pushes toward you when you only last-hit
    if s.wave_position == WavePosition.MIDDLE:
        s.wave_position = WavePosition.PUSHING_TO_ME


def _do_farm_push(s: LaneState):
    """Use abilities to push wave fast."""
    cs_gained = random.randint(4, 6)
    s.my_gold += cs_gained * CS_GOLD_AVG
    s.enemy_minions = max(0, s.enemy_minions - cs_gained)
    s.my_mana -= 60  # Abilities cost mana
    s.my_mana = max(0, s.my_mana)
    s.my_q_cd = 6.0  # Used Q to push
    s.my_position = Position.MIDDLE

    # Wave pushes toward them
    wave_advance = {
        WavePosition.FROZEN_NEAR_ME: WavePosition.PUSHING_TO_ME,
        WavePosition.PUSHING_TO_ME: WavePosition.MIDDLE,
        WavePosition.MIDDLE: WavePosition.SLOW_PUSH_TO_THEM,
        WavePosition.SLOW_PUSH_TO_THEM: WavePosition.CRASHED,
        WavePosition.CRASHED: WavePosition.CRASHED,
    }
    s.wave_position = wave_advance.get(s.wave_position, WavePosition.MIDDLE)


def _do_freeze(s: LaneState):
    """Hold wave in current position."""
    cs_gained = random.randint(2, 3)
    s.my_gold += cs_gained * CS_GOLD_AVG
    s.enemy_minions = max(0, s.enemy_minions - cs_gained)
    # Wave stays roughly where it is (maybe drifts toward you)
    if s.wave_position == WavePosition.MIDDLE:
        s.wave_position = WavePosition.FROZEN_NEAR_ME
    s.my_position = Position.SAFE


def _do_thin_wave(s: LaneState):
    """Kill casters to set up slow push."""
    s.my_gold += 3 * CS_GOLD_AVG  # Kill 3 casters
    s.enemy_minions = max(0, s.enemy_minions - 3)
    s.my_mana -= 40
    s.my_mana = max(0, s.my_mana)
    s.wave_position = WavePosition.SLOW_PUSH_TO_THEM
    s.my_position = Position.MIDDLE


def _do_reset_wave(s: LaneState):
    """Let the wave push into you."""
    cs_gained = random.randint(1, 2)  # Fewer CS since you're letting them push
    s.my_gold += cs_gained * CS_GOLD_AVG
    s.wave_position = WavePosition.PUSHING_TO_ME
    s.my_position = Position.SAFE


def _do_short_trade(s: LaneState, enemy_model: str):
    """One ability combo then back off."""
    power_ratio = s.my_combat_power / max(1, s.enemy_combat_power)

    # Your damage: based on combat power + randomness
    my_dmg = s.my_combat_power * 0.15 * random.uniform(0.8, 1.2)
    s.enemy_hp -= my_dmg
    s.my_mana -= 50
    s.my_mana = max(0, s.my_mana)
    s.my_q_cd = 7.0  # Put main ability on CD

    # Enemy trades back (depends on model)
    if enemy_model == "optimal":
        enemy_dmg = s.enemy_combat_power * 0.18 * random.uniform(0.9, 1.1)
    elif enemy_model == "passive":
        enemy_dmg = s.enemy_combat_power * 0.05 * random.uniform(0.5, 1.0)
    else:  # average
        enemy_dmg = s.enemy_combat_power * 0.12 * random.uniform(0.7, 1.2)

    s.my_hp -= enemy_dmg
    s.enemy_q_cd_est = 7.0
    s.my_position = Position.MIDDLE

    # Some CS still happens during trades
    s.my_gold += random.randint(1, 2) * CS_GOLD_AVG


def _do_extended_trade(s: LaneState, enemy_model: str):
    """Multiple ability rotations, stay in their face."""
    power_ratio = s.my_combat_power / max(1, s.enemy_combat_power)

    my_dmg = s.my_combat_power * 0.35 * random.uniform(0.7, 1.3)
    s.enemy_hp -= my_dmg
    s.my_mana -= 100
    s.my_mana = max(0, s.my_mana)
    s.my_q_cd = 7.0
    s.my_w_cd = 10.0

    if enemy_model == "optimal":
        enemy_dmg = s.enemy_combat_power * 0.30 * random.uniform(0.9, 1.1)
    elif enemy_model == "passive":
        enemy_dmg = s.enemy_combat_power * 0.15 * random.uniform(0.6, 1.0)
    else:
        enemy_dmg = s.enemy_combat_power * 0.25 * random.uniform(0.7, 1.2)

    s.my_hp -= enemy_dmg
    s.enemy_q_cd_est = 7.0
    s.enemy_w_cd_est = 10.0
    s.my_position = Position.EXTENDED

    s.my_gold += random.randint(0, 1) * CS_GOLD_AVG


def _do_all_in(s: LaneState, enemy_model: str):
    """Go for the kill. High risk, high reward."""
    power_ratio = s.my_combat_power / max(1, s.enemy_combat_power)

    # All abilities + summoners
    my_dmg = s.my_combat_power * 0.65 * random.uniform(0.6, 1.4)
    if s.my_summ2_type == "ignite" and s.my_summ2_cd <= 0:
        my_dmg += s.my_combat_power * 0.12  # Ignite damage
        s.my_summ2_cd = 180.0

    s.enemy_hp -= my_dmg
    s.my_mana -= 150
    s.my_mana = max(0, s.my_mana)
    s.my_q_cd = 7.0
    s.my_w_cd = 10.0
    s.my_e_cd = 12.0
    if s.my_level >= 6:
        s.my_r_cd = 80.0

    # Enemy fights back hard
    if enemy_model == "optimal":
        enemy_dmg = s.enemy_combat_power * 0.55 * random.uniform(0.8, 1.2)
    elif enemy_model == "passive":
        enemy_dmg = s.enemy_combat_power * 0.30 * random.uniform(0.5, 1.0)
    else:
        enemy_dmg = s.enemy_combat_power * 0.45 * random.uniform(0.6, 1.3)

    # Enemy might flash if they'd die
    if s.enemy_hp - my_dmg <= 0 and s.enemy_flash_cd_est <= 0 and random.random() < 0.5:
        enemy_dmg *= 0.3  # They escaped, less damage back
        s.enemy_hp = max(50, s.enemy_hp)  # Survived with low HP
        s.enemy_flash_cd_est = 300.0

    s.my_hp -= enemy_dmg
    s.my_position = Position.EXTENDED

    # If enemy died, big gold reward
    if s.enemy_hp <= 0:
        s.my_gold += 300  # Kill gold
        s.enemy_hp = 0


def _do_ward(s: LaneState):
    """Place a ward in river for vision."""
    s.enemy_jg_last_seen = 0  # Effectively "refreshes" vision
    s.enemy_jg_location = EnemyJgLocation.UNKNOWN  # Updated with actual info
    s.my_position = Position.MIDDLE
    # Some CS while warding
    s.my_gold += random.randint(1, 2) * CS_GOLD_AVG


def _do_recall(s: LaneState):
    """Back to base. Lose CS but gain items."""
    # Recall takes ~8 seconds, walk back takes ~12
    # You get to spend your gold on items → combat power increase
    item_value = s.my_gold * 0.7  # Spend ~70% of gold
    s.my_combat_power += item_value / 400  # Rough: 400g = 1 combat power point
    s.my_hp = s.my_hp_max  # Full heal
    s.my_mana = s.my_mana_max
    # Wave pushes into you while you're gone
    s.wave_position = WavePosition.PUSHING_TO_ME
    s.my_position = Position.SAFE
    # Lose about 1 wave of CS
    s.enemy_minions = 6


def _do_roam(s: LaneState):
    """Roam to a side lane. Might get a kill, might waste time."""
    # Lose CS (wave dies to tower)
    s.wave_position = WavePosition.CRASHED  # Will bounce back
    s.my_position = Position.RIVER

    # Roam outcome: 30% get kill, 20% assist, 50% waste time
    roll = random.random()
    if roll < 0.30:
        s.my_gold += 300 + 150  # Kill + assist gold
    elif roll < 0.50:
        s.my_gold += 150  # Assist gold
    # else: wasted time, lost CS


def _do_roam_objective(s: LaneState):
    """Rotate to dragon/herald."""
    s.wave_position = WavePosition.CRASHED
    s.my_position = Position.RIVER

    # Objective taken: 40% success
    if random.random() < 0.40:
        s.my_gold += 200  # Objective gold


def _check_gank(s: LaneState, enemy_model: str):
    """Random gank check based on state."""
    gank_chance = s.gank_risk * 0.15  # Base: 15% of gank_risk score

    if enemy_model == "optimal":
        gank_chance *= 1.5  # Better junglers gank more

    if random.random() < gank_chance:
        # Getting ganked!
        if s.has_flash and random.random() < 0.6:
            # Flash away — survive but lose flash
            s.my_flash_cd = 300.0
            s.my_hp -= s.enemy_combat_power * 0.1  # Took some damage
            s.my_position = Position.SAFE
        elif random.random() < 0.4:
            # Die to gank
            s.my_hp = 0
        else:
            # Escape without flash (lucky)
            s.my_hp -= s.enemy_combat_power * 0.2
            s.my_position = Position.UNDER_TOWER
