import pytest
from reportlab.lib.units import cm

from dobble.pdf import PageGrid, write_circles_pdf, write_deck_pdf


def test_a4_grid_of_8_5cm_cards():
    g = PageGrid("a4", 8.5, margin_cm=1.0, gap_cm=0.5)
    assert (g.cols, g.rows, g.per_page) == (2, 3, 6)
    assert g.pages(57) == 10


def test_slots_are_centred_and_mirroring_swaps_columns():
    g = PageGrid("a4", 8.5)
    x_left, y_top = g.slot(0)
    x_right, _ = g.slot(1)
    assert x_right - x_left == pytest.approx(9.0 * cm)
    assert g.slot(1, mirrored=True) == pytest.approx(g.slot(0))
    # symmetric margins left/right
    assert x_left == pytest.approx(g.page_w - (x_right + g.diameter))
    # first row sits at the top of the page
    assert y_top + g.diameter == pytest.approx(g.page_h - g.slot(g.cols * (g.rows - 1))[1])
    cx, cy = g.centre(0)
    assert (cx, cy) == pytest.approx((x_left + g.diameter / 2, y_top + g.diameter / 2))


def test_too_large_diameter_is_rejected():
    with pytest.raises(ValueError):
        PageGrid("a4", 25)


def test_pdfs_are_written(tmp_path):
    from PIL import Image
    card = tmp_path / "card.png"
    Image.new("RGBA", (50, 50), (255, 0, 0, 255)).save(card)
    back = tmp_path / "back.png"
    Image.new("RGB", (40, 60), (0, 0, 255)).save(back)
    out = tmp_path / "deck.pdf"
    pages = write_deck_pdf([str(card)] * 7, str(out), 8.5, "a4", 1.0, 0.5, back=str(back))
    assert pages == 4 and out.stat().st_size > 0
    pages, per_page = write_circles_pdf(str(tmp_path / "c.pdf"), 8.0, 10)
    assert (pages, per_page) == (2, 6)


def test_back_offset_shifts_only_the_back_pages(tmp_path, monkeypatch):
    from PIL import Image
    from reportlab.lib.units import mm
    from reportlab.pdfgen.canvas import Canvas
    card = tmp_path / "card.png"
    Image.new("RGBA", (50, 50), (255, 0, 0, 255)).save(card)
    back = tmp_path / "back.png"
    Image.new("RGB", (60, 60), (0, 0, 255)).save(back)
    draws = []
    monkeypatch.setattr(Canvas, "drawImage", lambda self, path, x, y, w, h, **kw: draws.append((path, x, y)))

    write_deck_pdf([str(card)] * 2, str(tmp_path / "deck.pdf"), 8.5, "a4", back=str(back))
    write_deck_pdf([str(card)] * 2, str(tmp_path / "deck2.pdf"), 8.5, "a4", back=str(back), back_offset=(1.5, -2.0))
    fronts = [d for d in draws if d[0] == str(card)]
    backs = [d for d in draws if d[0] == str(back)]
    assert fronts[:2] == pytest.approx(fronts[2:])                      # fronts never move
    assert backs[2][1] == pytest.approx(backs[0][1] + 1.5 * mm)        # right
    assert backs[2][2] == pytest.approx(backs[0][2] + 2.0 * mm)        # negative DOWN = up = +y in PDF space
