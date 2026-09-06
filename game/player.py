"""
Player system for Hearthstone Battlegrounds.

A Player owns Hearthstone state that belongs specifically to that player.
Game-wide coordination and artificial recruit interaction timing are handled by
Bob/Recruitment and the RecruitScheduler.
"""

from copy import deepcopy

from .actions import ActionSpace
from .tavern import Tavern
from .heroes import HEROES


class Player:
    """Represents one player in the game."""

    MAX_GOLD = 10
    MAX_BOARD_SIZE = 7
    MAX_HAND_SIZE = 10

    def __init__(self, player_id):
        self.player_id = player_id

        # =====================================================
        # ECONOMY
        # =====================================================

        self.gold = 0

        # AP/waiting used to be stored as game resources on Player.  Keep
        # compatibility fallbacks for isolated tests/tools, but live recruit
        # phases bind a RecruitScheduler and use its private scheduling state.
        self._recruit_scheduler = None
        self._legacy_ap = 0
        self._legacy_waiting = False

        # =====================================================
        # HERO
        # =====================================================

        self.hero = None
        self.hero_choices = []
        self.hero_power_cost = 0

        # Combat durability.
        # These are initialized from the selected hero.
        self.health = 0
        self.armor = 0

        # =====================================================
        # TAVERN
        # =====================================================

        self.tavern_tier = 1

        self.tavern = Tavern(
            player_id=player_id,
            tier=1,
        )

        # =====================================================
        # BOARD / HAND
        # =====================================================

        # Board positions are fixed.
        # Empty positions are represented by None.
        self.board = [None] * self.MAX_BOARD_SIZE

        # Hand remains a compact list.
        self.hand = []

        # =====================================================
        # RECRUIT STATE
        # =====================================================

        # Actions currently offered to this player/AI.
        self.action_space = ActionSpace()

        # =====================================================
        # COMBAT / ELIMINATION STATE
        # =====================================================

        self.eliminated = False

        # Final placement once known.
        # Example:
        # 1 = winner
        # 8 = first player eliminated
        self.placement = None

        # Most recent combat opponent.
        # Used to avoid immediate rematches where possible.
        self.last_opponent_id = None

        # Snapshot of the board this player entered their
        # most recent combat with.
        #
        # This is preserved so an eliminated player can later
        # be used as the ghost opponent when the number of
        # living players is odd.
        self.last_combat_board = None

    # =========================================================
    # RECRUIT-SCHEDULER COMPATIBILITY
    # =========================================================

    def bind_recruit_scheduler(self, scheduler):
        """Bind private simulator scheduling state to this seat."""

        self._recruit_scheduler = scheduler

    def _has_scheduler_state(self):
        return (
            self._recruit_scheduler is not None
            and self._recruit_scheduler.has_player(self.player_id)
        )

    @property
    def ap(self):
        """Deprecated alias for remaining scheduler interaction budget."""

        if self._has_scheduler_state():
            return self._recruit_scheduler.remaining_budget(self.player_id)
        return self._legacy_ap

    @ap.setter
    def ap(self, amount):
        self.set_ap(amount)

    @property
    def waiting(self):
        """Deprecated alias for scheduler finished state."""

        if self.eliminated:
            return True
        if self._has_scheduler_state():
            return self._recruit_scheduler.is_finished(self.player_id)
        return self._legacy_waiting

    @waiting.setter
    def waiting(self, value):
        value = bool(value)
        if self._has_scheduler_state():
            state = self._recruit_scheduler.state_for(self.player_id)
            if value:
                self._recruit_scheduler.finish_player(self.player_id, "legacy_waiting")
            elif state.finished and state.remaining_budget > 0:
                self._recruit_scheduler.reopen_player(self.player_id)
            return
        self._legacy_waiting = value

    # =========================================================
    # GOLD
    # =========================================================

    def set_gold(self, amount):
        """Set the player's gold."""

        self.gold = min(
            max(amount, 0),
            self.MAX_GOLD,
        )

    def add_gold(self, amount):
        """Add gold, respecting the maximum gold cap."""

        if amount < 0:
            raise ValueError(
                "Cannot add negative gold."
            )

        self.gold = min(
            self.gold + amount,
            self.MAX_GOLD,
        )

    def spend_gold(self, amount):
        """Spend gold."""

        if amount < 0:
            raise ValueError(
                "Cannot spend negative gold."
            )

        if self.gold < amount:
            raise ValueError(
                "Not enough gold."
            )

        self.gold -= amount

    # =========================================================
    # LEGACY AP API
    # =========================================================

    def set_ap(self, amount):
        """Set remaining interaction budget through the legacy AP API."""

        amount = int(amount)
        if amount < 0:
            raise ValueError(
                "AP cannot be negative."
            )

        if self._has_scheduler_state():
            self._recruit_scheduler.set_remaining_budget(self.player_id, amount)
        else:
            self._legacy_ap = amount
            if amount > 0:
                self._legacy_waiting = False

    def spend_ap(self, amount=1):
        """Consume interaction budget through the legacy AP API."""

        amount = int(amount)
        if amount < 0:
            raise ValueError(
                "Cannot spend negative AP."
            )

        if self._has_scheduler_state():
            self._recruit_scheduler.consume_budget(self.player_id, amount)
            return

        if self._legacy_ap < amount:
            raise ValueError(
                "Not enough AP."
            )

        self._legacy_ap -= amount

        if self._legacy_ap == 0:
            self._legacy_waiting = True

    # =========================================================
    # HERO
    # =========================================================

    def set_hero(self, hero_id):
        """
        Assign a hero to the player.

        Health, armor, and hero power cost are initialized
        directly from the hero definition.
        """

        if hero_id not in HEROES:
            raise ValueError(
                f"Unknown hero ID: {hero_id}"
            )

        if self.hero is not None:
            raise ValueError(
                "Player already has a hero."
            )

        hero_definition = HEROES[hero_id]

        self.hero = hero_id

        self.hero_power_cost = (
            hero_definition["power"]["cost"]
        )

        self.health = hero_definition.get(
            "health",
            30,
        )

        # The structured database represents no armor (e.g. Patchwerk) as null.
        self.armor = int(hero_definition.get("armor") or 0)

    def get_hero_definition(self):
        """Return the player's complete hero definition."""

        if self.hero is None:
            return None

        return HEROES[self.hero]

    def get_hero_name(self):
        """Return the player's hero name."""

        hero_definition = self.get_hero_definition()

        if hero_definition is None:
            return None

        return hero_definition["name"]

    def get_hero_power(self):
        """Return the player's hero power definition."""

        hero_definition = self.get_hero_definition()

        if hero_definition is None:
            return None

        return hero_definition["power"]

    # =========================================================
    # HEALTH / ARMOR
    # =========================================================

    def take_damage(self, amount):
        """
        Deal damage to the player.

        Armor absorbs damage first.
        Remaining damage is dealt to health.

        Returns:
            Tuple:
                (armor_damage, health_damage)
        """

        if amount < 0:
            raise ValueError(
                "Damage cannot be negative."
            )

        if self.eliminated:
            raise ValueError(
                "Eliminated player cannot take damage."
            )

        armor_damage = min(
            self.armor,
            amount,
        )

        self.armor -= armor_damage

        remaining_damage = (
            amount - armor_damage
        )

        health_damage = min(
            self.health,
            remaining_damage,
        )

        self.health -= health_damage

        if self.health <= 0:
            self.health = 0
            self.mark_eliminated()

        return (
            armor_damage,
            health_damage,
        )

    def is_alive(self):
        """Return True if the player is still alive."""

        return not self.eliminated

    # =========================================================
    # RECRUIT STATE
    # =========================================================

    def reset_for_recruit_phase(self, gold, ap=None):
        """Reset Hearthstone recruit state for a new phase.

        ``ap`` is accepted only for old callers. Live games initialize the
        interaction budget in RecruitScheduler before this method is called.
        """

        if self.eliminated:
            raise ValueError(
                "Eliminated player cannot enter recruitment."
            )

        self.set_gold(gold)

        if self._has_scheduler_state():
            # Scheduler.begin_phase already created fresh unfinished state.
            if ap is not None:
                self._recruit_scheduler.set_remaining_budget(self.player_id, ap)
        else:
            self.set_ap(0 if ap is None else ap)
            self._legacy_waiting = False

    def end_turn(self):
        """Finish this seat's recruit phase."""

        if self._has_scheduler_state():
            self._recruit_scheduler.finish_player(self.player_id, "end_turn")
        else:
            self._legacy_waiting = True

    # =========================================================
    # TAVERN
    # =========================================================

    def upgrade_tavern(self, new_tier):
        """Set the player's Tavern to a new tier."""

        if new_tier <= self.tavern_tier:
            raise ValueError(
                "New Tavern tier must be higher."
            )

        if new_tier > 6:
            raise ValueError(
                "Maximum Tavern tier is 6."
            )

        self.tavern_tier = new_tier

        self.tavern.set_tier(
            new_tier
        )

    # =========================================================
    # COMBAT STATE
    # =========================================================

    def set_last_opponent(self, opponent_id):
        """Store the player's most recent opponent."""

        if opponent_id == self.player_id:
            raise ValueError(
                "Player cannot be their own opponent."
            )

        self.last_opponent_id = opponent_id

    def snapshot_combat_board(self):
        """
        Save the exact board the player is entering combat with.

        Runtime stats and buffs are preserved in the snapshot.
        """

        self.last_combat_board = deepcopy(
            self.board
        )

        return deepcopy(
            self.last_combat_board
        )

    def get_last_combat_board(self):
        """Return an independent copy of the last combat board."""

        if self.last_combat_board is None:
            return None

        return deepcopy(
            self.last_combat_board
        )

    # =========================================================
    # ELIMINATION / PLACEMENT
    # =========================================================

    def mark_eliminated(self, placement=None):
        """
        Mark this player as eliminated.

        Placement may be assigned immediately or later by Bob/
        the combat system after simultaneous eliminations have
        been ordered using player priority.
        """

        self.eliminated = True

        if self._has_scheduler_state():
            self._recruit_scheduler.set_remaining_budget(self.player_id, 0)
            self._recruit_scheduler.finish_player(self.player_id, "eliminated")
        else:
            self._legacy_waiting = True
            self._legacy_ap = 0

        if placement is not None:
            self.set_placement(
                placement
            )

    def set_placement(self, placement):
        """Assign the player's final placement."""

        if placement < 1 or placement > 8:
            raise ValueError(
                "Placement must be between 1 and 8."
            )

        if self.placement is not None:
            raise ValueError(
                "Player already has a placement."
            )

        self.placement = placement

    # =========================================================
    # DEBUG
    # =========================================================

    def __repr__(self):
        hero_name = self.get_hero_name()

        board_count = sum(
            minion is not None
            for minion in self.board
        )

        logical_time = None
        if self._has_scheduler_state():
            logical_time = self._recruit_scheduler.logical_time(self.player_id)

        return (
            f"Player("
            f"id={self.player_id}, "
            f"hero={hero_name}, "
            f"health={self.health}, "
            f"armor={self.armor}, "
            f"gold={self.gold}, "
            f"interaction_budget={self.ap}, "
            f"logical_time={logical_time}, "
            f"tavern_tier={self.tavern_tier}, "
            f"board={board_count}/"
            f"{self.MAX_BOARD_SIZE}, "
            f"hand={len(self.hand)}/"
            f"{self.MAX_HAND_SIZE}, "
            f"finished={self.waiting}, "
            f"eliminated={self.eliminated}, "
            f"placement={self.placement}, "
            f"last_opponent={self.last_opponent_id}"
            f")"
        )
