"""Editable pages: one SVG per page with every symbol as its own <image>, for Inkscape & co.

The page is laid out with the same PageGrid as the PDF, in millimetres (viewBox units = mm), and
every symbol is placed from the cards.json manifest with `translate(cx cy) rotate(a)`, so it can
be moved, resized, rotated or swapped afterwards. Cut lines sit on their own layer.
"""
import base64
import os
import xml.etree.ElementTree as ET
from pathlib import Path

from PIL import Image

from .pdf import PageGrid
from .theme import hex_color

PT_TO_MM = 25.4 / 72
SVG_NS = "http://www.w3.org/2000/svg"
XLINK_NS = "http://www.w3.org/1999/xlink"
INKSCAPE_NS = "http://www.inkscape.org/namespaces/inkscape"

ET.register_namespace("", SVG_NS)
ET.register_namespace("xlink", XLINK_NS)
ET.register_namespace("inkscape", INKSCAPE_NS)


def _f(x):
    """Compact number formatting: 3 decimals, no trailing zeros."""
    return f"{x:.3f}".rstrip("0").rstrip(".") or "0"


def _href(path, svg_dir, embed):
    """Relative link to `path` from `svg_dir`, an absolute file URI if no relative path exists,
    or a base64 data URI with `embed`."""
    path = Path(path).resolve()
    if embed:
        data = base64.b64encode(path.read_bytes()).decode("ascii")
        mime = "image/jpeg" if path.suffix.lower() in (".jpg", ".jpeg") else "image/png"
        return f"data:{mime};base64,{data}"
    try:
        return Path(os.path.relpath(path, Path(svg_dir).resolve())).as_posix()
    except ValueError:             # different drive on Windows
        return path.as_uri()


def _image(parent, href, x, y, w, h, **attrs):
    el = ET.SubElement(parent, "image", x=_f(x), y=_f(y), width=_f(w), height=_f(h),
                       preserveAspectRatio="none", **attrs)
    el.set("href", href)
    el.set(f"{{{XLINK_NS}}}href", href)
    return el


def _layer(root, id_, label):
    g = ET.SubElement(root, "g", id=id_)
    g.set(f"{{{INKSCAPE_NS}}}groupmode", "layer")
    g.set(f"{{{INKSCAPE_NS}}}label", label)
    return g


def _page(g):
    w, h = g.page_w * PT_TO_MM, g.page_h * PT_TO_MM
    return ET.Element("svg", xmlns=SVG_NS, width=f"{_f(w)}mm", height=f"{_f(h)}mm",
                      viewBox=f"0 0 {_f(w)} {_f(h)}")


def _write(root, path):
    tree = ET.ElementTree(root)
    ET.indent(tree, space=" ")
    tree.write(path, encoding="utf-8", xml_declaration=True)


