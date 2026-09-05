import json
import random
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from game.card_effects import (
    BEETLE,
    BLOOD_GEM,
    BUZZING_VERMIN,
    CLEVER_CASTAWAY,
    CRATER_MINER,
    EXPERT_AVIATOR,
    FLIGHTY_SCOUT,
    GLIM_GUARDIAN,
    LULLABOT,
    MECHAGNOME_INTERPRETER,
    MIND_MUCK,
    MINI_MYRMIDON,
    MINI_TRIDENT,
    PRODIGIOUS_TUSKER,
    SELLEMENTAL,
    SOUTHSEA_BUSKER,
    SUSPICIOUS_PRISONGUARD,
    TUSKED_CAMPER,
    register_card_effects,
)
from game.combat import CombatEngine
from game.effects import EffectSystem, EffectZone
from game.events import EventDispatcher, GameEvent


CARDS_FILE = (
    ROOT
    / "data"
    / "raw"
    / "cards.json"
)


class FakePool:
    def __init__(self):
        self.card_definitions = json.loads(CARDS_FILE.read_text(encoding='utf-8'))
        self.card_definitions_by_id = {
            card['id']: card
            for card in self.card_definitions
            if isinstance(card.get('id'), int)
        }


class FakePlayer:
    MAX_HAND_SIZE = 10

    def __init__(self, player_id):
        self.player_id = player_id
        self.board = [None] * 7
        self.hand = []
        self.tavern = SimpleNamespace(slots=[None] * 6, spell=None, frozen=False)
        self.gold = 10
        self.health = 30
        self.armor = 0
        self.eliminated = False

    def add_gold(self, amount):
        self.gold = min(10, self.gold + amount)

    def spend_gold(self, amount):
        if self.gold < amount:
            raise ValueError('Not enough gold')
        self.gold -= amount

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
        self.events = EventDispatcher()
        self.random = random.Random(1)
        self.effects = EffectSystem(
            game=self,
            events=self.events,
            rng=self.random,
        )
        register_card_effects(self.effects)

    def get_player(self, player_id):
        return self.players[player_id]


def card(game, card_id, golden=False):
    return game.effects.create_card(card_id, golden=golden, generated=True)


def fake_minion(card_id, attack=1, health=1, minion_type='Neutral'):
    return {
        'id': card_id,
        'name': f'Fake {card_id}',
        'cardType': 'minion',
        'attack': attack,
        'health': health,
        'minionType': minion_type,
        'minionTypes': [minion_type],
        'keywords': [],
        'isGolden': False,
    }


def passed(name):
    print(f'[PASS] {name}')


game = FakeGame()
p0 = game.get_player(0)
engine = CombatEngine(
    events=game.events,
    rng=game.random,
    priority_order=game.priority_order,
)

# ---------------------------------------------------------------------------
# Lullabot End of Turn
# ---------------------------------------------------------------------------
lullabot = card(game, LULLABOT)
p0.board[0] = lullabot
before = lullabot['health']
game.events.emit(GameEvent.TURN_END, player_id=0)
assert lullabot['health'] == before + 1
passed('Lullabot End of Turn')

# ---------------------------------------------------------------------------
# Southsea Busker delayed gold
# ---------------------------------------------------------------------------
p0.gold = 3
busker = card(game, SOUTHSEA_BUSKER)
p0.board[1] = busker
game.events.emit(GameEvent.CARD_PLAYED, player_id=0, card=busker, minion=busker)
assert game.effects.get_player_state(0)['pending_gold_next_turn'] == 1
game.round_number = 2
game.events.emit(GameEvent.TURN_START, player_id=0)
assert p0.gold == 4
passed('Southsea Busker next-turn Gold')

# ---------------------------------------------------------------------------
# Mini-Myrmidon Spellcraft + temporary spell buff
# ---------------------------------------------------------------------------
p0.hand.clear()
myrmidon = card(game, MINI_MYRMIDON)
p0.board[2] = myrmidon
game.events.emit(GameEvent.CARD_PLAYED, player_id=0, card=myrmidon, minion=myrmidon)
assert len(p0.hand) == 1 and p0.hand[0]['id'] == MINI_TRIDENT

