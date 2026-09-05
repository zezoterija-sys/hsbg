from game.combat import CombatEngine


def _minion(name, attack, health, keywords=()):
    return {
        "name": name,
        "attack": attack,
        "health": health,
        "keywords": list(keywords),
    }


def test_venomous_applies_to_first_minion_actually_damaged_each_combat():
    engine = CombatEngine()
    source_side = engine.create_side(
        0,
        1,
        [_minion("Venom source", 1, 10, ("Venomous",))],
    )
    target_side = engine.create_side(
        1,
        1,
        [
            _minion("First target", 0, 20),
            _minion("Second target", 0, 20),
        ],
    )

    source = source_side.board[0]
    first, second = target_side.board

    engine.deal_minion_damage(
        source,
        first,
        1,
        source_side=source_side,
        target_side=target_side,
    )
    assert first["health"] <= 0
    assert source["_combat_venomous_available"] is False

    engine.deal_minion_damage(
        source,
        second,
        1,
        source_side=source_side,
        target_side=target_side,
    )
    assert second["health"] == 19


def test_divine_shield_does_not_consume_venomous_before_actual_damage():
    engine = CombatEngine()
    source_side = engine.create_side(
        0,
        1,
        [_minion("Venom source", 1, 10, ("Venomous",))],
    )
    target_side = engine.create_side(
        1,
        1,
        [
            _minion("Shielded", 0, 20, ("Divine Shield",)),
            _minion("Unshielded", 0, 20),
        ],
    )

    source = source_side.board[0]
    shielded, unshielded = target_side.board

    dealt = engine.deal_minion_damage(
        source,
        shielded,
        1,
        source_side=source_side,
        target_side=target_side,
    )
    assert dealt == 0
    assert shielded["health"] == 20
    assert source["_combat_venomous_available"] is True

    engine.deal_minion_damage(
        source,
        unshielded,
        1,
        source_side=source_side,
        target_side=target_side,
    )
    assert unshielded["health"] <= 0
    assert source["_combat_venomous_available"] is False


def test_new_combat_copy_refreshes_venomous():
    engine = CombatEngine()
    definition = _minion("Venom source", 1, 10, ("Venomous",))

    first_combat = engine.create_side(0, 1, [definition])
    first_combat.board[0]["_combat_venomous_available"] = False

    second_combat = engine.create_side(0, 1, [definition])
    assert second_combat.board[0]["_combat_venomous_available"] is True
