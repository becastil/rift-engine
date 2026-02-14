"""
Base scraper class that all scrapers inherit from.
Handles rate limiting, caching, and health checks so you don't
repeat that logic in every scraper.
"""

import time
import hashlib
import json
import os
from pathlib import Path
from datetime import datetime, timedelta

import httpx

# Where raw scraped files get saved
CACHE_DIR = Path(__file__).parent.parent / "data" / "raw"


class BaseScraper:
    """
    Every scraper extends this class. It gives you:
    - Automatic rate limiting (won't hammer a website too fast)
    - Local file caching (saves responses so you don't re-scrape the same thing)
    - Health checks (verifies a site is up before scraping)
    """

    def __init__(self, source_name: str, base_url: str, requests_per_second: float = 0.5):
        self.source_name = source_name
        self.base_url = base_url
        self.min_delay = 1.0 / requests_per_second  # seconds between requests
        self.last_request_time = 0.0
        self.cache_dir = CACHE_DIR / source_name

        # Create cache directory if it doesn't exist
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        # HTTP client with reasonable timeouts
        self.client = httpx.Client(
            timeout=30.0,
            follow_redirects=True,
            headers={"User-Agent": "RiftEngine/0.1 (personal research project)"},
        )

    def _rate_limit(self):
        """Wait if we're requesting too fast."""
        elapsed = time.time() - self.last_request_time
        if elapsed < self.min_delay:
            time.sleep(self.min_delay - elapsed)
        self.last_request_time = time.time()

    def _cache_key(self, url: str) -> str:
        """Turn a URL into a safe filename for caching."""
        url_hash = hashlib.md5(url.encode()).hexdigest()[:12]
        return f"{datetime.now().strftime('%Y%m%d')}_{url_hash}.json"

    def _get_cached(self, url: str, max_age_hours: int = 24):
        """
        Check if we already scraped this URL recently.
        Returns the cached data if fresh enough, None otherwise.
        """
        cache_file = self.cache_dir / self._cache_key(url)
        if cache_file.exists():
            age = datetime.now() - datetime.fromtimestamp(cache_file.stat().st_mtime)
            if age < timedelta(hours=max_age_hours):
                with open(cache_file, "r") as f:
                    return json.load(f)
        return None

    def _save_cache(self, url: str, data: dict):
        """Save scraped data to the cache."""
        cache_file = self.cache_dir / self._cache_key(url)
        with open(cache_file, "w") as f:
            json.dump(data, f, indent=2, default=str)

    def fetch(self, url: str, use_cache: bool = True) -> dict | None:
        """
        Fetch a URL with rate limiting and caching.
        Returns parsed JSON or {"html": raw_html} for HTML responses.
        """
        # Check cache first
        if use_cache:
            cached = self._get_cached(url)
            if cached is not None:
                print(f"  [CACHE HIT] {url}")
                return cached

        # Rate limit
        self._rate_limit()

        try:
            print(f"  [FETCHING] {url}")
            response = self.client.get(url)
            response.raise_for_status()

            # Try to parse as JSON, fall back to HTML
            try:
                data = response.json()
            except json.JSONDecodeError:
                data = {"html": response.text, "url": url}

            # Cache the result
            if use_cache:
                self._save_cache(url, data)

            return data

        except httpx.HTTPError as e:
            print(f"  [ERROR] Failed to fetch {url}: {e}")
            return None

    def health_check(self) -> bool:
        """
        Quick check: is this data source alive and responding?
        Returns True if the site is reachable.
        """
        try:
            response = self.client.get(self.base_url, timeout=10.0)
            is_healthy = response.status_code == 200
            status = "HEALTHY" if is_healthy else f"UNHEALTHY (status {response.status_code})"
            print(f"[{self.source_name}] {status}")
            return is_healthy
        except Exception as e:
            print(f"[{self.source_name}] UNREACHABLE: {e}")
            return False

    def close(self):
        """Clean up the HTTP client."""
        self.client.close()
