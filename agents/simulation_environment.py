"""
Fair Battlegrounds simulation environment for both MCTS brains.

Key principle:
THIS MODULE NEVER CLONES THE REAL BOB.

For each root observation it builds a clean public template Bob containing only
information the root player is allowed to know. Each MCTS simulation deep-copies
that clean template, then samples hidden opponent boards/hands/Taverns and pool
occupancy from the belief model.

This gives MCTS access to the real engine mechanics without giving it exact
hidden information from the real lobby.

The environment implements:
- MCTSEnvironment for pure MCTS,
- NeuralMCTSEnvironment.observe() for neural PUCT,
- cheap random opponent behavior inside imaginary futures,
- random-rollout evaluation based on simulated outcomes, not board heuristics.
"""

from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
from dataclasses import dataclass, field
import random
from typing import Any, Sequence

from agents.belief_model import (
    BeliefConfig,
    PoolBeliefModel,
)
from agents.observation import (
    AgentMemory,
    AgentObservation,
    ObservationBuilder,
)
from agents.rollout_policy import (
    RandomLegalPolicy,
    RandomPolicyConfig,
    RolloutRewardConfig,
)
from game.actions import Action, ActionType
from game.bob import Bob
from game.pool import CardPool
from game.dark_gift_effects import _ensure_registered as ensure_dark_gift_effects
from game.effects import PendingChoice


@dataclass
class DeterminizedGameState:
    """One mutable imaginary world used by one MCTS simulation."""

    game: Bob
    memory: AgentMemory
    root_player_id: int

    root_actions_this_turn: int = 0
    opponent_actions_this_turn: dict[int, int] = field(
        default_factory=dict
    )

    last_counted_combat_round: int = 0


