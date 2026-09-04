"""A theme is a folder under themes/ with a theme.json and the images for one symbol set.

theme.json keys (all optional except name):
  extends       name of a base theme whose keys are inherited
  raw_dir       folder with the downloaded/hand-collected source images   (default "raw")
  extras_dir    folder with ready-made transparent PNGs added as symbols    (default "extras")
  symbols_dir   folder that `prepare` writes and `build` reads             (default "symbols")
  raw_ext       extension of the raw files                                  (default "jpg")
  transparent   raw files already have an alpha channel: only trim them     (default false)
  selection     numeric prefixes (NNN_) of the raw files to use; absent = all raw files
  extras        {file in extras_dir: output stem}, e.g. {"Pokeball.png": "152_pokeball"}
  pockets       {"NNN": [[x, y], ...]} seed pixels of enclosed white pockets for background removal
  background    {"white_level": 245, "opaque_level": 200}
  back          card back image, relative to the theme folder
  back_zoom     enlarge the back image so its edge lies outside the cut line (default 1.0)
  fetch         {"script": "fetch.py", "args": [...]} run by `dobble fetch` with --out <raw_dir>
  render        default build settings: base_size, gap, max_rotation (jitter in degrees on top
                of each symbol's random 45-degree base orientation)
  outline       {"width": 0.025, "color": "#000000", "min_size": 600}: `prepare` strokes the
                silhouette of every raw symbol (not the extras) with a solid border; absent = none
  back_ring     {"color": "#rrggbb", "width": 2.0}: colour and width (mm outside the cut line)
                of the filled ring that `--back-ring` draws around the cut circle on the back
                pages in place of the cut line, so a slightly misaligned back shows colour
                instead of white paper after cutting; a plain "#rrggbb" string is a shorthand

Relative paths resolve against the folder of the theme.json that defines them, so an inherited
`back` still points into the base theme's folder.
"""
import json
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
THEMES_ROOT = ROOT / "themes"

DEFAULT_BACKGROUND = {"white_level": 245, "opaque_level": 200}
DEFAULT_RENDER = {"base_size": 0.40, "gap": 0.015, "max_rotation": 40}
DEFAULT_OUTLINE = {"width": 0.025, "color": "#000000", "min_size": 600}
DEFAULT_BACK_RING = {"color": "#000000", "width": 2.0}


@dataclass
class Theme:
    name: str
    dir: Path
    raw_dir: Path
    extras_dir: Path
    symbols_dir: Path
    raw_ext: str = "jpg"
    transparent: bool = False
    selection: list | None = None
    extras: dict = field(default_factory=dict)
    pockets: dict = field(default_factory=dict)          # int -> [(x, y), ...]
    background: dict = field(default_factory=lambda: dict(DEFAULT_BACKGROUND))
    back: Path | None = None
    back_zoom: float = 1.0
    fetch: dict | None = None                           # {"script": Path, "args": [...]}
    render: dict = field(default_factory=lambda: dict(DEFAULT_RENDER))
    outline: dict | None = None                         # {"width", "color" as (r, g, b), "min_size"}
    back_ring: dict | None = None                       # {"color" as (r, g, b), "width" in mm}

    @property
    def symbol_count(self):
        """Number of symbols `prepare` will produce (raw selection + extras)."""
        if self.selection is not None:
            n = len(set(self.selection))
        else:
            n = len(list(self.raw_dir.glob(f"*.{self.raw_ext}")))
        return n + len(self.extras)


def parse_color(c):
    """'#rgb', '#rrggbb' or an [r, g, b] list -> (r, g, b)."""
    if isinstance(c, str):
        h = c.lstrip("#")
        if len(h) == 3:
            h = "".join(ch * 2 for ch in h)
        if len(h) != 6:
            raise ValueError(f"bad colour {c!r}: expected #rrggbb")
        return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
    r, g, b = c
    return (int(r), int(g), int(b))


def hex_color(rgb):
    """(r, g, b) -> '#rrggbb'."""
    return "#%02x%02x%02x" % tuple(int(v) for v in rgb)


def _read(name, root):
    d = Path(root) / name
    path = d / "theme.json"
    if not path.exists():
        available = ", ".join(sorted(p.parent.name for p in Path(root).glob("*/theme.json"))) or "none"
        raise FileNotFoundError(f"no theme '{name}' in {root} (available: {available})")
    with open(path, encoding="utf-8") as f:
        return d, json.load(f)


def load_theme(name, root=THEMES_ROOT):
    """Load themes/<name>/theme.json, following `extends`, and resolve all paths."""
    chain = []
    d, cfg = _read(name, root)
    chain.append((d, cfg))
    seen = {name}
    while cfg.get("extends"):
        base = cfg["extends"]
        if base in seen:
            raise ValueError(f"theme '{name}': circular extends via '{base}'")
        seen.add(base)
        d, cfg = _read(base, root)
        chain.append((d, cfg))

    merged = {}                               # key -> (value, folder that defined it)
    for d, cfg in reversed(chain):
        for k, v in cfg.items():
            if k not in ("extends", "name"):
                merged[k] = (v, d)

    own = chain[0][0]

    def value(key, default=None):
        return merged[key][0] if key in merged else default

    def path(key, default=None):
        if key in merged:
            v, d = merged[key]
            return (d / v).resolve() if v is not None else None
        return (own / default).resolve() if default is not None else None

    outline = value("outline")
    if outline is not None and outline is not False:
        outline = {**DEFAULT_OUTLINE, **(outline if isinstance(outline, dict) else {})}
        outline["color"] = parse_color(outline["color"])
    else:
        outline = None

    back_ring = value("back_ring")
    if back_ring is not None and back_ring is not False:
        if not isinstance(back_ring, dict):
            back_ring = {"color": back_ring}
        back_ring = {**DEFAULT_BACK_RING, **back_ring}
        back_ring = {"color": parse_color(back_ring["color"]), "width": float(back_ring["width"])}
    else:
        back_ring = None

    fetch = value("fetch")
    if fetch:
        d = merged["fetch"][1]
        fetch = {"script": (d / fetch["script"]).resolve(), "args": list(fetch.get("args", []))}

    return Theme(
        name=name,
        dir=own.resolve(),
        raw_dir=path("raw_dir", "raw"),
        extras_dir=path("extras_dir", "extras"),
        symbols_dir=path("symbols_dir", "symbols"),
        raw_ext=value("raw_ext", "jpg").lstrip("."),
        transparent=bool(value("transparent", False)),
        selection=value("selection"),
        extras=dict(value("extras", {})),
        pockets={int(k): [tuple(p) for p in v] for k, v in value("pockets", {}).items()},
        background={**DEFAULT_BACKGROUND, **value("background", {})},
        back=path("back"),
        back_zoom=float(value("back_zoom", 1.0)),
        fetch=fetch,
        render={**DEFAULT_RENDER, **value("render", {})},
        outline=outline,
        back_ring=back_ring,
    )


def list_themes(root=THEMES_ROOT):
    return sorted(p.parent.name for p in Path(root).glob("*/theme.json"))
