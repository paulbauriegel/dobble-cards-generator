#!/usr/bin/env python3
"""Build and render a complete Dobble deck: 57 cards, 8 symbols each, from the 57 Pokemon in
images/gen1_artwork_alpha. Any two cards share exactly one symbol (projective plane of order 7,
see algorithm.md). All 57 cards are used, not the 55 of the commercial deck.

Layouts:
    packed (default)  8 different sizes per card, packed tightly using the artwork's real outline.
                      Every Pokemon appears exactly once in each of the 8 sizes across its 8 cards.
    ring              one symbol in the centre, seven on a ring, all roughly the same size.

Usage:
    python dobble_cards.py                       # render images/cards/card_01.png .. card_57.png + cards.json
    python dobble_cards.py --pdf deck.pdf        # also lay the cards out in a printable PDF (8.5 cm)
    python dobble_cards.py --pdf deck.pdf --back images/important/back.png   # double-sided: fronts, then backs
    python dobble_cards.py --seed 7 --gap 0.02   # different random layout, wider spacing
    python dobble_cards.py --layout ring         # the old evenly spaced layout
    python dobble_cards.py --verify-only         # just build and check the deck, no rendering
"""
import argparse
import json
import math
import os
import random
import sys
from collections import defaultdict
from itertools import combinations

import numpy as np
from PIL import Image, ImageDraw

BASE = os.path.dirname(os.path.abspath(__file__))
SYMBOL_DIR = os.path.join(BASE, "images", "gen1_artwork_alpha")
CARD_DIR = os.path.join(BASE, "images", "cards")

N = 7  # order of the plane: N^2 + N + 1 = 57 symbols and cards, N + 1 = 8 symbols per card

# Relative long-side length of the 8 size ranks on a card, largest first. Multiplied by --base-size
# (fraction of the card diameter). The packer shrinks a card uniformly if the art does not fit and
# grows every symbol afterwards where there is room, so these are starting points, not final sizes.
SIZE_LADDER = [1.0, 0.85, 0.72, 0.62, 0.54, 0.48, 0.43, 0.38]

# Sizes are meant as visible area, not bounding-box length. A symbol's long side is multiplied by
# sqrt(SHAPE_REF / (aspect * fill)) so wide or thin artwork (Moltres, the Pokemon logo) gets as much
# ink as a compact one. SHAPE_REF is the median aspect*fill of the Gen 1 artwork set, so a typical
# Pokemon keeps its size and only outliers change.
SHAPE_REF = 0.43
SHAPE_FACTOR_RANGE = (0.8, 2.0)


# ---------------------------------------------------------------- deck construction
def dobble(n=N):
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


def verify(cards, n=N):
    """Raise if the deck is not a valid Dobble deck; return a short report otherwise."""
    total = n * n + n + 1
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


# ---------------------------------------------------------------- size ranks
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


# ---------------------------------------------------------------- image helpers
def scaled_rotated(img, long_side, angle):
    """Resize `img` so its longer side is `long_side` px, then rotate by `angle` degrees (expanding)."""
    w, h = img.size
    scale = long_side / max(w, h)
    img = img.resize((max(1, round(w * scale)), max(1, round(h * scale))), Image.LANCZOS)
    return img.rotate(angle, resample=Image.BICUBIC, expand=True) if angle else img


def fit_rotated(img, box, angle):
    """Scale `img` so that, after rotating by `angle` degrees, its bounding box fits in `box` px."""
    a = math.radians(angle)
    w, h = img.size
    rw = abs(w * math.cos(a)) + abs(h * math.sin(a))
    rh = abs(w * math.sin(a)) + abs(h * math.cos(a))
    scale = box / max(rw, rh)
    img = img.resize((max(1, round(w * scale)), max(1, round(h * scale))), Image.LANCZOS)
    return img.rotate(angle, resample=Image.BICUBIC, expand=True)


