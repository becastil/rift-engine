"""
Data loader — takes raw scraped data and inserts it into the database tables.

This is the bridge between "raw CSV/JSON files" and "clean database tables."
Each load function handles one data source and knows how to map its columns
to our schema.

Usage:
    python -m warehouse.loader
"""

import json
import sqlite3
from pathlib import Path

import pandas as pd

from warehouse.schema import get_connection, DB_PATH


def load_oracle_elixir_csv(csv_path: str | Path):
    """
    Load an Oracle's Elixir CSV file into the matches and match_players tables.

    OE CSVs have one row per player per game. Team-level rows have position="team".
    We split these into two tables:
    - matches: one row per game (from team-level rows)
    - match_players: one row per player per game
    """
    print(f"Loading Oracle's Elixir data from {csv_path}...")
    df = pd.read_csv(csv_path, low_memory=False)
    print(f"  Raw CSV: {len(df)} rows, {len(df.columns)} columns")

    conn = get_connection()

    # ─── Load match-level data (team rows) ───
    # OE marks team aggregate rows with position == "team"
    if "position" in df.columns:
        team_df = df[df["position"] == "team"].copy()
    else:
        print("  WARNING: No 'position' column found. Column names may differ.")
        print(f"  Available columns: {list(df.columns[:20])}")
        conn.close()
        return

    # Map OE column names to our schema
    # (OE column names may vary — adjust these mappings as needed)
    matches_loaded = 0
    for game_id, game_rows in team_df.groupby("gameid"):
        if len(game_rows) < 2:
            continue

        blue_row = game_rows[game_rows["side"] == "Blue"].iloc[0] if len(game_rows[game_rows["side"] == "Blue"]) > 0 else None
        red_row = game_rows[game_rows["side"] == "Red"].iloc[0] if len(game_rows[game_rows["side"] == "Red"]) > 0 else None

        if blue_row is None or red_row is None:
            continue

        try:
            conn.execute("""
                INSERT OR IGNORE INTO matches
                (match_id, patch, tournament, date, duration_seconds,
                 blue_team_id, red_team_id, winner_side, source, source_confidence)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'oracle_elixir', 1.0)
            """, (
                str(game_id),
                str(blue_row.get("patch", "")),
                str(blue_row.get("league", "")),
                str(blue_row.get("date", "")),
                int(blue_row.get("gamelength", 0)) if pd.notna(blue_row.get("gamelength")) else None,
                str(blue_row.get("teamname", "")),
                str(red_row.get("teamname", "")),
                "blue" if blue_row.get("result") == 1 else "red",
            ))
            matches_loaded += 1
        except Exception as e:
            pass  # Skip duplicates silently

    print(f"  Loaded {matches_loaded} matches")

    # ─── Load player-level data ───
    player_df = df[df["position"] != "team"].copy() if "position" in df.columns else df.copy()

    players_loaded = 0
    for _, row in player_df.iterrows():
        try:
            conn.execute("""
                INSERT OR IGNORE INTO match_players
                (match_id, player_name, team_id, side, role, champion_id,
                 kills, deaths, assists, cs, gold_earned, damage_dealt,
                 vision_score, gold_at_15, cs_at_15, xp_diff_at_15)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                str(row.get("gameid", "")),
                str(row.get("playername", "")),
                str(row.get("teamname", "")),
                str(row.get("side", "")).lower(),
                str(row.get("position", "")).lower(),
                str(row.get("champion", "")),
                int(row["kills"]) if pd.notna(row.get("kills")) else None,
                int(row["deaths"]) if pd.notna(row.get("deaths")) else None,
                int(row["assists"]) if pd.notna(row.get("assists")) else None,
                int(row["total cs"]) if pd.notna(row.get("total cs")) else None,
                int(row["earnedgold"]) if pd.notna(row.get("earnedgold")) else None,
                int(row["damagetochampions"]) if pd.notna(row.get("damagetochampions")) else None,
                int(row["visionscore"]) if pd.notna(row.get("visionscore")) else None,
                int(row["goldat15"]) if pd.notna(row.get("goldat15")) else None,
                int(row["csat15"]) if pd.notna(row.get("csat15")) else None,
                int(row["xpdiffat15"]) if pd.notna(row.get("xpdiffat15")) else None,
            ))
            players_loaded += 1
        except Exception:
            pass

    conn.commit()
    conn.close()
    print(f"  Loaded {players_loaded} player records")
    print("  Done!")


def load_champion_data(champions: list[dict]):
    """
    Load champion data (from CommunityDragon) into the champions table.
    """
    conn = get_connection()
    loaded = 0
    for champ in champions:
        try:
            conn.execute("""
                INSERT OR REPLACE INTO champions
                (champion_id, display_name)
                VALUES (?, ?)
            """, (
                str(champ.get("alias", champ.get("name", ""))),
                str(champ.get("name", "")),
            ))
            loaded += 1
        except Exception:
            pass

    conn.commit()
    conn.close()
    print(f"Loaded {loaded} champions into database")


def load_item_data(items: list[dict]):
    """
    Load item data (from CommunityDragon) into the items table.
    """
    conn = get_connection()
    loaded = 0
    for item in items:
        try:
            conn.execute("""
                INSERT OR REPLACE INTO items
                (item_id, name, total_cost, build_path)
                VALUES (?, ?, ?, ?)
            """, (
                int(item.get("id", 0)),
                str(item.get("name", "")),
                int(item.get("priceTotal", 0)),
                json.dumps(item.get("from", [])),
            ))
            loaded += 1
        except Exception:
            pass

    conn.commit()
    conn.close()
    print(f"Loaded {loaded} items into database")


if __name__ == "__main__":
    from warehouse.schema import create_tables, table_counts

    # Make sure tables exist
    create_tables()

    print("\nCurrent database state:")
    for table, count in table_counts().items():
        print(f"  {table}: {count} rows")

    print("\nTo load Oracle's Elixir data, run:")
    print("  from warehouse.loader import load_oracle_elixir_csv")
    print("  load_oracle_elixir_csv('data/raw/oracle_elixir/your_file.csv')")
