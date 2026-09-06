"""Focused pool-accounting regressions for ordinary triples."""

from game.bob import Bob


def initialized_game():
    game = Bob(seed=24680)
    game.initialize_game()
    for player in game.players:
        game.choose_hero(player.player_id, player.hero_choices[0])
    return game


def test_mixed_triple_sale_returns_only_physical_pool_components():
    game = initialized_game()
    player = game.get_player(0)
    base = player.tavern.slots[0]

    player.hand = [
        game.effects.create_card(base["id"], generated=False)
        for _ in range(2)
    ]
    game.effects.add_generated_to_hand(
        0,
        game.effects.create_card(base["id"]),
    )

    assert len(player.hand) == 1
    golden = player.hand.pop()
    assert golden["isGolden"]
    assert len(golden["_triple_component_ids"]) == 3
    assert golden["_pool_copies"] == [base["id"], base["id"]]

    player.board[0] = golden
    before = game.pool.available_count()
    game.sell_minion(0, 0)

    assert game.pool.available_count() == before + 2


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
