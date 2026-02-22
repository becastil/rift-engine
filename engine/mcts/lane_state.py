"""
Lane State — the zoomed-in snapshot of a single lane at a moment in time.

Think of GameState as a bird's-eye view of the whole map.
LaneState is like sitting in the player's chair — what THEY see and care about
for the next 20 seconds of gameplay.

~30 variables total. Enough for meaningful MCTS rollouts without exploding in complexity.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
import copy


class Position(Enum):
    """Where you are in lane (simplified)."""
    UNDER_TOWER = "under_tower"    # Very safe, farming under turret
    SAFE = "safe"                  # Near your tower, hard to gank
    MIDDLE = "middle"              # Neutral position
    EXTENDED = "extended"          # Pushed up, gankable
    RIVER = "river"               # Left lane for a roam/ward


class WavePosition(Enum):
    """Where the minion wave is."""
    FROZEN_NEAR_ME = "frozen_near_me"        # Best spot — safe CS, enemy overextends to farm
    PUSHING_TO_ME = "pushing_to_me"          # Wave coming toward you
    MIDDLE = "middle"                        # Neutral
    SLOW_PUSH_TO_THEM = "slow_push_to_them"  # Building a big wave
    CRASHED = "crashed"                      # Your wave hit their tower — roam/recall window


class EnemyJgLocation(Enum):
    """Last known enemy jungler position."""
    TOPSIDE = "topside"
    BOTSIDE = "botside"
    MID = "mid"
    UNKNOWN = "unknown"


@dataclass
class LaneState:
    """Everything one mid-laner cares about for a 20-second decision."""

    # ── YOUR CHAMPION ──
    my_champion_id: str = "Unknown"
    my_hp: float = 600.0
    my_hp_max: float = 600.0
    my_mana: float = 300.0
    my_mana_max: float = 300.0
    my_level: int = 1
    my_xp_to_next: float = 280.0

    # Cooldowns (seconds remaining; 0 = ready)
    my_q_cd: float = 0.0
    my_w_cd: float = 0.0
    my_e_cd: float = 0.0
    my_r_cd: float = 0.0
    my_flash_cd: float = 0.0
    my_summ2_cd: float = 0.0
    my_summ2_type: str = "ignite"  # ignite, tp, barrier, exhaust, cleanse

    my_position: Position = Position.MIDDLE
    my_gold: float = 500.0
    my_items: list[str] = field(default_factory=list)
    my_combat_power: float = 100.0

    # ── ENEMY LANER ──
    enemy_champion_id: str = "Unknown"
    enemy_hp: float = 600.0
    enemy_hp_max: float = 600.0
    enemy_mana_est: float = 300.0  # Estimated — you can't see exact enemy mana
    enemy_level: int = 1
    enemy_q_cd_est: float = 0.0
    enemy_w_cd_est: float = 0.0
    enemy_e_cd_est: float = 0.0
    enemy_r_cd_est: float = 0.0
    enemy_flash_cd_est: float = 0.0
    enemy_position: Position = Position.MIDDLE
    enemy_combat_power: float = 100.0

    # ── WAVE STATE ──
    my_minions: int = 6      # How many of your minions are alive
    enemy_minions: int = 6   # How many enemy minions
    wave_position: WavePosition = WavePosition.MIDDLE
    is_cannon_wave: bool = False  # Cannon waves push harder and are worth more gold

    # ── MAP CONTEXT ──
    enemy_jg_last_seen: float = 999.0       # Seconds since last spotted (999 = never)
    enemy_jg_location: EnemyJgLocation = EnemyJgLocation.UNKNOWN
    ally_jg_position: str = "unknown"       # Simplified
    dragon_timer: float = 300.0             # Seconds until dragon spawns (0 = up now)
    herald_timer: float = 840.0
    my_tower_hp: float = 100.0              # Percentage
    enemy_tower_hp: float = 100.0

    # ── TIME ──
    game_time: float = 90.0   # Seconds into the game
    phase: str = "early"       # early, mid, late

    def clone(self) -> "LaneState":
        """Create a deep copy for simulation rollouts."""
        return copy.deepcopy(self)

    @property
    def my_hp_pct(self) -> float:
        return (self.my_hp / self.my_hp_max * 100) if self.my_hp_max > 0 else 0

    @property
    def enemy_hp_pct(self) -> float:
        return (self.enemy_hp / self.enemy_hp_max * 100) if self.enemy_hp_max > 0 else 0

    @property
    def my_mana_pct(self) -> float:
        return (self.my_mana / self.my_mana_max * 100) if self.my_mana_max > 0 else 0

    @property
    def has_ult(self) -> bool:
        return self.my_r_cd <= 0 and self.my_level >= 6

    @property
    def enemy_has_ult_est(self) -> bool:
        return self.enemy_r_cd_est <= 0 and self.enemy_level >= 6

    @property
    def has_flash(self) -> bool:
        return self.my_flash_cd <= 0

    @property
    def gank_risk(self) -> float:
        """0-1 score of how likely you are to get ganked right now."""
        risk = 0.0
        # Extended position = more risk
        if self.my_position == Position.EXTENDED:
            risk += 0.3
        elif self.my_position == Position.MIDDLE:
            risk += 0.1
        # Unknown jungler = more risk
        if self.enemy_jg_location == EnemyJgLocation.UNKNOWN:
            risk += 0.2
        elif self.enemy_jg_location == EnemyJgLocation.MID:
            risk += 0.4
        # Haven't seen jungler in a while = more risk
        if self.enemy_jg_last_seen > 30:
            risk += 0.15
        # No flash = way more vulnerable
        if not self.has_flash:
            risk += 0.2
        return min(1.0, risk)

    def to_dict(self) -> dict:
        """Serialize to dict for JSON/API."""
        d = {}
        for k, v in self.__dict__.items():
            if isinstance(v, (Position, WavePosition, EnemyJgLocation)):
                d[k] = v.value
            elif isinstance(v, list):
                d[k] = list(v)
            else:
                d[k] = v
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "LaneState":
        """Deserialize from dict."""
        state = cls()
        for k, v in data.items():
            if k == "my_position" or k == "enemy_position":
                setattr(state, k, Position(v))
            elif k == "wave_position":
                state.wave_position = WavePosition(v)
            elif k == "enemy_jg_location":
                state.enemy_jg_location = EnemyJgLocation(v)
            elif hasattr(state, k):
                setattr(state, k, v)
        return state
