"""Turn the white background of Gen 1 artwork JPGs into transparency.

Usage:
    python make_transparent.py                 # the 57 Pokemon in SELECTION -> images/gen1_artwork_alpha
    python make_transparent.py --all           # all 151
    python make_transparent.py --no-trim       # keep the original canvas instead of cropping to content

How it works:
  * Only white that is CONNECTED TO THE IMAGE BORDER becomes transparent, so white body parts
    (Charizard's claws, eyes, Mr. Mime's body) stay opaque. Enclosed background pockets are
    listed by hand in POCKETS below.
  * Anti-aliased edge pixels get a partial alpha and their colour is un-blended from white,
    so there is no white fringe on coloured card backgrounds.
"""
import argparse, os, sys
import numpy as np
from PIL import Image

BASE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(BASE, "images", "gen1_artwork")
DST = os.path.join(BASE, "images", "gen1_artwork_alpha")
SPRITE_SRC = os.path.join(BASE, "images", "gen1_png")
SPRITE_DST = os.path.join(BASE, "images", "gen1_sprites_alpha")

# 57 = number of symbols in a 7-symbols-per-card Dobble deck. Picked for recognisability and
# for being visually distinct from each other (Dobble is a spot-the-match game). Edit freely.
SELECTION = [
    1, 2, 3,            # Bulbasaur line
    4, 5, 6,            # Charmander line
    7, 8, 9,            # Squirtle line
    25, 26,             # Pikachu, Raichu
    133, 134, 135, 136, # Eevee, Vaporeon, Jolteon, Flareon
    144, 145, 146,      # Articuno, Zapdos, Moltres
    150, 151,           # Mewtwo, Mew
    149,                # Dragonite
    143,                # Snorlax
    92, 93, 94,         # Gastly, Haunter, Gengar
    66, 67, 68,         # Machop, Machoke, Machamp
    29,                 # Nidoran (female)
    142,                # Aerodactyl
    77,                 # Ponyta
    129, 130,           # Magikarp, Gyarados
    131,                # Lapras
    39,                 # Jigglypuff
    54,                 # Psyduck
    79,                 # Slowpoke
    95,                 # Onix
    104,                # Cubone
    132,                # Ditto
    65,                 # Alakazam
    59,                 # Arcanine
    37,                 # Vulpix
    35,                 # Clefairy
    10, 12,             # Caterpie, Butterfree
    74,                 # Geodude
    50,                 # Diglett
    61,                 # Poliwhirl
    123,                # Scyther
    63,                 # Abra
    122,                # Mr. Mime
    113,                # Chansey
]

# Extra symbols that are not Pokemon. They are already transparent and are copied into the output
# folder as-is (trimmed), numbered after 151 so they sort last. SELECTION + EXTRAS must be 57.
IMPORTANT_DIR = os.path.join(BASE, "images", "important")
EXTRAS = {
    "Pokeball.png":    "152_pokeball",
    "PokemonLogo.png": "153_pokemon-logo",
    "TeamRocket.png":  "154_team-rocket",
    "ash-2.png":       "155_ash",
}

WHITE_LEVEL = 245   # min(r,g,b) at or above this is treated as pure background
OPAQUE_LEVEL = 200  # min(r,g,b) at or below this is fully opaque; in between = soft edge

# White background that is fully ENCLOSED by the drawing (e.g. inside Mew's tail loop) cannot be
# told apart from a white body part automatically, so those pockets are listed here as (x, y)
# seed pixels in the original 900px artwork. Each seed is flood-filled like the outer background.
# Found by scanning for enclosed flat-white regions and checking them by eye.
POCKETS = {
    5:   [(506, 558)],                                   # Charmeleon: under the arm
    6:   [(692, 439)],                                   # Charizard: between body and tail
    18:  [(588, 389)],                                   # Pidgeot: between crest and wing
    26:  [(147, 657), (274, 625)],                       # Raichu: tail loop, between legs
    34:  [(389, 196)],                                   # Nidoking: between horn and ear
    52:  [(341, 162), (331, 205)],                       # Meowth: between whiskers
    59:  [(270, 226)],                                   # Arcanine: mane / leg
    65:  [(347, 247)],                                   # Alakazam: under the arm
    67:  [(230, 469)],                                   # Machoke: under the arm
    122: [(124, 153)],                                   # Mr. Mime: between arm and head
    123: [(271, 311), (218, 249)],                        # Scyther: between wing and arm
    125: [(348, 150), (295, 198), (272, 242), (449, 698)],  # Electabuzz: antenna, arm, legs
    130: [(71, 448), (275, 540)],                        # Gyarados: jaw, between neck and body
    144: [(548, 729)],                                   # Articuno: between tail and wing
    145: [(327, 350), (498, 350), (295, 337), (553, 375), (472, 404)],  # Zapdos: between feathers
    150: [(450, 242)],                                   # Mewtwo: between arm and neck
    151: [(152, 339), (705, 393)],                       # Mew: tail loop, under the arm
}


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


