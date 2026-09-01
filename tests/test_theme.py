import json

import pytest

from dobble.theme import list_themes, load_theme


def write_theme(root, name, cfg):
    d = root / name
    d.mkdir()
    (d / "theme.json").write_text(json.dumps(cfg))
    return d


def test_defaults(tmp_path):
    d = write_theme(tmp_path, "plain", {"name": "plain"})
    t = load_theme("plain", tmp_path)
    assert (t.raw_dir, t.extras_dir, t.symbols_dir) == (d / "raw", d / "extras", d / "symbols")
    assert t.raw_ext == "jpg" and t.transparent is False and t.selection is None
    assert t.back is None and t.fetch is None
    assert t.background == {"white_level": 245, "opaque_level": 200}
    assert t.render["base_size"] == 0.40


def test_extends_inherits_and_resolves_paths_against_the_defining_theme(tmp_path):
    base = write_theme(tmp_path, "base", {
        "name": "base", "selection": [1, 2, 3], "extras": {"x.png": "004_x"},
        "pockets": {"2": [[1, 2]]}, "back": "back.jpg",
        "fetch": {"script": "fetch.py", "args": ["--variant", "a"]},
        "render": {"gap": 0.05},
    })
    child = write_theme(tmp_path, "child", {
        "name": "child", "extends": "base", "raw_ext": "png", "transparent": True,
        "extras_dir": "../base/extras",
        "fetch": {"script": "../base/fetch.py", "args": ["--variant", "b"]},
    })
    t = load_theme("child", tmp_path)
    assert t.dir == child and t.raw_dir == child / "raw" and t.symbols_dir == child / "symbols"
    assert t.extras_dir == base / "extras"
    assert t.back == base / "back.jpg"                       # inherited, resolved against base
    assert t.fetch == {"script": base / "fetch.py", "args": ["--variant", "b"]}
    assert t.selection == [1, 2, 3] and t.extras == {"x.png": "004_x"}
    assert t.pockets == {2: [(1, 2)]}
    assert t.raw_ext == "png" and t.transparent is True
    assert t.render == {"base_size": 0.40, "gap": 0.05, "max_rotation": 40}
    assert t.symbol_count == 4


def test_missing_theme_lists_available(tmp_path):
    write_theme(tmp_path, "a", {"name": "a"})
    with pytest.raises(FileNotFoundError, match="available: a"):
        load_theme("nope", tmp_path)
    assert list_themes(tmp_path) == ["a"]


def test_circular_extends(tmp_path):
    write_theme(tmp_path, "a", {"name": "a", "extends": "b"})
    write_theme(tmp_path, "b", {"name": "b", "extends": "a"})
    with pytest.raises(ValueError, match="circular"):
        load_theme("a", tmp_path)