def disc_card(size, border, background):
    """Blank round card (RGBA, transparent outside the disc) with an optional grey outline."""
    ss = 4
    mask = Image.new("L", (size * ss, size * ss), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, size * ss - 1, size * ss - 1), fill=255)
    mask = mask.resize((size, size), Image.LANCZOS)
    card = Image.new("RGBA", (size, size), background + (255,))
    card.putalpha(mask)
    if border > 0:
        ring = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        ImageDraw.Draw(ring).ellipse((border / 2, border / 2, size - border / 2, size - border / 2),
                                     outline=(120, 120, 120, 255), width=border)
        card.alpha_composite(ring)
    return card


# ---------------------------------------------------------------- packed layout
def alpha_mask(img_rgba):
    return np.asarray(img_rgba.getchannel("A")) > 128


def shape_factor(img_rgba):
    """Multiplier for the long side so that this artwork shows about the same visible area as a
    reference shape (see SHAPE_REF)."""
    fill = alpha_mask(img_rgba).mean()
    w, h = img_rgba.size
    aspect = min(w, h) / max(w, h)
    factor = math.sqrt(SHAPE_REF / max(aspect * fill, 1e-6))
    return min(SHAPE_FACTOR_RANGE[1], max(SHAPE_FACTOR_RANGE[0], factor))


def dilate(mask, px):
    """Grow `mask` by `px` pixels in every direction (square structuring element)."""
    if px <= 0:
        return mask
    out = np.pad(mask, px)
    for _ in range(px):
        m = out.copy()
        m[1:, :] |= out[:-1, :]
        m[:-1, :] |= out[1:, :]
        m[:, 1:] |= out[:, :-1]
        m[:, :-1] |= out[:, 1:]
        m[1:, 1:] |= out[:-1, :-1]
        m[1:, :-1] |= out[:-1, 1:]
        m[:-1, 1:] |= out[1:, :-1]
        m[:-1, :-1] |= out[1:, 1:]
        out = m
    return out


def paste_mask(mask, x0, y0, grid):
    """Return a full-grid boolean array with `mask` placed at (x0, y0), clipped to the grid."""
    full = np.zeros((grid, grid), dtype=bool)
    h, w = mask.shape
    sx, sy = max(0, -x0), max(0, -y0)
    ex, ey = min(w, grid - x0), min(h, grid - y0)
    if ex > sx and ey > sy:
        full[y0 + sy:y0 + ey, x0 + sx:x0 + ex] = mask[sy:ey, sx:ex]
    return full


def footprint(mask, x0, y0, grid, gap_px):
    """Full-grid mask of `mask` at (x0, y0) grown by `gap_px` (the space other symbols must keep)."""
    return paste_mask(dilate(mask, gap_px), x0 - gap_px, y0 - gap_px, grid)


def find_spot(mask, occupied, rng, tries):
    """Random position inside the disc where `mask` does not touch `occupied`, or None."""
    grid = occupied.shape[0]
    h, w = mask.shape
    for _ in range(tries):
        r = (grid / 2) * math.sqrt(rng.random())
        a = rng.uniform(0, 2 * math.pi)
        x0 = round(grid / 2 + r * math.cos(a) - w / 2)
        y0 = round(grid / 2 + r * math.sin(a) - h / 2)
        if x0 < 0 or y0 < 0 or x0 + w > grid or y0 + h > grid:
            continue
        if not (occupied[y0:y0 + h, x0:x0 + w] & mask).any():
            return x0, y0
    return None


def edt(free):
    """Approximate Euclidean distance from every True pixel of `free` to the nearest False pixel.

    Peels the free region one pixel layer at a time, alternating 4- and 8-neighbourhoods
    (octagonal metric, within a few percent of Euclidean). The maximum is the radius of the
    largest empty circle.
    """
    dist = np.zeros(free.shape, dtype=np.int32)
    cur = free.copy()
    k = 0
    while cur.any():
        k += 1
        nxt = cur.copy()
        nxt[1:, :] &= cur[:-1, :]
        nxt[:-1, :] &= cur[1:, :]
        nxt[:, 1:] &= cur[:, :-1]
        nxt[:, :-1] &= cur[:, 1:]
        if k % 2 == 0:
            nxt[1:, 1:] &= cur[:-1, :-1]
            nxt[1:, :-1] &= cur[:-1, 1:]
            nxt[:-1, 1:] &= cur[1:, :-1]
            nxt[:-1, :-1] &= cur[1:, 1:]
        # pixels on the array border have no outside neighbour; treat the border as non-free
        nxt[0, :] = nxt[-1, :] = nxt[:, 0] = nxt[:, -1] = False
        dist[cur & ~nxt] = k
        cur = nxt
    return dist


