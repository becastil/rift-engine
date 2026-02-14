"""
Run all scrapers to refresh local data.
Usage: python -m scripts.scrape_all
"""

from scrapers.oracle_elixir import OracleElixirScraper
from scrapers.community_dragon import CommunityDragonScraper
from warehouse.loader import load_champion_data, load_item_data
from warehouse.schema import create_tables


def main():
    print("=== RIFT ENGINE — Full Data Refresh ===\n")

    # Ensure database exists
    create_tables()

    # 1. CommunityDragon (champion + item data)
    print("\n--- CommunityDragon ---")
    cd = CommunityDragonScraper()
    if cd.health_check():
        champions = cd.fetch_all_champions()
        if champions:
            load_champion_data(champions)

        items = cd.fetch_all_items()
        if items:
            load_item_data(items)
    cd.close()

    # 2. Oracle's Elixir (pro match data)
    print("\n--- Oracle's Elixir ---")
    oe = OracleElixirScraper()
    if oe.health_check():
        print("Oracle's Elixir is up. Download CSVs manually from:")
        print("  https://oracleselixir.com/tools/downloads")
        print("Then run: python -m warehouse.loader")
    oe.close()

    print("\n=== Done! ===")


if __name__ == "__main__":
    main()
