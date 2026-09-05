"""Tests for Brain B's compact learned hero preference model."""

import torch

from agents.hero_selector import HeroSelector


def test_hero_selector_starts_neutral():
    model = HeroSelector(card_vocab_size=20)
    scores = model(torch.tensor([2, 3, 4]))
    assert torch.equal(scores, torch.zeros_like(scores))


def test_hero_selector_is_bounded():
    model = HeroSelector(card_vocab_size=20)
    with torch.no_grad():
        model.hero_score.weight[5, 0] = 100.0
    score = float(model(torch.tensor([5]))[0].item())
    assert -1.0 <= score <= 1.0
