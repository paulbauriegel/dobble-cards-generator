"""Printable PDFs: the deck (fronts, optionally with mirrored back pages) and blank circle templates."""
import math

from PIL import Image
from reportlab.lib.pagesizes import A3, A4, letter
from reportlab.lib.units import cm, mm
from reportlab.pdfgen import canvas

PAGE_SIZES = {"a4": A4, "a3": A3, "letter": letter}


class PageGrid:
    """Rows and columns of circles of `diameter_cm` centred on a page, with `gap_cm` between them."""

    def __init__(self, page, diameter_cm, margin_cm=1.0, gap_cm=0.5):
        self.page_w, self.page_h = PAGE_SIZES[page.lower()]
        self.diameter, self.margin, self.gap = diameter_cm * cm, margin_cm * cm, gap_cm * cm
        if self.diameter > self.page_w - 2 * self.margin or self.diameter > self.page_h - 2 * self.margin:
            raise ValueError("circle diameter is larger than the printable page area")
        pitch = self.diameter + self.gap
        self.cols = max(1, int((self.page_w - 2 * self.margin + self.gap) // pitch))
        self.rows = max(1, int((self.page_h - 2 * self.margin + self.gap) // pitch))
        self.per_page = self.cols * self.rows
        grid_w = self.cols * self.diameter + (self.cols - 1) * self.gap
        grid_h = self.rows * self.diameter + (self.rows - 1) * self.gap
        self._x0 = (self.page_w - grid_w) / 2                              # left edge of column 0
        self._y0 = self.page_h - (self.page_h - grid_h) / 2 - self.diameter  # bottom edge of row 0 (top row)

    def pages(self, count):
        return math.ceil(count / self.per_page)

    def slot(self, idx, mirrored=False):
        """Lower-left corner of circle `idx` on its page. `mirrored` flips columns for duplex backs."""
        col, row = idx % self.cols, idx // self.cols
        if mirrored:
            col = self.cols - 1 - col
        pitch = self.diameter + self.gap
        return self._x0 + col * pitch, self._y0 - row * pitch

    def centre(self, idx, mirrored=False):
        x, y = self.slot(idx, mirrored)
        return x + self.diameter / 2, y + self.diameter / 2

    def top_left(self, idx, mirrored=False):
        """Top-left corner of circle `idx` in y-down page coordinates (SVG), still in points."""
        x, y = self.slot(idx, mirrored)
        return x, self.page_h - (y + self.diameter)


def write_deck_pdf(card_paths, output, diameter_cm, page, margin_cm=1.0, gap_cm=0.5, line_width=0.25,
                   back=None, mirror_back=True, back_zoom=1.0, back_offset=(0.0, 0.0),
                   back_ring=None, back_ring_mm=2.0):
    """Lay the cards out on pages of `page` size. With `back`, every page of fronts is followed by a
    page with the back image at the same positions (mirrored left/right for long-edge duplex
    printing unless mirror_back is False), so double-sided printing gives every cut card a back.
    `back_offset` shifts everything on the back pages by (right, down) millimetres, to compensate
    a printer whose second side lands a little off the first. `back_ring`, an (r, g, b) colour,
    fills a ring `back_ring_mm` wide around every back's cut circle in place of the stroked circle,
    so a cut that lands a little off shows that colour instead of white paper."""
    g = PageGrid(page, diameter_cm, margin_cm, gap_cm)
    d, r = g.diameter, g.diameter / 2
    off_x, off_y = back_offset[0] * mm, -back_offset[1] * mm   # PDF y grows upwards

    def draw_back(c, x, y):
        """Back image scaled to cover the disc, clipped to the circle, over the optional ring."""
        c.saveState()
        if back_ring:
            c.setFillColorRGB(*(v / 255 for v in back_ring))
            c.circle(x + r, y + r, r + back_ring_mm * mm, stroke=0, fill=1)
        clip = c.beginPath()
        clip.circle(x + r, y + r, r)
        c.clipPath(clip, stroke=0, fill=0)
        bw, bh = back_size
        scale = d / min(bw, bh) * back_zoom
        w, h = bw * scale, bh * scale
        c.drawImage(back, x + (d - w) / 2, y + (d - h) / 2, w, h, mask="auto")
        c.restoreState()
        if not back_ring:                # the ring's edge is the cutting guide
            c.circle(x + r, y + r, r, stroke=1, fill=0)

    if back:
        with Image.open(back) as im:
            back_size = im.size

    c = canvas.Canvas(output, pagesize=(g.page_w, g.page_h))
    c.setTitle("Dobble deck")
    pages = 0
    for start in range(0, len(card_paths), g.per_page):
        chunk = card_paths[start:start + g.per_page]
        c.setLineWidth(line_width)   # hairline cutting guide
        for idx, path in enumerate(chunk):
            x, y = g.slot(idx)
            c.drawImage(path, x, y, d, d, mask="auto")
            c.circle(x + r, y + r, r, stroke=1, fill=0)
        c.showPage()
        pages += 1
        if back:
            c.setLineWidth(line_width)
            for idx in range(len(chunk)):
                x, y = g.slot(idx, mirrored=mirror_back)
                draw_back(c, x + off_x, y + off_y)
            c.showPage()
            pages += 1
    c.save()
    return pages


def write_circles_pdf(output, diameter_cm, count, page="a4", margin_cm=1.0, gap_cm=0.5,
                      line_width=0.5, cut_marks=True):
    """Write `count` empty circles of `diameter_cm` to `output`, paginating as needed.
    Returns (pages, circles per page)."""
    g = PageGrid(page, diameter_cm, margin_cm, gap_cm)
    radius = g.diameter / 2
    c = canvas.Canvas(output, pagesize=(g.page_w, g.page_h))
    c.setTitle("Circles")
    c.setLineWidth(line_width)
    for i in range(count):
        if i > 0 and i % g.per_page == 0:
            c.showPage()
            c.setLineWidth(line_width)
        cx, cy = g.centre(i % g.per_page)
        c.circle(cx, cy, radius, stroke=1, fill=0)
        if cut_marks:
            tick = 3 * mm
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                c.line(cx + dx * radius, cy + dy * radius,
                       cx + dx * (radius + tick), cy + dy * (radius + tick))
    c.save()
    return g.pages(count), g.per_page
