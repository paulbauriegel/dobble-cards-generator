"""The dinos theme's fetch script: list parsing over paginated pages and PNG conversion."""
import importlib.util
import io
from pathlib import Path

from PIL import Image

SCRIPT = Path(__file__).resolve().parent.parent / "themes" / "dinos" / "fetch.py"
spec = importlib.util.spec_from_file_location("dinos_fetch", SCRIPT)
fetch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fetch)

PAGE = """<div class="search-result-thumb"><a href="/articles/{slug}.php"><img src="https://cdn.example/{slug}.{ext}?class=thumbnail" alt="x"></a></div>"""
NAV = '<a href="?cat=dinosaur&page=1">1</a><a href="?cat=dinosaur&amp;page=2">2</a>'


def test_parse_list_follows_pages_and_dedupes(tmp_path, monkeypatch):
    pages = {
        1: PAGE.format(slug="allosaurus", ext="webp") + PAGE.format(slug="triceratops", ext="png") + NAV,
        2: PAGE.format(slug="triceratops", ext="png") + PAGE.format(slug="velociraptor", ext="jpg") + NAV,
    }
    monkeypatch.setattr(fetch, "get", lambda url: pages[int(url.rsplit("=", 1)[1])].encode())

    entries = fetch.parse_list(str(tmp_path))

    assert entries == [
        ("allosaurus", "https://cdn.example/allosaurus.webp"),
        ("triceratops", "https://cdn.example/triceratops.png"),
        ("velociraptor", "https://cdn.example/velociraptor.jpg"),
    ]
    assert sorted(p.name for p in tmp_path.iterdir()) == ["dinosaur_1.html", "dinosaur_2.html"]
    # second run reads the cache and does not touch the network
    monkeypatch.setattr(fetch, "get", lambda url: (_ for _ in ()).throw(AssertionError("network used")))
    assert fetch.parse_list(str(tmp_path)) == entries


def test_save_png_keeps_alpha_and_converts_opaque_formats(tmp_path):
    buf = io.BytesIO()
    Image.new("RGB", (5, 5), (255, 255, 255)).save(buf, "JPEG")
    fetch.save_png(buf.getvalue(), tmp_path / "opaque.png")
    assert Image.open(tmp_path / "opaque.png").mode == "RGB"

    buf = io.BytesIO()
    Image.new("RGBA", (5, 5), (0, 0, 0, 0)).convert("P").save(buf, "PNG")
    fetch.save_png(buf.getvalue(), tmp_path / "alpha.png")
    out = Image.open(tmp_path / "alpha.png")
    assert out.mode == "RGBA" and out.getpixel((0, 0))[3] == 0
