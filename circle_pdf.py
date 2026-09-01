#!/usr/bin/env python3
"""Generate a PDF filled with circles (e.g. blank Dobble-style card templates).

Usage examples:
    python circle_pdf.py                       # A4, 8 cm circles, circles.pdf
    python circle_pdf.py -d 9 -o cards.pdf     # 9 cm circles
    python circle_pdf.py -n 20 --page letter   # 20 circles on US Letter pages
"""

import argparse
import math

from reportlab.lib.pagesizes import A4, A3, letter
from reportlab.lib.units import cm, mm
from reportlab.pdfgen import canvas

PAGE_SIZES = {"a4": A4, "a3": A3, "letter": letter}


def draw_circles(output, diameter_cm, count, page="a4", margin_cm=1.0,
                 gap_cm=0.5, line_width=0.5, cut_marks=True):
    """Write `count` circles of `diameter_cm` to `output`, paginating as needed."""
    page_w, page_h = PAGE_SIZES[page.lower()]
    diameter = diameter_cm * cm
    radius = diameter / 2
    margin = margin_cm * cm
    gap = gap_cm * cm

    # How many circles fit per row/column.
    cols = max(1, int((page_w - 2 * margin + gap) // (diameter + gap)))
    rows = max(1, int((page_h - 2 * margin + gap) // (diameter + gap)))
    per_page = cols * rows

    if diameter > page_w - 2 * margin or diameter > page_h - 2 * margin:
        raise ValueError("Circle diameter is larger than the printable page area.")

    # Centre the grid on the page.
    grid_w = cols * diameter + (cols - 1) * gap
    grid_h = rows * diameter + (rows - 1) * gap
    x0 = (page_w - grid_w) / 2 + radius
    y0 = page_h - (page_h - grid_h) / 2 - radius

    c = canvas.Canvas(output, pagesize=(page_w, page_h))
    c.setTitle("Circles")
    c.setLineWidth(line_width)

    for i in range(count):
        if i > 0 and i % per_page == 0:
            c.showPage()
            c.setLineWidth(line_width)
        idx = i % per_page
        col, row = idx % cols, idx // cols
        cx = x0 + col * (diameter + gap)
        cy = y0 - row * (diameter + gap)
        c.circle(cx, cy, radius, stroke=1, fill=0)
        if cut_marks:
            tick = 3 * mm
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                c.line(cx + dx * radius, cy + dy * radius,
                       cx + dx * (radius + tick), cy + dy * (radius + tick))

    c.save()
    pages = math.ceil(count / per_page)
    return pages, per_page


def main():
    p = argparse.ArgumentParser(description="Create a PDF of printable circles.")
    p.add_argument("-o", "--output", default="circles.pdf", help="output PDF path")
    p.add_argument("-d", "--diameter", type=float, default=8.0, help="circle diameter in cm")
    p.add_argument("-n", "--count", type=int, default=6, help="number of circles")
    p.add_argument("--page", choices=PAGE_SIZES, default="a4", help="page size")
    p.add_argument("--margin", type=float, default=1.0, help="page margin in cm")
    p.add_argument("--gap", type=float, default=0.5, help="gap between circles in cm")
    p.add_argument("--line-width", type=float, default=0.5, help="stroke width in points")
    p.add_argument("--no-cut-marks", action="store_true", help="omit the small cut marks")
    args = p.parse_args()

    pages, per_page = draw_circles(
        args.output, args.diameter, args.count, args.page, args.margin,
        args.gap, args.line_width, cut_marks=not args.no_cut_marks,
    )
    print(f"Wrote {args.count} circle(s) to {args.output} "
          f"({pages} page(s), up to {per_page} per page).")


if __name__ == "__main__":
    main()