def gap_spot(mask, occupied, inside, rng, slack, tries=60, reach=0.15):
    """Position for `mask` in (or near) the largest empty gap of the free space, or None.

    The gap is found with a distance transform on a 2x downsampled grid; a random pixel among
    those within `slack` of the maximum is used as the centre, with growing jitter per try.
    """
    free = inside & ~occupied
    d = edt(free[::2, ::2])
    m = d.max()
    if m == 0:
        return None
    ys, xs = np.nonzero(d >= slack * m)
    grid = occupied.shape[0]
    h, w = mask.shape
    for t in range(tries):
        k = rng.randrange(len(ys))
        cx, cy = xs[k] * 2 + 1, ys[k] * 2 + 1
        r = reach * grid * (t / tries) * math.sqrt(rng.random())
        a = rng.uniform(0, 2 * math.pi)
        x0 = round(cx + r * math.cos(a) - w / 2)
        y0 = round(cy + r * math.sin(a) - h / 2)
        if x0 < 0 or y0 < 0 or x0 + w > grid or y0 + h > grid:
            continue
        if not (occupied[y0:y0 + h, x0:x0 + w] & mask).any():
            return x0, y0
    return None


def pack_card(small_images, ranks, rng, grid, gap_px, base_size, max_rotation, factors=None,
              gap_slack=0.75, do_relax=True, tries=300, grow_step=1.04, grow_cap=1.3):
    """Place the symbols (largest rank first) inside a disc of `grid` px without overlaps.

    Passes: gap-filling placement -> relax -> grow -> relax -> grow.
    small_images: list of RGBA images (downscaled), ranks: matching list of size ranks.
    Returns (placements, coverage, gap): placements are (cx, cy, long_side, angle) in grid pixels,
    coverage is the fraction of the disc covered by artwork, gap the radius of the largest empty
    circle as a fraction of the diameter.
    """
    yy, xx = np.mgrid[0:grid, 0:grid]
    inside = (xx - grid / 2 + 0.5) ** 2 + (yy - grid / 2 + 0.5) ** 2 <= (grid / 2 - gap_px) ** 2
    outside = ~inside
    order = sorted(range(len(small_images)), key=lambda i: ranks[i])   # rank 0 = largest first
    factors = factors or [1.0] * len(small_images)
    shrink_all = 1.0

    # ---- placement: the largest symbol goes anywhere it fits, every further one into the biggest gap
    for _restart in range(30):
        occupied = outside.copy()
        placed = {}
        ok = True
        for n_placed, i in enumerate(order):
            angle = rng.uniform(-max_rotation, max_rotation)
            target = min(0.9 * grid, base_size * SIZE_LADDER[ranks[i]] * grid * shrink_all * factors[i])
            size = target
            spot = None
            for _shrink in range(9):
                mask = alpha_mask(scaled_rotated(small_images[i], size, angle))
                if n_placed > 0:
                    spot = gap_spot(mask, occupied, inside, rng, gap_slack)
                if spot is None:
                    spot = find_spot(mask, occupied, rng, tries)
                if spot:
                    break
                size *= 0.95
            if not spot:
                ok = False
                break
            x0, y0 = spot
            h, w = mask.shape
            placed[i] = dict(cx=x0 + w / 2, cy=y0 + h / 2, size=size, angle=angle, mask=mask,
                             full=paste_mask(mask, x0, y0, grid),
                             foot=footprint(mask, x0, y0, grid, gap_px), cap=target * grow_cap)
            occupied |= placed[i]["foot"]
        if ok:
            break
        shrink_all *= 0.95
    else:
        raise RuntimeError("could not pack card even after shrinking; lower --base-size")

    # count of footprints per cell, so "everything except symbol i" is one subtraction
    foot_count = sum(p["foot"].astype(np.int16) for p in placed.values())

    def fits(i, mask, x0, y0):
        h, w = mask.shape
        if x0 < 0 or y0 < 0 or x0 + w > grid or y0 + h > grid:
            return False
        others = outside | ((foot_count - placed[i]["foot"].astype(np.int16)) > 0)
        return not (others[y0:y0 + h, x0:x0 + w] & mask).any()

    def commit(i, mask, x0, y0, size=None):
        nonlocal foot_count
        p = placed[i]
        h, w = mask.shape
        new_foot = footprint(mask, x0, y0, grid, gap_px)
        foot_count += new_foot.astype(np.int16) - p["foot"].astype(np.int16)
        p.update(cx=x0 + w / 2, cy=y0 + h / 2, mask=mask, full=paste_mask(mask, x0, y0, grid), foot=new_foot)
        if size is not None:
            p["size"] = size

    def grow():
        """Enlarge symbols in place while there is room (capped so the size order survives)."""
        grew = True
        while grew:
            grew = False
            for i in order:
                p = placed[i]
                new_size = p["size"] * grow_step
                if new_size > p["cap"]:
                    continue
                mask = alpha_mask(scaled_rotated(small_images[i], new_size, p["angle"]))
                h, w = mask.shape
                x0, y0 = round(p["cx"] - w / 2), round(p["cy"] - h / 2)
                if fits(i, mask, x0, y0):
                    commit(i, mask, x0, y0, new_size)
                    grew = True

    def relax(rounds=8, step_frac=0.5, max_step=0.05 * grid):
        """Lloyd relaxation: move each symbol toward the centroid of its power-diagram cell."""
        for _ in range(rounds):
            best = np.full((grid, grid), -1, dtype=np.int8)
            best_v = np.full((grid, grid), np.inf)
            for i, p in placed.items():
                r = math.sqrt(p["full"].sum() / math.pi)
                v = np.hypot(xx + 0.5 - p["cx"], yy + 0.5 - p["cy"]) - r
                upd = v < best_v
                best_v[upd] = v[upd]
                best[upd] = i
            moved = 0.0
            for i in order:
                p = placed[i]
                cell = (best == i) & inside
                if not cell.any():
                    continue
                dx = (xx[cell].mean() + 0.5 - p["cx"]) * step_frac
                dy = (yy[cell].mean() + 0.5 - p["cy"]) * step_frac
                step = math.hypot(dx, dy)
                if step > max_step:
                    dx, dy = dx * max_step / step, dy * max_step / step
                h, w = p["mask"].shape
                for _halving in range(3):
                    x0, y0 = round(p["cx"] + dx - w / 2), round(p["cy"] + dy - h / 2)
                    if fits(i, p["mask"], x0, y0):
                        moved += math.hypot(x0 + w / 2 - p["cx"], y0 + h / 2 - p["cy"])
                        commit(i, p["mask"], x0, y0)
                        break
                    dx, dy = dx / 2, dy / 2
            if moved < 0.5:
                break

    if do_relax:
        relax()
    grow()
    if do_relax:
        relax()
        grow()

    # sanity: no overlaps, everything inside the disc
    total = sum(p["full"].astype(np.uint8) for p in placed.values())
    assert total.max() <= 1, "symbols overlap"
    assert not (total.astype(bool) & outside).any(), "symbol crosses the card edge"
    coverage = total.astype(bool).sum() / inside.sum()
    gap = edt((inside & ~total.astype(bool))[::2, ::2]).max() * 2 / grid
    spots = [(placed[i]["cx"], placed[i]["cy"], placed[i]["size"], placed[i]["angle"])
             for i in range(len(small_images))]
    return spots, coverage, gap


