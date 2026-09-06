"""Fast tests for Brain-B observation/action encoding and policy forward pass."""

from __future__ import annotations

import torch

from agents.action_encoder import ActionEncoder
from agents.observation import (
    AgentObservation,
    ChoiceView,
    OpponentBoardMemory,
    OwnPlayerView,
    PoolKnowledge,
    PublicOpponentView,
    TavernUpgradeMemory,
)
from agents.observation_encoder import CardVocabulary, ObservationEncoder
from game.actions import Action, ActionType
from models.policy_network import PolicyNetwork


def _observation(*, with_memory: bool = True) -> AgentObservation:
    self_view = OwnPlayerView(
        player_id=0,
        hero_id=100,
        hero_power={"id": 101, "name": "Test Power"},
        health=37,
        armor=5,
        gold=7,
        ap=42,
        tavern_tier=4,
        waiting=False,
        eliminated=False,
        placement=None,
        board=(
            {
                "id": 700,
                "name": "Own Minion",
                "attack": 12,
                "health": 13,
                "tier": 4,
            },
        ),
        hand=(),
        tavern_slots=(),
        tavern_spell=None,
        tavern_frozen=False,
        effect_state={
            "free_refreshes": 2,
            "gold_spent_game": 23,
            "last_tavern_spell": {"id": 500},
            "refresh_random_buffs": [(10, 10), (5, 7)],
        },
        max_gold=12,
        hero_power_cost=2,
    )

    memory = None
    if with_memory:
        memory = OpponentBoardMemory(
            player_id=1,
            seen_round=4,
            rounds_old=2,
            board=(
                {
                    "id": 600,
                    "attack": 8,
                    "health": 8,
                    "tier": 3,
                },
            ),
        )

    opponent = PublicOpponentView(
        player_id=1,
        hero_id=400,
        health=30,
        armor=2,
        tavern_tier=3,
        eliminated=False,
        placement=None,
        last_opponent_id=0,
        last_seen_board=memory,
    )

    pool = PoolKnowledge(
        initial_minion_copies_by_tier={
            1: 18,
            2: 18,
            3: 15,
            4: 15,
            5: 11,
            6: 11,
        },
        initial_spell_copies_by_tier={
            1: 5,
            2: 7,
            3: 9,
            4: 11,
            5: 9,
            6: 7,
        },
        own_visible_counts={700: 1},
        opponent_memory_evidence=(),
    )

    return AgentObservation(
        player_id=0,
        round_number=6,
        phase="recruit",
        game_over=False,
        self_player=self_view,
        opponents=(opponent,),
        last_opponent_id=1,
        pool=pool,
        recent_tavern_upgrades=(
            TavernUpgradeMemory(
                player_id=1,
                old_tier=2,
                new_tier=3,
                seen_round=5,
                rounds_old=1,
            ),
        ),
        pending_choice=ChoiceView(
            options=(
                {"id": 300, "name": "Choice Card"},
                "gems",
            ),
            resolver_key="test",
            kind="discover",
            source_card_id=201,
        ),
    )


def _vocabulary() -> CardVocabulary:
    return CardVocabulary(
        [100, 101, 201, 300, 400, 500, 600, 700]
    )


def test_observation_schema_encodes_identity_economy_and_effect_state():
    vocabulary = _vocabulary()
    encoder = ObservationEncoder(vocabulary)
    encoded = encoder.encode(_observation())

    assert ObservationEncoder.SCHEMA_VERSION == 4
    assert encoded.scalar_features.shape == (
        ObservationEncoder.SCALAR_FEATURE_SIZE,
    )
    assert encoded.card_features.shape == (
        ObservationEncoder.TOTAL_CARD_SLOTS,
        ObservationEncoder.CARD_FEATURE_SIZE,
    )
    assert encoded.identity_ids.shape == (
        ObservationEncoder.IDENTITY_SLOTS,
    )

    assert encoded.identity_ids[
        ObservationEncoder.OWN_HERO_IDENTITY_SLOT
    ].item() == vocabulary.encode(100)
    assert encoded.identity_ids[
        ObservationEncoder.OWN_HERO_POWER_IDENTITY_SLOT
    ].item() == vocabulary.encode(101)

    assert encoded.scalar_features[
        encoder.scalar_index("self_max_gold")
    ].item() > 0
    assert encoded.scalar_features[
        encoder.scalar_index("self_hero_power_cost")
    ].item() > 0
    assert encoded.scalar_features[
        encoder.scalar_index("effect_free_refreshes")
    ].item() > 0


def test_unseen_opponent_board_does_not_appear_in_encoding():
    encoder = ObservationEncoder(_vocabulary())
    encoded = encoder.encode(
        _observation(with_memory=False)
    )

    opponent_mask = encoded.card_mask[
        ObservationEncoder.OWN_CARD_SLOTS :
    ]
    assert not opponent_mask.any().item()


def test_choose_option_encodes_concrete_card_or_semantic_token():
    observation = _observation()
    encoder = ActionEncoder()

    card_choice = Action(
        ActionType.CHOOSE_OPTION,
        option_idx=0,
    )
    string_choice = Action(
        ActionType.CHOOSE_OPTION,
        option_idx=1,
    )

    assert encoder.candidate_card_id(
        card_choice,
        observation,
    ) == 300
    assert encoder.candidate_card_id(
        string_choice,
        observation,
    ) is None

    first = encoder.encode(
        string_choice,
        observation,
    )
    second = encoder.encode(
        string_choice,
        observation,
    )
    assert first == second
    assert sum(first[-ActionEncoder.CHOICE_TOKEN_BUCKETS :]) == 1.0


def test_policy_network_forward_is_finite_with_candidate_cards():
    observation = _observation()
    vocabulary = _vocabulary()
    observation_encoder = ObservationEncoder(
        vocabulary
    )
    action_encoder = ActionEncoder()

    actions = (
        Action(ActionType.CHOOSE_OPTION, option_idx=0),
        Action(ActionType.CHOOSE_OPTION, option_idx=1),
    )

    encoded_observation = observation_encoder.encode(
        observation
    )
    action_features = torch.tensor(
        action_encoder.encode_many(
            actions,
            observation,
        ),
        dtype=torch.float32,
    )
    action_card_ids = torch.tensor(
        [
            vocabulary.encode(
                action_encoder.candidate_card_id(
                    action,
                    observation,
                )
            )
            for action in actions
        ],
        dtype=torch.long,
    )

    model = PolicyNetwork(
        card_vocab_size=len(vocabulary)
    )
    output = model(
        encoded_observation,
        action_features,
        action_card_ids,
    )

    assert output.policy_logits.shape == (2,)
    assert output.value.ndim == 0
    assert torch.isfinite(output.policy_logits).all()
    assert torch.isfinite(output.value)


def test_card_vocabulary_fingerprint_tracks_mapping():
    left = CardVocabulary([3, 1, 2])
    right = CardVocabulary([1, 2, 3])
    changed = CardVocabulary([1, 2, 4])

    assert left.fingerprint == right.fingerprint
    assert left.fingerprint != changed.fingerprint
