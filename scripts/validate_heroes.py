"""Validate heroes.py structure"""

import sys
from pathlib import Path

# Validate the runtime catalog, including the pinned ruleset repairs.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from game.heroes import HEROES

# Define required fields
HERO_REQUIRED = {"name", "health", "armor", "power"}
POWER_REQUIRED = {"id", "name", "cost", "text"}

errors = []
missing_buddies = []

for hero_id, hero_data in HEROES.items():
    hero_name = hero_data.get("name", "UNKNOWN")
    
    # Check hero fields
    for field in HERO_REQUIRED:
        if field not in hero_data:
            errors.append(f"Hero {hero_id} ({hero_name}): Missing '{field}'")
    
    # Check power fields
    if "power" in hero_data and hero_data["power"]:
        power = hero_data["power"]
        for field in POWER_REQUIRED:
            if field not in power or power[field] is None:
                errors.append(f"Hero {hero_id} ({hero_name}) Power: Missing '{field}'")
        if isinstance(power.get("id"), bool) or not isinstance(power.get("id"), int):
            errors.append(
                f"Hero {hero_id} ({hero_name}) Power: 'id' must be an integer"
            )
    elif "power" not in hero_data or hero_data["power"] is None:
        errors.append(f"Hero {hero_id} ({hero_name}): NO POWER")
    
    # Note missing buddy (not required but good to know)
    if "buddy" not in hero_data or hero_data["buddy"] is None:
        missing_buddies.append(f"{hero_id} ({hero_name})")

if errors:
    print(f"❌ {len(errors)} ERRORS FOUND:\n")
    for err in errors:
        print(f"  {err}")
else:
    print("✅ All heroes have required fields!")

if missing_buddies:
    print(f"\n⚠️  {len(missing_buddies)} heroes without buddy:")
    for buddy in missing_buddies[:10]:
        print(f"  {buddy}")
    if len(missing_buddies) > 10:
        print(f"  ... and {len(missing_buddies) - 10} more")
else:
    print("✅ All heroes have buddies!")

print(f"\n📊 Total: {len(HEROES)} heroes checked")
raise SystemExit(1 if errors else 0)
