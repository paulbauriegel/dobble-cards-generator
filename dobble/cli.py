"""Command line entry point (transitional: same flags as the old dobble_cards.py)."""
import argparse
import json
import os
import random
import sys

from PIL import Image

from .packing import shape_factor
from .pdf import write_deck_pdf
from .plane import deck_size, dobble, verify
from .ranks import assign_size_ranks, random_size_ranks
from .render import render_packed, render_ring

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SYMBOL_DIR = os.path.join(BASE, "themes", "pokemon", "symbols")
CARD_DIR = os.path.join(BASE, "out", "pokemon", "cards")
N = 7


def load_symbols(symbol_dir, shuffle_seed=None):
    files = sorted(f for f in os.listdir(symbol_dir) if f.lower().endswith(".png"))
    if len(files) != deck_size(N):
        sys.exit(f"need exactly {deck_size(N)} symbol images in {symbol_dir}, found {len(files)}")
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
                    help="assign images to symbol slots randomly instead of in file order")
    ap.add_argument("--max-rotation", type=float, default=40, help="max rotation of a symbol in degrees")
    ap.add_argument("--border", type=int, default=1, help="grey outline width in the PNG in px, 0 for none")
    ap.add_argument("--base-size", type=float, default=0.40)
    ap.add_argument("--gap", type=float, default=0.015)
    ap.add_argument("--grid", type=int, default=400)
    ap.add_argument("--no-balanced-sizes", action="store_true")
    ap.add_argument("--no-relax", action="store_true")
    ap.add_argument("--gap-slack", type=float, default=0.75)
    ap.add_argument("--min-scale", type=float, default=0.8)
    ap.add_argument("--pdf")
    ap.add_argument("-d", "--diameter", type=float, default=8.5)
    ap.add_argument("--page", default="a4")
    ap.add_argument("--line-width", type=float, default=0.25)
    ap.add_argument("--back")
    ap.add_argument("--back-zoom", type=float, default=1.0)
    ap.add_argument("--pdf-only", action="store_true")
    ap.add_argument("--no-mirror-back", action="store_true")
    ap.add_argument("--verify-only", action="store_true")
    args = ap.parse_args()

    cards = dobble(N)
    print("deck check:", verify(cards, N))
    if args.verify_only:
        return

    if args.pdf_only:
        if not args.pdf:
            sys.exit("--pdf-only needs --pdf")
        card_paths = [os.path.join(args.out, f"card_{i:02d}.png") for i in range(1, len(cards) + 1)]
        missing = [p for p in card_paths if not os.path.exists(p)]
        if missing:
            sys.exit(f"{len(missing)} card PNGs missing in {args.out}; run without --pdf-only first")
        pages = write_deck_pdf(card_paths, args.pdf, args.diameter, args.page, 1.0, 0.5, args.line_width,
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

    os.makedirs(args.out, exist_ok=True)
    card_paths, deck_cards, coverages, gaps = [], [], [], []
    for i, card in enumerate(cards, 1):
        imgs = [images[s] for s in card]
        if args.layout == "packed":
            card_ranks = [ranks[(i - 1, s)] for s in card]
            img, placements, cov, gap = render_packed(
                imgs, card_ranks, args.size, rng, args.grid, args.gap, args.base_size,
                args.max_rotation, args.border, gap_slack=args.gap_slack, relax=not args.no_relax)
        else:
            card_ranks = [None] * len(card)
            img, placements, cov, gap = render_ring(imgs, args.size, rng, args.max_rotation, args.border,
                                                    args.min_scale)
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
        pages = write_deck_pdf(card_paths, args.pdf, args.diameter, args.page, 1.0, 0.5, args.line_width,
                               back=args.back, mirror_back=not args.no_mirror_back, back_zoom=args.back_zoom)
        backs = " with back pages" if args.back else ""
        print(f"wrote {args.pdf} ({pages} pages{backs}, {args.diameter} cm cards)")


if __name__ == "__main__":
    main()
