import json

with open("data/raw/cards.json", "r", encoding="utf-8") as f:
    cards = json.load(f)

types = sorted({card.get("cardType") for card in cards if card.get("cardType")})

for t in types:
    print(t)