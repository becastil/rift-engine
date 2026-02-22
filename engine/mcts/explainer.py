"""
Explainer — translates MCTS results into plain English an 8th grader can understand.

Every recommendation follows the format:
  DO THIS NOW: [action]
  WHY: [reason]
  WATCH FOR: [what to look out for]
  PLAN CHANGES IF: [what would change the recommendation]
"""

from engine.mcts.lane_state import LaneState, Position, WavePosition
from engine.mcts.actions import LaneAction
from engine.mcts.tree import MCTSResult


def explain_recommendation(state: LaneState, result: MCTSResult) -> dict:
    """
    Turn an MCTS result into a plain-English recommendation.
    
    Returns:
        {
            "do_this": "Short trade with your Q",
            "why": "Their Q is on cooldown for 4 more seconds...",
            "watch_for": "If their jungler shows on the map...",
            "plan_changes_if": "They hit level 6 before you...",
            "confidence": "High (78%)",
            "next_2_min": "Push wave → recall → buy items → push again",
            "position_advice": "Stay in the middle of lane"
        }
    """
    action = result.best_action
    confidence = result.confidence

    do_this = _action_to_english(action, state)
    why = _explain_why(action, state, result)
    watch_for = _explain_watch(action, state)
    plan_changes = _explain_changes(action, state)
    next_plan = _explain_sequence(result.best_sequence, state)
    position = _position_advice(state)

    # Confidence label
    if confidence >= 0.6:
        conf_label = f"HIGH ({int(confidence*100)}%)"
    elif confidence >= 0.35:
        conf_label = f"MEDIUM ({int(confidence*100)}%)"
    else:
        conf_label = f"LOW ({int(confidence*100)}%) — multiple options are close"

    return {
        "do_this": do_this,
        "why": why,
        "watch_for": watch_for,
        "plan_changes_if": plan_changes,
        "confidence": conf_label,
        "next_2_min": next_plan,
        "position_advice": position,
    }


def _action_to_english(action: LaneAction, state: LaneState) -> str:
    """Convert action enum to plain English."""
    templates = {
        LaneAction.FARM_SAFE: "Farm safely — just last-hit minions, don't push up",
        LaneAction.FARM_PUSH: "Push the wave hard — use your abilities on the minions",
        LaneAction.FREEZE: "Freeze the wave — hold it near your tower so the enemy has to overextend for CS",
        LaneAction.THIN_WAVE: "Thin the wave — kill the caster minions to start a slow push",
        LaneAction.RESET_WAVE: "Let the wave push to you — step back and let minions come to your side",
        LaneAction.SHORT_TRADE: f"Short trade — hit {state.my_champion_id}'s combo then back off immediately",
        LaneAction.EXTENDED_TRADE: f"Extended trade — stay in their face and use multiple ability rotations",
        LaneAction.ALL_IN: f"GO ALL IN — commit everything to kill {state.enemy_champion_id}!",
        LaneAction.WARD_RIVER: "Ward the river bush — you need vision to play aggressive safely",
        LaneAction.RECALL: "Recall now — go back to base, buy items, and come back stronger",
        LaneAction.ROAM_TOP: "Roam top — push your wave first, then walk up to help top lane",
        LaneAction.ROAM_BOT: "Roam bot — push your wave first, then walk down to help bot lane",
        LaneAction.ROAM_DRAGON: "Rotate to dragon — help your team secure the objective",
        LaneAction.ROAM_HERALD: "Rotate to Rift Herald — help your team take it for tower plates",
    }
    return templates.get(action, action.value)


