"""
Patch Note Decoder — Uses Firecrawl to extract and analyze League of Legends patch notes.

How it works:
1. Finds the latest patch notes URL from Riot's news page
2. Uses Firecrawl's /extract to pull structured champion/item/system changes
3. Stores everything in SQLite for history
4. Can summarize changes by role (mid, top, jungle, etc.)

Usage:
    from scrapers.patch_decoder import PatchDecoder
    decoder = PatchDecoder()
    patch = decoder.decode_latest()
    mid_summary = decoder.summarize_by_role(patch.version, "mid")
"""

import json
import re
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import httpx
from dotenv import load_dotenv
import os

load_dotenv(Path(__file__).parent.parent / ".env")

# ─── Data Models ───

@dataclass
class PatchChange:
    """One individual change in a patch (e.g., 'Ahri Q damage increased')."""
    change_type: str        # 'champion_buff', 'champion_nerf', 'champion_adjust', 'item_change', 'system_change'
    target_name: str        # champion or item name
    ability: str = ""       # Q/W/E/R/Passive or empty
    description: str = ""   # human-readable description
    roles_affected: list[str] = field(default_factory=list)  # ["mid", "support"]
    impact_score: float = 0.0  # -3 (huge nerf) to +3 (huge buff)
    raw_detail: str = ""    # original text from patch notes


@dataclass
class PatchResult:
    """Complete decoded patch."""
    version: str
    url: str
    changes: list[PatchChange]
    extracted_at: str
    raw_json: dict = field(default_factory=dict)


# Role mapping — which champions primarily play which roles
# This is a rough heuristic; Firecrawl's extraction handles most of it
ROLE_KEYWORDS = {
    "top": ["top", "toplaner", "bruiser", "juggernaut", "tank"],
    "jungle": ["jungle", "jungler", "jg"],
    "mid": ["mid", "midlaner", "mage", "assassin"],
    "adc": ["adc", "bot", "marksman", "botlaner"],
    "support": ["support", "supp", "enchanter", "engage"],
}