target = fake_minion(900001, attack=3, health=3, minion_type='Beast')
p0.board[3] = target
spell = p0.hand.pop(0)
game.events.emit(
    GameEvent.SPELL_CAST,
    player_id=0,
    spell=spell,
    card=spell,
    target=target,
)
assert target['attack'] == 5
game.round_number = 3
game.events.emit(GameEvent.TURN_START, player_id=0)
assert target['attack'] == 3
passed('Spellcraft generation + until-next-turn buff expiry')

# ---------------------------------------------------------------------------
# Suspicious Prisonguard Activate
# ---------------------------------------------------------------------------
prisonguard = card(game, SUSPICIOUS_PRISONGUARD)
activate_target = fake_minion(900002, attack=2, health=2)
p0.board = [prisonguard, activate_target, None, None, None, None, None]
p0.gold = 5
game.round_number = 4
target_ref = game.effects.resolve_target_ref(0, EffectZone.BOARD, 1)
game.effects.resolve_activate(0, 0, target_ref=target_ref)
assert (activate_target['attack'], activate_target['health']) == (5, 5)
assert p0.gold == 4
passed('Activate + targeted buff + cost')

# ---------------------------------------------------------------------------
# Crater Miner Choose One
# ---------------------------------------------------------------------------
p0.hand.clear()
crater = card(game, CRATER_MINER)
p0.board[0] = crater
game.events.emit(GameEvent.CARD_PLAYED, player_id=0, card=crater, minion=crater)
pending = game.effects.get_pending_choice(0)
assert pending is not None and len(pending.options) == 2
game.effects.resolve_choice(0, pending.options.index('blood_gems'))
assert [c['id'] for c in p0.hand] == [BLOOD_GEM, BLOOD_GEM]
passed('Choose One + generated Blood Gems')

# ---------------------------------------------------------------------------
# Mind Muck targeted Battlecry + Tavern consume
# ---------------------------------------------------------------------------
p0.hand.clear()
mind_muck = card(game, MIND_MUCK)
demon = fake_minion(900003, attack=2, health=2, minion_type='Demon')
food = fake_minion(900004, attack=4, health=5, minion_type='Beast')
p0.board = [demon, mind_muck, None, None, None, None, None]
p0.tavern.slots = [food, None, None, None, None, None]
game.events.emit(
    GameEvent.CARD_PLAYED,
    player_id=0,
    card=mind_muck,
    minion=mind_muck,
    target=demon,
)
assert (demon['attack'], demon['health']) == (6, 7)
assert p0.tavern.slots[0] is None
passed('Targeted Battlecry + Tavern consume')

# ---------------------------------------------------------------------------
# Mechagnome Interpreter on played Mech
# ---------------------------------------------------------------------------
interpreter = card(game, MECHAGNOME_INTERPRETER)
played_mech = fake_minion(900005, attack=2, health=2, minion_type='Mech')
p0.board = [interpreter, played_mech, None, None, None, None, None]
game.events.emit(
    GameEvent.CARD_PLAYED,
    player_id=0,
    card=played_mech,
    minion=played_mech,
)
assert (played_mech['attack'], played_mech['health']) == (5, 3)
passed('Mechagnome Interpreter play trigger')

# ---------------------------------------------------------------------------
# Buzzing Vermin Deathrattle combat summon
# ---------------------------------------------------------------------------
vermin = card(game, BUZZING_VERMIN)
side = engine.create_side(0, 1, [])
engine.emit(
    GameEvent.DEATHRATTLE,
    player_id=0,
    side=side,
    minion=vermin,
    death_position=0,
)
assert len(side.board) == 1
assert side.board[0]['id'] == BEETLE
assert (side.board[0]['attack'], side.board[0]['health']) == (2, 2)
passed('Deathrattle generated combat summon')

