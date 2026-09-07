"""Focused pool-accounting and special-combination triple regressions."""

from game.bob import Bob
from game.triples import ELEMENTAL_OF_SURPRISE, TRIPLE_REWARD


def initialized_game():
    game = Bob(seed=24680)
    game.initialize_game()
    for player in game.players:
        game.choose_hero(player.player_id, player.hero_choices[0])
    return game


def elemental_ids(game, count=2):
    ids = []
    for card in game.pool.card_definitions:
        card_id = card.get("id")
        if (card.get("cardType") == "minion"
                and card_id != ELEMENTAL_OF_SURPRISE
                and game.effects.is_minion_type(card, "Elemental")
                and card_id not in ids):
            ids.append(card_id)
            if len(ids) == count:
                return ids
    raise AssertionError("Test database does not contain enough Elementals.")


def take_pool_copy(game, card_id):
    index = next(
        index
        for index, card in enumerate(game.pool.available_cards)
        if card.get("id") == card_id
    )
    return game.pool.available_cards.pop(index)


def test_mixed_triple_sale_returns_only_physical_pool_components():
    game = initialized_game()
    player = game.get_player(0)
    card_id = player.tavern.slots[0]["id"]
    initial_pool_count = game.pool.available_count()

    player.hand = [
        take_pool_copy(game, card_id),
        take_pool_copy(game, card_id),
    ]
    assert game.pool.available_count() == initial_pool_count - 2

    game.effects.add_generated_to_hand(
        0,
        game.effects.create_card(card_id),
    )

    assert len(player.hand) == 1
    golden = player.hand.pop()
    assert golden["isGolden"]
    assert len(golden["_triple_component_ids"]) == 3
    assert golden["_pool_copies"] == [card_id, card_id]

    player.board[0] = golden
    game.sell_minion(0, 0)

    assert game.pool.available_count() == initial_pool_count


def test_fully_generated_triple_sale_returns_no_pool_copies():
    game = initialized_game()
    player = game.get_player(0)
    base = player.tavern.slots[0]

    player.hand = [game.effects.create_card(base["id"]) for _ in range(2)]
    game.effects.add_generated_to_hand(
        0,
        game.effects.create_card(base["id"]),
    )

    assert len(player.hand) == 1
    golden = player.hand.pop()
    assert golden["isGolden"]
    assert len(golden["_triple_component_ids"]) == 3
    assert golden["_pool_copies"] == []

    player.board[0] = golden
    before = game.pool.available_count()
    game.sell_minion(0, 0)

    assert game.pool.available_count() == before


def test_one_surprise_completes_pair_and_keeps_surprise_enchantment_delta():
    game = initialized_game()
    player = game.get_player(0)
    target_id = elemental_ids(game, 1)[0]
    target_base = game.effects._definition_by_id(target_id)

    pair = [game.effects.create_card(target_id) for _ in range(2)]
    surprise = game.effects.create_card(ELEMENTAL_OF_SURPRISE)
    game.effects.apply_buff(surprise, attack=5, health=7)
    player.hand = pair + [surprise]

    game.triples.resolve(0)

    assert len(player.hand) == 1
    golden = player.hand[0]
    assert golden["id"] == target_id
    assert golden["isGolden"]
    assert golden["attack"] == target_base["attackGold"] + 5
    assert golden["health"] == target_base["healthGold"] + 7
    assert sorted(golden["_triple_component_ids"]) == sorted(
        [target_id, target_id, ELEMENTAL_OF_SURPRISE]
    )


def test_two_surprises_complete_one_elemental_into_that_elemental():
    game = initialized_game()
    player = game.get_player(0)
    target_id = elemental_ids(game, 1)[0]
    player.hand = [
        game.effects.create_card(target_id),
        game.effects.create_card(ELEMENTAL_OF_SURPRISE),
        game.effects.create_card(ELEMENTAL_OF_SURPRISE),
    ]

    game.triples.resolve(0)

    assert len(player.hand) == 1
    assert player.hand[0]["id"] == target_id
    assert player.hand[0]["isGolden"]


def test_one_surprise_does_not_merge_two_different_elementals():
    game = initialized_game()
    player = game.get_player(0)
    first_id, second_id = elemental_ids(game, 2)
    player.hand = [
        game.effects.create_card(first_id),
        game.effects.create_card(second_id),
        game.effects.create_card(ELEMENTAL_OF_SURPRISE),
    ]

    game.triples.resolve(0)

    assert len(player.hand) == 3
    assert not any(card["isGolden"] for card in player.hand)


def test_unrelated_golden_minion_does_not_grant_triple_reward_when_played():
    game = initialized_game()
    player = game.get_player(0)
    card_id = player.tavern.slots[0]["id"]
    golden = game.effects.create_card(card_id, golden=True)
    player.hand = [golden]

    game.play_minion(0, 0, 0)

    assert not any(card.get("id") == TRIPLE_REWARD for card in player.hand)
