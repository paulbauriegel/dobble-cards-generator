"""Finite projective plane of prime order n: n^2 + n + 1 symbols and cards, n + 1 symbols per card,
any two cards share exactly one symbol. See docs/algorithm.md."""
from itertools import combinations


def is_prime(n):
    return n >= 2 and all(n % k for k in range(2, int(n ** 0.5) + 1))


def deck_size(n):
    """Number of symbols (= number of cards) in the plane of order n."""
    return n * n + n + 1


def order_for(symbol_count):
    """Plane order n such that n^2 + n + 1 == symbol_count, n prime. Raises ValueError otherwise."""
    n = 2
    while deck_size(n) < symbol_count:
        n += 1
    if deck_size(n) != symbol_count or not is_prime(n):
        valid = ", ".join(f"{deck_size(k)} ({k + 1} per card)" for k in (2, 3, 5, 7, 11) )
        raise ValueError(f"{symbol_count} symbols do not form a Dobble deck; valid counts: {valid}")
    return n


def dobble(n):
    """Cards of the projective plane of prime order n, as lists of symbol indices 0 .. n^2+n."""
    def inf(m):          # infinity symbols n^2 .. n^2+n
        return n * n + m

    def pt(x, y):        # affine symbols 0 .. n^2-1
        return x * n + y

    cards = []
    for m in range(n):
        for b in range(n):
            cards.append([pt(x, (m * x + b) % n) for x in range(n)] + [inf(m)])
    for x0 in range(n):
        cards.append([pt(x0, y) for y in range(n)] + [inf(n)])
    cards.append([inf(m) for m in range(n + 1)])
    return cards


def verify(cards, n):
    """Raise if the deck is not a valid Dobble deck of order n; return a short report otherwise."""
    total = deck_size(n)
    assert len(cards) == total, f"expected {total} cards, got {len(cards)}"
    for c in cards:
        assert len(c) == n + 1 and len(set(c)) == n + 1, f"card has wrong symbol count: {c}"
    for a, b in combinations(cards, 2):
        shared = set(a) & set(b)
        assert len(shared) == 1, f"cards {a} and {b} share {len(shared)} symbols"
    counts = [0] * total
    for c in cards:
        for s in c:
            counts[s] += 1
    assert all(k == n + 1 for k in counts), "every symbol must appear on exactly n+1 cards"
    return (f"{total} cards, {n + 1} symbols each, {total} symbols, "
            f"every pair of cards shares exactly one symbol, every symbol is on {n + 1} cards")
