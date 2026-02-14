"""
Game State — the snapshot of everything happening in a simulated match at any moment.

This is the central data structure. The simulation loop reads and writes to this.
Think of it like a giant scoreboard that tracks every detail of the game.
"""

from dataclasses import dataclass, field
from enum import Enum


class GamePhase(Enum):
    EARLY = "early"     # 0:00 - 14:00
    MID = "mid"         # 14:00 - 25:00
    LATE = "late"       # 25:00+


class Role(Enum):
    TOP = "top"
    JUNGLE = "jungle"
    MID = "mid"
    ADC = "adc"
    SUPPORT = "support"


class DragonType(Enum):
    INFERNAL = "infernal"
    MOUNTAIN = "mountain"
    OCEAN = "ocean"
    CLOUD = "cloud"
    HEXTECH = "hextech"
    CHEMTECH = "chemtech"
    ELDER = "elder"


@dataclass
class PlayerState:
    """Everything about one player at a moment in the game."""
    champion_id: str
    role: Role
    player_name: str = ""

    # Progression
    level: int = 1
    gold: float = 500.0          # Starting gold
    cs: int = 0
    xp: float = 0.0

    # Combat stats
    kills: int = 0
    deaths: int = 0
    assists: int = 0

    # Items (list of item IDs the player has purchased)
    items: list = field(default_factory=list)

    # Skills: how many points in each ability
    skill_points: dict = field(default_factory=lambda: {"Q": 0, "W": 0, "E": 0, "R": 0})

    # Status
    alive: bool = True
    respawn_at: float = 0.0      # game_time when they come back to life

    # Summoner spell cooldowns (0 = ready, >0 = seconds until ready)
    flash_cd: float = 0.0
    tp_cd: float = 0.0

    # Calculated combat power (updated each tick based on stats + items + level)
    combat_power: float = 100.0

    def is_flash_up(self) -> bool:
        return self.flash_cd <= 0

    def is_tp_up(self) -> bool:
        return self.tp_cd <= 0


@dataclass
class TeamState:
    """Everything about one team at a moment in the game."""
    team_id: str
    side: str               # "blue" or "red"
    players: list[PlayerState] = field(default_factory=list)

    # Structures
    towers_standing: int = 11   # starts with 11 towers (3 lanes x 3 + 2 nexus)
    inhibitors_up: int = 3

    # Objectives
    dragons_taken: list[DragonType] = field(default_factory=list)
    dragon_soul: DragonType | None = None
    barons_taken: int = 0
    baron_buff_active: bool = False
    baron_buff_expires: float = 0.0
    heralds_taken: int = 0
    grubs_taken: int = 0

    @property
    def total_gold(self) -> float:
        return sum(p.gold for p in self.players)

    @property
    def total_kills(self) -> int:
        return sum(p.kills for p in self.players)

    @property
    def alive_count(self) -> int:
        return sum(1 for p in self.players if p.alive)

    def get_player_by_role(self, role: Role) -> PlayerState | None:
        for p in self.players:
            if p.role == role:
                return p
        return None


@dataclass
class GameState:
    """The complete state of a simulated match."""
    blue_team: TeamState
    red_team: TeamState
    patch: str = ""

    # Time tracking
    game_time: float = 0.0       # seconds elapsed
    phase: GamePhase = GamePhase.EARLY

    # Game status
    game_over: bool = False
    winner: str | None = None    # "blue" or "red"

    # Objective timers (seconds until available; 0 = available now)
    next_dragon_spawn: float = 300.0    # 5:00
    next_herald_spawn: float = 840.0    # 14:00
    next_baron_spawn: float = 1200.0    # 20:00
    grubs_available: bool = True        # Available at 5:00, replaced by herald at 14:00

    # Dragon tracking
    dragons_spawned: int = 0
    soul_point: int = 4                 # dragons needed for soul

    def update_phase(self):
        """Check if we should transition to the next game phase."""
        if self.game_time >= 1500:    # 25:00
            self.phase = GamePhase.LATE
        elif self.game_time >= 840:   # 14:00
            self.phase = GamePhase.MID

    def all_players(self) -> list[PlayerState]:
        """Get all 10 players."""
        return self.blue_team.players + self.red_team.players

    def gold_diff(self) -> float:
        """Blue team's gold advantage (positive = blue ahead)."""
        return self.blue_team.total_gold - self.red_team.total_gold

    def get_team(self, side: str) -> TeamState:
        return self.blue_team if side == "blue" else self.red_team

    def get_opponent(self, side: str) -> TeamState:
        return self.red_team if side == "blue" else self.blue_team