def render_packed(images, ranks, size, rng, args):
    """Packed layout. Returns (card image, placements in card pixels, coverage, largest gap)."""
    grid = args.grid
    gap_px = max(1, round(args.gap * grid))
    small = []
    for img in images:
        s = img.copy()
        s.thumbnail((grid, grid), Image.LANCZOS)
        small.append(s)
    factors = [shape_factor(img) for img in images]
    spots, coverage, gap = pack_card(small, ranks, rng, grid, gap_px, args.base_size, args.max_rotation,
                                     factors=factors, gap_slack=args.gap_slack, do_relax=not args.no_relax)
    card = disc_card(size, args.border, (255, 255, 255))
    f = size / grid
    placements = []
    for img, (cx, cy, s, angle) in zip(images, spots):
        piece = scaled_rotated(img, s * f, angle)
        card.alpha_composite(piece, (round(cx * f - piece.width / 2), round(cy * f - piece.height / 2)))
        placements.append((cx * f, cy * f, s * f, angle))
    return card, placements, coverage, gap


# ---------------------------------------------------------------- ring layout
def render_ring(images, size, rng, args):
    """One symbol in the centre, the rest on a ring, all about the same size."""
    R = size / 2
    k = len(images) - 1
    ring_r = 0.63 * R
    slot = min(2 * ring_r * math.sin(math.pi / k), 2 * (0.98 * R - ring_r))
    centre_slot = 2 * (ring_r - slot / 2) * 0.95

    card = disc_card(size, args.border, (255, 255, 255))
    order = list(range(len(images)))
    rng.shuffle(order)
    start = rng.uniform(0, 2 * math.pi)
    spots = [(R, R, centre_slot)]
    for i in range(k):
        ang = start + 2 * math.pi * i / k
        spots.append((R + ring_r * math.cos(ang), R + ring_r * math.sin(ang), slot))

    placements = [None] * len(images)
    covered = np.zeros((size, size), dtype=bool)
    for idx, (cx, cy, box) in zip(order, spots):
        angle = rng.uniform(-args.max_rotation, args.max_rotation)
        box *= rng.uniform(args.min_scale, 1.0)
        piece = fit_rotated(images[idx], box, angle)
        x0, y0 = round(cx - piece.width / 2), round(cy - piece.height / 2)
        card.alpha_composite(piece, (x0, y0))
        placements[idx] = (cx, cy, max(piece.size), angle)
        covered[y0:y0 + piece.height, x0:x0 + piece.width] |= alpha_mask(piece)
    coverage = covered.sum() / (math.pi * R * R)
    return card, placements, coverage, None