def to_transparent(img, trim=True, pockets=()):
    rgb = np.asarray(img.convert("RGB")).astype(np.float32)
    minc = rgb.min(axis=2)

    # Pixels that could be background or a soft edge; flood from the border (and pocket seeds) through them.
    candidate = minc > OPAQUE_LEVEL
    bg = border_connected(candidate, pockets)

    alpha = np.ones_like(minc)
    soft = np.clip((WHITE_LEVEL - minc) / (WHITE_LEVEL - OPAQUE_LEVEL), 0.0, 1.0)
    alpha[bg] = soft[bg]

    # Un-blend the edge colour from white: pixel = a*c + (1-a)*255  ->  c = (pixel - (1-a)*255) / a
    a3 = alpha[..., None]
    safe_a = np.maximum(a3, 1e-3)
    unblended = (rgb - (1.0 - a3) * 255.0) / safe_a
    out_rgb = np.where(a3 > 0, np.clip(unblended, 0, 255), 0)

    out = np.dstack([out_rgb, alpha * 255.0]).round().astype(np.uint8)
    result = Image.fromarray(out, "RGBA")
    if trim:
        bbox = result.getchannel("A").getbbox()
        if bbox:
            result = result.crop(bbox)
    return result


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--all", action="store_true", help="convert all 151 instead of SELECTION")
    ap.add_argument("--no-trim", action="store_true", help="do not crop to the opaque bounding box")
    ap.add_argument("--out", default=DST)
    ap.add_argument("--sprites", action="store_true",
                    help="build the same symbol set from the transparent HOME sprites (images/gen1_png) instead")
    args = ap.parse_args()

    if args.sprites:
        src_dir, ext = SPRITE_SRC, ".png"
        if args.out == DST:
            args.out = SPRITE_DST
    else:
        src_dir, ext = SRC, ".jpg"
    files = sorted(f for f in os.listdir(src_dir) if f.lower().endswith(ext))
    by_num = {int(f[:3]): f for f in files}
    nums = sorted(by_num) if args.all else SELECTION
    missing = [n for n in nums if n not in by_num]
    if missing:
        sys.exit(f"missing images for {missing}; run download_gen1.py --variant artwork (or png for --sprites) first")
    if not args.all and len(set(SELECTION)) + len(EXTRAS) != 57:
        sys.exit(f"SELECTION has {len(set(SELECTION))} unique entries + {len(EXTRAS)} extras, expected 57")

    os.makedirs(args.out, exist_ok=True)
    for n in nums:
        src = os.path.join(src_dir, by_num[n])
        dst = os.path.join(args.out, os.path.splitext(by_num[n])[0] + ".png")
        if args.sprites:   # already transparent: just trim
            img = Image.open(src).convert("RGBA")
            bbox = img.getchannel("A").getbbox()
            if bbox and not args.no_trim:
                img = img.crop(bbox)
            img.save(dst, optimize=True)
        else:
            to_transparent(Image.open(src), trim=not args.no_trim, pockets=POCKETS.get(n, ())).save(dst, optimize=True)
        print("wrote", os.path.relpath(dst, BASE))
    if not args.all:
        for src_name, out_name in EXTRAS.items():
            img = Image.open(os.path.join(IMPORTANT_DIR, src_name)).convert("RGBA")
            bbox = img.getchannel("A").getbbox()
            if bbox and not args.no_trim:
                img = img.crop(bbox)
            dst = os.path.join(args.out, out_name + ".png")
            img.save(dst, optimize=True)
            print("wrote", os.path.relpath(dst, BASE), "(extra, copied)")
    wanted = {os.path.splitext(by_num[n])[0] + ".png" for n in nums}
    if not args.all:
        wanted |= {out_name + ".png" for out_name in EXTRAS.values()}
    for f in os.listdir(args.out):
        if f.endswith(".png") and f not in wanted:
            os.remove(os.path.join(args.out, f)); print("removed stale", f)
    print(f"done: {len(nums) + (0 if args.all else len(EXTRAS))} files in {os.path.relpath(args.out, BASE)}")


if __name__ == "__main__":
    main()