# ---------------------------------------------------------------------------
# Flighty Scout from hand at Start of Combat
# ---------------------------------------------------------------------------
p0.hand = [card(game, FLIGHTY_SCOUT)]
side = engine.create_side(0, 1, [])
engine.emit(GameEvent.COMBAT_START, side_a=side)
assert len(side.board) == 1 and side.board[0]['id'] == FLIGHTY_SCOUT
assert len(p0.hand) == 1
passed('Start-of-Combat summon from hand without consuming hand card')

# ---------------------------------------------------------------------------
# Glim Guardian Rally
# ---------------------------------------------------------------------------
glim = card(game, GLIM_GUARDIAN)
side = engine.create_side(0, 1, [glim])
runtime_glim = side.board[0]
before = runtime_glim['attack']
engine.emit(
    GameEvent.ATTACK,
    player_id=0,
    attacker=runtime_glim,
    attacking_side=side,
    source_side=side,
)
assert runtime_glim['attack'] == before + 2
passed('Rally self-buff')

# ---------------------------------------------------------------------------
# Tusked Camper Rally uses Blood Gem values
# ---------------------------------------------------------------------------
camper = card(game, TUSKED_CAMPER)
side = engine.create_side(0, 1, [camper])
runtime_camper = side.board[0]
before = (runtime_camper['attack'], runtime_camper['health'])
engine.emit(
    GameEvent.ATTACK,
    player_id=0,
    attacker=runtime_camper,
    attacking_side=side,
    source_side=side,
)
assert (runtime_camper['attack'], runtime_camper['health']) == (before[0] + 1, before[1] + 1)
passed('Rally Blood Gem application')

# ---------------------------------------------------------------------------
# Prodigious Tusker buffs another friendly attacker
# ---------------------------------------------------------------------------
tusker = card(game, PRODIGIOUS_TUSKER)
friend = fake_minion(900006, attack=3, health=3, minion_type='Beast')
side = engine.create_side(0, 2, [tusker, friend])
runtime_tusker, runtime_friend = side.board
engine.emit(
    GameEvent.ATTACK,
    player_id=0,
    attacker=runtime_friend,
    attacking_side=side,
    source_side=side,
)
assert (runtime_friend['attack'], runtime_friend['health']) == (4, 4)
assert runtime_tusker['attack'] == tusker['attack']
passed('Friendly-attack trigger')

# ---------------------------------------------------------------------------
# Expert Aviator combat-only hand summon
# ---------------------------------------------------------------------------
aviator = card(game, EXPERT_AVIATOR)
p0.hand = [
    fake_minion(900007, attack=2, health=2),
    fake_minion(900008, attack=8, health=1),
    fake_minion(900009, attack=5, health=5),
]
side = engine.create_side(0, 2, [aviator])
runtime_aviator = side.board[0]
engine.emit(
    GameEvent.ATTACK,
    player_id=0,
    attacker=runtime_aviator,
    attacking_side=side,
    source_side=side,
)
assert any(card['id'] == 900008 for card in side.board)
assert len(p0.hand) == 3
passed('Combat-only summon from hand')

# ---------------------------------------------------------------------------
# Sellemental sell generates Water Droplet
# ---------------------------------------------------------------------------
p0.hand.clear()
sellemental = card(game, SELLEMENTAL)
game.events.emit(GameEvent.CARD_SOLD, player_id=0, card=sellemental, minion=sellemental)
assert len(p0.hand) == 1
assert p0.hand[0]['id'] == 64040
assert (p0.hand[0]['attack'], p0.hand[0]['health']) == (3, 3)
passed('Sell trigger + generated token')

# ---------------------------------------------------------------------------
# Clever Castaway Discover
# ---------------------------------------------------------------------------
p0.hand.clear()
castaway = card(game, CLEVER_CASTAWAY)
p0.board = [castaway, None, None, None, None, None, None]
p0.gold = 10
game.round_number = 5
game.effects.resolve_activate(0, 0)
pending = game.effects.get_pending_choice(0)
assert pending is not None and pending.kind == 'discover'
assert len(pending.options) <= 3
game.effects.resolve_choice(0, 0)
assert len(p0.hand) == 1
passed('Activate Discover Tavern spell')

print()
print('ALL LARGE REAL-CARD BATCH TESTS PASSED')
