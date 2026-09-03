import numpy as np
from PIL import Image, ImageDraw

from dobble.imaging import add_outline, dilate_alpha


def test_dilate_alpha_grows_a_point_into_a_disc():
    a = np.zeros((21, 21), dtype=np.float32)
    a[10, 10] = 1.0
    d = dilate_alpha(a, 4)
    ys, xs = np.nonzero(d)
    assert set(zip(xs, ys)) == {(x, y) for y in range(21) for x in range(21) if (x - 10) ** 2 + (y - 10) ** 2 <= 16}
    assert d.max() == 1.0 and d[10, 10] == 1.0


def test_add_outline_wraps_the_shape_in_a_stroke_without_covering_it():
    img = Image.new("RGBA", (100, 60), (0, 0, 0, 0))
    ImageDraw.Draw(img).rectangle((20, 10, 79, 49), fill=(200, 40, 40, 255))
    out = add_outline(img, width=0.05, color=(0, 0, 255), min_size=0)   # r = 5 px, no upscaling

    assert out.size == (110, 70)
    px = np.asarray(out)
    assert tuple(px[10 + 5, 20 + 5]) == (200, 40, 40, 255)      # original pixel untouched (shifted by r)
    assert tuple(px[5 + 5, 5 + 20]) == (0, 0, 255, 255)         # just above the top edge: stroke
    assert tuple(px[5 + 5, 5 + 79]) == (0, 0, 255, 255)         # and outside the right edge
    assert px[0, 0, 3] == 0 and px[5 + 30, 0, 3] == 0            # corners and far edge stay transparent
    stroke = (px[..., 3] > 0) & (px[..., :3] == (0, 0, 255)).all(axis=2)
    assert stroke.sum() > 0 and not stroke[15:55, 25:85].any()  # stroke only outside the rectangle


def test_add_outline_upscales_small_images_first():
    img = Image.new("RGBA", (40, 20), (0, 0, 0, 0))
    ImageDraw.Draw(img).ellipse((0, 0, 39, 19), fill=(0, 0, 0, 255))
    out = add_outline(img, width=0.025, min_size=400)
    r = round(0.025 * 400)
    assert out.size == (400 + 2 * r, 200 + 2 * r)