def _explain_why(action: LaneAction, state: LaneState, result: MCTSResult) -> str:
    """Explain WHY this is the best action."""
    reasons = []

    if action in (LaneAction.SHORT_TRADE, LaneAction.EXTENDED_TRADE, LaneAction.ALL_IN):
        # Trading/fighting reasons
        if state.enemy_q_cd_est > 3:
            reasons.append(f"their Q is on cooldown (~{int(state.enemy_q_cd_est)}s left), so they can't trade back as hard")
        if state.my_hp_pct > state.enemy_hp_pct + 15:
            reasons.append(f"you're healthier ({int(state.my_hp_pct)}% vs their {int(state.enemy_hp_pct)}%)")
        if state.my_level > state.enemy_level:
            reasons.append(f"you're level {state.my_level} and they're only {state.enemy_level} — your stats are higher")
        if state.has_flash and state.enemy_flash_cd_est > 0:
            reasons.append("you have Flash and they don't — huge safety advantage")
        if action == LaneAction.ALL_IN and state.has_ult and not state.enemy_has_ult_est:
            reasons.append("you have your ultimate and they don't — massive damage advantage")
        if not reasons:
            reasons.append(f"the simulation found this wins {int(result.confidence*100)}% of the time")

    elif action in (LaneAction.FARM_SAFE, LaneAction.FREEZE, LaneAction.RESET_WAVE):
        if state.my_hp_pct < 40:
            reasons.append(f"you're low HP ({int(state.my_hp_pct)}%) — fighting would be risky")
        if state.gank_risk > 0.4:
            reasons.append("there's a high chance the enemy jungler is nearby")
        if state.enemy_combat_power > state.my_combat_power * 1.1:
            reasons.append("the enemy has a stat advantage right now — better to farm and wait for items")
        if not reasons:
            reasons.append("it's the safest way to keep getting gold without risking anything")

    elif action == LaneAction.FARM_PUSH:
        if state.wave_position in (WavePosition.MIDDLE, WavePosition.SLOW_PUSH_TO_THEM):
            reasons.append("pushing gives you a recall/roam window once the wave crashes into their tower")
        reasons.append("you have enough mana to push without going OOM")

    elif action == LaneAction.RECALL:
        reasons.append(f"you have {int(state.my_gold)}g to spend on items")
        if state.my_hp_pct < 50:
            reasons.append("and you're low on HP")
        if state.wave_position == WavePosition.CRASHED:
            reasons.append("the wave is crashed so you won't miss many minions")

    elif action == LaneAction.WARD_RIVER:
        reasons.append(f"enemy jungler hasn't been seen in {int(state.enemy_jg_last_seen)}s — you need vision")

    elif action in (LaneAction.ROAM_TOP, LaneAction.ROAM_BOT):
        reasons.append("your wave is pushed so you have time to roam without losing CS")

    elif action in (LaneAction.ROAM_DRAGON, LaneAction.ROAM_HERALD):
        reasons.append("the objective is up and your team can take it with your help")

    if not reasons:
        reasons.append(f"the engine simulated {result.iterations_run} scenarios and this came out on top")

    return ". ".join(reasons).capitalize() + "."


def _explain_watch(action: LaneAction, state: LaneState) -> str:
    """What to watch out for while doing this action."""
    warnings = []

    if state.gank_risk > 0.3:
        warnings.append("the minimap — enemy jungler could be heading your way")
    if action in (LaneAction.SHORT_TRADE, LaneAction.EXTENDED_TRADE, LaneAction.ALL_IN):
        warnings.append("enemy cooldowns — if they dodge your main ability, back off")
        if state.enemy_level == 5:
            warnings.append("they're about to hit level 6 (ultimate) — the matchup changes at that point")
    if action == LaneAction.RECALL:
        warnings.append("the wave position — make sure it's pushing away from you before you recall")
    if action in (LaneAction.ROAM_TOP, LaneAction.ROAM_BOT):
        warnings.append("your wave — if you roam with a bad wave, the enemy mid will take your tower plates")

    if not warnings:
        warnings.append("nothing specific — just play it out")

    return "Watch " + "; ".join(warnings) + "."


def _explain_changes(action: LaneAction, state: LaneState) -> str:
    """What would make you change this plan?"""
    changes = []

    if state.my_level < 6 and state.enemy_level < 6:
        changes.append("they hit level 6 first — back off and farm safely until you catch up")
    if state.enemy_jg_location == state.enemy_jg_location.UNKNOWN:
        changes.append("enemy jungler shows on the opposite side of the map — that's your green light to play aggressive")
    if action in (LaneAction.FARM_SAFE, LaneAction.FREEZE):
        changes.append("your jungler pings they're coming to gank — get ready to follow up")
    if action == LaneAction.ALL_IN:
        changes.append("they get a heal from their support or jungler — abort the all-in")

    if not changes:
        changes.append("the enemy plays something unexpected — always be ready to adapt")

    return "Plan changes if: " + "; ".join(changes) + "."


def _explain_sequence(sequence: list[str], state: LaneState) -> str:
    """Turn the 3-step sequence into a readable plan."""
    step_names = {
        "farm_safe": "farm safely",
        "farm_push": "push the wave",
        "freeze": "freeze the wave",
        "thin_wave": "thin the wave",
        "reset_wave": "let wave reset",
        "short_trade": "take a short trade",
        "extended_trade": "go for an extended trade",
        "all_in": "all-in for the kill",
        "ward_river": "ward river",
        "recall": "recall to base",
        "roam_top": "roam top",
        "roam_bot": "roam bot",
        "roam_dragon": "rotate to dragon",
        "roam_herald": "rotate to herald",
    }
    steps = [step_names.get(s, s) for s in sequence]

    if len(steps) == 1:
        return steps[0].capitalize()
    elif len(steps) == 2:
        return f"{steps[0].capitalize()} → then {steps[1]}"
    else:
        return f"{steps[0].capitalize()} → {steps[1]} → {steps[2]}"


def _position_advice(state: LaneState) -> str:
    """Quick positioning tip."""
    if state.gank_risk > 0.5:
        return "Stay near your tower — gank risk is high"
    if state.wave_position == WavePosition.FROZEN_NEAR_ME:
        return "Stay on the safe side of the wave — let them come to you"
    if state.wave_position == WavePosition.CRASHED:
        return "You can step up since the wave is at their tower"
    return "Stay in the middle of lane — balanced position"
