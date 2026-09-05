"""Extract ALL heroes from cards.json"""

import json
from pathlib import Path

cards_file = Path("data/raw/cards.json")
with open(cards_file) as f:
    cards = json.load(f)

# Build ID lookup
cards_by_id = {card["id"]: card for card in cards}

# Extract ALL heroes
heroes_data = {}

for card in cards:
    if card.get("isHero"):
        hero_id = card["id"]
        
        power = None
        buddy = None
        
        # Find power and buddy from childIds
        for child_id in card.get("childIds", []):
            child = cards_by_id.get(child_id)
            if not child:
                continue
            
            if child.get("cardType") == "hero_power":
                power = child
            elif "buddy" in child.get("categories", []):
                buddy = child
        
        heroes_data[hero_id] = {
            "name": card["name"].strip(),
            "health": card.get("health"),
            "armor": card.get("armor"),
            "power": power,
            "buddy": buddy,
        }

# Generate Python code
output = '"""Hero definitions - Hearthstone Battlegrounds"""\n\nHEROES = {\n'

for hero_id, data in heroes_data.items():
    output += f"    {hero_id}: {{\n"
    output += f'        "name": "{data["name"]}",\n'
    output += f'        "health": {data["health"]},\n'
    output += f'        "armor": {data["armor"]},\n'
    
    if data["power"]:
        p = data["power"]
        output += f'        "power": {{\n'
        output += f'            "id": {p["id"]},\n'
        output += f'            "name": "{p["name"].strip()}",\n'
        output += f'            "cost": {p.get("manaCost", 0)},\n'
        text = p.get("text", "").replace(chr(10), " ").replace('"', '\\"')
        output += f'            "text": "{text}",\n'
        if p.get("textGold"):
            text_gold = p.get("textGold", "").replace(chr(10), " ").replace('"', '\\"')
            output += f'            "textGold": "{text_gold}",\n'
        output += f'        }},\n'
    
    if data["buddy"]:
        b = data["buddy"]
        output += f'        "buddy": {{\n'
        output += f'            "id": {b["id"]},\n'
        output += f'            "name": "{b["name"].strip()}",\n'
        output += f'            "attack": {b.get("attack", 0)},\n'
        if b.get("attackGold"):
            output += f'            "attackGold": {b.get("attackGold")},\n'
        output += f'            "health": {b.get("health", 0)},\n'
        if b.get("healthGold"):
            output += f'            "healthGold": {b.get("healthGold")},\n'
        text = b.get("text", "").replace(chr(10), " ").replace('"', '\\"')
        output += f'            "text": "{text}",\n'
        if b.get("textGold"):
            text_gold = b.get("textGold", "").replace(chr(10), " ").replace('"', '\\"')
            output += f'            "textGold": "{text_gold}",\n'
        output += f'        }},\n'
    
    output += "    },\n"

output += "}\n"

# Write to heroes.py
heroes_file = Path("game/heroes.py")
with open(heroes_file, "w") as f:
    f.write(output)

print(f"✅ Extracted {len(heroes_data)} heroes to {heroes_file}")