class PatchDecoder:
    """Decodes League of Legends patch notes using Firecrawl."""

    PATCH_NEWS_URL = "https://www.leagueoflegends.com/en-us/news/game-updates/"
    PATCH_BASE_URL = "https://www.leagueoflegends.com/en-us/news/game-updates/"

    def __init__(self, db_path: Optional[Path] = None):
        self.api_key = os.getenv("FIRECRAWL_API_KEY", "")
        if not self.api_key:
            raise ValueError("FIRECRAWL_API_KEY not found in .env")

        self.db_path = db_path or (Path(__file__).parent.parent / "data" / "rift_engine.db")

        # Lazy import — only load firecrawl when actually needed
        try:
            from firecrawl import FirecrawlApp
            self.firecrawl = FirecrawlApp(api_key=self.api_key)
        except ImportError:
            raise ImportError("firecrawl-py not installed. Run: pip install firecrawl-py")

    def detect_latest_patch(self) -> dict:
        """
        Find the newest patch notes URL from Riot's game updates page.

        Returns dict with 'url', 'title', 'version' (parsed from title).
        Falls back to scraping with httpx if Firecrawl fails.
        """
        print("🔍 Detecting latest patch notes...")

        # Strategy 1: Use Firecrawl to scrape the news listing page
        try:
            result = self.firecrawl.scrape(
                self.PATCH_NEWS_URL,
                formats=["markdown"]
            )
            markdown = result.markdown if hasattr(result, "markdown") else (result.get("markdown", "") if isinstance(result, dict) else "")

            # Find patch note links in the markdown
            # Pattern: [Patch X.Y Notes](url) or similar
            patch_pattern = r'\[.*?[Pp]atch\s+(\d+\.\d+).*?\]\((https?://[^\)]+)\)'
            matches = re.findall(patch_pattern, markdown)

            if matches:
                version, url = matches[0]  # First match = latest
                return {"version": version, "url": url, "title": f"Patch {version} Notes"}

            # Fallback pattern: just find URLs with "patch" in them
            url_pattern = r'(https://www\.leagueoflegends\.com/en-us/news/game-updates/patch-[\d-]+-notes/?)'
            urls = re.findall(url_pattern, markdown)
            if urls:
                url = urls[0]
                # Extract version from URL like "patch-25-3-notes"
                ver_match = re.search(r'patch-(\d+)-(\d+)-notes', url)
                version = f"{ver_match.group(1)}.{ver_match.group(2)}" if ver_match else "unknown"
                return {"version": version, "url": url, "title": f"Patch {version} Notes"}

        except Exception as e:
            print(f"⚠️ Firecrawl scrape failed: {e}")

        # Strategy 2: Direct HTTP request as fallback
        try:
            resp = httpx.get(self.PATCH_NEWS_URL, follow_redirects=True, timeout=15)
            # Look for patch note links in HTML
            url_pattern = r'href="(/en-us/news/game-updates/patch-(\d+)-(\d+)-notes/?)"'
            matches = re.findall(url_pattern, resp.text)
            if matches:
                path, major, minor = matches[0]
                url = f"https://www.leagueoflegends.com{path}"
                version = f"{major}.{minor}"
                return {"version": version, "url": url, "title": f"Patch {version} Notes"}
        except Exception as e:
            print(f"⚠️ HTTP fallback failed: {e}")

        raise RuntimeError("Could not detect latest patch notes. The page layout may have changed.")

    def extract_patch_notes(self, url: str) -> dict:
        """
        Use Firecrawl /extract to pull structured data from a patch notes page.

        Returns raw extracted JSON with champion_changes, item_changes, system_changes.
        """
        print(f"📄 Extracting patch notes from: {url}")

        schema = {
            "type": "object",
            "properties": {
                "patch_version": {"type": "string", "description": "The patch version number like 25.3 or 14.24"},
                "champion_changes": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "champion_name": {"type": "string"},
                            "change_type": {"type": "string", "enum": ["buff", "nerf", "adjust"]},
                            "abilities_affected": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Which abilities changed: Q, W, E, R, Passive, Base Stats"
                            },
                            "description": {
                                "type": "string",
                                "description": "Concise summary of what changed and the specific numbers"
                            },
                            "roles_affected": {
                                "type": "array",
                                "items": {"type": "string", "enum": ["top", "jungle", "mid", "adc", "support"]},
                                "description": "Which roles this champion is commonly played in"
                            },
                            "impact_score": {
                                "type": "number",
                                "description": "How impactful is this change? -3 (huge nerf) to +3 (huge buff). 0 = neutral adjust."
                            }
                        }
                    }
                },
                "item_changes": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "item_name": {"type": "string"},
                            "change_type": {"type": "string", "enum": ["buff", "nerf", "adjust", "new", "removed"]},
                            "description": {"type": "string"},
                            "roles_affected": {
                                "type": "array",
                                "items": {"type": "string", "enum": ["top", "jungle", "mid", "adc", "support"]}
                            }
                        }
                    }
                },
                "system_changes": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "system_name": {"type": "string", "description": "e.g. Dragon, Baron, Turret Plating, Runes, etc."},
                            "description": {"type": "string"}
                        }
                    }
                }
            }
        }

        try:
            result = self.firecrawl.extract(
                urls=[url],
                prompt=(
                    "Extract ALL champion changes, item changes, and system/objective changes "
                    "from these League of Legends patch notes. For each champion change, include "
                    "the specific ability (Q/W/E/R/Passive/Base Stats), whether it's a buff or nerf, "
                    "the exact number changes (e.g., 'damage 80/120/160 → 90/130/170'), and which "
                    "roles are most impacted. Rate impact from -3 (devastating nerf) to +3 (massive buff)."
                ),
                schema=schema,
            )

            # Handle different response formats from firecrawl-py
            if isinstance(result, dict):
                return result.get("data", result)
            elif hasattr(result, "data"):
                return result.data if isinstance(result.data, dict) else {"raw": str(result.data)}
            else:
                return {"raw": str(result)}

        except Exception as e:
            print(f"❌ Firecrawl extract failed: {e}")
            raise

    def parse_changes(self, raw_data: dict) -> list[PatchChange]:
        """
        Normalize raw Firecrawl output into a list of PatchChange objects.
        Handles missing fields, weird formats, etc.
        """
        changes = []

        # Champion changes
        for champ in raw_data.get("champion_changes", []):
            change_type_raw = champ.get("change_type", "adjust")
            change_type = f"champion_{change_type_raw}"

            abilities = champ.get("abilities_affected", [])
            if abilities:
                # Create one PatchChange per ability for granularity
                for ability in abilities:
                    changes.append(PatchChange(
                        change_type=change_type,
                        target_name=champ.get("champion_name", "Unknown"),
                        ability=ability,
                        description=champ.get("description", ""),
                        roles_affected=champ.get("roles_affected", []),
                        impact_score=float(champ.get("impact_score", 0)),
                        raw_detail=json.dumps(champ),
                    ))
            else:
                changes.append(PatchChange(
                    change_type=change_type,
                    target_name=champ.get("champion_name", "Unknown"),
                    description=champ.get("description", ""),
                    roles_affected=champ.get("roles_affected", []),
                    impact_score=float(champ.get("impact_score", 0)),
                    raw_detail=json.dumps(champ),
                ))

        # Item changes — handle varying field names from Firecrawl
        for item in raw_data.get("item_changes", []):
            name = item.get("item_name") or item.get("item") or item.get("name") or "Unknown"
            desc = item.get("description") or item.get("change") or ""
            # Parse impact from string or number
            impact_raw = item.get("impact") or item.get("impact_score") or 0
            try:
                impact = float(str(impact_raw).replace("+", ""))
            except (ValueError, TypeError):
                impact = 0.0
            changes.append(PatchChange(
                change_type="item_change",
                target_name=name,
                description=desc,
                roles_affected=item.get("roles_affected", []),
                impact_score=impact,
                raw_detail=json.dumps(item),
            ))

        # System changes — handle varying field names
        for sys_change in raw_data.get("system_changes", []):
            name = sys_change.get("system_name") or sys_change.get("system") or sys_change.get("name") or "System"
            desc = sys_change.get("description") or sys_change.get("change") or ""
            changes.append(PatchChange(
                change_type="system_change",
                target_name=name,
                description=desc,
                raw_detail=json.dumps(sys_change),
            ))

        return changes

    def store_patch(self, patch_version: str, url: str, changes: list[PatchChange], raw_json: dict):
        """Save patch data to SQLite."""
        conn = sqlite3.connect(str(self.db_path))
        c = conn.cursor()

        # Ensure tables exist
        from warehouse.schema import create_patch_tables
        create_patch_tables(conn)

        now = datetime.now(timezone.utc).isoformat()

        # Upsert patch record
        c.execute(
            "INSERT OR REPLACE INTO patches (patch_version, url, extracted_at, raw_json) VALUES (?, ?, ?, ?)",
            (patch_version, url, now, json.dumps(raw_json))
        )

        # Delete old changes for this patch (in case of re-decode)
        c.execute("DELETE FROM patch_changes WHERE patch_version = ?", (patch_version,))

        # Insert changes
        for ch in changes:
            c.execute(
                """INSERT INTO patch_changes 
                   (patch_version, change_type, target_name, ability, description, roles_affected, impact_score, raw_detail)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    patch_version,
                    ch.change_type,
                    ch.target_name,
                    ch.ability,
                    ch.description,
                    json.dumps(ch.roles_affected),
                    ch.impact_score,
                    ch.raw_detail,
                )
            )

        conn.commit()
        conn.close()
        print(f"💾 Stored {len(changes)} changes for patch {patch_version}")

    def summarize_by_role(self, patch_version: str, role: str) -> dict:
        """
        Get a role-specific summary of patch changes.
        
        Returns:
            {
                "role": "mid",
                "patch": "25.3",
                "buffs": [...],
                "nerfs": [...],
                "item_changes": [...],
                "system_changes": [...],
                "tldr": "Short summary"
            }
        """
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row

        rows = conn.execute(
            "SELECT * FROM patch_changes WHERE patch_version = ?",
            (patch_version,)
        ).fetchall()
        conn.close()

        buffs = []
        nerfs = []
        item_changes = []
        system_changes = []

        for row in rows:
            roles = json.loads(row["roles_affected"]) if row["roles_affected"] else []
            
            # Include if role matches OR if no roles specified (system changes affect everyone)
            if role not in roles and roles:
                continue

            entry = {
                "target": row["target_name"],
                "ability": row["ability"],
                "description": row["description"],
                "impact": row["impact_score"],
            }

            if row["change_type"] == "champion_buff":
                buffs.append(entry)
            elif row["change_type"] == "champion_nerf":
                nerfs.append(entry)
            elif row["change_type"] == "item_change":
                item_changes.append(entry)
            elif row["change_type"] == "system_change":
                system_changes.append(entry)

        # Build TLDR
        tldr_parts = []
        if buffs:
            names = list(set(b["target"] for b in buffs))
            tldr_parts.append(f"BUFFED: {', '.join(names)}")
        if nerfs:
            names = list(set(n["target"] for n in nerfs))
            tldr_parts.append(f"NERFED: {', '.join(names)}")
        if item_changes:
            tldr_parts.append(f"{len(item_changes)} item change(s)")
        if system_changes:
            tldr_parts.append(f"{len(system_changes)} system change(s)")

        return {
            "role": role,
            "patch": patch_version,
            "buffs": buffs,
            "nerfs": nerfs,
            "item_changes": item_changes,
            "system_changes": system_changes,
            "tldr": " | ".join(tldr_parts) if tldr_parts else "No significant changes for this role.",
        }

    def decode_latest(self) -> PatchResult:
        """Full pipeline: detect → extract → parse → store → return."""
        patch_info = self.detect_latest_patch()
        raw = self.extract_patch_notes(patch_info["url"])
        changes = self.parse_changes(raw)

        version = raw.get("patch_version", patch_info["version"])
        now = datetime.now(timezone.utc).isoformat()

        self.store_patch(version, patch_info["url"], changes, raw)

        return PatchResult(
            version=version,
            url=patch_info["url"],
            changes=changes,
            extracted_at=now,
            raw_json=raw,
        )

    def decode_url(self, url: str, version: str = "unknown") -> PatchResult:
        """Decode a specific patch URL (for manual/historical use)."""
        raw = self.extract_patch_notes(url)
        changes = self.parse_changes(raw)
        version = raw.get("patch_version", version)
        now = datetime.now(timezone.utc).isoformat()

        self.store_patch(version, url, changes, raw)

        return PatchResult(
            version=version, url=url, changes=changes,
            extracted_at=now, raw_json=raw,
        )

    def get_stored_patches(self) -> list[dict]:
        """List all patches we've decoded."""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT patch_version, url, extracted_at FROM patches ORDER BY extracted_at DESC").fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get_stored_changes(self, patch_version: str) -> list[dict]:
        """Get all changes for a stored patch."""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM patch_changes WHERE patch_version = ? ORDER BY change_type, target_name",
            (patch_version,)
        ).fetchall()
        conn.close()
        results = []
        for r in rows:
            d = dict(r)
            d["roles_affected"] = json.loads(d["roles_affected"]) if d["roles_affected"] else []
            results.append(d)
        return results
