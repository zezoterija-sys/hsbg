import json
import random
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
CARDS_FILE = ROOT / "data" / "raw" / "cards.json"

from game.card_effects import register_card_effects
from game.combat import CombatEngine
from game.effects import EffectSystem, EffectZone
from game.events import EventDispatcher, GameEvent
from game.tier36_effects import (
    TIER36_CARD_IDS,
    SLY_INFILTRATOR,
    SNARE_TRAPPER,
    BRANN_BRONZEBEARD,
    SANGUINE_CHAMPION,
    CHORAL_MRRRGLR,
    EREDAR_ESCAPIST,
    TYRAEL,
    UNBOUND_TEMPEST,
    UTILITY_DRONE,
    VETERAN_BRIGAND,
    BALINDA_STONEHEARTH,
    REPAIR_JOB,
    TWISTED_WRATHGUARD,
    ELEMENTAL_OF_SURPRISE,
    FALLING_SKY_GOLEM,
    ETERNAL_SUMMONER,
    ETERNAL_KNIGHT,
    SKY_ADMIRAL_ROGERS,
    BLOOD_GEM_BARRAGE,
    DEATHSTRIDER,
    CRIMSON_VINDICATOR,
    ETERNAL_SUMMONER,
    MAGICFIN_MYCOLOGIST,
    SHINY_RING,
)


class FakePool:
    def __init__(self):
        self.card_definitions = json.loads(CARDS_FILE.read_text(encoding="utf-8"))
        self.card_definitions_by_id = {
            card["id"]: card
            for card in self.card_definitions
            if isinstance(card.get("id"), int)
        }


class FakePlayer:
    MAX_HAND_SIZE = 10

    def __init__(self, player_id):
        self.player_id = player_id
        self.board = [None] * 7
        self.hand = []
        self.tavern = SimpleNamespace(slots=[None] * 6, spell=None, frozen=False)
        self.gold = 10
        self.max_gold = 10
        self.health = 30
        self.armor = 0
        self.eliminated = False
        self.last_combat_won = None
        self.last_combat_tied = False

    def spend_gold(self, amount):
        if self.gold < amount:
            raise ValueError("Not enough Gold")
        self.gold -= amount

    def add_gold(self, amount):
        self.gold = min(self.max_gold, self.gold + amount)

    def take_damage(self, amount):
        armor_damage = min(self.armor, amount)
        self.armor -= armor_damage
        health_damage = amount - armor_damage
        self.health = max(0, self.health - health_damage)
        return armor_damage, health_damage


class FakeGame:
    def __init__(self):
        self.pool = FakePool()
        self.players = [FakePlayer(i) for i in range(8)]
        self.priority_order = list(range(8))
        self.round_number = 1
        self.phase = "recruit"
        self.events = EventDispatcher(record_history=True)
        self.random = random.Random(7)
        self.effects = EffectSystem(game=self, events=self.events, rng=self.random)
        register_card_effects(self.effects)

    def get_player(self, player_id):
        return self.players[player_id]


def card(game, card_id, golden=False):
    return game.effects.create_card(card_id, golden=golden, generated=True)


def fake_minion(card_id, attack=1, health=1, minion_type="Neutral", tier=1):
    return {
        "id": card_id,
        "name": f"Fake {card_id}",
        "cardType": "minion",
        "attack": attack,
        "health": health,
        "tier": tier,
        "minionType": minion_type,
        "minionTypes": [minion_type],
        "keywords": [],
        "isGolden": False,
    }


def passed(name):
    print(f"[PASS] {name}")


# ---------------------------------------------------------------------------
# Coverage: authoritative cards.json -> exact Tier 3-6 solo Tavern pool.
# ---------------------------------------------------------------------------
game = FakeGame()
effects = game.effects
p0 = game.get_player(0)

actual = {3: set(), 4: set(), 5: set(), 6: set()}
for definition in game.pool.card_definitions:
    tier = definition.get("tier")
    if tier not in actual:
        continue
    if definition.get("cardType") != "minion" or definition.get("pool") is not True:
        continue
    if "tavern" not in (definition.get("categories") or []):
        continue
    if definition.get("isDuosOnly", False):
        continue
    actual[tier].add(definition["id"])

