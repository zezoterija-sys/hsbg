"""Season 14 Dark Discovery integration tests."""

from pathlib import Path

from game.actions import ActionType
from game.bob import Bob


CARDS_FILE = Path(__file__).resolve().parents[1] / "data" / "raw" / "cards.json"


def _start_real_recruit(seed=24680):
    game = Bob(cards_file=str(CARDS_FILE), seed=seed)
    game.initialize_game()
    for player in game.players:
        game.choose_hero(player.player_id, player.hero_choices[0])
    assert game.phase == "recruit"
    return game


def _action(game, player_id, action_type):
    return next(
        action
        for action in game.get_player_action_space(player_id)
        if action.action_type == action_type
    )


def test_dark_discovery_is_a_real_scheduler_action_and_reserves_pool_copies():
    game = _start_real_recruit()
    player = game.get_player(0)

    # Isolate the Season 14 unlock rule without simulating two irrelevant empty
    # combat rounds. The live scheduler/ActionSpace/Pool path remains real.
    game.round_number = 3
    player.gold = 3
    game.update_all_action_spaces()

    legal = game.get_player_action_space(0)
    assert any(action.action_type == ActionType.DARK_GIFT for action in legal)

    budget_before = game.scheduler.remaining_budget(0)
    time_before = game.scheduler.logical_time(0)
    pool_before = game.pool.available_count()

    game.execute_action(0, _action(game, 0, ActionType.DARK_GIFT))

    assert player.gold == 0
    assert game.dark_gifts.uses(0) == 1
    assert game.scheduler.remaining_budget(0) == budget_before - 1
    assert game.scheduler.logical_time(0) == time_before + 1

    pending = game.effects.get_pending_choice(0)
    assert pending is not None
    assert pending.kind == "dark_gift"
    assert len(pending.options) == 3

    # All three exact physical minion copies are reserved while the Discover is
    # unresolved. No other seat can draw them from the shared pool meanwhile.
    assert game.pool.available_count() == pool_before - 3

    # A mandatory continuation is zero scheduler cost and is the only action the
    # choosing player may submit even though other seats remain at logical time 0.
    choice_actions = game.get_player_action_space(0)
    assert len(choice_actions) == 3
    assert all(action.action_type == ActionType.CHOOSE_OPTION for action in choice_actions)

    selected_offer = pending.options[0]
    selected_id = selected_offer.minion["id"]
    selected_gift_id = selected_offer.gift["id"]

    game.execute_action(0, choice_actions[0])

    assert game.scheduler.remaining_budget(0) == budget_before - 1
    assert game.scheduler.logical_time(0) == time_before + 1
    assert game.effects.get_pending_choice(0) is None
    assert game.pool.available_count() == pool_before - 1

    selected = player.hand[-1]
    assert selected["id"] == selected_id
    assert selected_gift_id in selected.get("_dark_gift_ids", [])
    assert any(
        attachment.get("id") == selected_gift_id
        and attachment.get("_dark_gift") is True
        for attachment in selected.get("_attachments", [])
    )

    # Once-per-turn is a game rule independent from the artificial scheduler.
    assert not any(
        action.action_type == ActionType.DARK_GIFT
        for action in game.get_player_action_space(0)
    )


def test_dark_discovery_unlock_and_turn_tier_schedule():
    game = _start_real_recruit(seed=13579)
    player = game.get_player(0)
    player.gold = 10

    assert game.dark_gifts.tiers_for_turn(1) == ()
    assert game.dark_gifts.tiers_for_turn(2) == ()
    assert game.dark_gifts.tiers_for_turn(3) == (2,)
    assert game.dark_gifts.tiers_for_turn(4) == (2, 3)
    assert game.dark_gifts.tiers_for_turn(5) == (3,)
    assert game.dark_gifts.tiers_for_turn(6) == (3, 4)
    assert game.dark_gifts.tiers_for_turn(7) == (4,)
    assert game.dark_gifts.tiers_for_turn(8) == (4, 5)
    assert game.dark_gifts.tiers_for_turn(9) == (4, 5, 6)
    assert game.dark_gifts.tiers_for_turn(10) == (5, 6)
    assert game.dark_gifts.tiers_for_turn(20) == (5, 6)

    game.round_number = 2
    game.update_all_action_spaces()
    assert not any(
        action.action_type == ActionType.DARK_GIFT
        for action in game.get_player_action_space(0)
    )

    game.round_number = 3
    game.update_all_action_spaces()
    assert any(
        action.action_type == ActionType.DARK_GIFT
        for action in game.get_player_action_space(0)
    )
