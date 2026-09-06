"""Regression tests for Dark Gifts that require multi-event engine behavior."""

from pathlib import Path

from game.bob import Bob
from game.dark_gift_effects import (
    DEMONOLOGY,
    DOUBLE_VISION,
    PERSISTING_HORROR,
    SUNKEN_PERSISTENCE,
    TARECGOSAS_BLESSING,
    TORETHS_BLESSING,
    attach_dark_gift,
)
from game.events import GameEvent


CARDS_FILE = Path(__file__).resolve().parents[1] / "data" / "raw" / "cards.json"


def _game(seed=901):
    game = Bob(cards_file=str(CARDS_FILE), seed=seed)
    game.create_players()
    game.phase = "recruit"
    game.round_number = 8
    game.priority_order = list(range(8))
    game.combat.engine.set_priority_order(game.priority_order)
    return game


def _gift(game, gift_id):
    return dict(game.pool.card_definitions_by_id[gift_id])


def _host(card_id=900100, **updates):
    card = {
        "id": card_id,
        "name": "Gift Host",
        "cardType": "minion",
        "attack": 8,
        "health": 12,
        "attackGold": 16,
        "healthGold": 24,
        "text": "",
        "tier": 4,
        "minionType": "Dragon",
        "minionTypes": ["Dragon"],
        "keywords": [],
    }
    card.update(updates)
    return card


def test_double_vision_generates_plain_extra_copy_after_selected_minion_enters_hand():
    game = _game()
    player = game.get_player(0)
    # Use a real card ID so the generated plain copy can come from the card DB.
    host = game.effects.create_card(120031, generated=False)
    attach_dark_gift(game.effects, 0, host, _gift(game, DOUBLE_VISION), acquired_turn=8)

    player.hand.append(host)
    game.events.emit(GameEvent.CARD_ADDED_TO_HAND, player_id=0, card=host)

    assert len(player.hand) == 2
    extra = player.hand[1]
    assert extra["id"] == host["id"]
    assert DOUBLE_VISION not in extra.get("_dark_gift_ids", [])
    assert not any(
        attachment.get("id") == DOUBLE_VISION
        for attachment in extra.get("_attachments", [])
        if isinstance(attachment, dict)
    )


def test_toreths_blessing_divine_shield_takes_three_damage_hits_to_break():
    game = _game()
    engine = game.combat.engine
    host = _host(keywords=["Divine Shield"])
    attach_dark_gift(game.effects, 0, host, _gift(game, TORETHS_BLESSING), acquired_turn=8)

    side = engine.create_side(0, 4, [host])
    enemy = engine.create_side(1, 4, [_host(900101, attack=3, health=50)])
    runtime = side.board[0]
    source = enemy.board[0]

    assert runtime["_combat_divine_shield"] is True

    assert engine.deal_minion_damage(source, runtime, 3, enemy, side) == 0
    assert runtime["_combat_divine_shield"] is True
    assert runtime["health"] == 12

    assert engine.deal_minion_damage(source, runtime, 3, enemy, side) == 0
    assert runtime["_combat_divine_shield"] is True
    assert runtime["health"] == 12

    assert engine.deal_minion_damage(source, runtime, 3, enemy, side) == 0
    assert runtime["_combat_divine_shield"] is False
    assert runtime["health"] == 12

    assert engine.deal_minion_damage(source, runtime, 3, enemy, side) == 3
    assert runtime["health"] == 9


def test_persisting_horror_reborn_returns_with_full_tracked_health_and_bonus_keywords():
    game = _game()
    engine = game.combat.engine
    host = _host(keywords=["Taunt"])
    attach_dark_gift(game.effects, 0, host, _gift(game, PERSISTING_HORROR), acquired_turn=10)
    game.effects.grant_keyword(host, "Divine Shield")

    side = engine.create_side(0, 4, [host])
    enemy = engine.create_side(1, 4, [_host(900102, attack=100, health=100)])
    runtime = side.board[0]

    # Let combat-start trackers observe the pre-damage full Health.
    engine.emit(GameEvent.COMBAT_START, side_a=side, side_b=enemy)
    runtime["_combat_divine_shield"] = False
    engine.deal_minion_damage(enemy.board[0], runtime, 100, enemy, side)
    engine.resolve_deaths(side, enemy)

    assert len(side.board) == 1
    reborn = side.board[0]
    assert reborn["health"] == 12
    assert game.effects.has_keyword(reborn, "Taunt")
    assert game.effects.has_keyword(reborn, "Divine Shield")
    assert not game.effects.has_keyword(reborn, "Reborn")


