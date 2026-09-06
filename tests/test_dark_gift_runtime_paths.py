"""Exercise Gift effects through real combat, hand and recruit event paths."""

import pytest

from game import dark_gift_effects as gifts
from game.effects import TriggerFamily
from game.events import GameEvent
from tests.test_dark_gift_specials import _game, _gift, _host


def _attach(game, gift_id, **updates):
    host = _host(**updates)
    gifts.attach_dark_gift(game.effects, 0, host, _gift(game, gift_id), acquired_turn=8)
    return host


@pytest.mark.parametrize("gift_id,keyword", [
    (gifts.FURTIVENESS, "Stealth"), (gifts.INVULNERABILITY, "Immune"),
    (gifts.CONSANGUINITY, "Rally"), (gifts.DEMONOLOGY, "Rally"),
    (gifts.CHARISMA, "Rally"), (gifts.FRESH_PERSPECTIVE, "Deathrattle"),
    (gifts.MYSTIC_ESSENCE, "Deathrattle"), (gifts.OFFENSIVE_SACRIFICE, "Deathrattle"),
    (gifts.DEFENSIVE_SACRIFICE, "Deathrattle"), (gifts.GOLEMANCY, "Deathrattle"),
])
def test_gained_keywords_are_on_the_physical_host(gift_id, keyword):
    game = _game()
    assert game.effects.has_keyword(_attach(game, gift_id), keyword)


@pytest.mark.parametrize("gift_id", [gifts.FRESH_PERSPECTIVE, gifts.MYSTIC_ESSENCE,
    gifts.OFFENSIVE_SACRIFICE, gifts.DEFENSIVE_SACRIFICE, gifts.GOLEMANCY])
def test_gift_deathrattles_execute_when_a_host_without_native_deathrattle_dies(gift_id):
    game = _game()
    engine = game.combat.engine
    host = _attach(game, gift_id)
    friend = _host(900101, attack=2, health=4)
    side = engine.create_side(0, 4, [host, friend])
    enemy = engine.create_side(1, 4, [_host(900102, attack=1000, health=1000)])
    engine.emit(GameEvent.COMBAT_START, side_a=side, side_b=enemy)
    engine.deal_minion_damage(enemy.board[0], side.board[0], 1000, enemy, side)
    engine.resolve_deaths(side, enemy)
    player = game.get_player(0)
    if gift_id == gifts.FRESH_PERSPECTIVE:
        assert game.effects.get_player_state(0)["free_refreshes"] == 2
    elif gift_id == gifts.MYSTIC_ESSENCE:
        assert len(player.hand) == 1 and player.hand[0]["cardType"] == "spell"
    elif gift_id == gifts.OFFENSIVE_SACRIFICE:
        assert side.board[0]["attack"] == 20
    elif gift_id == gifts.DEFENSIVE_SACRIFICE:
        assert side.board[0]["health"] == 26
    else:
        golem = next(card for card in side.board if card.get("name") == "Dark Gift Golem")
        assert (golem["attack"], golem["health"]) == (8, 12)


@pytest.mark.parametrize("gift_id,family,amount", [
    (gifts.BATTLE_SCARS_EARLY, TriggerFamily.BATTLECRY, 2),
    (gifts.BATTLE_SCARS_LATE, TriggerFamily.BATTLECRY, 3),
    (gifts.DEATHS_EMBRACE_EARLY, TriggerFamily.DEATHRATTLE, 1),
    (gifts.DEATHS_EMBRACE_LATE, TriggerFamily.DEATHRATTLE, 2),
    (gifts.SPELL_SIPHON_EARLY, None, 2),
    (gifts.SPELL_SIPHON_LATE, None, 3),
])
def test_history_gifts_continue_growing_in_hand(gift_id, family, amount):
    game = _game()
    host = _attach(game, gift_id)
    game.get_player(0).hand.append(host)
    if family is None:
        game.events.emit(GameEvent.SPELL_CAST, player_id=0, spell={"categories": ["tavern"]})
    else:
        game.events.emit(GameEvent.TRIGGER_RESOLVED, player_id=0, family=family)
    assert (host["attack"], host["health"]) == (8 + amount, 12 + amount)


@pytest.mark.parametrize("gift_id,attack,health", [
    (gifts.TRANSCENDENCE, 24, 36), (gifts.HOSTILITY, 16, 12),
    (gifts.RESISTANCE, 8, 24), (gifts.ADMIRATION, 10, 12),
])
def test_start_of_combat_scalers(gift_id, attack, health):
    game = _game()
    side = game.combat.engine.create_side(0, 4, [_host(900101, attack=2), _attach(game, gift_id)])
    enemy = game.combat.engine.create_side(1, 4, [_host(900102)])
    game.events.emit(GameEvent.COMBAT_START, side_a=side, side_b=enemy)
    assert (side.board[1]["attack"], side.board[1]["health"]) == (attack, health)


@pytest.mark.parametrize("gift_id,delta", [(gifts.SHARPENED_SWORD, (3, 0)),
    (gifts.TOUGHENED_SHIELD, (0, 3)), (gifts.DEXTERITY_EARLY, (2, 2)),
    (gifts.DEXTERITY_LATE, (4, 4))])
def test_card_play_gifts_include_spells_cast_from_hand(gift_id, delta):
    game = _game()
    host = _attach(game, gift_id)
    player = game.get_player(0)
    player.board[0] = host
    player.hand.append(game.effects.create_card(104436))
    game.cast_spell(0, 0)
    assert (host["attack"], host["health"]) == (8 + delta[0], 12 + delta[1])


@pytest.mark.parametrize("gift_id", [gifts.REPLICATION, gifts.AFFINITY])
def test_two_turn_gifts_generate_only_after_two_turn_ends(gift_id):
    game = _game()
    player = game.get_player(0)
    host = game.effects.create_card(120031)
    gifts.attach_dark_gift(game.effects, 0, host, _gift(game, gift_id), acquired_turn=8)
    player.board[0] = host
    game.events.emit(GameEvent.TURN_END, player_id=0)
    assert player.hand == []
    game.events.emit(GameEvent.TURN_END, player_id=0)
    assert len(player.hand) == 1
    assert not player.hand[0].get("_dark_gift_ids")


def test_time_turning_and_echoing_voice_trigger_the_hosts_original_effects():
    game = _game()
    counts = {"end": 0, "battlecry": 0}
    def end(ctx):
        counts["end"] += 1
    def battlecry(ctx):
        counts["battlecry"] += 1
    game.effects.register_end_of_turn(900100, end)
    game.effects.register_battlecry(900101, battlecry)
    player = game.get_player(0)
    player.board[0] = _attach(game, gifts.TIME_TURNING)
    player.board[1] = _attach(game, gifts.ECHOING_VOICE, id=900101)
    game.events.emit(GameEvent.TURN_START, player_id=0)
    assert counts == {"end": 1, "battlecry": 0}
    game.events.emit(GameEvent.TURN_END, player_id=0)
    assert counts == {"end": 2, "battlecry": 1}


def test_polarization_adds_mech_stats_and_attached_effect_identity():
    game = _game()
    host = _attach(game, gifts.POLARIZATION, minionType="Mech", minionTypes=["Mech"])
    game.get_player(0).board[0] = host
    game.events.emit(GameEvent.TURN_END, player_id=0)
    mech = host["_attachments"][-1]
    assert mech["cardType"] == "minion"
    assert (host["attack"], host["health"]) == (8 + mech["attack"], 12 + mech["health"])
    assert host["_magnetization_count"] == 1
