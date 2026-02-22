"""
MCTS Tree Search — the brain that picks the best action.

How MCTS works (like a chess engine but for League):

1. SELECTION: Start at root, walk down the tree picking promising branches
2. EXPANSION: When you reach a leaf, try a new action
3. ROLLOUT: From that new state, play randomly for a few steps to see what happens
4. BACKPROPAGATION: Send the score back up the tree so good branches get more visits

After enough iterations (1000+), the most-visited action from the root is the best one.

UCB1 formula balances "actions that scored well" vs "actions we haven't tried much."
Think of it like: try the restaurant you love, but occasionally try a new place.
"""

import math
import random
from dataclasses import dataclass, field
from typing import Optional

from engine.mcts.lane_state import LaneState
from engine.mcts.actions import LaneAction, get_legal_actions
from engine.mcts.simulator import simulate_step
from engine.mcts.scoring import score_state, quick_evaluate


@dataclass
class MCTSNode:
    """One node in the search tree = one game state + stats about how good it is."""
    state: LaneState
    action: Optional[LaneAction] = None  # Action that LED to this state
    parent: Optional["MCTSNode"] = None
    children: list["MCTSNode"] = field(default_factory=list)

    visits: int = 0
    total_score: float = 0.0
    untried_actions: list[LaneAction] = field(default_factory=list)

    @property
    def avg_score(self) -> float:
        return self.total_score / max(1, self.visits)

    def ucb1(self, exploration: float = 1.41) -> float:
        """
        UCB1 = average_score + exploration * sqrt(ln(parent_visits) / my_visits)
        
        High average = exploit (pick what works).
        Low visits = explore (try something new).
        """
        if self.visits == 0:
            return float("inf")  # Always try unvisited nodes first
        parent_visits = self.parent.visits if self.parent else 1
        exploit = self.avg_score
        explore = exploration * math.sqrt(math.log(parent_visits) / self.visits)
        return exploit + explore

    def is_fully_expanded(self) -> bool:
        return len(self.untried_actions) == 0

    def best_child(self, exploration: float = 1.41) -> "MCTSNode":
        """Pick the child with highest UCB1 score."""
        return max(self.children, key=lambda c: c.ucb1(exploration))


@dataclass
class MCTSResult:
    """What the MCTS engine recommends."""
    best_action: LaneAction
    confidence: float          # 0-1, how sure are we?
    action_scores: dict        # {action_name: {visits, avg_score}}
    iterations_run: int
    best_sequence: list[str]   # Top 3 actions in sequence (next 60 sec plan)


def run_mcts(
    state: LaneState,
    iterations: int = 1000,
    enemy_model: str = "average",
    rollout_depth: int = 6,        # 6 steps × 20 sec = 2 minutes lookahead
    exploration: float = 1.41,
) -> MCTSResult:
    """
    Run MCTS from the given state and return the best action.
    
    Args:
        state: Current lane state
        iterations: How many times to simulate (more = better but slower)
        enemy_model: "average", "optimal", or "passive"
        rollout_depth: How many 20-sec steps to look ahead during rollouts
        exploration: UCB1 exploration constant (higher = more exploration)
    
    Returns:
        MCTSResult with best action, confidence, and all action scores
    """
    root = MCTSNode(state=state)
    root.untried_actions = get_legal_actions(state)

    for _ in range(iterations):
        node = root

        # ── 1. SELECTION: walk down tree using UCB1 ──
        while node.is_fully_expanded() and node.children:
            node = node.best_child(exploration)

        # ── 2. EXPANSION: try an untried action ──
        if node.untried_actions:
            action = node.untried_actions.pop(random.randrange(len(node.untried_actions)))
            new_state = simulate_step(node.state, action, enemy_model)
            child = MCTSNode(
                state=new_state,
                action=action,
                parent=node,
                untried_actions=get_legal_actions(new_state),
            )
            node.children.append(child)
            node = child

        # ── 3. ROLLOUT: play randomly from here ──
        rollout_score = _rollout(node.state, rollout_depth, enemy_model)

        # ── 4. BACKPROPAGATION: send score back up the tree ──
        while node is not None:
            node.visits += 1
            node.total_score += rollout_score
            node = node.parent

    # ── RESULTS ──
    if not root.children:
        # Edge case: no valid actions (shouldn't happen with farm_safe fallback)
        return MCTSResult(
            best_action=LaneAction.FARM_SAFE,
            confidence=0.0,
            action_scores={},
            iterations_run=iterations,
            best_sequence=["farm_safe"],
        )

    # Best action = most visited (not highest avg score — more robust)
    best_child = max(root.children, key=lambda c: c.visits)

    # Build action scores summary
    action_scores = {}
    total_visits = sum(c.visits for c in root.children)
    for child in root.children:
        action_scores[child.action.value] = {
            "visits": child.visits,
            "avg_score": round(child.avg_score, 2),
            "visit_pct": round(child.visits / max(1, total_visits) * 100, 1),
        }

    # Confidence = how dominant the best action is
    confidence = best_child.visits / max(1, total_visits)

    # Best sequence: look 3 levels deep
    best_sequence = [best_child.action.value]
    node = best_child
    for _ in range(2):
        if node.children:
            next_best = max(node.children, key=lambda c: c.visits)
            best_sequence.append(next_best.action.value)
            node = next_best
        else:
            break

    return MCTSResult(
        best_action=best_child.action,
        confidence=round(confidence, 3),
        action_scores=action_scores,
        iterations_run=iterations,
        best_sequence=best_sequence,
    )


def _rollout(state: LaneState, depth: int, enemy_model: str) -> float:
    """
    Random playout from this state for 'depth' steps.
    Returns the cumulative score.
    """
    total_score = 0.0
    current = state

    for _ in range(depth):
        if current.my_hp <= 0:
            total_score -= 50  # Death penalty carries forward
            break

        actions = get_legal_actions(current)
        action = random.choice(actions)
        next_state = simulate_step(current, action, enemy_model)
        total_score += score_state(current, next_state)
        current = next_state

    # Add static evaluation of final state
    total_score += quick_evaluate(current) * 0.3  # Weighted less than dynamic scoring

    return total_score