def write_deck_svg(manifest, symbols_dir, out_dir, diameter_cm, page, margin_cm=1.0, gap_cm=0.5,
                   line_width=0.25, back=None, mirror_back=True, back_zoom=1.0, embed=False,
                   back_offset=(0.0, 0.0), back_ring=None, back_ring_mm=2.0):
    """Write page_NN.svg (and page_NN_back.svg with `back`) into `out_dir` from a cards.json
    `manifest` and the PNGs in `symbols_dir`. `back_offset` shifts the back pages by (right, down)
    millimetres for printers whose second side lands off the first; `back_ring`, an (r, g, b)
    colour, fills a ring `back_ring_mm` wide around every back's cut circle in place of the cut line.
    Returns the written paths."""
    g = PageGrid(page, diameter_cm, margin_cm, gap_cm)
    d = g.diameter * PT_TO_MM
    r = d / 2
    stroke = _f(line_width * PT_TO_MM)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    symbols_dir = Path(symbols_dir)
    names = manifest["symbols"]
    placements = manifest["placements"]

    sizes, hrefs = {}, {}

    def symbol(name):
        if name not in sizes:
            path = symbols_dir / f"{name}.png"
            with Image.open(path) as im:
                sizes[name] = im.size
            hrefs[name] = _href(path, out_dir, embed)
        return sizes[name], hrefs[name]

    if back:
        back = Path(back)
        with Image.open(back) as im:
            back_size = im.size
        back_href = _href(back, out_dir, embed)

    def cut_circle(layer, cx, cy):
        ET.SubElement(layer, "circle", cx=_f(cx), cy=_f(cy), r=_f(r), fill="none", stroke="#000000",
                      **{"stroke-width": stroke})

    def front_page(pageno, first):
        root = _page(g)
        cards = _layer(root, "cards", "cards")
        cuts = _layer(root, "cut-lines", "cut lines")
        for idx, card_no in enumerate(range(first, min(first + g.per_page, len(placements)))):
            x0, y0 = (v * PT_TO_MM for v in g.top_left(idx))
            syms = placements[card_no]["symbols"]
            card = ET.SubElement(cards, "g", id=f"card-{card_no + 1:02d}")
            card.set(f"{{{INKSCAPE_NS}}}label",
                     f"card {card_no + 1:02d}: " + ", ".join(s["symbol"] for s in syms))
            ET.SubElement(card, "circle", cx=_f(x0 + r), cy=_f(y0 + r), r=_f(r), fill="#ffffff")
            for s in syms:
                (pw, ph), href = symbol(s["symbol"])
                long_side = s["size"] * d
                w, h = pw / max(pw, ph) * long_side, ph / max(pw, ph) * long_side
                cx, cy = x0 + s["cx"] * d, y0 + s["cy"] * d
                # PIL rotates counter-clockwise, SVG (y down) clockwise; normalised to (-180, 180]
                angle = (-s["rotation"] + 180) % 360 - 180
                transform = f"translate({_f(cx)} {_f(cy)}) rotate({_f(angle)})"
                _image(card, href, -w / 2, -h / 2, w, h, id=f"card{card_no + 1:02d}-{s['symbol']}",
                       transform=transform)
            cut_circle(cuts, x0 + r, y0 + r)
        path = out_dir / f"page_{pageno:02d}.svg"
        _write(root, path)
        return path

    def back_page(pageno, count):
        root = _page(g)
        defs = ET.SubElement(root, "defs")
        backs = _layer(root, "backs", "backs")
        cuts = _layer(root, "cut-lines", "cut lines")
        bw, bh = back_size
        scale = d / min(bw, bh) * back_zoom
        w, h = bw * scale, bh * scale
        # the back artwork once, centred on the origin, and a disc clip in the same local space;
        # every slot is a translated <use> of it (clip-path applies inside the use's transform)
        _image(defs, back_href, -w / 2, -h / 2, w, h, id="back-image")
        clip = ET.SubElement(defs, "clipPath", id="disc")
        ET.SubElement(clip, "circle", cx="0", cy="0", r=_f(r))
        for idx in range(count):
            x0, y0 = (v * PT_TO_MM for v in g.top_left(idx, mirrored=mirror_back))
            cx, cy = x0 + r + back_offset[0], y0 + r + back_offset[1]
            if back_ring:
                ET.SubElement(backs, "circle", id=f"back-ring-{idx}", cx=_f(cx), cy=_f(cy),
                              r=_f(r + back_ring_mm), fill=hex_color(back_ring))
            use = ET.SubElement(backs, "use", id=f"back-{idx}", transform=f"translate({_f(cx)} {_f(cy)})")
            use.set("href", "#back-image")
            use.set(f"{{{XLINK_NS}}}href", "#back-image")
            use.set("clip-path", "url(#disc)")
            if not back_ring:            # the ring's edge is the cutting guide
                cut_circle(cuts, cx, cy)
        path = out_dir / f"page_{pageno:02d}_back.svg"
        _write(root, path)
        return path

    written = []
    for pageno, first in enumerate(range(0, len(placements), g.per_page), start=1):
        written.append(front_page(pageno, first))
        if back:
            written.append(back_page(pageno, min(g.per_page, len(placements) - first)))
    return written