# ---------------------------------------------------------------- pdf
def write_pdf(card_paths, output, diameter_cm, page, margin_cm, gap_cm, line_width=0.25,
              back=None, mirror_back=True, back_zoom=1.0):
    """Lay the cards out on pages of `page` size. With `back`, every page of fronts is followed by a
    page with the back image at the same positions (mirrored left/right for long-edge duplex
    printing unless mirror_back is False), so double-sided printing gives every cut card a back."""
    from reportlab.lib.units import cm
    from reportlab.pdfgen import canvas
    from circle_pdf import PAGE_SIZES

    page_w, page_h = PAGE_SIZES[page.lower()]
    diameter, margin, gap = diameter_cm * cm, margin_cm * cm, gap_cm * cm
    cols = max(1, int((page_w - 2 * margin + gap) // (diameter + gap)))
    rows = max(1, int((page_h - 2 * margin + gap) // (diameter + gap)))
    per_page = cols * rows
    grid_w = cols * diameter + (cols - 1) * gap
    grid_h = rows * diameter + (rows - 1) * gap
    x0 = (page_w - grid_w) / 2
    y0 = page_h - (page_h - grid_h) / 2 - diameter

    def slot(idx, mirrored=False):
        col, row = idx % cols, idx // cols
        if mirrored:
            col = cols - 1 - col
        return x0 + col * (diameter + gap), y0 - row * (diameter + gap)

    def draw_back(c, x, y):
        """Back image scaled to cover the disc, clipped to the circle."""
        c.saveState()
        clip = c.beginPath()
        clip.circle(x + diameter / 2, y + diameter / 2, diameter / 2)
        c.clipPath(clip, stroke=0, fill=0)
        bw, bh = back_size
        scale = diameter / min(bw, bh) * back_zoom
        w, h = bw * scale, bh * scale
        c.drawImage(back, x + (diameter - w) / 2, y + (diameter - h) / 2, w, h, mask="auto")
        c.restoreState()
        c.circle(x + diameter / 2, y + diameter / 2, diameter / 2, stroke=1, fill=0)

    if back:
        with Image.open(back) as im:
            back_size = im.size

    c = canvas.Canvas(output, pagesize=(page_w, page_h))
    c.setTitle("Dobble deck")
    pages = 0
    for start in range(0, len(card_paths), per_page):
        chunk = card_paths[start:start + per_page]
        c.setLineWidth(line_width)   # hairline cutting guide
        for idx, path in enumerate(chunk):
            x, y = slot(idx)
            c.drawImage(path, x, y, diameter, diameter, mask="auto")
            c.circle(x + diameter / 2, y + diameter / 2, diameter / 2, stroke=1, fill=0)
        c.showPage()
        pages += 1
        if back:
            c.setLineWidth(line_width)
            for idx in range(len(chunk)):
                x, y = slot(idx, mirrored=mirror_back)
                draw_back(c, x, y)
            c.showPage()
            pages += 1
    c.save()
    return pages


# ---------------------------------------------------------------- main
def load_symbols(symbol_dir, shuffle_seed=None):
    files = sorted(f for f in os.listdir(symbol_dir) if f.lower().endswith(".png"))
    if len(files) != N * N + N + 1:
        sys.exit(f"need exactly {N * N + N + 1} symbol images in {symbol_dir}, found {len(files)}")
    if shuffle_seed is not None:
        random.Random(shuffle_seed).shuffle(files)
    return files


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=CARD_DIR, help="folder for the card PNGs")
    ap.add_argument("--symbols", default=SYMBOL_DIR, help="folder with the 57 symbol PNGs")
    ap.add_argument("--layout", choices=["packed", "ring"], default="packed")
    ap.add_argument("--size", type=int, default=1200, help="card diameter in pixels")
    ap.add_argument("--seed", type=int, default=42, help="random seed for sizes, rotation and placement")
    ap.add_argument("--shuffle-symbols", action="store_true",
                    help="assign Pokemon to symbol slots randomly instead of in file order")
    ap.add_argument("--max-rotation", type=float, default=40, help="max rotation of a symbol in degrees")
    ap.add_argument("--border", type=int, default=1, help="grey outline width in the PNG in px, 0 for none")
    # packed layout
    ap.add_argument("--base-size", type=float, default=0.40,
                    help="packed: long side of the largest symbol as a fraction of the card diameter")
    ap.add_argument("--gap", type=float, default=0.015,
                    help="packed: minimum space between symbols as a fraction of the card diameter")
    ap.add_argument("--grid", type=int, default=400, help="packed: collision grid resolution in px")
    ap.add_argument("--no-balanced-sizes", action="store_true",
                    help="packed: random size ranks per card instead of one of each size per Pokemon")
    ap.add_argument("--no-relax", action="store_true",
                    help="packed: skip the relaxation passes that even out the whitespace")
    ap.add_argument("--gap-slack", type=float, default=0.75,
                    help="packed: a new symbol goes into a gap at least this fraction as deep as the biggest one")
    # ring layout
    ap.add_argument("--min-scale", type=float, default=0.8, help="ring: smallest symbol size relative to its slot")
    # pdf
    ap.add_argument("--pdf", help="also write a printable PDF to this path")
    ap.add_argument("-d", "--diameter", type=float, default=8.5, help="card diameter in cm for the PDF")
    ap.add_argument("--page", default="a4", help="PDF page size: a4, a3 or letter")
    ap.add_argument("--line-width", type=float, default=0.25, help="PDF cutting circle stroke in points")
    ap.add_argument("--back", help="image for the card back; adds a back page after every page of fronts "
                                   "so the deck can be printed double-sided")
    ap.add_argument("--back-zoom", type=float, default=1.0,
                    help="enlarge the back image by this factor so its edge lies outside the cut line")
    ap.add_argument("--pdf-only", action="store_true",
                    help="do not re-render the cards; build the PDF from the PNGs already in --out")
    ap.add_argument("--no-mirror-back", action="store_true",
                    help="do not mirror the back pages left/right (use for short-edge duplex or manual re-feeding)")
    ap.add_argument("--verify-only", action="store_true")
    args = ap.parse_args()

    cards = dobble()
    print("deck check:", verify(cards))
    if args.verify_only:
        return

    if args.pdf_only:
        if not args.pdf:
            sys.exit("--pdf-only needs --pdf")
        card_paths = [os.path.join(args.out, f"card_{i:02d}.png") for i in range(1, len(cards) + 1)]
        missing = [p for p in card_paths if not os.path.exists(p)]
        if missing:
            sys.exit(f"{len(missing)} card PNGs missing in {args.out}; run without --pdf-only first")
        pages = write_pdf(card_paths, args.pdf, args.diameter, args.page, 1.0, 0.5, args.line_width,
                          back=args.back, mirror_back=not args.no_mirror_back, back_zoom=args.back_zoom)
        backs = " with back pages" if args.back else ""
        print(f"wrote {args.pdf} ({pages} pages{backs}, {args.diameter} cm cards) from existing PNGs")
        return

    files = load_symbols(args.symbols, args.seed if args.shuffle_symbols else None)
    names = [os.path.splitext(f)[0] for f in files]
    images = [Image.open(os.path.join(args.symbols, f)).convert("RGBA") for f in files]
    rng = random.Random(args.seed)
    ranks = None
    if args.layout == "packed":
        ranks = random_size_ranks(cards, rng) if args.no_balanced_sizes else assign_size_ranks(cards, rng)
        boosted = sorted(((shape_factor(im), n) for im, n in zip(images, names)), reverse=True)
        print("shape factors (long-side boost for wide/thin artwork): " +
              ", ".join(f"{n} x{f:.2f}" for f, n in boosted if f > 1.15))
        if not args.no_balanced_sizes:
            print("size ranks: every card has each of the 8 sizes once, every Pokemon has each size once")

    os.makedirs(args.out, exist_ok=True)
    card_paths, deck_cards, coverages, gaps = [], [], [], []
    for i, card in enumerate(cards, 1):
        imgs = [images[s] for s in card]
        if args.layout == "packed":
            card_ranks = [ranks[(i - 1, s)] for s in card]
            img, placements, cov, gap = render_packed(imgs, card_ranks, args.size, rng, args)
        else:
            card_ranks = [None] * len(card)
            img, placements, cov, gap = render_ring(imgs, args.size, rng, args)
        path = os.path.join(args.out, f"card_{i:02d}.png")
        img.save(path)
        card_paths.append(path)
        coverages.append(cov)
        gaps.append(gap)
        deck_cards.append({
            "coverage": round(cov, 3), "largest_gap": None if gap is None else round(gap, 3),
            "symbols": [
                {"symbol": names[s], "rank": r, "shape_factor": round(shape_factor(images[s]), 2),
                 "cx": round(cx / args.size, 4), "cy": round(cy / args.size, 4),
                 "size": round(sz / args.size, 4), "rotation": round(angle, 1)}
                for s, r, (cx, cy, sz, angle) in zip(card, card_ranks, placements)]})
        gap_txt = "" if gap is None else f", largest gap {gap:.3f}"
        print(f"card {i:02d} ({cov:4.0%} covered{gap_txt}): " + ", ".join(names[s] for s in card))

    deck = {
        "order": N, "cards": len(cards), "symbols_per_card": N + 1, "layout": args.layout,
        "symbol_dir": os.path.relpath(args.symbols, BASE),
        "symbols": names,
        "cards_by_index": cards,
        "cards_by_name": [[names[s] for s in c] for c in cards],
        "placements": deck_cards,
    }
    with open(os.path.join(args.out, "cards.json"), "w", encoding="utf-8") as f:
        json.dump(deck, f, indent=1)
    summary = f"mean disc coverage {sum(coverages) / len(coverages):.0%}"
    if all(g is not None for g in gaps):
        summary += f", mean largest empty circle {sum(gaps) / len(gaps):.3f} of the diameter"
    print(f"wrote {len(cards)} cards and cards.json to {os.path.relpath(args.out, BASE)}; {summary}")

    if args.pdf:
        pages = write_pdf(card_paths, args.pdf, args.diameter, args.page, 1.0, 0.5, args.line_width,
                          back=args.back, mirror_back=not args.no_mirror_back, back_zoom=args.back_zoom)
        backs = " with back pages" if args.back else ""
        print(f"wrote {args.pdf} ({pages} pages{backs}, {args.diameter} cm cards)")


if __name__ == "__main__":
    main()
