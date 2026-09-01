"""Turn a card's symbol images and their packing into a round card PNG."""
from dataclasses import dataclass

from PIL import Image, ImageDraw

from .packing import pack_card, scaled_rotated


@dataclass
class CardResult:
    image: Image.Image
    placements: list        # per symbol: (cx, cy, long_side, angle) in card pixels
    coverage: float         # fraction of the disc covered by artwork
    largest_gap: float      # radius of the largest empty circle as a fraction of the diameter


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


def render_packed(images, ranks, size, rng, grid, gap, base_size, max_rotation, border, factors,
                  gap_slack=0.75, relax=True):
    """Pack `images` (with size `ranks` and shape `factors`) on a collision grid of `grid` px and
    composite them onto a card of `size` px."""
    gap_px = max(1, round(gap * grid))
    small = []
    for img in images:
        s = img.copy()
        s.thumbnail((grid, grid), Image.LANCZOS)
        small.append(s)
    spots, coverage, largest_gap = pack_card(small, ranks, rng, grid, gap_px, base_size, max_rotation,
                                             factors=factors, gap_slack=gap_slack, do_relax=relax)
    card = disc_card(size, border)
    f = size / grid
    placements = []
    for img, (cx, cy, s, angle) in zip(images, spots):
        piece = scaled_rotated(img, s * f, angle)
        card.alpha_composite(piece, (round(cx * f - piece.width / 2), round(cy * f - piece.height / 2)))
        placements.append((cx * f, cy * f, s * f, angle))
    return CardResult(card, placements, coverage, largest_gap)
