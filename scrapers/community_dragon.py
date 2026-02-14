"""
CommunityDragon scraper.
Fetches champion base stats, item data, and patch info from Riot's raw data files.
This is your source of truth for game mechanics numbers.

Usage:
    python -m scrapers.community_dragon
"""

import json
from pathlib import Path

from scrapers.base_scraper import BaseScraper

# CommunityDragon hosts Riot's raw game data files
CDRAGON_BASE = "https://raw.communitydragon.org/latest"


class CommunityDragonScraper(BaseScraper):
    """
    Fetches champion stats, items, and other game data from CommunityDragon.
    This data comes directly from Riot's game client files, so it's 100% accurate
    for the current patch.
    """

    def __init__(self):
        super().__init__(
            source_name="community_dragon",
            base_url="https://raw.communitydragon.org",
            requests_per_second=1.0,  # CDragon is a CDN, can go faster
        )

    def fetch_all_champions(self) -> list[dict] | None:
        """
        Fetch the list of all champions with their basic info.
        Returns a list of champion objects with id, name, and title.
        """
        url = f"{CDRAGON_BASE}/plugins/rcp-be-lol-game-data/global/default/v1/champion-summary.json"
        data = self.fetch(url)
        if data is None:
            return None

        # Filter out the "-1" entry (placeholder)
        champions = [c for c in data if c.get("id", -1) > 0]
        print(f"  [CHAMPIONS] Found {len(champions)} champions")
        return champions

    def fetch_champion_details(self, champion_id: int) -> dict | None:
        """
        Fetch detailed stats for a specific champion.
        Includes base stats, stat growth, abilities, and more.

        Args:
            champion_id: Riot's numeric champion ID (e.g., 266 for Aatrox)
        """
        url = f"{CDRAGON_BASE}/plugins/rcp-be-lol-game-data/global/default/v1/champions/{champion_id}.json"
        return self.fetch(url)

    def fetch_all_items(self) -> list[dict] | None:
        """
        Fetch data for all items in the game.
        Includes cost, stats, build path, and descriptions.
        """
        url = f"{CDRAGON_BASE}/plugins/rcp-be-lol-game-data/global/default/v1/items.json"
        data = self.fetch(url)
        if data is None:
            return None

        # Filter out removed/unavailable items
        items = [i for i in data if i.get("priceTotal", 0) > 0]
        print(f"  [ITEMS] Found {len(items)} purchasable items")
        return items

    def extract_champion_stats(self, champion_data: dict) -> dict:
        """
        Pull out the key stats we need for simulation from raw champion data.
        Returns a clean dict with just the fields we care about.
        """
        # The exact structure depends on CDragon's format
        # This extracts what we need for the champions table
        return {
            "champion_id": champion_data.get("alias", champion_data.get("name", "")),
            "display_name": champion_data.get("name", ""),
            "base_stats": {
                "hp": champion_data.get("hp", 0),
                "hpperlevel": champion_data.get("hpperlevel", 0),
                "mp": champion_data.get("mp", 0),
                "armor": champion_data.get("armor", 0),
                "armorperlevel": champion_data.get("armorperlevel", 0),
                "spellblock": champion_data.get("spellblock", 0),
                "attackdamage": champion_data.get("attackdamage", 0),
                "attackspeed": champion_data.get("attackspeed", 0),
                "attackrange": champion_data.get("attackrange", 0),
                "movespeed": champion_data.get("movespeed", 0),
            },
        }

    def extract_item_data(self, item_data: dict) -> dict:
        """
        Pull out key item fields for the items table.
        """
        return {
            "item_id": item_data.get("id", 0),
            "name": item_data.get("name", ""),
            "total_cost": item_data.get("priceTotal", 0),
            "description": item_data.get("description", ""),
            "from_items": item_data.get("from", []),
        }


def main():
    """Test the CommunityDragon scraper."""
    scraper = CommunityDragonScraper()

    if not scraper.health_check():
        print("CommunityDragon appears to be down.")
        return

    # Fetch champion list
    print("\n--- Fetching Champions ---")
    champions = scraper.fetch_all_champions()
    if champions:
        print(f"First 5 champions: {[c.get('name') for c in champions[:5]]}")

    # Fetch items
    print("\n--- Fetching Items ---")
    items = scraper.fetch_all_items()
    if items:
        print(f"First 5 items: {[i.get('name') for i in items[:5]]}")

    scraper.close()
    print("\nDone! Champion and item data is cached in data/raw/community_dragon/")


if __name__ == "__main__":
    main()
