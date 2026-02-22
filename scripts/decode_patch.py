#!/usr/bin/env python3
"""
CLI tool to decode League of Legends patch notes.

Usage:
    python scripts/decode_patch.py                    # Decode latest patch
    python scripts/decode_patch.py --url URL          # Decode specific URL
    python scripts/decode_patch.py --role mid          # Show mid lane summary for latest stored patch
    python scripts/decode_patch.py --list              # List all stored patches
"""

import sys
import argparse
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from scrapers.patch_decoder import PatchDecoder


def main():
    parser = argparse.ArgumentParser(description="Decode LoL patch notes with Firecrawl")
    parser.add_argument("--url", help="Specific patch notes URL to decode")
    parser.add_argument("--role", help="Show summary for a specific role (top/jungle/mid/adc/support)")
    parser.add_argument("--patch", help="Patch version for role summary (default: latest stored)")
    parser.add_argument("--list", action="store_true", help="List all stored patches")
    parser.add_argument("--detect", action="store_true", help="Just detect the latest patch URL")
    args = parser.parse_args()

    try:
        decoder = PatchDecoder()
    except Exception as e:
        print(f"❌ Error initializing decoder: {e}")
        sys.exit(1)

    if args.detect:
        info = decoder.detect_latest_patch()
        print(f"Latest patch: {info['version']}")
        print(f"URL: {info['url']}")
        return

    if args.list:
        patches = decoder.get_stored_patches()
        if not patches:
            print("No patches stored yet. Run without --list to decode one.")
            return
        print("Stored patches:")
        for p in patches:
            print(f"  {p['patch_version']} — {p['url']} (decoded {p['extracted_at']})")
        return

    if args.role:
        version = args.patch
        if not version:
            patches = decoder.get_stored_patches()
            if not patches:
                print("No patches stored. Decode one first.")
                return
            version = patches[0]["patch_version"]

        summary = decoder.summarize_by_role(version, args.role)
        print(f"\n{'='*50}")
        print(f"  PATCH {summary['patch']} — {summary['role'].upper()} LANE SUMMARY")
        print(f"{'='*50}")
        print(f"\nTLDR: {summary['tldr']}")

        if summary['buffs']:
            print(f"\n🟢 BUFFS:")
            for b in summary['buffs']:
                print(f"  • {b['target']} ({b.get('ability','')}) — {b['description']}")

        if summary['nerfs']:
            print(f"\n🔴 NERFS:")
            for n in summary['nerfs']:
                print(f"  • {n['target']} ({n.get('ability','')}) — {n['description']}")

        if summary['item_changes']:
            print(f"\n🔧 ITEM CHANGES:")
            for i in summary['item_changes']:
                print(f"  • {i['target']} — {i['description']}")

        if summary['system_changes']:
            print(f"\n⚙️ SYSTEM CHANGES:")
            for sc in summary['system_changes']:
                print(f"  • {sc['target']} — {sc['description']}")
        return

    # Default: decode latest (or specific URL)
    print("🚀 Starting patch decode...")
    if args.url:
        result = decoder.decode_url(args.url)
    else:
        result = decoder.decode_latest()

    print(f"\n✅ Patch {result.version} decoded!")
    print(f"   URL: {result.url}")
    print(f"   Changes found: {len(result.changes)}")

    # Quick summary
    buffs = [c for c in result.changes if 'buff' in c.change_type]
    nerfs = [c for c in result.changes if 'nerf' in c.change_type]
    items = [c for c in result.changes if c.change_type == 'item_change']
    system = [c for c in result.changes if c.change_type == 'system_change']

    print(f"\n   Champion buffs: {len(buffs)}")
    print(f"   Champion nerfs: {len(nerfs)}")
    print(f"   Item changes: {len(items)}")
    print(f"   System changes: {len(system)}")
    print(f"\nUse --role mid/top/jungle/adc/support for role-specific summary.")


if __name__ == "__main__":
    main()
