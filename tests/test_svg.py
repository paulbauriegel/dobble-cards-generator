import re
import xml.etree.ElementTree as ET

import pytest
from PIL import Image

from dobble.pdf import PageGrid
from dobble.svg import PT_TO_MM, write_deck_svg

SVG = "{http://www.w3.org/2000/svg}"
XLINK = "{http://www.w3.org/1999/xlink}"


@pytest.fixture
def deck(tmp_path):
    symbols = tmp_path / "symbols"
    symbols.mkdir()
    Image.new("RGBA", (40, 20), (255, 0, 0, 255)).save(symbols / "wide.png")
    Image.new("RGBA", (30, 30), (0, 255, 0, 255)).save(symbols / "square.png")
    manifest = {
        "symbols": ["wide", "square"], "cards": 7,
        "placements": [{"symbols": [
            {"symbol": "wide", "cx": 0.3, "cy": 0.4, "size": 0.5, "rotation": 30.0},
            {"symbol": "square", "cx": 0.7, "cy": 0.6, "size": 0.25, "rotation": -10.0},
        ]} for _ in range(7)],
    }
    back = tmp_path / "back.png"
    Image.new("RGB", (40, 60), (0, 0, 255)).save(back)
    return manifest, symbols, back


def test_pages_and_geometry(tmp_path, deck):
    manifest, symbols, _ = deck
    out = tmp_path / "svg"
    written = write_deck_svg(manifest, symbols, out, 8.5, "a4")
    assert [p.name for p in written] == ["page_01.svg", "page_02.svg"]

    root = ET.parse(written[0]).getroot()
    assert root.get("viewBox") == "0 0 210 297" and root.get("width") == "210mm"
    cards = root.find(f"{SVG}g[@id='cards']")
    assert len(cards.findall(f"{SVG}g")) == 6
    assert len(cards.findall(f".//{SVG}image")) == 12
    assert len(ET.parse(written[1]).getroot().find(f"{SVG}g[@id='cards']").findall(f"{SVG}g")) == 1
    assert len(root.find(f"{SVG}g[@id='cut-lines']").findall(f"{SVG}circle")) == 6

    d = 85.0
    x0, y0 = (v * PT_TO_MM for v in PageGrid("a4", 8.5).top_left(2))
    card = cards.findall(f"{SVG}g")[2]
    assert card.get("id") == "card-03"
    disc = card.find(f"{SVG}circle")
    assert (float(disc.get("cx")), float(disc.get("cy")), float(disc.get("r"))) == pytest.approx(
        (x0 + d / 2, y0 + d / 2, d / 2), abs=1e-3)
    wide, square = card.findall(f"{SVG}image")
    assert wide.get("id") == "card03-wide"
    assert (float(wide.get("width")), float(wide.get("height"))) == pytest.approx((0.5 * d, 0.25 * d))
    assert (float(wide.get("x")), float(wide.get("y"))) == pytest.approx((-0.25 * d, -0.125 * d))
    tx, ty = x0 + 0.3 * d, y0 + 0.4 * d
    m = re.fullmatch(r"translate\(([\d.-]+) ([\d.-]+)\) rotate\(([\d.-]+)\)", wide.get("transform"))
    assert (float(m[1]), float(m[2]), float(m[3])) == pytest.approx((tx, ty, -30), abs=1e-3)
    assert square.get("transform").endswith("rotate(10)")
    href = wide.get("href")
    assert href == wide.get(f"{XLINK}href") and not href.startswith("data:")
    assert (out / href).resolve() == (symbols / "wide.png").resolve()