def test_tarecgosa_blessing_persists_double_positive_combat_gains_to_real_board_copy():
    game = _game()
    player = game.get_player(0)
    host = _host()
    attach_dark_gift(game.effects, 0, host, _gift(game, TARECGOSAS_BLESSING), acquired_turn=8)

    # Real Combat._snapshot_boards() tags every persistent board minion before
    # CombatEngine receives its copied combat side. Mirror that production
    # boundary here because this unit test constructs the side directly.
    host["_persistent_board_index"] = 0
    player.board[0] = host

    engine = game.combat.engine
    side = engine.create_side(0, 4, player.board)
    enemy = engine.create_side(1, 4, [_host(900103, attack=0, health=50)])
    runtime = side.board[0]
    assert runtime["_persistent_board_index"] == 0

    engine.emit(GameEvent.COMBAT_START, side_a=side, side_b=enemy)
    runtime["attack"] += 5
    runtime["health"] += 4
    runtime.setdefault("keywords", []).append("Windfury")
    engine.emit(GameEvent.COMBAT_END, side_a=side, side_b=enemy)

    # Original 8/12 plus DOUBLE the +5/+4 combat gain.
    assert player.board[0]["attack"] == 18
    assert player.board[0]["health"] == 20
    assert game.effects.has_keyword(player.board[0], "Windfury")


def test_demonology_adds_one_generated_fodder_to_each_of_next_three_refreshes():
    game = _game()
    player = game.get_player(0)
    host = _host(minionType="Demon", minionTypes=["Demon"])
    attach_dark_gift(game.effects, 0, host, _gift(game, DEMONOLOGY), acquired_turn=6)
    player.board[0] = host

    # Rally once to arm three future refreshes.
    game.events.emit(
        GameEvent.ATTACK,
        player_id=0,
        attacker=host,
        source_side=None,
        attacking_side=None,
    )
    state = game.effects.get_player_state(0)
    assert state["dark_gift_fodder_refreshes"] == 3

    for remaining in (2, 1, 0):
        before = len(player.tavern.slots)
        game.events.emit(GameEvent.TAVERN_REFRESHED, player_id=0)
        assert len(player.tavern.slots) == before + 1
        assert player.tavern.slots[-1]["id"] == 130084
        assert player.tavern.slots[-1].get("_generated") is True
        assert state["dark_gift_fodder_refreshes"] == remaining

    before = len(player.tavern.slots)
    game.events.emit(GameEvent.TAVERN_REFRESHED, player_id=0)
    assert len(player.tavern.slots) == before


def test_sunken_persistence_converts_new_spellcraft_temporary_stats_and_keyword_to_permanent():
    game = _game()
    player = game.get_player(0)
    source = _host(card_id=80745, minionType="Naga", minionTypes=["Naga"])
    attach_dark_gift(game.effects, 0, source, _gift(game, SUNKEN_PERSISTENCE), acquired_turn=3)
    player.board[0] = source

    target = _host(900104, attack=5, health=5, keywords=[])
    player.board[1] = target

    spell = {
        "id": 999001,
        "name": "Synthetic Spellcraft",
        "cardType": "spell",
        "categories": ["spellcraft"],
        "_spellcraft_temporary": True,
        "_spellcraft_source_id": source["id"],
    }

    def synthetic_spell_effect(event):
        if event.get("spell") is not spell:
            return
        game.effects.apply_buff(target, attack=3, health=2, until_next_turn=True)
        game.effects.grant_keyword(target, "Windfury", until_next_turn=True)

    game.events.register(GameEvent.SPELL_CAST, synthetic_spell_effect, order=0)
    game.events.emit(GameEvent.SPELL_CAST, player_id=0, spell=spell, card=spell, target=target)

    assert (target["attack"], target["health"]) == (8, 7)
    assert game.effects.has_keyword(target, "Windfury")
    assert target.get("_temporary_stat_modifiers", []) == []
    assert "Windfury" in target.get("_permanent_keyword_grants", [])

    game.round_number += 1
    game.events.emit(GameEvent.TURN_START, player_id=0, round_number=game.round_number)
    assert (target["attack"], target["health"]) == (8, 7)
    assert game.effects.has_keyword(target, "Windfury")
