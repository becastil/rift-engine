"""
Database schema for Rift Engine.
Creates all the SQLite tables that store match data, champion stats, items, etc.

Think of this like creating empty spreadsheet tabs — each table is a tab with
specific columns, and they link together through shared IDs.

Usage:
    python -m warehouse.schema
"""

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "rift_engine.db"


def get_connection() -> sqlite3.Connection:
    """Get a connection to the database. Creates the file if it doesn't exist."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA journal_mode=WAL")  # Better performance for reads + writes
    conn.execute("PRAGMA foreign_keys=ON")    # Enforce relationships between tables
    return conn


def create_tables():
    """Create all database tables. Safe to run multiple times — won't overwrite existing data."""
    conn = get_connection()
    c = conn.cursor()

    # ─── MATCHES ───
    # One row per game. Links to teams, has outcome info.
    c.execute("""
        CREATE TABLE IF NOT EXISTS matches (
            match_id        TEXT PRIMARY KEY,
            patch           TEXT,
            tournament      TEXT,
            date            TEXT,
            duration_seconds INTEGER,
            blue_team_id    TEXT,
            red_team_id     TEXT,
            winner_side     TEXT,
            first_blood_side TEXT,
            first_tower_side TEXT,
            first_dragon_side TEXT,
            blue_bans       TEXT,       -- JSON array of 5 champion IDs
            red_bans        TEXT,       -- JSON array of 5 champion IDs
            source          TEXT,       -- "oracle_elixir", "gol", "riot_api"
            source_confidence REAL DEFAULT 1.0
        )
    """)

    # ─── MATCH PLAYERS ───
    # One row per player per game (10 rows per game).
    c.execute("""
        CREATE TABLE IF NOT EXISTS match_players (
            match_id        TEXT NOT NULL,
            player_name     TEXT NOT NULL,
            team_id         TEXT,
            side            TEXT,       -- "blue" or "red"
            role            TEXT,       -- "top", "jungle", "mid", "adc", "support"
            champion_id     TEXT,
            kills           INTEGER,
            deaths          INTEGER,
            assists         INTEGER,
            cs              INTEGER,
            gold_earned     INTEGER,
            damage_dealt    INTEGER,
            vision_score    INTEGER,
            gold_at_15      INTEGER,
            cs_at_15        INTEGER,
            xp_diff_at_15   INTEGER,
            PRIMARY KEY (match_id, player_name)
        )
    """)

    # ─── MATCH EVENTS ───
    # Timestamped events within a game (kills, objectives, item purchases).
    c.execute("""
        CREATE TABLE IF NOT EXISTS match_events (
            event_id        INTEGER PRIMARY KEY AUTOINCREMENT,
            match_id        TEXT NOT NULL,
            timestamp_ms    INTEGER,    -- milliseconds into the game
            event_type      TEXT,       -- KILL, TOWER, DRAGON, BARON, HERALD, ITEM_BUY, LEVEL_UP
            actor_player    TEXT,       -- who did the action
            target          TEXT,       -- who/what was affected
            details         TEXT        -- JSON blob with extra info
        )
    """)

    # ─── CHAMPIONS ───
    # Static champion data (base stats, abilities). Updated each patch.
    c.execute("""
        CREATE TABLE IF NOT EXISTS champions (
            champion_id     TEXT PRIMARY KEY,
            display_name    TEXT,
            archetype       TEXT,       -- fighter, mage, assassin, marksman, tank, support
            base_stats      TEXT,       -- JSON: hp, ad, armor, mr, etc.
            stat_growth     TEXT,       -- JSON: per-level increases
            abilities       TEXT,       -- JSON: Q/W/E/R with descriptions + cooldowns
            resource_type   TEXT        -- mana, energy, none, health
        )
    """)

    # ─── CHAMPION META ───
    # Patch-specific data from stats sites (win rates, builds, runes).
    # This changes every 2 weeks when a new patch drops.
    c.execute("""
        CREATE TABLE IF NOT EXISTS champion_meta (
            champion_id     TEXT NOT NULL,
            patch           TEXT NOT NULL,
            role            TEXT NOT NULL,
            win_rate        REAL,
            pick_rate       REAL,
            ban_rate        REAL,
            best_runes      TEXT,       -- JSON: rune page configuration
            core_build      TEXT,       -- JSON: ordered list of core items
            skill_order     TEXT,       -- JSON: e.g. ["Q","W","E","Q","Q","R",...]
            matchups        TEXT,       -- JSON: {opponent: win_rate}
            win_rate_by_length TEXT,    -- JSON: {"15": 0.48, "25": 0.52, ...}
            source          TEXT,       -- "u.gg", "lolalytics"
            PRIMARY KEY (champion_id, patch, role)
        )
    """)

    # ─── ITEMS ───
    # All items in the game with costs and stats.
    c.execute("""
        CREATE TABLE IF NOT EXISTS items (
            item_id         INTEGER PRIMARY KEY,
            name            TEXT,
            total_cost      INTEGER,
            stats           TEXT,       -- JSON: {ad: 40, crit: 25, ...}
            passive         TEXT,       -- description of passive/active effects
            category        TEXT,       -- starter, component, legendary, boots
            build_path      TEXT        -- JSON: list of component item IDs
        )
    """)

    # ─── TEAMS ───
    # Pro teams with their current rosters.
    c.execute("""
        CREATE TABLE IF NOT EXISTS teams (
            team_id         TEXT PRIMARY KEY,
            name            TEXT,
            region          TEXT,       -- LCK, LCS, LEC, LPL, etc.
            active_roster   TEXT        -- JSON: {top: "player", jg: "player", ...}
        )
    """)

    # ─── PATCHES (Firecrawl Patch Decoder) ───
    c.execute("""
        CREATE TABLE IF NOT EXISTS patches (
            patch_version   TEXT PRIMARY KEY,
            url             TEXT,
            extracted_at    TIMESTAMP,
            raw_json        TEXT
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS patch_changes (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            patch_version   TEXT,
            change_type     TEXT,
            target_name     TEXT,
            ability         TEXT,
            description     TEXT,
            roles_affected  TEXT,
            impact_score    REAL,
            raw_detail      TEXT,
            FOREIGN KEY (patch_version) REFERENCES patches(patch_version)
        )
    """)

    conn.commit()
    conn.close()
    print("All database tables created successfully!")
    print(f"Database location: {DB_PATH}")


def create_patch_tables(conn: sqlite3.Connection):
    """Create just the patch tables (used by patch_decoder without full schema rebuild)."""
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS patches (
            patch_version TEXT PRIMARY KEY, url TEXT, extracted_at TIMESTAMP, raw_json TEXT
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS patch_changes (
            id INTEGER PRIMARY KEY AUTOINCREMENT, patch_version TEXT, change_type TEXT,
            target_name TEXT, ability TEXT, description TEXT, roles_affected TEXT,
            impact_score REAL, raw_detail TEXT,
            FOREIGN KEY (patch_version) REFERENCES patches(patch_version)
        )
    """)
    conn.commit()


def table_counts() -> dict:
    """Quick check: how many rows are in each table?"""
    conn = get_connection()
    tables = ["matches", "match_players", "match_events", "champions",
              "champion_meta", "items", "teams"]
    counts = {}
    for table in tables:
        try:
            count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            counts[table] = count
        except sqlite3.OperationalError:
            counts[table] = "TABLE NOT FOUND"
    conn.close()
    return counts


if __name__ == "__main__":
    create_tables()
    print("\nRow counts:")
    for table, count in table_counts().items():
        print(f"  {table}: {count}")
