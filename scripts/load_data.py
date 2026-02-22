"""
Load scraped data into the SQLite database.

Reads the JSON files from data/raw/ and inserts them into the proper tables.
Run this after scraping to populate the database with real data.

Usage:
    python -m scripts.load_data
"""

import json
import sqlite3
from pathlib import Path

# Project root
ROOT = Path(__file__).parent.parent
DATA_DIR = ROOT / "data" / "raw"


def get_connection() -> sqlite3.Connection:
    db_path = ROOT / "data" / "rift_engine.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def load_champions(conn: sqlite3.Connection):
    """Load champion base stats from Data Dragon JSON into the champions table."""
    champ_file = DATA_DIR / "ddragon" / "champions.json"
    if not champ_file.exists():
        print("  [SKIP] No champion data found at", champ_file)
        return 0

    with open(champ_file) as f:
        champions = json.load(f)

    count = 0
    for name, data in champions.items():
        stats = data.get("stats", {})
        tags = data.get("tags", [])

        # Split base stats and growth stats
        base_stats = {
            "hp": stats.get("hp", 0),
            "mp": stats.get("mp", 0),
            "movespeed": stats.get("movespeed", 0),
            "armor": stats.get("armor", 0),
            "spellblock": stats.get("spellblock", 0),
            "attackrange": stats.get("attackrange", 0),
            "hpregen": stats.get("hpregen", 0),
            "mpregen": stats.get("mpregen", 0),
            "attackdamage": stats.get("attackdamage", 0),
            "attackspeed": stats.get("attackspeed", 0),
        }

        growth_stats = {
            "hp": stats.get("hpperlevel", 0),
            "mp": stats.get("mpperlevel", 0),
            "armor": stats.get("armorperlevel", 0),
            "spellblock": stats.get("spellblockperlevel", 0),
            "hpregen": stats.get("hpregenperlevel", 0),
            "mpregen": stats.get("mpregenperlevel", 0),
            "attackdamage": stats.get("attackdamageperlevel", 0),
            "attackspeed": stats.get("attackspeedperlevel", 0),
        }

        # Figure out resource type from mp
        if stats.get("mp", 0) == 0:
            resource_type = "none"
        elif stats.get("mp", 0) == 200:
            resource_type = "energy"
        else:
            resource_type = "mana"

        # Primary archetype from tags
        archetype = tags[0].lower() if tags else "unknown"

        conn.execute("""
            INSERT OR REPLACE INTO champions
            (champion_id, display_name, archetype, base_stats, stat_growth, abilities, resource_type)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            data.get("id", name),
            name,
            archetype,
            json.dumps(base_stats),
            json.dumps(growth_stats),
            json.dumps({"tags": tags}),  # placeholder — abilities need separate scrape
            resource_type
        ))
        count += 1

    conn.commit()
    print(f"  [OK] Loaded {count} champions into database")
    return count


def load_items(conn: sqlite3.Connection):
    """Load item data from Data Dragon JSON into the items table."""
    item_file = DATA_DIR / "ddragon" / "items.json"
    if not item_file.exists():
        print("  [SKIP] No item data found at", item_file)
        return 0

    with open(item_file) as f:
        items = json.load(f)

    count = 0
    for item_id, data in items.items():
        gold = data.get("gold", {})
        stats = data.get("stats", {})
        tags = data.get("tags", [])
        build_from = data.get("from", [])

        # Categorize the item
        total_cost = gold.get("total", 0)
        if total_cost <= 500:
            category = "starter"
        elif total_cost <= 1200:
            category = "component"
        elif "Boots" in tags or "boots" in data.get("name", "").lower():
            category = "boots"
        else:
            category = "legendary"

        conn.execute("""
            INSERT OR REPLACE INTO items
            (item_id, name, total_cost, stats, passive, category, build_path)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            int(item_id),
            data.get("name", "Unknown"),
            total_cost,
            json.dumps(stats),
            data.get("description", ""),
            category,
            json.dumps(build_from)
        ))
        count += 1

    conn.commit()
    print(f"  [OK] Loaded {count} items into database")
    return count


def load_champion_meta(conn: sqlite3.Connection):
    """Load U.GG meta data (win rates, builds, counters) into champion_meta table."""
    meta_file = DATA_DIR / "ugg" / "champion_meta.json"
    if not meta_file.exists():
        print("  [SKIP] No U.GG meta data found at", meta_file)
        return 0

    with open(meta_file) as f:
        meta = json.load(f)

    patch = meta.get("patch", "unknown")
    count = 0

    for champ_name, data in meta.get("champions", {}).items():
        # Build matchups dict from counters list
        matchups = {}
        for counter in data.get("counters", []):
            matchups[counter["name"]] = counter.get("wr_against", 50.0)

        conn.execute("""
            INSERT OR REPLACE INTO champion_meta
            (champion_id, patch, role, win_rate, pick_rate, ban_rate,
             best_runes, core_build, skill_order, matchups, source)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            champ_name,
            patch,
            data.get("role", "unknown"),
            data.get("win_rate", 0),
            data.get("pick_rate", 0),
            data.get("ban_rate", 0),
            json.dumps({"keystone": data.get("keystone", ""), "secondary": data.get("secondary_tree", "")}),
            json.dumps(data.get("build_variants", [])),
            json.dumps(data.get("skill_priority", [])),
            json.dumps(matchups),
            "u.gg"
        ))
        count += 1

    conn.commit()
    print(f"  [OK] Loaded meta data for {count} champions (patch {patch})")
    return count


def main():
    print("=" * 50)
    print("Rift Engine — Loading Data into Database")
    print("=" * 50)

    # First, make sure tables exist
    from warehouse.schema import create_tables
    create_tables()

    conn = get_connection()

    print("\nLoading champion base stats...")
    load_champions(conn)

    print("\nLoading item data...")
    load_items(conn)

    print("\nLoading champion meta (U.GG)...")
    load_champion_meta(conn)

    # Print summary
    print("\n" + "=" * 50)
    print("Database Summary:")
    tables = ["champions", "items", "champion_meta", "matches", "match_players"]
    for table in tables:
        count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        print(f"  {table}: {count} rows")
    print("=" * 50)

    conn.close()


if __name__ == "__main__":
    main()