assert {tier: len(ids) for tier, ids in actual.items()} == {3: 43, 4: 55, 5: 46, 6: 35}
assert actual == TIER36_CARD_IDS
passed("All 179 Tier 3-6 solo Tavern minion IDs accounted for")

# Cards whose behavior lives in generic engine/global passives instead of a
# card-local registration.
native_or_global = {
    96812,   # Annoy-o-Module: keywords + Magnetic
    65031,   # Deadly Spore: Venomous
    112364,  # Prosthetic Hand: special Magnetic targets
    99199,   # Malchezaar: global refresh-payment hook
    108463,  # Persistent Poet: combat result commit hook
    116190,  # Thorned Trailblazer: global Choose One hook
    92406,   # Tortollan Blue Shell: sell-value hook
    101280,  # Elemental of Surprise: triple-compatibility hook
    130798,  # Falling Sky Golem: wherever-scaler hook
    92413,   # Warpwing: Immune while attacking
}

missing = []
for tier, ids in TIER36_CARD_IDS.items():
    for card_id in ids:
        covered = bool(
            effects.get_effects_for_card(card_id)
            or effects.get_activate_ability({"id": card_id})
            or card_id in effects._spellcraft
            or card_id in effects._trigger_multipliers
            or card_id in effects._target_rules
            or card_id in native_or_global
        )
        if not covered:
            missing.append((tier, card_id, game.pool.card_definitions_by_id[card_id]["name"]))
assert not missing, missing
passed("Every Tier 3-6 minion has local or native/global behavior coverage")

# ---------------------------------------------------------------------------
# Tier 3: Choose One and free Refresh state.
# ---------------------------------------------------------------------------
p0.board = [None] * 7
p0.hand.clear()
source = card(game, SLY_INFILTRATOR)
p0.board[0] = source
game.events.emit(GameEvent.CARD_PLAYED, player_id=0, card=source, minion=source)
choice = effects.get_pending_choice(0)
assert choice is not None and choice.kind == "choose_one"
effects.resolve_choice(0, choice.options.index("refreshes"))
assert effects.get_player_state(0)["free_refreshes"] == 2
passed("Tier 3 Choose One resolver")

# ---------------------------------------------------------------------------
# Tier 4: maximum-Gold Choose One.
# ---------------------------------------------------------------------------
p0.board = [None] * 7
source = card(game, SNARE_TRAPPER)
p0.board[0] = source
game.events.emit(GameEvent.CARD_PLAYED, player_id=0, card=source, minion=source)
choice = effects.get_pending_choice(0)
assert choice is not None
effects.resolve_choice(0, choice.options.index("max_gold"))
assert p0.max_gold == 11
passed("Tier 4 maximum-Gold mechanic")

# ---------------------------------------------------------------------------
# Tier 5: Brann doubles a real Battlecry.
# ---------------------------------------------------------------------------
p0.board = [card(game, BRANN_BRONZEBEARD), None, None, None, None, None, None]
state = effects.get_player_state(0)
state["blood_gem_attack_bonus"] = 0
state["blood_gem_health_bonus"] = 0
champion = card(game, SANGUINE_CHAMPION)
p0.board[1] = champion
game.events.emit(GameEvent.CARD_PLAYED, player_id=0, card=champion, minion=champion)
assert state["blood_gem_attack_bonus"] == 2
assert state["blood_gem_health_bonus"] == 2
passed("Tier 5 Brann trigger multiplier")

# ---------------------------------------------------------------------------
# Tier 6: Balinda repeats only a targeted spell.
# ---------------------------------------------------------------------------
p0.board = [card(game, BALINDA_STONEHEARTH), fake_minion(910001, 2, 2), None, None, None, None, None]
target = p0.board[1]
spell = card(game, REPAIR_JOB)
game.events.emit(GameEvent.SPELL_CAST, player_id=0, spell=spell, card=spell, target=target)
assert (target["attack"], target["health"]) == (10, 18)
passed("Balinda targeted spell multiplier")

