Dobble is a finite projective plane in disguise. The deck has 55 cards with 8 symbols each, drawn from 57 symbols, and any two cards share exactly one symbol. That property is exactly the axiom of a projective plane: any two lines meet in exactly one point.

**The mapping**

- Symbol = point
- Card = line
- "Two cards share exactly one symbol" = "two lines intersect in exactly one point"

A projective plane of order n has n² + n + 1 points and the same number of lines, with n + 1 points on each line. Dobble uses n = 7, giving 57 symbols, 57 possible cards, and 8 symbols per card. The commercial deck drops two cards and ships 55.

**Construction for prime n**

Start with the affine plane over integers mod n: points are pairs (x, y) with x, y in 0..n-1, giving n² symbols. Lines come in three families, and each family gets extra "points at infinity" so that parallel lines also meet somewhere.

1. Sloped lines: for every slope m and intercept b, the card holds the points (x, m·x + b mod n) for all x, plus the infinity point for slope m. That yields n² cards.
2. Vertical lines: for every x0, the card holds (x0, y) for all y, plus one shared vertical infinity point. That yields n cards.
3. The line at infinity: one card holding all n + 1 infinity points.

Total is n² + n + 1 cards, each with n + 1 symbols.

**Why every pair shares exactly one symbol**

- Two sloped lines with different slopes meet in exactly one affine point, because m1·x + b1 = m2·x + b2 has one solution mod a prime. They have different infinity points, so the count is one.
- Two lines with the same slope never meet in the affine part but share that slope's infinity point.
- A vertical and a sloped line meet once at x = x0 and have different infinity points.
- The line at infinity meets every other card at exactly its one infinity point.

**Code**

```python
def dobble(n):  # n must be prime
    cards = []
    inf = lambda m: n * n + m          # infinity symbols n^2 .. n^2+n
    pt = lambda x, y: x * n + y        # affine symbols 0 .. n^2-1
    for m in range(n):
        for b in range(n):
            cards.append([pt(x, (m * x + b) % n) for x in range(n)] + [inf(m)])
    for x0 in range(n):
        cards.append([pt(x0, y) for y in range(n)] + [inf(n)])
    cards.append([inf(m) for m in range(n + 1)])
    return cards
```

Check: every pair of the 57 cards from `dobble(7)` shares exactly one symbol. Symbol indices map to whatever pictures you like.

**Why it only works for some sizes**

The mod-n arithmetic needs division to be well defined, so n must be prime. Prime powers like 4, 8 or 9 also work, but you must use finite-field arithmetic instead of plain modular arithmetic. No projective plane of order 6 exists, so a Dobble with 7 symbols per card is impossible. Dobble Kids uses n = 5 with 6 symbols per card, and there are 31 possible cards, of which it ships 30.
