"""Place symbols of different sizes inside a disc without overlap, using the artwork's real outline."""
import math

import numpy as np
from PIL import Image

# Relative long-side length of the 8 size ranks of a standard (order 7) deck, largest first.
# Multiplied by base_size (fraction of the card diameter). The packer shrinks a card uniformly if
# the art does not fit and grows every symbol afterwards where there is room, so these are
# starting points, not final sizes.
_LADDER_8 = [1.0, 0.85, 0.72, 0.62, 0.54, 0.48, 0.43, 0.38]
SMALLEST_RANK = _LADDER_8[-1]

# A symbol's long side is multiplied by sqrt(ref / (aspect * fill)), clamped to this range, so wide
# or thin artwork gets about as much visible area as a compact one. See shape_reference().
SHAPE_FACTOR_RANGE = (0.8, 2.0)

# Every symbol gets a random base orientation in steps of this many degrees, see orientations().
ROTATION_STEP = 45


def size_ladder(k):
    """Relative sizes of the k ranks on a card, largest first, from 1.0 down to SMALLEST_RANK."""
    if k == len(_LADDER_8):
        return list(_LADDER_8)
    if k == 1:
        return [1.0]
    return [SMALLEST_RANK ** (i / (k - 1)) for i in range(k)]


def scaled_rotated(img, long_side, angle):
    """Resize `img` so its longer side is `long_side` px, then rotate by `angle` degrees (expanding)."""
    w, h = img.size
    scale = long_side / max(w, h)
    img = img.resize((max(1, round(w * scale)), max(1, round(h * scale))), Image.LANCZOS)
    return img.rotate(angle, resample=Image.BICUBIC, expand=True) if angle else img


def orientations(rng, max_rotation, step=ROTATION_STEP):
    """Candidate angles for one symbol, in degrees within [0, 360).

    The first is a random multiple of `step` plus a jitter of up to +-max_rotation, so symbols face
    random directions instead of all standing upright. The rest are the other multiples of `step`
    with the same jitter, nearest first, which the packer tries when the symbol does not fit as drawn.
    """
    if step <= 0 or 360 % step:
        raise ValueError(f"rotation step must divide 360, got {step}")
    n = int(360 // step)
    base = rng.randrange(n) * step + rng.uniform(-max_rotation, max_rotation)
    deltas = [0]
    for k in range(1, n // 2 + 1):
        deltas.append(k * step)
        if 2 * k != n:              # 180 degrees is its own opposite
            deltas.append(-k * step)
    return [(base + d) % 360 for d in deltas]


def alpha_mask(img_rgba):
    return np.asarray(img_rgba.getchannel("A")) > 128


def _aspect_fill(img_rgba):
    """aspect (short/long side) times fill (opaque fraction of the bounding box): a compactness measure."""
    w, h = img_rgba.size
    return (min(w, h) / max(w, h)) * alpha_mask(img_rgba).mean()


def shape_reference(images):
    """Median compactness of a symbol set. Symbols at the median keep their nominal size, wide or
    thin ones are enlarged so every symbol shows about the same visible area."""
    return float(np.median([_aspect_fill(im) for im in images]))


def shape_factor(img_rgba, ref):
    """Multiplier for the long side so that this artwork shows about the same visible area as a
    symbol of compactness `ref` (see shape_reference)."""
    factor = math.sqrt(ref / max(_aspect_fill(img_rgba), 1e-6))
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


def gap_centres(occupied, inside, slack):
    """Centres (xs, ys) of the largest empty gaps of the free space, or None if nothing is free.

    Found with a distance transform on a 2x downsampled grid: every pixel whose distance to the
    nearest occupied pixel is within `slack` of the maximum counts as a gap centre.
    """
    d = edt((inside & ~occupied)[::2, ::2])
    m = d.max()
    if m == 0:
        return None
    ys, xs = np.nonzero(d >= slack * m)
    return xs * 2 + 1, ys * 2 + 1


def gap_spot(mask, occupied, centres, rng, tries=60, reach=0.15):
    """Position for `mask` in (or near) one of the gap `centres` (see gap_centres), or None.
    A random centre is used per try, with growing jitter."""
    xs, ys = centres
    grid = occupied.shape[0]
    h, w = mask.shape
    for t in range(tries):
        k = rng.randrange(len(ys))
        cx, cy = xs[k], ys[k]
        r = reach * grid * (t / tries) * math.sqrt(rng.random())
        a = rng.uniform(0, 2 * math.pi)
        x0 = round(cx + r * math.cos(a) - w / 2)
        y0 = round(cy + r * math.sin(a) - h / 2)
        if x0 < 0 or y0 < 0 or x0 + w > grid or y0 + h > grid:
            continue
        if not (occupied[y0:y0 + h, x0:x0 + w] & mask).any():
            return x0, y0
    return None


def place_any(angles, raster, occupied, centres, rng, tries):
    """First (angle, mask, (x0, y0)) over `angles` that fits, or None. `raster(angle)` gives the mask.
    Every orientation is tried in the biggest gap before any one is placed at random."""
    masks = {}

    def mask_at(angle):
        if angle not in masks:
            masks[angle] = raster(angle)
        return masks[angle]

    if centres is not None:
        for angle in angles:
            spot = gap_spot(mask_at(angle), occupied, centres, rng)
            if spot:
                return angle, mask_at(angle), spot
    for angle in angles:
        spot = find_spot(mask_at(angle), occupied, rng, tries)
        if spot:
            return angle, mask_at(angle), spot
    return None


def pack_card(small_images, ranks, rng, grid, gap_px, base_size, max_rotation, factors=None,
              gap_slack=0.75, do_relax=True, tries=300, grow_step=1.04, grow_cap=1.3):
    """Place the symbols (largest rank first) inside a disc of `grid` px without overlaps.

    Passes: gap-filling placement -> relax -> grow -> relax -> grow.
    Each symbol faces a random direction (a multiple of ROTATION_STEP plus up to +-max_rotation of
    jitter); the other multiples are tried before the symbol is shrunk to fit.
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
    ladder = size_ladder(len(small_images))
    shrink_all = 1.0

    # ---- placement: the largest symbol goes anywhere it fits, every further one into the biggest gap
    for _restart in range(30):
        occupied = outside.copy()
        placed = {}
        ok = True
        for n_placed, i in enumerate(order):
            angles = orientations(rng, max_rotation)
            centres = gap_centres(occupied, inside, gap_slack) if n_placed > 0 else None
            target = min(0.9 * grid, base_size * ladder[ranks[i]] * grid * shrink_all * factors[i])
            size = target
            hit = None
            for _shrink in range(9):
                def raster(angle, size=size):
                    return alpha_mask(scaled_rotated(small_images[i], size, angle))
                hit = place_any(angles, raster, occupied, centres, rng, tries)
                if hit:
                    break
                size *= 0.95
            if not hit:
                ok = False
                break
            angle, mask, (x0, y0) = hit
            h, w = mask.shape
            placed[i] = dict(cx=x0 + w / 2, cy=y0 + h / 2, size=size, angle=angle, mask=mask,
                             full=paste_mask(mask, x0, y0, grid),
                             foot=footprint(mask, x0, y0, grid, gap_px), cap=target * grow_cap)
            occupied |= placed[i]["foot"]
        if ok:
            break
        shrink_all *= 0.95
    else:
        raise RuntimeError("could not pack card even after shrinking; lower base_size")

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
