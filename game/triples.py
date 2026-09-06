"""Ordinary three-copy triples and the Solos Triple Reward lifecycle."""

from collections import defaultdict
from copy import deepcopy

from .events import GameEvent


TRIPLE_REWARD = 59604  # TB_BaconShop_Triples_01, not the anomaly variants.
ELEMENTAL_OF_SURPRISE = 101280  # BG26_175


class TripleSystem:
    RESOLVER_KEY = "triple_reward"

    def __init__(self, game):
        self.game = game
        self._resolving = set()
        game.effects.register_choice_resolver(self.RESOLVER_KEY, self._resolve_reward)
        game.events.register(GameEvent.CARD_PLAYED, self._on_play, order=-10000)
        game.events.register(GameEvent.SPELL_CAST, self._on_spell, order=-10000)
        for event in (GameEvent.CARD_BOUGHT, GameEvent.CARD_ADDED_TO_HAND,
                      GameEvent.CARD_PLAYED, GameEvent.CHOICE_RESOLVED,
                      GameEvent.ACTION_RESOLVED, GameEvent.MINION_SUMMONED,
                      GameEvent.RECRUIT_START, GameEvent.TURN_START, GameEvent.TURN_END):
            game.events.register(event, self._check_event, order=20000)

    def _check_event(self, event):
        if self.game.phase != "recruit":
            return
        player_id = event.get("player_id")
        ids = [player_id] if player_id is not None else [p.player_id for p in self.game.players]
        for player_id in ids:
            self.resolve(player_id)

    def _find_triple(self, cards):
        """Return (copies, output_base_id) for the next legal triple.

        Exact three-copy triples take precedence. Elemental of Surprise is the
        one ordinary minion exception: it can stand in for copies of a single
        Elemental identity. It does not allow three unrelated Elementals to
        combine. When Surprise is used as the wildcard, the resulting golden
        minion is the other Elemental rather than Surprise itself.
        """
        groups = defaultdict(list)
        for card in cards:
            groups[card["id"]].append(card)

        for card_id, group in groups.items():
            if len(group) >= 3:
                return group[:3], card_id

        surprises = groups.get(ELEMENTAL_OF_SURPRISE, [])
        if not surprises:
            return None, None

        # One Surprise completes a natural pair of the same Elemental.
        for card in cards:
            card_id = card["id"]
            if card_id == ELEMENTAL_OF_SURPRISE:
                continue
            group = groups.get(card_id, [])
            if (len(group) >= 2
                    and self.game.effects.is_minion_type(group[0], "Elemental")):
                return [group[0], group[1], surprises[0]], card_id

        # Two Surprises can complete one copy of any Elemental.
        if len(surprises) >= 2:
            for card in cards:
                card_id = card["id"]
                if card_id == ELEMENTAL_OF_SURPRISE:
                    continue
                if self.game.effects.is_minion_type(card, "Elemental"):
                    return [card, surprises[0], surprises[1]], card_id

        return None, None

    def resolve(self, player_id):
        """Combine eligible copies from hand and board, never from combat/shop."""
        if self.game.phase != "recruit" or player_id in self._resolving:
            return
        player = self.game.get_player(player_id)
        if player.eliminated:
            return
        self._resolving.add(player_id)
        try:
            while True:
                eligible = [
                    card
                    for card in list(player.board) + list(player.hand)
                    if (isinstance(card, dict) and card.get("cardType") == "minion"
                        and not self.game.effects.is_golden(card))
                ]
                copies, output_base_id = self._find_triple(eligible)
                if copies is None:
                    break
                golden = self.combine(copies, output_base_id=output_base_id)
                identities = {id(card) for card in copies}
                player.hand[:] = [c for c in player.hand if id(c) not in identities]
                player.board[:] = [None if id(c) in identities else c for c in player.board]
                if len(player.hand) < player.MAX_HAND_SIZE:
                    player.hand.append(golden)
                    self.game.events.emit(GameEvent.CARD_ADDED_TO_HAND,
                                          player_id=player_id, card=golden, tripled=True)
                elif self.game.pool.is_pool_card(golden):
                    self.game.pool.return_card(golden)
                self.game.effects.recompute_auras()
        finally:
            self._resolving.remove(player_id)

    def combine(self, copies, *, output_base_id=None):
        """Golden base + net enchantment deltas, floored separately per stat.

        Aura bonuses are excluded: the new hand card has no board aura. Keep
        attachment identities and temporary expiry metadata independently of
        the native golden effect so Magnetics are neither lost nor doubled.
        For Elemental of Surprise triples each consumed card's enchantment
        delta is measured against its own printed base before being added to the
        chosen resulting Elemental's golden base.
        """
        effects = self.game.effects
        if output_base_id is None:
            output_base_id = copies[0]["id"]
        base = effects._definition_by_id(output_base_id)
        golden = effects.create_card(base["id"], golden=True, generated=False)
        for stat in ("attack", "health"):
            normal = int(base.get(stat, 0) or 0)
            golden_base = int(base.get(stat + "Gold") if base.get(stat + "Gold") is not None else 2 * normal)
            delta = 0
            for card in copies:
                card_base = effects._definition_by_id(card["id"])
                card_normal = int(card_base.get(stat, 0) or 0)
                delta += (int(card.get(stat, card_normal) or 0) - card_normal
                          - int(card.get("_aura_" + stat + "_bonus", 0) or 0))
            golden[stat] = golden_base + max(0, delta)
        golden["golden"] = True
        golden["_triple_component_ids"] = [c["id"] for c in copies]
        golden["_pool_copies"] = [card_id for c in copies for card_id in
                                  c.get("_pool_copies", [] if c.get("_generated") else [c["id"]])]
        golden["_generated"] = not bool(golden["_pool_copies"])
        for key in ("_attachments", "_temporary_stat_modifiers"):
            values = [deepcopy(value) for c in copies for value in c.get(key, [])]
            if values:
                golden[key] = values
        permanent = set(base.get("keywords", []))
        for c in copies:
            permanent.update(c.get("_permanent_keyword_grants", []))
            for keyword in c.get("keywords", []):
                if not any(str(k).casefold() == str(keyword).casefold()
                           for k in golden.get("keywords", [])):
                    golden.setdefault("keywords", []).append(keyword)
                info = c.get("_temporary_keywords", {}).get(keyword)
                if info is None or info.get("original_present"):
                    permanent.add(keyword)
            for keyword, info in c.get("_temporary_keywords", {}).items():
                target = golden.setdefault("_temporary_keywords", {}).setdefault(
                    keyword, {"original_present": False, "expiries": []})
                target["expiries"].extend(info["expiries"])
        golden["_permanent_keyword_grants"] = sorted(permanent)
        golden["_blood_gems_received"] = sum(int(c.get("_blood_gems_received", 0)) for c in copies)
        return golden

    def grant_reward(self, player_id):
        tier = min(6, self.game.get_player(player_id).tavern.tier + 1)
        reward = self.game.effects.create_card(TRIPLE_REWARD)
        reward["_discover_tier"] = tier
        reward["text"] = f"<b>Discover</b> a minion from <b>Tier {tier}</b>."
        return self.game.effects.add_generated_to_hand(player_id, reward)

    def _on_play(self, event):
        card = event.get("card")
        if (self.game.phase == "recruit" and isinstance(card, dict)
                and card.get("cardType") == "minion" and self.game.effects.is_golden(card)
                and card.get("_triple_component_ids")
                and not card.get("_no_triple_reward")
                and not card.get("_dark_gift_no_triple_reward")):
            self.grant_reward(event.get("player_id"))

    def _on_spell(self, event):
        card = event.get("spell") or event.get("card")
        if not isinstance(card, dict) or card.get("id") != TRIPLE_REWARD:
            return
        player_id = event.get("player_id")
        tier = int(card.get("_discover_tier", min(6, self.game.get_player(player_id).tavern.tier + 1)))
        if not 1 <= tier <= 6:
            raise ValueError("Triple Reward has an invalid Discover tier.")
        if self.game.effects.get_pending_choice(player_id) is not None:
            raise ValueError("Resolve the existing choice before casting a Triple Reward.")
        offers, seen = [], set()
        for _ in range(3):
            candidates = [c for c in self.game.pool.available_cards
                          if c.get("cardType") == "minion" and c.get("tier") == tier
                          and c["id"] not in seen]
            if not candidates:
                break
            chosen = self.game.random.choice(candidates)
            seen.add(chosen["id"])
            index = next(i for i, c in enumerate(self.game.pool.available_cards) if c is chosen)
            offers.append(self.game.pool.available_cards.pop(index))
        if offers:
            self.game.effects.start_choice(player_id, self.RESOLVER_KEY, offers,
                                           kind="discover", source_card_id=TRIPLE_REWARD,
                                           metadata={"reserved_offers": offers, "tier": tier})

    def _resolve_reward(self, system, player_id, option, metadata):
        for card in metadata["reserved_offers"]:
            if card is not option:
                self.game.pool.return_card(card)
        player = self.game.get_player(player_id)
        if len(player.hand) >= player.MAX_HAND_SIZE or player.eliminated:
            self.game.pool.return_card(option)
            return
        player.hand.append(option)
        self.game.events.emit(GameEvent.CARD_ADDED_TO_HAND, player_id=player_id, card=option)