def test_embed_and_backs(tmp_path, deck):
    manifest, symbols, back = deck
    out = tmp_path / "svg"
    written = write_deck_svg(manifest, symbols, out, 8.5, "a4", back=back, back_zoom=1.1, embed=True)
    assert [p.name for p in written] == ["page_01.svg", "page_01_back.svg", "page_02.svg", "page_02_back.svg"]

    front = ET.parse(written[0]).getroot()
    assert front.find(f".//{SVG}image").get("href").startswith("data:image/png;base64,")

    back_page = ET.parse(written[1]).getroot()
    uses = back_page.find(f"{SVG}g[@id='backs']").findall(f"{SVG}use")
    clips = back_page.findall(f".//{SVG}clipPath")
    assert len(uses) == 6 and len(clips) == 1 and clips[0].get("id") == "disc"
    assert (clips[0][0].get("cx"), clips[0][0].get("cy"), clips[0][0].get("r")) == ("0", "0", "42.5")
    assert uses[0].get("href") == "#back-image" and uses[0].get("clip-path") == "url(#disc)"
    # the artwork is embedded once, centred on the origin, scaled to cover the disc times the zoom
    images = back_page.findall(f".//{SVG}image")
    assert len(images) == 1 and images[0].get("id") == "back-image"
    w, h = float(images[0].get("width")), float(images[0].get("height"))
    assert (w, h) == pytest.approx((85 * 1.1, 85 * 1.1 * 1.5), abs=1e-3)
    assert (float(images[0].get("x")), float(images[0].get("y"))) == pytest.approx((-w / 2, -h / 2), abs=1e-3)
    # mirrored: back 0 sits where front card 1 sits
    x1, y1 = (v * PT_TO_MM for v in PageGrid("a4", 8.5).top_left(1))
    m = re.fullmatch(r"translate\(([\d.-]+) ([\d.-]+)\)", uses[0].get("transform"))
    assert (float(m[1]), float(m[2])) == pytest.approx((x1 + 42.5, y1 + 42.5), abs=1e-3)
    assert len(ET.parse(written[3]).getroot().find(f"{SVG}g[@id='backs']").findall(f"{SVG}use")) == 1


def test_back_offset_shifts_backs_and_their_cut_lines(tmp_path, deck):
    manifest, symbols, back = deck
    written = write_deck_svg(manifest, symbols, tmp_path / "svg", 8.5, "a4", back=back, back_offset=(1.5, -2.0))
    back_page = ET.parse(written[1]).getroot()
    use = back_page.find(f"{SVG}g[@id='backs']").find(f"{SVG}use")
    m = re.fullmatch(r"translate\(([\d.-]+) ([\d.-]+)\)", use.get("transform"))
    x1, y1 = (v * PT_TO_MM for v in PageGrid("a4", 8.5).top_left(1))
    assert (float(m[1]), float(m[2])) == pytest.approx((x1 + 42.5 + 1.5, y1 + 42.5 - 2.0), abs=1e-3)
    cut = back_page.find(f"{SVG}g[@id='cut-lines']").find(f"{SVG}circle")
    assert (float(cut.get("cx")), float(cut.get("cy"))) == pytest.approx((float(m[1]), float(m[2])), abs=1e-3)
    # the fronts are untouched
    front_cut = ET.parse(written[0]).getroot().find(f"{SVG}g[@id='cut-lines']").find(f"{SVG}circle")
    x0, y0 = (v * PT_TO_MM for v in PageGrid("a4", 8.5).top_left(0))
    assert (float(front_cut.get("cx")), float(front_cut.get("cy"))) == pytest.approx((x0 + 42.5, y0 + 42.5), abs=1e-3)


def test_back_ring_circles_sit_under_the_backs(tmp_path, deck):
    manifest, symbols, back = deck
    written = write_deck_svg(manifest, symbols, tmp_path / "plain", 8.5, "a4", back=back)
    assert ET.parse(written[1]).getroot().find(f"{SVG}g[@id='backs']").findall(f"{SVG}circle") == []

    written = write_deck_svg(manifest, symbols, tmp_path / "ring", 8.5, "a4", back=back,
                             back_ring=(0, 20, 73), back_ring_mm=2.0, back_offset=(1.5, 0.0))
    back_page = ET.parse(written[1]).getroot()
    backs = back_page.find(f"{SVG}g[@id='backs']")
    rings, uses = backs.findall(f"{SVG}circle"), backs.findall(f"{SVG}use")
    # the ring replaces the cut line on the backs; the fronts keep theirs
    assert back_page.find(f"{SVG}g[@id='cut-lines']").findall(f"{SVG}circle") == []
    assert len(ET.parse(written[0]).getroot().find(f"{SVG}g[@id='cut-lines']").findall(f"{SVG}circle")) == 6
    assert len(rings) == len(uses) == 6
    for ring, use in zip(rings, uses):
        assert ring.get("fill") == "#001449" and float(ring.get("r")) == pytest.approx(42.5 + 2.0)
        m = re.fullmatch(r"translate\(([\d.-]+) ([\d.-]+)\)", use.get("transform"))
        assert (float(ring.get("cx")), float(ring.get("cy"))) == pytest.approx((float(m[1]), float(m[2])), abs=1e-3)
        # the ring is drawn before the artwork so the artwork covers it inside the cut line
        assert list(backs).index(ring) < list(backs).index(use)
