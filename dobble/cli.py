"""dobble: build printable Dobble decks from a theme's symbol images.

    dobble verify [n]               check the projective-plane construction of order n (default 7)
    dobble fetch <theme>            run the theme's fetch script to download raw images
    dobble prepare <theme>          raw images -> transparent, trimmed PNGs in the theme's symbols folder
    dobble build <theme> [--pdf]    render out/<theme>/cards/card_NN.png + cards.json (+ deck.pdf)
    dobble pdf <theme>              lay out an existing build as out/<theme>/deck.pdf
    dobble svg <theme>              lay out an existing build as editable out/<theme>/svg/page_NN.svg
    dobble circles                  blank circle templates
"""
import argparse
import json
import random
import subprocess
import sys
from pathlib import Path

from PIL import Image

from .imaging import add_outline, to_transparent, trim_alpha
from .packing import shape_factor, shape_reference
from .pdf import write_circles_pdf, write_deck_pdf
from .plane import deck_size, dobble, order_for, verify
from .ranks import assign_size_ranks
from .render import render_packed
from .svg import write_deck_svg
from .theme import DEFAULT_OUTLINE, ROOT, list_themes, load_theme

OUT_ROOT = ROOT / "out"


def rel(path):
    """Path relative to the project root as a posix string, or absolute if outside."""
    path = Path(path).resolve()
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def out_dir(theme, override=None):
    return Path(override).resolve() if override else OUT_ROOT / theme.name


def theme_or_exit(name):
    try:
        return load_theme(name)
    except FileNotFoundError as e:
        sys.exit(str(e))


# ---------------------------------------------------------------- verify
def cmd_verify(args):
    cards = dobble(args.order)
    print("deck check:", verify(cards, args.order))


# ---------------------------------------------------------------- fetch
def cmd_fetch(args):
    t = theme_or_exit(args.theme)
    if not t.fetch:
        sys.exit(f"theme '{t.name}' has no fetch script; put the images into {rel(t.raw_dir)} by hand")
    t.raw_dir.mkdir(parents=True, exist_ok=True)
    cmd = [sys.executable, str(t.fetch["script"]), *t.fetch["args"], "--out", str(t.raw_dir), *args.extra]
    print("running:", " ".join(cmd[1:]))
    sys.exit(subprocess.call(cmd))


# ---------------------------------------------------------------- prepare
def raw_number(path):
    """Leading NNN_ number of a raw file name, or None."""
    stem = path.stem
    return int(stem[:3]) if len(stem) > 3 and stem[:3].isdigit() and stem[3] == "_" else None


def has_transparency(img):
    """True if the image carries an alpha channel with at least one non-opaque pixel."""
    if img.mode == "P" and "transparency" in img.info:
        img = img.convert("RGBA")
    if img.mode not in ("RGBA", "LA"):
        return False
    return img.getchannel("A").getextrema()[0] < 255


def outline_settings(theme, args):
    """Outline parameters for `prepare`, or None: --no-outline wins, --outline overrides the theme's width."""
    if getattr(args, "no_outline", False):
        return None
    width = getattr(args, "outline", None)
    if width is None:
        return dict(theme.outline) if theme.outline else None
    base = theme.outline or {**DEFAULT_OUTLINE, "color": (0, 0, 0)}
    return {**base, "width": width}


