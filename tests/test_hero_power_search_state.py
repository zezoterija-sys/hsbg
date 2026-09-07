"""Hero Power lifecycle must survive the player-visible search boundary."""

from copy import deepcopy
import random

import pytest

from agents.observation import AgentMemory, ObservationBuilder
from agents.simulation_environment import DeterminizedBattlegroundsEnvironment
from game.actions import ActionType
from game.bob import Bob
from game.effects import EffectZone
from game.hero_powers import HeroPowerSystem


def make_game():
    game = Bob(seed=4401)
    game.initialize_game()
    for player in game.players:
        game.choose_hero(player.player_id, player.hero_choices[0])
    player = game.get_player(0)
    # A controlled fixture avoids depending on the shuffled hero offers.
    player.hero = 57929  # George
    from game.heroes import HEROES
    player.set_hero_power(HEROES[57929]["power"])
    player.hero_power_cost = 1
    player.gold = 10
    player.board[0] = game.effects.create_card(120031)
    game.update_all_action_spaces()
    return game, player, HeroPowerSystem.for_game(game)


def use_george(game):
    target = game.effects.resolve_target_ref(0, EffectZone.BOARD, 0)
    game.use_hero_power(0, target_ref=target)


def test_spent_power_stays_spent_in_determinized_world():
    game, _, powers = make_game()
    use_george(game)
    game.update_all_action_spaces()
    observation = ObservationBuilder(AgentMemory(0)).build(game)
    world = DeterminizedBattlegroundsEnvironment().sample_determinization(
        observation, 0, random.Random(12)
    ).game
    copied = HeroPowerSystem.for_game(world)
    assert copied.uses_this_turn(0) == powers.uses_this_turn(0) == 1
    assert copied.uses_this_game(0) == 1
    assert not copied.can_use(0)
    world.update_action_space(0)
    assert not any(a.action_type == ActionType.HERO_POWER for a in world.get_player_action_space(0))


def test_root_state_copies_extra_uses_and_arms_but_not_opponent_secrets():
    game, _, powers = make_game()
    powers.grant_extra_uses(0, 2)
    powers.arm(0, "visible_next_combat", {"tier": 4})
    powers.arm(1, "opponent_only", {"secret": 999})
    use_george(game)
    game.update_all_action_spaces()
    observation = ObservationBuilder(AgentMemory(0)).build(game)
    environment = DeterminizedBattlegroundsEnvironment()
    world = environment.sample_determinization(observation, 0, random.Random(12)).game
    copied = HeroPowerSystem.for_game(world)
    assert copied.extra_uses_this_turn(0) == 2
    assert copied.can_use(0)
    assert copied.peek_arm(0, "visible_next_combat") == {"tier": 4}
    assert not copied.is_armed(1, "opponent_only")
    copied.peek_arm(0, "visible_next_combat")["tier"] = 6
    use_george(world)
    assert powers.uses_this_turn(0) == 1
    assert powers.peek_arm(0, "visible_next_combat") == {"tier": 4}
    sibling = environment.sample_determinization(observation, 0, random.Random(13)).game
    assert sibling.hero_powers.uses_this_turn(0) == 1
    assert sibling.hero_powers.peek_arm(0, "visible_next_combat") == {"tier": 4}


@pytest.mark.parametrize("blocked", ["choice", "game_over"])
def test_direct_call_cannot_bypass_recruit_lock(blocked):
    game, player, powers = make_game()
    if blocked == "choice":
        game.effects.start_choice(0, game.dark_gifts.RESOLVER_KEY, [1])
    else:
        game.game_over = True
    before = deepcopy(player.board[0])
    with pytest.raises(ValueError):
        use_george(game)
    assert player.gold == 10
    assert player.board[0] == before
    assert powers.uses_this_turn(0) == 0


def test_unregistered_direct_call_is_guarded_before_action_generation():
    game = Bob(seed=12)
    game.create_players()
    game.phase = "recruit"
    player = game.get_player(0)
    player.set_hero(62242)  # Eudora: still unimplemented
    player.gold = 10
    player.set_ap(20)
    with pytest.raises(ValueError):
        game.use_hero_power(0)
    assert player.gold == 10


def test_state_snapshot_and_restore_do_not_share_mutable_payloads():
    game, _, powers = make_game()
    powers.arm(0, "next_combat", {"tier": 4})
    powers.grant_extra_uses(0, 2)
    use_george(game)
    snapshot = powers.export_player_state(0)
    copied = deepcopy(game).hero_powers
    copied.restore_player_state(0, snapshot)
    snapshot["armed"]["next_combat"]["tier"] = 6
    assert powers.peek_arm(0, "next_combat") == {"tier": 4}
    assert copied.peek_arm(0, "next_combat") == {"tier": 4}


def test_restore_old_turn_keeps_game_count_but_expires_turn_uses():
    game, _, powers = make_game()
    powers.grant_extra_uses(0, 2)
    use_george(game)
    snapshot = powers.export_player_state(0)
    game.round_number += 1
    powers.restore_player_state(0, snapshot)
    assert powers.uses_this_game(0) == 1
    assert powers.uses_this_turn(0) == 0
    assert powers.extra_uses_this_turn(0) == 0


@pytest.mark.parametrize("invalid", [{"power_id": -1}, {"uses_turn": -1}, {"armed": []}])
def test_invalid_lifecycle_restore_rejected_without_mutation(invalid):
    _, _, powers = make_game()
    original = powers.export_player_state(0)
    malformed = dict(original, **invalid)
    with pytest.raises(ValueError):
        powers.restore_player_state(0, malformed)
    assert powers.export_player_state(0) == original
