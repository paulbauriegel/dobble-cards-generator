"""Turn white-background artwork into transparent, trimmed symbol PNGs.

  * Only white that is CONNECTED TO THE IMAGE BORDER becomes transparent, so white body parts
    (claws, eyes, a white belly) stay opaque. Enclosed background pockets are passed in as seed
    pixels (see `pockets`).
  * Anti-aliased edge pixels get a partial alpha and their colour is un-blended from white,
    so there is no white fringe on coloured card backgrounds.
"""
import numpy as np
from PIL import Image

WHITE_LEVEL = 245   # min(r,g,b) at or above this is treated as pure background
OPAQUE_LEVEL = 200  # min(r,g,b) at or below this is fully opaque; in between = soft edge


def border_connected(mask, seeds=()):
    """Connected component(s) of `mask` (bool HxW) that touch the image border or contain a seed, 4-connected."""
    reach = np.zeros_like(mask)
    reach[0, :] = mask[0, :]; reach[-1, :] = mask[-1, :]
    reach[:, 0] = mask[:, 0]; reach[:, -1] = mask[:, -1]
    for x, y in seeds:
        if not mask[y, x]:
            raise ValueError(f"pocket seed {(x, y)} is not on a white pixel")
        reach[y, x] = True
    while True:
        grown = reach.copy()
        grown[1:, :] |= reach[:-1, :]
        grown[:-1, :] |= reach[1:, :]
        grown[:, 1:] |= reach[:, :-1]
        grown[:, :-1] |= reach[:, 1:]
        grown &= mask
        if np.array_equal(grown, reach):
            return reach
        reach = grown


def trim_alpha(img):
    """Crop an RGBA image to the bounding box of its non-transparent pixels."""
    bbox = img.getchannel("A").getbbox()
    return img.crop(bbox) if bbox else img


def to_transparent(img, trim=True, pockets=(), white_level=WHITE_LEVEL, opaque_level=OPAQUE_LEVEL):
    rgb = np.asarray(img.convert("RGB")).astype(np.float32)
    minc = rgb.min(axis=2)

    # Pixels that could be background or a soft edge; flood from the border (and pocket seeds) through them.
    candidate = minc > opaque_level
    bg = border_connected(candidate, pockets)

    alpha = np.ones_like(minc)
    soft = np.clip((white_level - minc) / (white_level - opaque_level), 0.0, 1.0)
    alpha[bg] = soft[bg]

    # Un-blend the edge colour from white: pixel = a*c + (1-a)*255  ->  c = (pixel - (1-a)*255) / a
    a3 = alpha[..., None]
    safe_a = np.maximum(a3, 1e-3)
    unblended = (rgb - (1.0 - a3) * 255.0) / safe_a
    out_rgb = np.where(a3 > 0, np.clip(unblended, 0, 255), 0)

    out = np.dstack([out_rgb, alpha * 255.0]).round().astype(np.uint8)
    result = Image.fromarray(out, "RGBA")
    return trim_alpha(result) if trim else result
