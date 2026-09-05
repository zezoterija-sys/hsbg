from copy import deepcopy
import random

from game.actions import ActionType
from game.combat import CombatEngine
from game.effects import EffectSystem, EffectZone, TriggerFamily
from game.events import EventDispatcher, GameEvent


class FakePool:
    def __init__(self):
        self.card_definitions_by_id = {
            10: {"id": 10, "name": "Token", "cardType": "minion", "attack": 1, "health": 1, "attackGold": 2, "healthGold": 2, "tier": 1, "keywords": [], "minionType": "Beast", "minionTypes": ["Beast"]},
            20: {"id": 20, "name": "Spell", "cardType": "spell", "manaCost": 0, "text": "", "textGold": ""},
        }
        self.card_definitions = list(self.card_definitions_by_id.values())


class FakePlayer:
    MAX_HAND_SIZE = 10
    def __init__(self, pid):
        self.player_id = pid
        self.board = [None] * 7
        self.hand = []
        self.gold = 10
        self.eliminated = False
        self.waiting = False
        self.ap = 100
        self.hero = None
    def spend_gold(self, n):
        if self.gold < n: raise ValueError
        self.gold -= n


class FakeGame:
    def __init__(self):
        self.events = EventDispatcher(record_history=True)
        self.pool = FakePool()
        self.players = [FakePlayer(i) for i in range(2)]
        self.priority_order = [0,1]
        self.round_number = 1
        self.phase = "recruit"
    def get_player(self, pid): return self.players[pid]


def card(cid, atk=1, hp=1, kws=None, typ="Beast", golden=False):
    return {"id": cid, "name": str(cid), "cardType": "minion", "attack": atk, "health": hp,
            "tier": 1, "keywords": kws or [], "minionType": typ, "minionTypes": [typ], "isGolden": golden}


g = FakeGame()
e = EffectSystem(g, g.events, rng=random.Random(1))
g.effects = e

# battlecry + multiplier
calls=[]
e.register_battlecry(100, lambda ctx: calls.append("bc"))
e.register_trigger_multiplier(101, [TriggerFamily.BATTLECRY], zones=(EffectZone.BOARD,), extra_normal=1, extra_golden=2)
g.players[0].board[0] = card(101)
played = card(100)
g.players[0].board[1] = played
g.events.emit(GameEvent.CARD_PLAYED, player_id=0, card=played)
assert calls == ["bc", "bc"]

# temporary buff expires next turn
played["attack"] = 2
e.apply_buff(played, attack=3, until_next_turn=True)
assert played["attack"] == 5
g.round_number = 2
g.events.emit(GameEvent.TURN_START, player_id=0)
assert played["attack"] == 2

# Spellcraft
source = card(200)
g.players[0].board[2] = source
e.register_spellcraft(200, 20)
g.round_number = 3
g.events.emit(GameEvent.TURN_START, player_id=0)
assert any(c.get("id") == 20 and c.get("_spellcraft_temporary") for c in g.players[0].hand)
g.events.emit(GameEvent.TURN_END, player_id=0)
assert not any(c.get("_spellcraft_temporary") for c in g.players[0].hand)

# Activate
act = card(300)
g.players[0].board[3] = act
act_calls=[]
e.register_activate(300, 2, lambda ctx: act_calls.append(ctx.event.get("target_idx")))
assert e.can_activate(0,3)
e.resolve_activate(0,3)
assert g.players[0].gold == 8 and act_calls == [None]
assert not e.can_activate(0,3)

# choice
resolved=[]
e.register_choice_resolver("x", lambda sys,pid,opt,meta: resolved.append((pid,opt)))
e.start_choice(0,"x",["a","b"])
e.resolve_choice(0,1)
assert resolved == [(0,"b")]

# Magnetic transfers registered attached effect
host = card(400, typ="Mech")
module = card(401, atk=2, hp=3, kws=["Magnetic", "Deathrattle"], typ="Mech")
attached_calls=[]
e.register_deathrattle(401, lambda ctx: attached_calls.append(ctx.effect_card_id))
e.magnetize(module, host)
assert host["attack"] == 3 and host["health"] == 4 and "Deathrattle" in host["keywords"]
# event source lookup sees attached effect on host
g.events.emit(GameEvent.DEATHRATTLE, player_id=0, minion=host)
assert attached_calls == [401]

# Rally runs when attacker attacks
rally_calls=[]
e.register_rally(500, lambda ctx: rally_calls.append(1))
engine=CombatEngine(events=g.events, rng=random.Random(2), priority_order=[0,1])
sa=engine.create_side(0,1,[card(500, atk=2,hp=2)])
sb=engine.create_side(1,1,[card(501, atk=1,hp=3)])
engine.attack(sa.board[0], sa, sb)
assert rally_calls == [1]

# Avenge counter
av_calls=[]
e.register_avenge(600,2,lambda ctx: av_calls.append(1))
sa=engine.create_side(0,1,[card(600,atk=1,hp=5), card(601), card(602)])
sb=engine.create_side(1,1,[card(603)])
# kill two friendlies simultaneously
sa.board[1]["health"] = 0
sa.board[2]["health"] = 0
engine.resolve_deaths(sa,sb)
assert av_calls == [1]

# Deathrattle summon via generated card factory
summoner = card(700, kws=["Deathrattle"])
e.register_deathrattle(700, lambda ctx: ctx.summon(10, count=2))
sa=engine.create_side(0,1,[summoner])
sb=engine.create_side(1,1,[card(701)])
sa.board[0]["health"] = 0
engine.resolve_deaths(sa,sb)
assert len(sa.board) == 2 and all(m["id"] == 10 for m in sa.board)

print("ALL BIG EFFECT FRAMEWORK TESTS PASSED")

# Targeted action representation sanity
from game.actions import ActionSpace, Action
from game.effects import TargetRef
class Tav:
    def __init__(self): self.slots=[None]*3; self.spell=None; self.frozen=False
fp=g.players[0]
fp.action_space=ActionSpace(); fp.tavern=Tav(); fp.tavern_tier=1
fp.waiting=False; fp.ap=10; fp.gold=10; fp.hand=[]; fp.board=[None]*7
spell={"id":800,"cardType":"spell","manaCost":1,"keywords":[]}
fp.hand.append(spell)
e.register_target_rule(800, lambda ctx: [TargetRef(ctx.player_id, EffectZone.BOARD, 0, ctx.game.get_player(ctx.player_id).board[0])])
fp.board[0]=card(801)
fp.action_space.generate_for_player(fp,g)
cast=[a for a in fp.action_space.get_legal_actions() if a.action_type==ActionType.CAST_SPELL]
assert len(cast)==1 and cast[0].effect_target_idx==0 and cast[0].effect_target_zone=="board"
print("TARGETED ACTION TEST PASSED")
