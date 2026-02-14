"""
Oracle's Elixir scraper.
Downloads their free CSV files containing pro match data.
This is your PRIMARY source for pro match stats.

Usage:
    python -m scrapers.oracle_elixir
"""

import os
from pathlib import Path

import pandas as pd

from scrapers.base_scraper import BaseScraper

# Oracle's Elixir provides direct CSV downloads
# These URLs may change — check oracleselixir.com/tools/downloads
OE_DOWNLOAD_URL = "https://oracleselixir.com/tools/downloads"


class OracleElixirScraper(BaseScraper):
    """
    Downloads and parses Oracle's Elixir CSV files.
    These CSVs contain one row per player per game for all major pro leagues.
    """

    def __init__(self):
        super().__init__(
            source_name="oracle_elixir",
            base_url="https://oracleselixir.com",
            requests_per_second=0.2,  # Be extra gentle — it's a community site
        )
        self.raw_dir = Path(__file__).parent.parent / "data" / "raw" / "oracle_elixir"
        self.raw_dir.mkdir(parents=True, exist_ok=True)

    def download_csv(self, csv_url: str, filename: str) -> Path | None:
        """
        Download a CSV file from Oracle's Elixir.
        You'll need to find the actual CSV URLs from their downloads page.

        Args:
            csv_url: Direct URL to the CSV file
            filename: What to save it as locally (e.g. "2024_spring.csv")

        Returns:
            Path to the downloaded file, or None if it failed
        """
        output_path = self.raw_dir / filename

        # Skip if we already have it and it's recent
        if output_path.exists():
            print(f"  [EXISTS] {filename} already downloaded")
            return output_path

        self._rate_limit()

        try:
            print(f"  [DOWNLOADING] {filename} from Oracle's Elixir...")
            response = self.client.get(csv_url)
            response.raise_for_status()

            with open(output_path, "wb") as f:
                f.write(response.content)

            print(f"  [DONE] Saved to {output_path}")
            return output_path

        except Exception as e:
            print(f"  [ERROR] Failed to download {filename}: {e}")
            return None

    def parse_csv(self, filepath: Path) -> pd.DataFrame:
        """
        Read an Oracle's Elixir CSV into a pandas DataFrame.
        Handles their specific column naming conventions.
        """
        df = pd.read_csv(filepath, low_memory=False)
        print(f"  [PARSED] {filepath.name}: {len(df)} rows, {len(df.columns)} columns")
        return df

    def extract_matches(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Extract match-level data from the player-level CSV.
        OE has one row per player, so we need to aggregate to get one row per match.
        """
        # Filter to team-level rows (OE includes both player and team rows)
        # Team rows have position == "team"
        if "position" in df.columns:
            team_rows = df[df["position"] == "team"].copy()
        else:
            # Fallback: group by game
            team_rows = df.copy()

        print(f"  [EXTRACTED] {len(team_rows)} team-level rows")
        return team_rows

    def extract_players(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Extract player-level data from the CSV.
        Filters out the team-aggregate rows to get individual player stats.
        """
        if "position" in df.columns:
            player_rows = df[df["position"] != "team"].copy()
        else:
            player_rows = df.copy()

        print(f"  [EXTRACTED] {len(player_rows)} player-level rows")
        return player_rows


def main():
    """
    Run this to test the Oracle's Elixir scraper.
    You'll need to update the CSV URL — get it from oracleselixir.com/tools/downloads
    """
    scraper = OracleElixirScraper()

    # Step 1: Health check
    if not scraper.health_check():
        print("Oracle's Elixir appears to be down. Try again later.")
        return

    print("\nOracle's Elixir is up! To download data:")
    print("1. Go to https://oracleselixir.com/tools/downloads")
    print("2. Find the CSV download link for the season you want")
    print("3. Call scraper.download_csv(url, 'filename.csv')")
    print("\nExample:")
    print("  scraper.download_csv('https://oracleselixir.com/...csv', '2025_spring.csv')")

    scraper.close()


if __name__ == "__main__":
    main()