def cmd_prepare(args):
    t = theme_or_exit(args.theme)
    files = sorted(t.raw_dir.glob(f"*.{t.raw_ext}"))
    if not files:
        how = f"run `dobble fetch {t.name}`" if t.fetch else "copy the images there"
        sys.exit(f"no *.{t.raw_ext} files in {rel(t.raw_dir)}; {how}")

    if args.all or t.selection is None:
        chosen = files
    else:
        by_num = {raw_number(f): f for f in files if raw_number(f) is not None}
        missing = [n for n in t.selection if n not in by_num]
        if missing:
            sys.exit(f"selection entries without a raw image in {rel(t.raw_dir)}: {missing}")
        chosen = [by_num[n] for n in dict.fromkeys(t.selection)]
    extras = [] if args.all else list(t.extras.items())

    count = len(chosen) + len(extras)
    if args.all:
        print(f"--all: converting every raw image ({count}); the result is not necessarily a valid deck")
    else:
        try:
            n = order_for(count)
        except ValueError as e:
            sys.exit(f"theme '{t.name}': {e}")
        print(f"{len(chosen)} raw images + {len(extras)} extras = {count} symbols: deck of order {n}, "
              f"{n + 1} symbols per card")

    outline = outline_settings(t, args)
    if outline:
        print("outline: {:.1%} of the long side in #{:02x}{:02x}{:02x}".format(outline["width"], *outline["color"]))

    t.symbols_dir.mkdir(parents=True, exist_ok=True)
    wanted = set()
    for src in chosen:
        dst = t.symbols_dir / (src.stem + ".png")
        img = Image.open(src)
        if t.transparent or has_transparency(img):
            img = img.convert("RGBA")
            img = img if args.no_trim else trim_alpha(img)
        else:
            img = to_transparent(img, trim=not args.no_trim,
                                 pockets=t.pockets.get(raw_number(src), ()), **t.background)
        if outline:
            img = add_outline(img, **outline)
        img.save(dst, optimize=True)
        wanted.add(dst.name)
        print("wrote", rel(dst))
    for src_name, stem in extras:
        src = t.extras_dir / src_name
        if not src.exists():
            sys.exit(f"extra '{src_name}' not found in {rel(t.extras_dir)}")
        img = Image.open(src).convert("RGBA")
        img = img if args.no_trim else trim_alpha(img)
        dst = t.symbols_dir / (stem + ".png")
        img.save(dst, optimize=True)
        wanted.add(dst.name)
        print("wrote", rel(dst), "(extra, copied)")
    for f in t.symbols_dir.glob("*.png"):
        if f.name not in wanted:
            f.unlink()
            print("removed stale", f.name)
    print(f"done: {len(wanted)} files in {rel(t.symbols_dir)}")


# ---------------------------------------------------------------- build
def load_symbols(theme, shuffle_seed=None):
    """(names, images, order n) for the theme's symbols folder. Exits if the count is not a deck size."""
    files = sorted(theme.symbols_dir.glob("*.png"))
    if not files:
        sys.exit(f"no symbol PNGs in {rel(theme.symbols_dir)}; run `dobble prepare {theme.name}` first")
    try:
        n = order_for(len(files))
    except ValueError as e:
        sys.exit(f"{rel(theme.symbols_dir)}: {e}")
    if shuffle_seed is not None:
        random.Random(shuffle_seed).shuffle(files)
    names = [f.stem for f in files]
    images = [Image.open(f).convert("RGBA") for f in files]
    return names, images, n


def render_settings(theme, args):
    """Packing parameters: command line flags override the theme's render defaults."""
    r = theme.render
    return dict(grid=args.grid, border=args.border, gap_slack=args.gap_slack, relax=not args.no_relax,
                gap=r["gap"] if args.gap is None else args.gap,
                base_size=r["base_size"] if args.base_size is None else args.base_size,
                max_rotation=r["max_rotation"] if args.max_rotation is None else args.max_rotation)


