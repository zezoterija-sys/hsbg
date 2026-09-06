"""Hero Power lifecycle regression tests.

These tests deliberately use a real hero definition but no hero-specific effect
handler.  They verify that printed data alone is not enough to expose a Hero
Power action and that the generic lifecycle controller owns legality/use state.
"""

from pathlib import Path

from game.actions import ActionType
from game.bob import Bob
from game.events import GameEvent
from game.hero_powers import HeroPowerSystem


CARDS_FILE = Path(__file__).resolve().parents[1] / "data" / "raw" / "cards.json"
GEORGE_HERO_ID = 57929
GEORGE_POWER_ID = 57562


def _game(*, round_number=1, gold=10):
    game = Bob(cards_file=str(CARDS_FILE), seed=8801)
    game.create_players()
    game.phase = "recruit"
    game.round_number = round_number
    player = game.get_player(0)
    player.set_hero(GEORGE_HERO_ID)
    player.set_gold(gold)
    player.set_ap(20)
    return game, player, HeroPowerSystem.for_game(game)


def _has_hero_power_action(game, player_id=0):
    game.update_action_space(player_id)
    return any(
        action.action_type == ActionType.HERO_POWER
        for action in game.get_player_action_space(player_id)
    )


def _hero_power_action(game, player_id=0):
    game.update_action_space(player_id)
    return next(
        action
        for action in game.get_player_action_space(player_id)
        if action.action_type == ActionType.HERO_POWER
    )


def test_printed_hero_power_without_runtime_rule_is_not_clickable():
    game, _, hero_powers = _game()

    assert hero_powers.get_rule(GEORGE_POWER_ID) is None
    assert hero_powers.can_use(0) is False
    assert _has_hero_power_action(game) is False


def test_passive_and_automatic_rules_never_create_clickable_actions():
    passive_game, _, passive = _game()
    passive.register_passive(GEORGE_POWER_ID)
    assert passive.can_use(0) is False
    assert _has_hero_power_action(passive_game) is False

    automatic_game, _, automatic = _game()
    automatic.register_automatic(GEORGE_POWER_ID)
    assert automatic.can_use(0) is False
    assert _has_hero_power_action(automatic_game) is False


def test_active_rule_enforces_turn_and_tavern_tier_unlocks_before_action_generation():
    game, player, hero_powers = _game(round_number=2)
    hero_powers.register_active(
        GEORGE_POWER_ID,
        unlock_turn=3,
        unlock_tavern_tier=4,
    )

    assert _has_hero_power_action(game) is False

    game.round_number = 3
    assert _has_hero_power_action(game) is False

    player.tavern_tier = 4
    player.tavern.set_tier(4)
    assert hero_powers.can_use(0) is True
    assert _has_hero_power_action(game) is True


def test_emitted_use_is_recorded_and_default_once_per_turn_limit_blocks_second_use():
    game, player, hero_powers = _game(round_number=5)
    hero_powers.register_active(GEORGE_POWER_ID)

    action = _hero_power_action(game)
    gold_before = player.gold
    game.execute_action(0, action)

    assert player.gold == gold_before - 1
    assert hero_powers.uses_this_turn(0) == 1
    assert hero_powers.uses_this_game(0) == 1
    assert hero_powers.can_use(0) is False
    assert _has_hero_power_action(game) is False

    game.round_number = 6
    assert hero_powers.uses_this_turn(0) == 0
    assert hero_powers.can_use(0) is True


def test_once_per_game_rule_remains_exhausted_on_later_turns():
    game, _, hero_powers = _game(round_number=5)
    hero_powers.register_active(GEORGE_POWER_ID, max_uses_per_game=1)

    game.events.emit(GameEvent.HERO_POWER_USED, player_id=0)
    assert hero_powers.uses_this_game(0) == 1

    game.round_number = 6
    assert hero_powers.uses_this_turn(0) == 0
    assert hero_powers.can_use(0) is False


def test_extra_uses_extend_only_the_current_turn_limit():
    game, _, hero_powers = _game(round_number=5)
    hero_powers.register_active(GEORGE_POWER_ID)

    game.events.emit(GameEvent.HERO_POWER_USED, player_id=0)
    assert hero_powers.can_use(0) is False

    hero_powers.grant_extra_uses(0, 1)
    assert hero_powers.can_use(0) is True

    game.events.emit(GameEvent.HERO_POWER_USED, player_id=0)
    assert hero_powers.uses_this_turn(0) == 2
    assert hero_powers.can_use(0) is False

    game.round_number = 6
    assert hero_powers.extra_uses_this_turn(0) == 0
    assert hero_powers.can_use(0) is True


def test_delayed_effect_arm_is_explicit_and_consumed_once():
    _, _, hero_powers = _game()

    hero_powers.arm(0, "next_combat", {"tier": 4})
    assert hero_powers.is_armed(0, "next_combat") is True
    assert hero_powers.peek_arm(0, "next_combat") == {"tier": 4}
    assert hero_powers.consume_arm(0, "next_combat") == {"tier": 4}
    assert hero_powers.is_armed(0, "next_combat") is False
    assert hero_powers.consume_arm(0, "next_combat") is None


def test_game_start_resets_runtime_uses_and_arms_but_preserves_rules():
    game, _, hero_powers = _game(round_number=5)
    hero_powers.register_active(GEORGE_POWER_ID, max_uses_per_game=1)
    game.events.emit(GameEvent.HERO_POWER_USED, player_id=0)
    hero_powers.arm(0, "test")

    assert hero_powers.uses_this_game(0) == 1
    assert hero_powers.is_armed(0, "test")

    game.events.emit(GameEvent.GAME_START, player_count=8)

    assert hero_powers.get_rule(GEORGE_POWER_ID) is not None
    assert hero_powers.uses_this_game(0) == 0
    assert hero_powers.is_armed(0, "test") is False
