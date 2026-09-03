import argparse
import io
import json

from PIL import Image, ImageDraw

from dobble import cli
from dobble.theme import load_theme


def test_build_writes_cards_and_manifest_and_releases_images(tmp_path, monkeypatch):
    theme_dir = tmp_path / "themes" / "blobs"
    (theme_dir / "symbols").mkdir(parents=True)
    (theme_dir / "theme.json").write_text(json.dumps({"name": "blobs"}))
    for i in range(7):                                   # order 2: 7 symbols, 7 cards of 3
        img = Image.new("RGBA", (60 + 10 * i, 60), (0, 0, 0, 0))
        ImageDraw.Draw(img).ellipse((0, 0, img.width - 1, 59), fill=(30 * i, 90, 120, 255))
        img.save(theme_dir / "symbols" / f"{i:03d}_blob.png")
    monkeypatch.setattr(cli, "load_theme", lambda name: load_theme(name, tmp_path / "themes"))

    rendered = []
    real_render = cli.render_packed

    def spy(*a, **k):
        res = real_render(*a, **k)
        rendered.append(res)
        return res

    monkeypatch.setattr(cli, "render_packed", spy)
    out = tmp_path / "out"
    args = argparse.Namespace(theme="blobs", seed=1, shuffle_symbols=False, size=200, grid=100, border=1,
                              gap_slack=0.75, no_relax=False, gap=None, base_size=None, max_rotation=None,
                              out=str(out), pdf=False)
    cli.cmd_build(args)

    assert sorted(p.name for p in (out / "cards").glob("*.png")) == [f"card_{i:02d}.png" for i in range(1, 8)]
    assert len(rendered) == 7 and all(r.image is None for r in rendered)   # pixels dropped after saving
    deck = json.loads((out / "cards.json").read_text())
    assert deck["order"] == 2 and deck["cards"] == 7 and len(deck["placements"]) == 7
    for card, entry in zip(deck["cards_by_index"], deck["placements"]):
        assert 0 < entry["coverage"] < 1 and 0 < entry["largest_gap"] < 1
        assert len(entry["symbols"]) == 3 == len(card)
        for s in entry["symbols"]:
            assert {"symbol", "rank", "shape_factor", "cx", "cy", "size", "rotation"} <= s.keys()


def test_prepare_keeps_alpha_of_transparent_raw_files_and_strips_white_from_the_rest(tmp_path, monkeypatch):
    theme_dir = tmp_path / "themes" / "mixed"
    (theme_dir / "raw").mkdir(parents=True)
    (theme_dir / "theme.json").write_text(json.dumps({"name": "mixed", "raw_ext": "png"}))
    # 001: white-background artwork, 002: already transparent (alpha channel with holes) -- 7 files for a valid deck
    for i in range(1, 8):
        if i % 2:
            img = Image.new("RGB", (80, 80), (255, 255, 255))
            ImageDraw.Draw(img).rectangle((20, 20, 59, 59), fill=(200, 30, 30))
        else:
            img = Image.new("RGBA", (80, 80), (0, 0, 0, 0))
            ImageDraw.Draw(img).rectangle((10, 10, 49, 49), fill=(30, 30, 200, 255))
        img.save(theme_dir / "raw" / f"{i:03d}_x.png")
    monkeypatch.setattr(cli, "load_theme", lambda name: load_theme(name, tmp_path / "themes"))

    cli.cmd_prepare(argparse.Namespace(theme="mixed", all=False, no_trim=False, no_outline=True, outline=None))

    white = Image.open(theme_dir / "symbols" / "001_x.png")
    assert white.mode == "RGBA" and white.size == (40, 40) and white.getpixel((0, 0)) == (200, 30, 30, 255)
    alpha = Image.open(theme_dir / "symbols" / "002_x.png")
    assert alpha.size == (40, 40) and alpha.getpixel((0, 0)) == (30, 30, 200, 255)


def test_has_transparency():
    assert not cli.has_transparency(Image.new("RGB", (4, 4), (255, 255, 255)))
    assert not cli.has_transparency(Image.new("RGBA", (4, 4), (0, 0, 0, 255)))
    assert cli.has_transparency(Image.new("RGBA", (4, 4), (0, 0, 0, 0)))
    buf = io.BytesIO()
    Image.new("RGBA", (4, 4), (0, 0, 0, 0)).convert("P").save(buf, "PNG")   # palette PNG with tRNS
    pal = Image.open(io.BytesIO(buf.getvalue()))
    assert pal.mode == "P" and cli.has_transparency(pal)
