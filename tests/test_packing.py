import random

import numpy as np
from PIL import Image, ImageDraw

from dobble.packing import pack_card, shape_reference, size_ladder
from dobble.render import render_packed


def blob(w, h, colour):
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(img).ellipse((0, 0, w - 1, h - 1), fill=colour + (255,))
    return img


BLOBS = [blob(80, 80, (255, 0, 0)), blob(120, 40, (0, 255, 0)), blob(60, 90, (0, 0, 255)), blob(70, 70, (0, 0, 0))]


def test_size_ladder():
    assert len(size_ladder(8)) == 8 and size_ladder(8)[0] == 1.0
    assert size_ladder(8) == [1.0, 0.85, 0.72, 0.62, 0.54, 0.48, 0.43, 0.38]
    four = size_ladder(4)
    assert four[0] == 1.0 and four[-1] == 0.38 and all(a > b for a, b in zip(four, four[1:]))
    assert len(size_ladder(12)) == 12


def test_shape_reference_is_median_of_aspect_times_fill():
    ref = shape_reference(BLOBS)
    assert 0.2 < ref < 0.8


def test_pack_card_places_everything_inside_the_disc():
    grid = 100
    spots, coverage, gap = pack_card(BLOBS, [0, 1, 2, 3], random.Random(0), grid, gap_px=2,
                                     base_size=0.4, max_rotation=30)
    assert len(spots) == 4
    for cx, cy, size, angle in spots:
        assert np.hypot(cx - grid / 2, cy - grid / 2) < grid / 2
        assert size > 0
    assert 0 < coverage < 1 and 0 < gap < 1


def test_render_packed_returns_card_and_placements():
    result = render_packed(BLOBS, [0, 1, 2, 3], 200, random.Random(0), grid=100, gap=0.02,
                           base_size=0.4, max_rotation=30, border=1, factors=[1.0] * 4)
    assert result.image.size == (200, 200)
    assert len(result.placements) == 4
    assert result.image.getpixel((0, 0))[3] == 0            # transparent corner
    assert result.image.getpixel((100, 100))[3] == 255      # opaque centre
