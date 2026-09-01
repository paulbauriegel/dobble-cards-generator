import random
from collections import defaultdict

import pytest

from dobble.plane import dobble
from dobble.ranks import assign_size_ranks


@pytest.mark.parametrize("n", [3, 7])
def test_every_card_and_every_symbol_has_each_rank_once(n):
    cards = dobble(n)
    ranks = assign_size_ranks(cards, random.Random(1))
    k = n + 1
    per_symbol = defaultdict(list)
    for i, card in enumerate(cards):
        assert sorted(ranks[(i, s)] for s in card) == list(range(k))
        for s in card:
            per_symbol[s].append(ranks[(i, s)])
    assert all(sorted(v) == list(range(k)) for v in per_symbol.values())


def test_seed_makes_ranks_reproducible():
    cards = dobble(3)
    assert assign_size_ranks(cards, random.Random(5)) == assign_size_ranks(cards, random.Random(5))
    assert assign_size_ranks(cards, random.Random(5)) != assign_size_ranks(cards, random.Random(6))
