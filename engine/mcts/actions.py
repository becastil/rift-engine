"""
Action Library — all the things a mid laner can do in a 20-second window.

Think of these as "buttons" you can press. The MCTS engine tries each one
thousands of times and picks the one that works best.
"""

from enum import Enum
from dataclasses import dataclass


class LaneAction(Enum):
    """Every possible action in a 20-second window."""

    # ── FARMING (safe gold/XP income) ──
    FARM_SAFE = "farm_safe"       # Last-hit carefully, stay near tower
    FARM_PUSH = "farm_push"       # Use abilities on the wave to push it fast
    FREEZE = "freeze"             # Hold wave in a good position (deny enemy CS)
    THIN_WAVE = "thin_wave"       # Kill caster minions to set up a slow push
    RESET_WAVE = "reset_wave"     # Let wave push into you (sets up freeze)

    # ── TRADING (damage the enemy) ──
    SHORT_TRADE = "short_trade"       # One ability combo then back off (e.g., Q-auto-back)
    EXTENDED_TRADE = "extended_trade" # Multiple rotations, stay in their face
    ALL_IN = "all_in"                 # Go for the kill — commit everything

    # ── MAP PLAYS ──
    WARD_RIVER = "ward_river"     # Place a ward for vision (costs a ward charge)
    RECALL = "recall"             # Back to base to buy items (takes 8 sec)
    ROAM_TOP = "roam_top"         # Leave lane to help top
    ROAM_BOT = "roam_bot"         # Leave lane to help bot
    ROAM_DRAGON = "roam_dragon"   # Rotate to dragon pit
    ROAM_HERALD = "roam_herald"   # Rotate to rift herald


# ── Action metadata ──

@dataclass
class ActionInfo:
    """Extra info about what an action requires and risks."""
    name: str
    min_hp_pct: float = 0.0       # Minimum HP% to attempt this
    min_mana_pct: float = 0.0     # Minimum mana% needed
    requires_abilities: bool = False  # Needs at least one ability off cooldown
    risk_level: float = 0.0       # 0 (safe) to 1 (very risky)
    time_cost: float = 20.0       # How many seconds this takes (all are 20s windows)
    leaves_lane: bool = False     # Do you leave lane? (lose CS)


ACTION_INFO: dict[LaneAction, ActionInfo] = {
    LaneAction.FARM_SAFE: ActionInfo("Farm Safe", risk_level=0.05),
    LaneAction.FARM_PUSH: ActionInfo("Farm Push", min_mana_pct=15, requires_abilities=True, risk_level=0.15),
    LaneAction.FREEZE: ActionInfo("Freeze", risk_level=0.1),
    LaneAction.THIN_WAVE: ActionInfo("Thin Wave", min_mana_pct=10, requires_abilities=True, risk_level=0.1),
    LaneAction.RESET_WAVE: ActionInfo("Reset Wave", risk_level=0.05),

    LaneAction.SHORT_TRADE: ActionInfo("Short Trade", min_hp_pct=25, min_mana_pct=20, requires_abilities=True, risk_level=0.3),
    LaneAction.EXTENDED_TRADE: ActionInfo("Extended Trade", min_hp_pct=40, min_mana_pct=35, requires_abilities=True, risk_level=0.5),
    LaneAction.ALL_IN: ActionInfo("All-In", min_hp_pct=50, min_mana_pct=40, requires_abilities=True, risk_level=0.8),

    LaneAction.WARD_RIVER: ActionInfo("Ward River", risk_level=0.15),
    LaneAction.RECALL: ActionInfo("Recall", risk_level=0.1, leaves_lane=True),
    LaneAction.ROAM_TOP: ActionInfo("Roam Top", min_hp_pct=30, risk_level=0.35, leaves_lane=True),
    LaneAction.ROAM_BOT: ActionInfo("Roam Bot", min_hp_pct=30, risk_level=0.35, leaves_lane=True),
    LaneAction.ROAM_DRAGON: ActionInfo("Roam Dragon", min_hp_pct=30, risk_level=0.3, leaves_lane=True),
    LaneAction.ROAM_HERALD: ActionInfo("Roam Herald", min_hp_pct=30, risk_level=0.3, leaves_lane=True),
}


def get_legal_actions(state) -> list[LaneAction]:
    """
    Given a LaneState, return which actions are actually possible right now.
    
    Filters out actions you can't do (e.g., can't all-in at 10% HP,
    can't use abilities when everything is on cooldown).
    """
    from engine.mcts.lane_state import LaneState

    legal = []
    has_ability = (state.my_q_cd <= 0 or state.my_w_cd <= 0 or state.my_e_cd <= 0)

    for action, info in ACTION_INFO.items():
        # HP check
        if state.my_hp_pct < info.min_hp_pct:
            continue
        # Mana check
        if state.my_mana_pct < info.min_mana_pct:
            continue
        # Ability check
        if info.requires_abilities and not has_ability:
            continue

        # Specific filters
        if action == LaneAction.ALL_IN and state.my_position == state.Position.UNDER_TOWER if hasattr(state, 'Position') else False:
            continue  # Hard to all-in from under tower

        if action == LaneAction.RECALL and state.my_position == state.Position.EXTENDED if hasattr(state, 'Position') else False:
            continue  # Don't recall while extended

        # Can't roam to dragon/herald if timer isn't up
        if action == LaneAction.ROAM_DRAGON and state.dragon_timer > 30:
            continue
        if action == LaneAction.ROAM_HERALD and state.herald_timer > 30:
            continue

        legal.append(action)

    # Always have at least farm_safe as a fallback
    if not legal:
        legal = [LaneAction.FARM_SAFE]

    return legal
