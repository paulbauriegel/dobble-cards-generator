"""Printable PDFs: the deck (fronts, optionally with mirrored back pages) and blank circle templates."""
import math

from PIL import Image
from reportlab.lib.pagesizes import A3, A4, letter
from reportlab.lib.units import cm, mm
from reportlab.pdfgen import canvas

PAGE_SIZES = {"a4": A4, "a3": A3, "letter": letter}


def write_deck_pdf(card_paths, output, diameter_cm, page, margin_cm, gap_cm, line_width=0.25,
                   back=None, mirror_back=True, back_zoom=1.0):
    """Lay the cards out on pages of `page` size. With `back`, every page of fronts is followed by a
    page with the back image at the same positions (mirrored left/right for long-edge duplex
    printing unless mirror_back is False), so double-sided printing gives every cut card a back."""
    page_w, page_h = PAGE_SIZES[page.lower()]
    diameter, margin, gap = diameter_cm * cm, margin_cm * cm, gap_cm * cm
    cols = max(1, int((page_w - 2 * margin + gap) // (diameter + gap)))
    rows = max(1, int((page_h - 2 * margin + gap) // (diameter + gap)))
    per_page = cols * rows
    grid_w = cols * diameter + (cols - 1) * gap
    grid_h = rows * diameter + (rows - 1) * gap
    x0 = (page_w - grid_w) / 2
    y0 = page_h - (page_h - grid_h) / 2 - diameter

    def slot(idx, mirrored=False):
        col, row = idx % cols, idx // cols
        if mirrored:
            col = cols - 1 - col
        return x0 + col * (diameter + gap), y0 - row * (diameter + gap)

    def draw_back(c, x, y):
        """Back image scaled to cover the disc, clipped to the circle."""
        c.saveState()
        clip = c.beginPath()
        clip.circle(x + diameter / 2, y + diameter / 2, diameter / 2)
        c.clipPath(clip, stroke=0, fill=0)
        bw, bh = back_size
        scale = diameter / min(bw, bh) * back_zoom
        w, h = bw * scale, bh * scale
        c.drawImage(back, x + (diameter - w) / 2, y + (diameter - h) / 2, w, h, mask="auto")
        c.restoreState()
        c.circle(x + diameter / 2, y + diameter / 2, diameter / 2, stroke=1, fill=0)

    if back:
        with Image.open(back) as im:
            back_size = im.size

    c = canvas.Canvas(output, pagesize=(page_w, page_h))
    c.setTitle("Dobble deck")
    pages = 0
    for start in range(0, len(card_paths), per_page):
        chunk = card_paths[start:start + per_page]
        c.setLineWidth(line_width)   # hairline cutting guide
        for idx, path in enumerate(chunk):
            x, y = slot(idx)
            c.drawImage(path, x, y, diameter, diameter, mask="auto")
            c.circle(x + diameter / 2, y + diameter / 2, diameter / 2, stroke=1, fill=0)
        c.showPage()
        pages += 1
        if back:
            c.setLineWidth(line_width)
            for idx in range(len(chunk)):
                x, y = slot(idx, mirrored=mirror_back)
                draw_back(c, x, y)
            c.showPage()
            pages += 1
    c.save()
    return pages


def write_circles_pdf(output, diameter_cm, count, page="a4", margin_cm=1.0,
                      gap_cm=0.5, line_width=0.5, cut_marks=True):
    """Write `count` empty circles of `diameter_cm` to `output`, paginating as needed."""
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
