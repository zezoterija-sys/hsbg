"""
Tavern system for Hearthstone Battlegrounds.

Each player owns their own Tavern instance.

The Tavern manages:
- Minion shop slots
- Tavern spell offering
- Frozen state
- Tavern tier
- Drawing cards from the shared CardPool
- Returning cards to the shared CardPool
"""


class Tavern:
    """
    Represents a player's Tavern.

    The Tavern owns the current shop offerings.
    The CardPool owns the available physical card copies.
    """

    def __init__(self, player_id, tier=1):
        if tier < 1 or tier > 6:
            raise ValueError(
                "Tavern tier must be between 1 and 6."
            )

        self.player_id = player_id
        self.tier = tier
        self.frozen = False

        # Normal minion shop slots.
        self.slots = self._create_slots(tier)

        # Tavern spell offering.
        self.spell = None

    # =========================================================
    # SLOT MANAGEMENT
    # =========================================================

    def _slot_count_for_tier(self, tier):
        """
        Return the number of normal minion slots.

        T1 = 3
        T2/T3 = 4
        T4/T5 = 5
        T6 = 6
        """

        if tier < 1 or tier > 6:
            raise ValueError(
                "Tavern tier must be between 1 and 6."
            )

        slots = 3

        if tier >= 2:
            slots += 1

        if tier >= 4:
            slots += 1

        if tier >= 6:
            slots += 1

        return slots

    def _create_slots(self, tier):
        """Create empty minion slots for a Tavern tier."""

        return [None] * self._slot_count_for_tier(tier)

    def _resize_slots_for_current_tier(self):
        """
        Expand the Tavern to match its current tier.

        Existing frozen offerings are preserved.
        Newly gained positions are added as empty slots.
        """

        required_slots = self._slot_count_for_tier(
            self.tier
        )

        current_slots = len(self.slots)

        if current_slots < required_slots:
            self.slots.extend(
                [None] * (
                    required_slots - current_slots
                )
            )

    # =========================================================
    # FREEZE
    # =========================================================

    def freeze(self):
        """Freeze the entire Tavern."""

        self.frozen = True

    def unfreeze(self):
        """Unfreeze the entire Tavern."""

        self.frozen = False

    # =========================================================
    # DRAWING FROM POOL
    # =========================================================

    def _fill_empty_minion_slots(self, pool):
        """
        Fill empty minion slots with eligible minions.

        Minions may come from Tavern tiers 1 through
        the player's current Tavern tier.
        """

        for idx, minion in enumerate(self.slots):

            if minion is not None:
                continue

            self.slots[idx] = pool.get_random_minion(
                min_tier=1,
                max_tier=self.tier,
            )

    def _fill_spell(self, pool):
        """
        Fill the Tavern spell offering.

        The spell may come from the current Tavern tier
        or any lower tier.
        """

        if self.spell is not None:
            return

        self.spell = pool.get_random_spell(
            min_tier=1,
            max_tier=self.tier,
        )

    # =========================================================
    # RECRUIT PHASE
    # =========================================================

    def refresh_for_new_recruit_phase(self, pool):
        """
        Prepare the Tavern for a new recruit phase.

        Not frozen:
            - Return all existing offerings.
            - Recreate the Tavern at the current tier.
            - Draw fresh offerings.

        Frozen:
            - Preserve existing offerings.
            - Apply any slot increase from a Tavern upgrade.
            - Fill bought or newly gained empty slots.
            - Preserve the existing Tavern spell if present.
        """

        if not self.frozen:

            self._return_current_offerings(pool)

            self.slots = self._create_slots(
                self.tier
            )

            self.spell = None

        else:

            # A Tavern upgrade takes effect at the next
            # recruit phase even if the shop is frozen.
            self._resize_slots_for_current_tier()

        self._fill_empty_minion_slots(pool)
        self._fill_spell(pool)

    # =========================================================
    # MANUAL REFRESH
    # =========================================================

    def refresh(self, pool):
        """
        Refresh the Tavern during recruitment.

        Current offerings are returned to the shared pool.
        New offerings are drawn using the current Tavern tier.

        Refresh also cancels Freeze.
        """

        self.frozen = False

        self._return_current_offerings(pool)

        self.slots = self._create_slots(
            self.tier
        )

        self.spell = None

        self._fill_empty_minion_slots(pool)
        self._fill_spell(pool)

    # =========================================================
    # RETURN TO POOL
    # =========================================================

    def _return_current_offerings(self, pool):
        """Return all current Tavern offerings to the pool."""

        for minion in self.slots:

            if minion is not None:
                pool.return_card(minion)

        if self.spell is not None:
            pool.return_card(self.spell)

    # =========================================================
    # TIER
    # =========================================================

    def set_tier(self, tier):
        """
        Set the Tavern tier.

        Changing the tier does not immediately alter the
        current shop. The new tier takes effect when the
        Tavern is next prepared or refreshed.
        """

        if tier < 1 or tier > 6:
            raise ValueError(
                "Tavern tier must be between 1 and 6."
            )

        self.tier = tier

    # =========================================================
    # DEBUG
    # =========================================================

    def __repr__(self):
        occupied_slots = sum(
            card is not None
            for card in self.slots
        )

        return (
            f"Tavern("
            f"player={self.player_id}, "
            f"tier={self.tier}, "
            f"slots={occupied_slots}/"
            f"{len(self.slots)}, "
            f"spell={self.spell is not None}, "
            f"frozen={self.frozen}"
            f")"
        )