# ---------------------------------------------------------------------------
# Tier 6: Choral Mrrrglr reads hand at Start of Combat.
# ---------------------------------------------------------------------------
p0.hand = [fake_minion(910002, 3, 4), fake_minion(910003, 5, 6)]
choral = card(game, CHORAL_MRRRGLR)
engine = CombatEngine(events=game.events, rng=game.random, priority_order=game.priority_order)
side = engine.create_side(0, 6, [choral])
runtime = side.board[0]
before = (runtime["attack"], runtime["health"])
engine.emit(GameEvent.COMBAT_START, side_a=side)
assert (runtime["attack"], runtime["health"]) == (before[0] + 8, before[1] + 10)
passed("Choral Mrrrglr Start of Combat")

# ---------------------------------------------------------------------------
# Tier 6: Eredar cumulative hero damage.
# ---------------------------------------------------------------------------
p0.board = [card(game, EREDAR_ESCAPIST), fake_minion(910004, 1, 1), None, None, None, None, None]
target = p0.board[1]
before = (target["attack"], target["health"])
game.events.emit(GameEvent.PLAYER_DAMAGED, player_id=0, amount=2, health_damage=2)
assert (target["attack"], target["health"]) == before
game.events.emit(GameEvent.PLAYER_DAMAGED, player_id=0, amount=1, health_damage=1)
# Shiny Ring buffs all friendly minions, including target.
assert (target["attack"], target["health"]) == (before[0] + 1, before[1] + 1)
passed("Eredar Escapist cumulative damage trigger")

# ---------------------------------------------------------------------------
# Tier 6: Tyrael sets exact stats.
# ---------------------------------------------------------------------------
p0.board = [card(game, TYRAEL), fake_minion(910005, 2, 7), None, None, None, None, None]
p0.gold = 10
ref = effects.resolve_target_ref(0, EffectZone.BOARD, 1)
effects.resolve_activate(0, 0, target_ref=ref)
assert (p0.board[1]["attack"], p0.board[1]["health"]) == (50, 50)
assert p0.gold == 8
passed("Tyrael Activate")

# ---------------------------------------------------------------------------
# Tier 6: Unbound Tempest every third Elemental.
# ---------------------------------------------------------------------------
p0.board = [card(game, UNBOUND_TEMPEST), None, None, None, None, None, None]
p0.tavern.slots = [fake_minion(910006, 9, 20, "Beast", 6), fake_minion(910007, 20, 10, "Beast", 6), None, None, None, None]
source = p0.board[0]
before = (source["attack"], source["health"])
for i in range(3):
    elem = fake_minion(920000 + i, 1, 1, "Elemental", 1)
    game.events.emit(GameEvent.CARD_PLAYED, player_id=0, card=elem, minion=elem)
assert (source["attack"], source["health"]) == (before[0] + 9, before[1] + 20)
passed("Unbound Tempest three-Elemental counter")

# ---------------------------------------------------------------------------
# Tier 6: Utility Drone reads magnetization count.
# ---------------------------------------------------------------------------
target = fake_minion(910008, 3, 3, "Mech")
target["_magnetization_count"] = 2
p0.board = [card(game, UTILITY_DRONE), target, None, None, None, None, None]
game.events.emit(GameEvent.TURN_END, player_id=0)
assert (target["attack"], target["health"]) == (11, 11)
passed("Utility Drone magnetization scaling")

# ---------------------------------------------------------------------------
# Tier 6: Veteran Brigand Choose One.
# ---------------------------------------------------------------------------
p0.board = [card(game, VETERAN_BRIGAND), fake_minion(910009, 1, 1, "Quilboar"), None, None, None, None, None]
source = p0.board[0]
game.events.emit(GameEvent.CARD_PLAYED, player_id=0, card=source, minion=source)
choice = effects.get_pending_choice(0)
assert choice is not None
effects.resolve_choice(0, choice.options.index("barrage"))
assert effects.get_player_state(0)["blood_gem_barrage_refreshes"] >= 3
passed("Veteran Brigand Choose One")

# ---------------------------------------------------------------------------
# Tier 6: Twisted Wrathguard queues exactly next-refresh Fodder.
# ---------------------------------------------------------------------------
p0.board = [card(game, TWISTED_WRATHGUARD), fake_minion(910010, 1, 1, "Demon"), None, None, None, None, None]
game.events.emit(GameEvent.CARD_SOLD, player_id=0, card=fake_minion(910011), minion=fake_minion(910011))
assert effects.get_player_state(0)["fodder_pending_count"] == 1
p0.tavern.slots = [None] * 6
game.events.emit(GameEvent.TAVERN_REFRESHED, player_id=0)
assert effects.get_player_state(0).get("fodder_pending_count", 0) == 0
assert p0.board[1]["attack"] > 1 and p0.board[1]["health"] > 1
passed("Twisted Wrathguard next-Refresh Fodder")


