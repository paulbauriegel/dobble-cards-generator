"""Turn a card's symbol images and their packing into a round card PNG."""
import math

import numpy as np
from PIL import Image, ImageDraw

from .packing import alpha_mask, pack_card, scaled_rotated, shape_factor


def fit_rotated(img, box, angle):
    """Scale `img` so that, after rotating by `angle` degrees, its bounding box fits in `box` px."""
    a = math.radians(angle)
    w, h = img.size
    rw = abs(w * math.cos(a)) + abs(h * math.sin(a))
    rh = abs(w * math.sin(a)) + abs(h * math.cos(a))
    scale = box / max(rw, rh)
    img = img.resize((max(1, round(w * scale)), max(1, round(h * scale))), Image.LANCZOS)
    return img.rotate(angle, resample=Image.BICUBIC, expand=True)


def disc_card(size, border, background=(255, 255, 255)):
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


def render_packed(images, ranks, size, rng, grid, gap, base_size, max_rotation, border,
                  gap_slack=0.75, relax=True):
    """Packed layout. Returns (card image, placements in card pixels, coverage, largest gap)."""
    gap_px = max(1, round(gap * grid))
    small = []
    for img in images:
        s = img.copy()
        s.thumbnail((grid, grid), Image.LANCZOS)
        small.append(s)
    factors = [shape_factor(img) for img in images]
    spots, coverage, largest_gap = pack_card(small, ranks, rng, grid, gap_px, base_size, max_rotation,
                                             factors=factors, gap_slack=gap_slack, do_relax=relax)
    card = disc_card(size, border)
    f = size / grid
    placements = []
    for img, (cx, cy, s, angle) in zip(images, spots):
        piece = scaled_rotated(img, s * f, angle)
        card.alpha_composite(piece, (round(cx * f - piece.width / 2), round(cy * f - piece.height / 2)))
        placements.append((cx * f, cy * f, s * f, angle))
    return card, placements, coverage, largest_gap


def render_ring(images, size, rng, max_rotation, border, min_scale=0.8):
    """One symbol in the centre, the rest on a ring, all about the same size."""
    R = size / 2
    k = len(images) - 1
    ring_r = 0.63 * R
    slot = min(2 * ring_r * math.sin(math.pi / k), 2 * (0.98 * R - ring_r))
    centre_slot = 2 * (ring_r - slot / 2) * 0.95

    card = disc_card(size, border)
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
        angle = rng.uniform(-max_rotation, max_rotation)
        box *= rng.uniform(min_scale, 1.0)
        piece = fit_rotated(images[idx], box, angle)
        x0, y0 = round(cx - piece.width / 2), round(cy - piece.height / 2)
        card.alpha_composite(piece, (x0, y0))
        placements[idx] = (cx, cy, max(piece.size), angle)
        covered[y0:y0 + piece.height, x0:x0 + piece.width] |= alpha_mask(piece)
    coverage = covered.sum() / (math.pi * R * R)
    return card, placements, coverage, None