def write_manifest(path, theme, n, cards, names, factors, results, ranks, size, seed, settings):
    placements = []
    for i, (card, res) in enumerate(zip(cards, results)):
        placements.append({
            "coverage": round(res.coverage, 3), "largest_gap": round(res.largest_gap, 3),
            "symbols": [
                {"symbol": names[s], "rank": ranks[(i, s)], "shape_factor": round(factors[s], 2),
                 "cx": round(cx / size, 4), "cy": round(cy / size, 4),
                 "size": round(sz / size, 4), "rotation": round(angle, 1)}
                for s, (cx, cy, sz, angle) in zip(card, res.placements)]})
    deck = {
        "theme": theme.name, "order": n, "cards": len(cards), "symbols_per_card": n + 1,
        "symbol_dir": rel(theme.symbols_dir), "seed": seed, "card_size_px": size, "settings": settings,
        "symbols": names,
        "cards_by_index": cards,
        "cards_by_name": [[names[s] for s in c] for c in cards],
        "placements": placements,
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(deck, f, indent=1)


def cmd_build(args):
    t = theme_or_exit(args.theme)
    names, images, n = load_symbols(t, args.seed if args.shuffle_symbols else None)
    cards = dobble(n)
    print("deck check:", verify(cards, n))

    rng = random.Random(args.seed)
    ranks = assign_size_ranks(cards, rng)
    ref = shape_reference(images)
    factors = [shape_factor(im, ref) for im in images]
    boosted = sorted(((f, name) for f, name in zip(factors, names) if f > 1.15), reverse=True)
    if boosted:
        print("long-side boost for wide/thin artwork: " + ", ".join(f"{name} x{f:.2f}" for f, name in boosted))
    settings = render_settings(t, args)

    out = out_dir(t, args.out)
    cards_dir = out / "cards"
    cards_dir.mkdir(parents=True, exist_ok=True)
    results = []
    for i, card in enumerate(cards):
        res = render_packed([images[s] for s in card], [ranks[(i, s)] for s in card], args.size, rng,
                            factors=[factors[s] for s in card], **settings)
        res.image.save(cards_dir / f"card_{i + 1:02d}.png")
        res.image = None    # release the pixels: only coverage, gap and placements are needed below
        results.append(res)
        print(f"card {i + 1:02d} ({res.coverage:4.0%} covered, largest gap {res.largest_gap:.3f}): "
              + ", ".join(names[s] for s in card))

    write_manifest(out / "cards.json", t, n, cards, names, factors, results, ranks, args.size, args.seed, settings)
    mean_cov = sum(r.coverage for r in results) / len(results)
    mean_gap = sum(r.largest_gap for r in results) / len(results)
    print(f"wrote {len(cards)} cards and cards.json to {rel(out)}; mean disc coverage {mean_cov:.0%}, "
          f"mean largest empty circle {mean_gap:.3f} of the diameter")
    if args.pdf:
        deck_pdf(t, out, args)
    if getattr(args, "svg", False):
        deck_svg(t, out, args)


# ---------------------------------------------------------------- pdf
def back_image(theme, args):
    """Resolved back image path from the flags and the theme, or None. Exits if it is missing."""
    back = None if args.no_back else (Path(args.back).resolve() if args.back else theme.back)
    if back and not back.exists():
        sys.exit(f"back image not found: {rel(back)}")
    return back


def deck_pdf(theme, out, args):
    paths = sorted((out / "cards").glob("card_*.png"))
    if not paths:
        sys.exit(f"no card PNGs in {rel(out / 'cards')}; run `dobble build {theme.name}` first")
    back = back_image(theme, args)
    zoom = theme.back_zoom if args.back_zoom is None else args.back_zoom
    output = Path(args.output).resolve() if getattr(args, "output", None) else out / "deck.pdf"
    pages = write_deck_pdf([str(p) for p in paths], str(output), args.diameter, args.page,
                           line_width=args.line_width, back=str(back) if back else None,
                           mirror_back=not args.no_mirror_back, back_zoom=zoom,
                           back_offset=tuple(args.back_offset))
    backs = f" with back pages ({rel(back)})" if back else ""
    print(f"wrote {rel(output)} ({pages} pages{backs}, {len(paths)} cards of {args.diameter} cm)")


def cmd_pdf(args):
    t = theme_or_exit(args.theme)
    deck_pdf(t, out_dir(t, args.out), args)


# ---------------------------------------------------------------- svg
def deck_svg(theme, out, args):
    """Editable pages from the manifest: every symbol its own <image>, cut lines on their own layer."""
    manifest_path = out / "cards.json"
    if not manifest_path.exists():
        sys.exit(f"no {rel(manifest_path)}; run `dobble build {theme.name}` first")
    with open(manifest_path, encoding="utf-8") as f:
        manifest = json.load(f)
    back = back_image(theme, args)
    zoom = theme.back_zoom if args.back_zoom is None else args.back_zoom
    svg_dir = Path(args.output).resolve() if getattr(args, "output", None) else out / "svg"
    written = write_deck_svg(manifest, theme.symbols_dir, svg_dir, args.diameter, args.page,
                             line_width=args.line_width, back=back, mirror_back=not args.no_mirror_back,
                             back_zoom=zoom, embed=args.embed, back_offset=tuple(args.back_offset))
    backs = " with back pages" if back else ""
    print(f"wrote {len(written)} SVG pages{backs} to {rel(svg_dir)} ({manifest['cards']} cards of "
          f"{args.diameter} cm, {written[0].name} .. {written[-1].name})")
    if args.embed:
        print("symbol images are embedded; the files are self-contained")
    else:
        print(f"symbol images are linked relative to {rel(theme.symbols_dir)}; use --embed for self-contained files")


def cmd_svg(args):
    t = theme_or_exit(args.theme)
    deck_svg(t, out_dir(t, args.out), args)


# ---------------------------------------------------------------- circles
def cmd_circles(args):
    pages, per_page = write_circles_pdf(args.output, args.diameter, args.count, args.page, args.margin,
                                        args.gap, args.line_width, cut_marks=not args.no_cut_marks)
    print(f"wrote {args.count} circle(s) to {args.output} ({pages} page(s), up to {per_page} per page)")


# ---------------------------------------------------------------- parser
def build_parser():
    ap = argparse.ArgumentParser(prog="dobble", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="command", required=True)
    themes = ", ".join(list_themes()) or "none yet"

    def theme_arg(p):
        p.add_argument("theme", help=f"theme folder under themes/ (available: {themes})")
        p.add_argument("--out", help="output folder (default out/<theme>)")

    pdf_opts = argparse.ArgumentParser(add_help=False)
    pdf_opts.add_argument("-d", "--diameter", type=float, default=8.5, help="card diameter in cm")
    pdf_opts.add_argument("--page", choices=["a4", "a3", "letter"], default="a4")
    pdf_opts.add_argument("--line-width", type=float, default=0.25, help="cutting circle stroke in points")
    pdf_opts.add_argument("--back", help="back image; overrides the theme's")
    pdf_opts.add_argument("--no-back", action="store_true", help="fronts only, no back pages")
    pdf_opts.add_argument("--back-zoom", type=float, help="enlarge the back image so its edge lies outside the cut line")
    pdf_opts.add_argument("--no-mirror-back", action="store_true",
                          help="do not mirror the back pages left/right (short-edge duplex or manual re-feeding)")
    pdf_opts.add_argument("--back-offset", type=float, nargs=2, default=(0.0, 0.0), metavar=("RIGHT", "DOWN"),
                          help="shift the back pages by RIGHT and DOWN millimetres (negative for left/up) to "
                               "compensate a printer whose second side lands off the first; default 0 0")

    p = sub.add_parser("verify", help="check the plane construction")
    p.add_argument("order", type=int, nargs="?", default=7, help="prime order n; deck has n^2+n+1 cards")
    p.set_defaults(func=cmd_verify)

    p = sub.add_parser("fetch", help="download a theme's raw images with its fetch script")
    p.add_argument("theme", help=f"available: {themes}")
    p.add_argument("extra", nargs=argparse.REMAINDER, help="extra arguments passed to the fetch script")
    p.set_defaults(func=cmd_fetch)

    p = sub.add_parser("prepare", help="turn raw images into transparent, trimmed symbol PNGs")
    p.add_argument("theme", help=f"available: {themes}")
    p.add_argument("--all", action="store_true", help="convert every raw image, ignoring the theme's selection")
    p.add_argument("--no-trim", action="store_true", help="keep the original canvas instead of cropping to content")
    p.add_argument("--outline", type=float, metavar="WIDTH",
                   help="stroke the silhouette of every raw symbol (not the extras) with a border this fraction "
                        "of its long side, e.g. 0.025 for a cartoon-style black border (theme default)")
    p.add_argument("--no-outline", action="store_true", help="skip the theme's outline")
    p.set_defaults(func=cmd_prepare)

    p = sub.add_parser("build", parents=[pdf_opts], help="render the cards (and optionally the PDF)")
    theme_arg(p)
    p.add_argument("--size", type=int, default=1200, help="card diameter in pixels")
    p.add_argument("--seed", type=int, default=42, help="random seed for sizes, rotation and placement")
    p.add_argument("--shuffle-symbols", action="store_true",
                   help="assign images to symbol slots randomly instead of in file order")
    p.add_argument("--max-rotation", type=float, help="jitter in degrees around a symbol's random 45-degree base orientation (theme default)")
    p.add_argument("--border", type=int, default=1, help="grey outline width in the PNG in px, 0 for none")
    p.add_argument("--base-size", type=float,
                   help="long side of the largest symbol as a fraction of the card diameter (theme default)")
    p.add_argument("--gap", type=float,
                   help="minimum space between symbols as a fraction of the card diameter (theme default)")
    p.add_argument("--grid", type=int, default=400, help="collision grid resolution in px")
    p.add_argument("--gap-slack", type=float, default=0.75,
                   help="a new symbol goes into a gap at least this fraction as deep as the biggest one")
    p.add_argument("--no-relax", action="store_true", help="skip the relaxation passes that even out the whitespace")
    p.add_argument("--pdf", action="store_true", help="also write out/<theme>/deck.pdf")
    p.add_argument("--svg", action="store_true", help="also write editable out/<theme>/svg/page_NN.svg")
    p.add_argument("--embed", action="store_true", help="with --svg: embed the symbol images instead of linking them")
    p.set_defaults(func=cmd_build)

    p = sub.add_parser("pdf", parents=[pdf_opts], help="lay out an existing build as a printable PDF")
    theme_arg(p)
    p.add_argument("-o", "--output", help="PDF path (default out/<theme>/deck.pdf)")
    p.set_defaults(func=cmd_pdf)

    p = sub.add_parser("svg", parents=[pdf_opts],
                       help="lay out an existing build as editable SVG pages (Inkscape etc.)")
    theme_arg(p)
    p.add_argument("-o", "--output", help="folder for the page SVGs (default out/<theme>/svg)")
    p.add_argument("--embed", action="store_true",
                   help="embed the symbol images (self-contained but large) instead of linking the PNGs")
    p.set_defaults(func=cmd_svg)

    p = sub.add_parser("circles", help="blank circle templates")
    p.add_argument("-o", "--output", default="circles.pdf")
    p.add_argument("-d", "--diameter", type=float, default=8.0, help="circle diameter in cm")
    p.add_argument("-n", "--count", type=int, default=6, help="number of circles")
    p.add_argument("--page", choices=["a4", "a3", "letter"], default="a4")
    p.add_argument("--margin", type=float, default=1.0, help="page margin in cm")
    p.add_argument("--gap", type=float, default=0.5, help="gap between circles in cm")
    p.add_argument("--line-width", type=float, default=0.5, help="stroke width in points")
    p.add_argument("--no-cut-marks", action="store_true")
    p.set_defaults(func=cmd_circles)
    return ap


def main(argv=None):
    args = build_parser().parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