class DeterminizedBattlegroundsEnvironment:
    """
    Shared environment implementation usable by MCTSAgent and NeuralMCTSAgent.

    Use one instance per agent when possible. It caches a clean public template
    for the current decision to avoid re-reading cards.json and re-registering
    all effects for every one of the 200 simulations.
    """

    def __init__(
        self,
        *,
        cards_file: str = "data/raw/cards.json",
        belief_config: BeliefConfig | None = None,
        random_policy_config: RandomPolicyConfig | None = None,
        rollout_reward_config: RolloutRewardConfig | None = None,
    ) -> None:
        self.cards_file = cards_file

        self.belief = PoolBeliefModel(
            belief_config
        )
        self.random_policy = RandomLegalPolicy(
            random_policy_config
        )
        self.rollout_rewards = (
            rollout_reward_config
            or RolloutRewardConfig()
        )

        # Cache only a clean world made from legal/public information.
        # Never place a real Bob here.
        self._template_observation: AgentObservation | None = None
        self._template_game: Bob | None = None

    # ==================================================================
    # MCTS ENVIRONMENT API
    # ==================================================================

    def sample_determinization(
        self,
        observation: AgentObservation,
        root_player_id: int,
        rng: random.Random,
    ) -> DeterminizedGameState:
        if observation.player_id != root_player_id:
            raise ValueError(
                "Observation does not belong to root_player_id."
            )

        if observation.phase != "recruit":
            raise ValueError(
                "Recruit MCTS determinization requires phase='recruit'."
            )

        template = self._get_public_template(
            observation
        )

        try:
            game = deepcopy(
                template
            )
        except Exception:
            # Conservative fallback for an engine object that later gains a
            # non-deepcopyable runtime resource. This still builds from the
            # observation, never from the real hidden game.
            game = self._build_public_template(
                observation
            )

        memory = AgentMemory(
            root_player_id
        )
        memory.seed_from_observation(
            observation
        )

        state = DeterminizedGameState(
            game=game,
            memory=memory,
            root_player_id=root_player_id,
            last_counted_combat_round=max(
                0,
                observation.round_number - 1,
            ),
        )

        self._seed_world_rngs(
            game,
            rng,
        )

        self._sample_hidden_opponents(
            state,
            observation,
            rng,
        )

        # Priority is an internal collision-resolution device rather than hidden
        # strategic information. Sample it independently in each world.
        game.priority_order = rng.sample(
            list(range(game.PLAYER_COUNT)),
            game.PLAYER_COUNT,
        )

        engine = getattr(
            getattr(game, "combat", None),
            "engine",
            None,
        )
        if engine is not None:
            setter = getattr(
                engine,
                "set_priority_order",
                None,
            )
            if callable(setter):
                setter(
                    game.priority_order
                )

        game.update_all_action_spaces()

        return state

    def legal_actions(
        self,
        state: DeterminizedGameState,
        root_player_id: int,
    ) -> Sequence[Action]:
        self._validate_state_owner(
            state,
            root_player_id,
        )

        game = state.game

        if self.is_terminal(
            state,
            root_player_id,
        ):
            return ()

        if game.phase != "recruit":
            self._advance_until_root_decision(
                state,
                self._fallback_rng(),
            )

        player = game.get_player(
            root_player_id
        )

        if (
            player.eliminated
            or (player.waiting and game.effects.get_pending_choice(root_player_id) is None)
            or game.phase != "recruit"
        ):
            return ()

        game.update_action_space(
            root_player_id
        )

        return tuple(
            game.get_player_action_space(
                root_player_id
            )
        )

    def step(
        self,
        state: DeterminizedGameState,
        root_player_id: int,
        action: Action,
        rng: random.Random,
    ) -> DeterminizedGameState:
        self._validate_state_owner(
            state,
            root_player_id,
        )

        if self.is_terminal(
            state,
            root_player_id,
        ):
            return state

        game = state.game

        if game.phase != "recruit":
            self._advance_until_root_decision(
                state,
                rng,
            )

        if self.is_terminal(
            state,
            root_player_id,
        ):
            return state

        root = game.get_player(
            root_player_id
        )

        if root.waiting:
            self._advance_until_root_decision(
                state,
                rng,
            )

        legal = tuple(
            self.legal_actions(
                state,
                root_player_id,
            )
        )

        if action not in legal:
            raise ValueError(
                "MCTS attempted an action that is illegal in this "
                f"determinization: {action}. "
                f"Legal={legal}"
            )

        previous_round = game.round_number

        self._execute_engine_action(
            game,
            root_player_id,
            action,
            rng,
        )

        state.root_actions_this_turn += 1

        if self.is_terminal(
            state,
            root_player_id,
        ):
            return state

        # If the root ended recruitment (explicitly or via AP exhaustion), let
        # all imaginary opponents finish so the real engine can resolve combat
        # and advance to the next recruit phase.
        root = game.get_player(
            root_player_id
        )

        if (
            game.phase == "recruit"
            and root.waiting
        ):
            self._finish_current_recruit_phase(
                state,
                rng,
            )

        # Otherwise give each imaginary opponent one cheap response action.
        elif game.phase == "recruit":
            self._run_one_opponent_cycle(
                state,
                rng,
            )

        if game.round_number != previous_round:
            state.root_actions_this_turn = 0
            state.opponent_actions_this_turn.clear()

        return state

    def is_terminal(
        self,
        state: DeterminizedGameState,
        root_player_id: int,
    ) -> bool:
        self._validate_state_owner(
            state,
            root_player_id,
        )

        game = state.game
        player = game.get_player(
            root_player_id
        )

        return bool(
            game.game_over
            or player.eliminated
            or (
                player.placement is not None
                and game.phase == "game_over"
            )
        )

    def observe(
        self,
        state: DeterminizedGameState,
        root_player_id: int,
    ) -> AgentObservation:
        """
        Return ONLY what the root player could know in this imaginary world.

        ObservationBuilder reads the root player's own exact state and the
        simulation memory. It does not expose sampled opponent hands, Taverns,
        exact boards, or exact remaining pool contents.
        """
        self._validate_state_owner(
            state,
            root_player_id,
        )

        builder = ObservationBuilder(
            state.memory
        )

        return builder.build(
            state.game
        )

    def random_rollout(
        self,
        state: DeterminizedGameState,
        root_player_id: int,
        rng: random.Random,
        max_steps: int,
    ) -> float:
        """
        Random forward rollout for pure MCTS.

        No board-strength heuristic is used. Value comes from:
        - actual simulated combat wins/losses during the rollout,
        - exact final placement if the rollout reaches elimination/game end.

        If the rollout hits max_steps first, only accumulated simulated combat
        outcome shaping remains.
        """
        self._validate_state_owner(
            state,
            root_player_id,
        )

        if max_steps <= 0:
            raise ValueError(
                "max_steps must be positive."
            )

        value = 0.0

        for _ in range(
            int(max_steps)
        ):
            if self.is_terminal(
                state,
                root_player_id,
            ):
                return self._clip_value(
                    self._terminal_value(
                        state,
                        root_player_id,
                    )
                    + value
                )

            game = state.game
            before_round = game.round_number

            legal = tuple(
                self.legal_actions(
                    state,
                    root_player_id,
                )
            )

            if not legal:
                self._advance_until_root_decision(
                    state,
                    rng,
                )

                if self.is_terminal(
                    state,
                    root_player_id,
                ):
                    return self._clip_value(
                        self._terminal_value(
                            state,
                            root_player_id,
                        )
                        + value
                    )

                legal = tuple(
                    self.legal_actions(
                        state,
                        root_player_id,
                    )
                )

                if not legal:
                    break

            action = self.random_policy.choose_action(
                legal,
                rng,
                actions_taken_this_turn=(
                    state.root_actions_this_turn
                ),
            )

            self.step(
                state,
                root_player_id,
                action,
                rng,
            )

            if state.game.round_number > before_round:
                value += self._latest_combat_reward(
                    state,
                    root_player_id,
                )

        if self.is_terminal(
            state,
            root_player_id,
        ):
            value += self._terminal_value(
                state,
                root_player_id,
            )

        return self._clip_value(
            value
        )

    # ==================================================================
    # PUBLIC TEMPLATE
    # ==================================================================

    def _get_public_template(
        self,
        observation: AgentObservation,
    ) -> Bob:
        if (
            self._template_observation
            is observation
            and self._template_game
            is not None
        ):
            return self._template_game

        template = self._build_public_template(
            observation
        )

        self._template_observation = observation
        self._template_game = template

        return template

    def _build_public_template(
        self,
        observation: AgentObservation,
    ) -> Bob:
        """
        Build a clean Bob using public/own information only.

        Opponent hidden boards/hands/Taverns remain empty here. They are sampled
        independently after the template is copied for each simulation.
        """
        game = Bob(
            cards_file=self.cards_file
        )
        # The real lobby roll is public. Never replace it with a new random
        # roll when constructing search worlds from the observation.
        game.active_minion_types = tuple(observation.active_minion_types)
        game.pool = CardPool(
            cards_file=self.cards_file,
            rng=game.random,
            ruleset=game.pool.ruleset,
            active_minion_types=game.active_minion_types,
        )

        # Avoid initialize_game(): it would randomly deal heroes/Taverns that
        # are not part of this root observation.
        game.create_players()
        game.scheduler.begin_phase(range(game.PLAYER_COUNT))
        for player in game.players:
            player.bind_recruit_scheduler(game.scheduler)

        game.round_number = int(
            observation.round_number
        )
        game.phase = observation.phase
        game.game_over = bool(
            observation.game_over
        )
        game.last_combat_result = None

        # Temporary deterministic placeholder. Each determinization replaces it.
        game.priority_order = list(
            range(game.PLAYER_COUNT)
        )

        self._apply_root_public_state(
            game,
            observation,
        )
        self._apply_opponent_public_state(
            game,
            observation,
        )

        # Start from a fresh full physical pool, then subtract only copies the
        # root actually knows are currently visible in its own zones.
        self.belief.remove_known_visible_cards(
            game.pool,
            observation,
        )

        self._restore_pending_choice(
            game,
            observation,
        )

        game.update_all_action_spaces()

        return game

    def _apply_root_public_state(
        self,
        game: Bob,
        observation: AgentObservation,
    ) -> None:
        view = observation.self_player
        player = game.get_player(
            observation.player_id
        )

        self._set_player_hero(
            player,
            view.hero_id,
        )

        player.health = int(
            view.health
        )
        player.armor = int(
            view.armor
        )
        player.gold = int(
            view.gold
        )
        player.max_gold = int(
            getattr(
                view,
                "max_gold",
                10,
            )
        )
        player.ap = int(
            view.ap
        )
        player.tavern_tier = int(
            view.tavern_tier
        )
        player.waiting = bool(
            view.waiting
        )
        player.eliminated = bool(
            view.eliminated
        )
        player.placement = view.placement

        # set_hero normally establishes this. Preserve observation value if
        # available because hero/card effects may have modified it.
        player.hero_power_cost = int(
            getattr(
                view,
                "hero_power_cost",
                getattr(
                    player,
                    "hero_power_cost",
                    0,
                ),
            )
        )

        player.board = deepcopy(
            list(view.board)
        )
        player.hand = [
            deepcopy(card)
            for card in view.hand
            if isinstance(card, dict)
        ]

        tavern = player.tavern
        setter = getattr(
            tavern,
            "set_tier",
            None,
        )
        if callable(setter):
            setter(
                player.tavern_tier
            )

        tavern.slots = deepcopy(
            list(view.tavern_slots)
        )
        tavern.spell = deepcopy(
            view.tavern_spell
        )
        tavern.frozen = bool(
            view.tavern_frozen
        )

        player.last_opponent_id = (
            observation.last_opponent_id
        )

        effect_state = game.effects.get_player_state(
            player.player_id
        )
        effect_state.clear()
        effect_state.update(
            deepcopy(
                dict(view.effect_state)
            )
        )
        game.dark_gifts.uses_by_player[player.player_id] = int(effect_state.get("dark_gift_uses", 0))
        if "dark_gift_last_used_turn" in effect_state:
            game.dark_gifts.last_used_turn[player.player_id] = int(effect_state["dark_gift_last_used_turn"])
        # Gift registrations are lazy in Bob. Restoring a gifted card must also
        # restore the executable rules, not just its visible dictionary.
        if any(isinstance(card, dict) and card.get("_dark_gift_ids")
               for card in list(player.board) + list(player.hand)):
            ensure_dark_gift_effects(game.effects)

    def _apply_opponent_public_state(
        self,
        game: Bob,
        observation: AgentObservation,
    ) -> None:
        for view in observation.opponents:
            player = game.get_player(
                view.player_id
            )

            self._set_player_hero(
                player,
                view.hero_id,
            )

            player.health = int(
                view.health
            )
            player.armor = int(
                view.armor
            )
            player.tavern_tier = int(
                view.tavern_tier
            )
            player.eliminated = bool(
                view.eliminated
            )
            player.placement = view.placement
            player.last_opponent_id = (
                view.last_opponent_id
            )

            player.board = [None] * 7
            player.hand = []
            player.gold = 0
            player.ap = 0
            player.waiting = bool(
                view.eliminated
            )

            tavern = player.tavern
            setter = getattr(
                tavern,
                "set_tier",
                None,
            )
            if callable(setter):
                setter(
                    player.tavern_tier
                )

            tavern.slots = [
                None
                for _ in range(
                    self.belief.tavern_slot_count(
                        player.tavern_tier
                    )
                )
            ]
            tavern.spell = None
            tavern.frozen = False

            memory = view.last_seen_board
            player.last_combat_board = (
                deepcopy(
                    list(memory.board)
                )
                if memory is not None
                else [None] * 7
            )

            if player.eliminated:
                player.ap = 0
                player.waiting = True

        # Best public approximation of the most recently eliminated ghost:
        # among eliminated players, the best placement was eliminated latest.
        eliminated = [
            view
            for view in observation.opponents
            if view.eliminated
            and view.placement is not None
        ]

        if eliminated:
            latest = min(
                eliminated,
                key=lambda item: int(
                    item.placement
                ),
            )

            combat = getattr(
                game,
                "combat",
                None,
            )
            if combat is not None:
                combat.last_eliminated_player_id = (
                    latest.player_id
                )

    def _restore_pending_choice(
        self,
        game: Bob,
        observation: AgentObservation,
    ) -> None:
        choice = deepcopy(observation.pending_choice)

        if choice is None:
            return

        if not choice.resolver_key:
            raise ValueError(
                "Pending ChoiceView is missing resolver_key. "
                "Use the revised agents/observation.py."
            )

        game.effects._pending_choices[
            observation.player_id
        ] = PendingChoice(
            player_id=observation.player_id,
            resolver_key=choice.resolver_key,
            options=list(choice.options),
            kind=choice.kind,
            source_card_id=choice.source_card_id,
            metadata=dict(choice.metadata),
        )
        if choice.resolver_key == game.dark_gifts.RESOLVER_KEY:
            # These exact copies are publicly reserved by the root choice.
            # They are not part of the root hand/shop counts removed above.
            for offer in choice.options:
                self.belief.consume_visible_card(game.pool, offer.minion)
        elif choice.resolver_key == game.triples.RESOLVER_KEY:
            for offer in choice.options:
                self.belief.consume_visible_card(game.pool, offer)

    # ==================================================================
    # HIDDEN OPPONENT SAMPLING
    # ==================================================================

    def _sample_hidden_opponents(
        self,
        state: DeterminizedGameState,
        observation: AgentObservation,
        rng: random.Random,
    ) -> None:
        game = state.game

        for view in observation.opponents:
            player = game.get_player(
                view.player_id
            )

            # Ghosts no longer have current recruit resources/Taverns.
            if view.eliminated:
                memory = view.last_seen_board
                if memory is not None:
                    ghost_board = deepcopy(
                        list(memory.board)
                    )
                else:
                    ghost_board = [None] * 7

                player.board = deepcopy(
                    ghost_board
                )
                player.last_combat_board = (
                    deepcopy(
                        ghost_board
                    )
                )
                continue

            player.board = (
                self.belief
                .sample_opponent_board(
                    view,
                    game.pool,
                    observation.round_number,
                    rng,
                )
            )

            player.hand = (
                self.belief
                .sample_hidden_hand(
                    view.tavern_tier,
                    observation.round_number,
                    game.pool,
                    rng,
                )
            )

            slots, spell = (
                self.belief
                .sample_hidden_tavern(
                    view.tavern_tier,
                    game.pool,
                    rng,
                )
            )

            player.tavern.slots = slots
            player.tavern.spell = spell
            player.tavern.frozen = False

            # Opponent gold/AP are hidden during recruit. Sample broad plausible
            # remaining resources rather than using the real values.
            base_gold = min(
                10,
                3 + max(
                    0,
                    observation.round_number - 1,
                ),
            )

            player.gold = rng.randint(
                0,
                base_gold,
            )
            player.max_gold = max(
                10,
                int(
                    getattr(
                        player,
                        "max_gold",
                        10,
                    )
                ),
            )
            player.ap = rng.randint(
                1,
                100,
            )
            player.waiting = False

        game.update_all_action_spaces()

    # ==================================================================
    # IMAGINARY OPPONENT POLICY
    # ==================================================================

    def _run_one_opponent_cycle(self, state, rng) -> None:
        self._advance_until_root_decision(state, rng)

    def _finish_current_recruit_phase(self, state, rng) -> None:
        self._advance_until_root_decision(state, rng)

    def _take_one_opponent_action(
        self,
        state: DeterminizedGameState,
        player_id: int,
        rng: random.Random,
    ) -> None:
        game = state.game

        if game.phase != "recruit":
            return

        game.update_action_space(
            player_id
        )

        legal = tuple(
            game.get_player_action_space(
                player_id
            )
        )

        if not legal:
            return

        count = (
            state.opponent_actions_this_turn
            .get(
                player_id,
                0,
            )
        )

        action = self.random_policy.choose_action(
            legal,
            rng,
            actions_taken_this_turn=count,
        )

        self._execute_engine_action(
            game,
            player_id,
            action,
            rng,
        )

        state.opponent_actions_this_turn[
            player_id
        ] = count + 1

    def _force_opponent_to_end(
        self,
        state: DeterminizedGameState,
        player_id: int,
        rng: random.Random,
    ) -> None:
        game = state.game
        player = game.get_player(
            player_id
        )

        if (
            player.eliminated
            or player.waiting
            or game.phase != "recruit"
        ):
            return

        for _ in range(12):
            game.update_action_space(
                player_id
            )

            legal = tuple(
                game.get_player_action_space(
                    player_id
                )
            )

            if not legal:
                return

            choices = [
                action
                for action in legal
                if getattr(
                    action.action_type,
                    "value",
                    None,
                )
                == "choose_option" 
            ]

            if choices:
                self._execute_engine_action(
                    game,
                    player_id,
                    rng.choice(
                        choices
                    ),
                    rng,
                )
                continue

            end = next(
                (
                    action
                    for action in legal
                    if action.action_type
                    == ActionType.END_TURN
                ),
                None,
            )

            if end is not None:
                self._execute_engine_action(
                    game,
                    player_id,
                    end,
                    rng,
                )
            return

    def _advance_until_root_decision(self, state, rng) -> None:
        """Run scheduler-eligible opponent batches up to the next root decision."""
        game = state.game
        root_id = state.root_player_id
        for _ in range(2000):
            if self.is_terminal(state, root_id):
                return
            if game.phase != "recruit":
                raise RuntimeError("Search expected synchronous recruit/combat transitions.")
            eligible = game.recruitment.eligible_player_ids()
            if root_id in eligible:
                game.update_all_action_spaces()
                return
            if not eligible:
                if game.recruitment.check_complete():
                    continue
                raise RuntimeError("Search recruit scheduler has no eligible seat.")
            game.update_all_action_spaces()
            submissions = []
            for player_id in eligible:
                legal = tuple(game.get_player_action_space(player_id))
                if not legal:
                    raise RuntimeError("Scheduler-eligible search opponent has no actions.")
                count = state.opponent_actions_this_turn.get(player_id, 0)
                action = self.random_policy.choose_action(
                    legal, rng, actions_taken_this_turn=count,
                )
                submissions.append((player_id, action))
                state.opponent_actions_this_turn[player_id] = count + 1
            previous_round = game.round_number
            with self._engine_random_context(game, rng):
                game.resolve_action_batch(submissions)
            if game.round_number != previous_round:
                state.root_actions_this_turn = 0
                state.opponent_actions_this_turn.clear()
        raise RuntimeError("Search opponent progression exceeded its safety limit.")

    # ==================================================================
    # ENGINE RNG / EXECUTION
    # ==================================================================

    def _execute_engine_action(
        self,
        game: Bob,
        player_id: int,
        action: Action,
        rng: random.Random,
    ) -> None:
        with self._engine_random_context(
            game,
            rng,
        ):
            game.execute_action(
                player_id,
                action,
            )

    @contextmanager
    def _engine_random_context(
        self,
        game: Bob,
        rng: random.Random,
    ):
        """
        Current engine modules still use a mixture of module-global random and
        component Random instances. Seed them from the search RNG while
        preserving the process-global random state outside this simulation call.

        Once Bob/Pool/Combat share a first-class engine RNG, this compatibility
        shim can be removed without changing the MCTS interfaces.
        """
        global_state = random.getstate()

        try:
            random.seed(
                rng.getrandbits(64)
            )
            self._seed_world_rngs(
                game,
                rng,
            )
            yield
        finally:
            random.setstate(
                global_state
            )

    @staticmethod
    def _seed_world_rngs(
        game: Bob,
        rng: random.Random,
    ) -> None:
        # Normal Bob shares one RNG across these owners. Seed each distinct
        # object once, preserving aliases while supporting separate component
        # RNGs. The order is fixed so search seeds reproduce across processes.
        combat = getattr(game, "combat", None)
        owners = (
            game,
            getattr(game, "pool", None),
            getattr(game, "effects", None),
            combat,
            getattr(combat, "engine", None),
        )
        seeded_ids = set()
        for owner in owners:
            world_rng = getattr(owner, "random", None)
            seed = getattr(world_rng, "seed", None)
            if callable(seed) and id(world_rng) not in seeded_ids:
                seed(rng.getrandbits(64))
                seeded_ids.add(id(world_rng))

    # ==================================================================
    # VALUE
    # ==================================================================

    def _latest_combat_reward(
        self,
        state: DeterminizedGameState,
        root_player_id: int,
    ) -> float:
        combat_round = max(
            0,
            state.game.round_number - 1,
        )

        if (
            combat_round
            <= state.last_counted_combat_round
        ):
            return 0.0

        state.last_counted_combat_round = (
            combat_round
        )

        player = state.game.get_player(
            root_player_id
        )

        if bool(
            getattr(
                player,
                "last_combat_tied",
                False,
            )
        ):
            return (
                self.rollout_rewards
                .combat_tie
            )

        if bool(
            getattr(
                player,
                "last_combat_won",
                False,
            )
        ):
            return (
                self.rollout_rewards
                .combat_win
            )

        return (
            self.rollout_rewards
            .combat_loss
        )

    @staticmethod
    def _terminal_value(
        state: DeterminizedGameState,
        root_player_id: int,
    ) -> float:
        player = state.game.get_player(
            root_player_id
        )

        placement = getattr(
            player,
            "placement",
            None,
        )

        if placement is None:
            return 0.0

        placement = max(
            1,
            min(
                8,
                int(placement),
            ),
        )

        return 1.0 - (
            2.0
            * (placement - 1)
            / 7.0
        )

    @staticmethod
    def _clip_value(
        value: float,
    ) -> float:
        return max(
            -1.0,
            min(
                1.0,
                float(value),
            ),
        )

    # ==================================================================
    # HELPERS
    # ==================================================================

    @staticmethod
    def _set_player_hero(
        player: Any,
        hero_id: int | str | None,
    ) -> None:
        if hero_id is None:
            return

        setter = getattr(
            player,
            "set_hero",
            None,
        )

        if not callable(setter):
            player.hero = hero_id
            return

        setter(
            hero_id
        )

    @staticmethod
    def _opponent_order(
        game: Bob,
        root_player_id: int,
    ) -> list[int]:
        ordered = [
            player_id
            for player_id in game.priority_order
            if player_id != root_player_id
        ]

        missing = [
            player.player_id
            for player in game.players
            if (
                player.player_id
                != root_player_id
                and player.player_id
                not in ordered
            )
        ]

        return ordered + missing

    @staticmethod
    def _validate_state_owner(
        state: DeterminizedGameState,
        root_player_id: int,
    ) -> None:
        if (
            state.root_player_id
            != root_player_id
        ):
            raise ValueError(
                "Determinized state belongs to a different root player."
            )

    @staticmethod
    def _fallback_rng() -> random.Random:
        # This path should be rare; callers normally provide the agent RNG.
        # Fixed seed keeps accidental use deterministic.
        return random.Random(0)

    def clear_template_cache(self) -> None:
        """Drop the current public-template cache."""
        self._template_observation = None
        self._template_game = None
