"""Size ranks: which of the k symbols on a card is drawn largest, second largest, ... smallest."""
from collections import defaultdict


def assign_size_ranks(cards, rng):
    """Map (card index, symbol) -> size rank 0..k-1 so that every card has each rank exactly once AND
    every symbol has each rank exactly once over its k cards.

    The card/symbol incidence graph is k-regular bipartite, so it has a proper k-edge-colouring
    (Koenig). We peel off one perfect matching per rank with Kuhn's augmenting-path algorithm.
    """
    k = len(cards[0])
    remaining = {i: list(c) for i, c in enumerate(cards)}
    for adj in remaining.values():
        rng.shuffle(adj)
    card_order = list(remaining)
    rng.shuffle(card_order)
    ranks = {}

    for rank in range(k):
        matched = {}                       # symbol -> card

        def augment(card, seen):
            for s in remaining[card]:
                if s in seen:
                    continue
                seen.add(s)
                if s not in matched or augment(matched[s], seen):
                    matched[s] = card
                    return True
            return False

        for card in card_order:
            if not augment(card, set()):
                raise RuntimeError("no perfect matching; deck is not regular?")
        for s, card in matched.items():
            ranks[(card, s)] = rank
            remaining[card].remove(s)

    per_symbol = defaultdict(list)
    for (i, s), r in ranks.items():
        per_symbol[s].append(r)
    assert all(sorted(ranks[(i, s)] for s in c) == list(range(k)) for i, c in enumerate(cards))
    assert all(sorted(v) == list(range(k)) for v in per_symbol.values())
    return ranks


def random_size_ranks(cards, rng):
    """Fallback: each card gets ranks 0..k-1 in random order, no balancing across the deck."""
    ranks = {}
    for i, c in enumerate(cards):
        order = list(range(len(c)))
        rng.shuffle(order)
        for s, r in zip(c, order):
            ranks[(i, s)] = r
    return ranks