# ---------------------------------------------------------------------------
# Tier 6: Deathstrider forces the left-most Deathrattle after a Rally.
# ---------------------------------------------------------------------------
p0.hand.clear()
p0.board = [None] * 7
eternal = card(game, ETERNAL_SUMMONER)
deathstrider = card(game, DEATHSTRIDER)
vindicator = card(game, CRIMSON_VINDICATOR)
side = engine.create_side(0, 6, [eternal, deathstrider, vindicator])
runtime_vindicator = side.board[2]
engine.emit(
    GameEvent.ATTACK,
    player_id=0,
    attacker=runtime_vindicator,
    attacking_side=side,
    source_side=side,
)
assert any(minion.get("id") == ETERNAL_KNIGHT for minion in side.board)
passed("Deathstrider forced left-most Deathrattle")

# ---------------------------------------------------------------------------
# Tier 6: Magicfin teaches a bought Tavern spell to a 1/1 Murloc.
# ---------------------------------------------------------------------------
p0.board = [card(game, MAGICFIN_MYCOLOGIST), fake_minion(930001, 1, 1, "Murloc"), None, None, None, None, None]
p0.hand.clear()
ring = card(game, SHINY_RING)
game.events.emit(GameEvent.SPELL_BOUGHT, player_id=0, spell=ring, card=ring)
assert len(p0.hand) == 1
apprentice = p0.hand[0]
assert apprentice.get("id") == 122285 and apprentice.get("_taught_spell", {}).get("id") == SHINY_RING
before = (p0.board[1]["attack"], p0.board[1]["health"])
p0.hand.clear()
p0.board[2] = apprentice
game.events.emit(GameEvent.CARD_PLAYED, player_id=0, card=apprentice, minion=apprentice)
assert (p0.board[1]["attack"], p0.board[1]["health"]) == (before[0] + 1, before[1] + 1)
passed("Magicfin taught Tavern spell")

# ---------------------------------------------------------------------------
# Engine-native special: Elemental of Surprise triple compatibility.
# ---------------------------------------------------------------------------
surprise = card(game, ELEMENTAL_OF_SURPRISE)
elemental = fake_minion(910012, 1, 1, "Elemental")
beast = fake_minion(910013, 1, 1, "Beast")
assert effects.can_triple_together(surprise, elemental)
assert not effects.can_triple_together(surprise, beast)
passed("Elemental of Surprise triple compatibility hook")

# ---------------------------------------------------------------------------
# Wherever scaler: Falling Sky Golem updates after Deathrattle triggers.
# ---------------------------------------------------------------------------
effects.get_player_state(0)["deathrattles_triggered_game"] = 0
p0.board = [card(game, FALLING_SKY_GOLEM), None, None, None, None, None, None]
golem = p0.board[0]
before = (golem["attack"], golem["health"])
game.events.emit(
    GameEvent.TRIGGER_RESOLVED,
    player_id=0,
    family=__import__("game.effects", fromlist=["TriggerFamily"]).TriggerFamily.DEATHRATTLE,
    card=card(game, ETERNAL_SUMMONER),
)
assert (golem["attack"], golem["health"]) == (before[0] + 4, before[1] + 2)
passed("Falling Sky Golem wherever scaler")

# ---------------------------------------------------------------------------
# Gold-spend counter: Sky Admiral Rogers at 9 Gold.
# ---------------------------------------------------------------------------
p0.board = [card(game, SKY_ADMIRAL_ROGERS), None, None, None, None, None, None]
p0.hand.clear()
p0.gold = 20
p0.max_gold = 20
effects.spend_gold(0, 9, reason="test")
assert len(p0.hand) == 1
assert p0.hand[0]["id"] in {122182, 122183, 122184, 122185, 122186}
passed("Sky Admiral Rogers Gold-spend counter")

print()
print("ALL TIER 3-6 COVERAGE AND BEHAVIOR TESTS PASSED")
