# dobble-generator

Generate a printable Dobble (Spot It) deck from any set of symbol images. A deck is a finite
projective plane: with 57 symbols you get 57 round cards of 8 symbols each, and any two cards
share exactly one symbol (see [docs/algorithm.md](docs/algorithm.md)).

Symbol sets are *themes* under `themes/<name>/`. Only the AI-generated **fairytale** sample set
is committed; the other themes document where their images come from.

## Setup

This is a [uv](https://docs.astral.sh/uv/) project. `uv sync` creates `.venv` with the pinned
dependencies from `uv.lock`; every command below runs through `uv run`.

```bash
uv sync
uv run pytest
```

## Usage

```bash
uv run dobble verify 7                 # check the plane construction
uv run dobble prepare fairytale        # the committed sample theme ...
uv run dobble build fairytale --pdf    # ... straight to out/fairytale/deck.pdf
uv run dobble fetch pokemon            # download raw images (theme-specific)
uv run dobble prepare pokemon          # raw images -> transparent, trimmed symbol PNGs
uv run dobble build pokemon --pdf      # render the cards and a printable PDF into out/pokemon/
uv run dobble pdf pokemon              # re-lay out an existing build as PDF
uv run dobble svg pokemon              # the same pages as editable SVGs for Inkscape & co.
uv run dobble circles -d 8 -n 6        # blank circle templates
```

`build` renders `out/<theme>/cards/card_NN.png` and `out/<theme>/cards.json` (which symbol sits
where on every card, plus coverage statistics). `--pdf` or the `pdf` command lay the cards out on
A4 (or A3, Letter) with a cutting circle around each card; if the theme has a back image, every
page of fronts is followed by a mirrored page of backs for long-edge duplex printing. Most
duplex printers land the second side a millimetre or two off the first; if the backs sit
consistently too high, say by 2 mm, `--back-offset 0 2` shifts the back pages down by that much
(`RIGHT DOWN` in millimetres, negative for left/up; off by default). `--back-zoom` hides small
shifts by running the back artwork past the cut line.

### Editable pages (SVG)

`build --svg` or the `svg` command write the same pages as `out/<theme>/svg/page_NN.svg`
(plus `page_NN_back.svg`), one SVG file per sheet in millimetres. Every symbol is its own
`<image>` element, so in Inkscape (or any SVG editor) you can move, resize, rotate, replace or
delete single symbols before printing; each card is a group named after its symbols. The cutting
circles sit on a separate *cut lines* layer that can be hidden. Print an edited page with
*File → Print* or save it as PDF from the editor.

By default the symbol PNGs are *linked* relative to the SVG (`themes/<theme>/symbols/`), which
keeps the files small but means they must stay inside this folder tree. `--embed` writes the
images into the SVG for self-contained files (roughly 20 MB per page for the pokemon theme).

## Themes

A theme is a folder `themes/<name>/` with a `theme.json` and these subfolders:

| folder | content |
|---|---|
| `raw/` | source images, one per symbol, named `NNN_name.<ext>` if you want to use `selection` |
| `extras/` | ready-made transparent PNGs added as symbols (logos, characters) |
| `symbols/` | what `prepare` writes and `build` reads: trimmed, transparent PNGs |

The number of symbols decides the deck: 7, 13, 31, 57 or 133 symbols give 3, 4, 6, 8 or 12
symbols per card (a projective plane of prime order 2, 3, 5, 7 or 11). `prepare` refuses any
other count.

`theme.json` keys, all optional except `name`:

| key | meaning | default |
|---|---|---|
| `extends` | base theme whose keys are inherited; relative paths in inherited keys still point into the base theme's folder | |
| `raw_dir`, `extras_dir`, `symbols_dir` | folders relative to the theme folder | `raw`, `extras`, `symbols` |
| `raw_ext` | extension of the raw files | `jpg` |
| `transparent` | raw files already have an alpha channel, `prepare` only trims them; without it, files that carry real transparency are still only trimmed and the rest get their white background removed | `false` |
| `selection` | numeric prefixes of the raw files to use | all raw files |
| `extras` | `{"file.png": "output_stem"}` copied from `extras_dir` | `{}` |
| `pockets` | `{"NNN": [[x, y], ...]}` seed pixels of white background pockets enclosed by the drawing | `{}` |
| `background` | `white_level` / `opaque_level` thresholds for background removal | 245 / 200 |
| `back`, `back_zoom` | card back image and how much to enlarge it past the cut line | none, 1.0 |
| `fetch` | `{"script": "fetch.py", "args": [...]}`, run by `dobble fetch` with `--out <raw_dir>` | none |
| `render` | defaults for `build`: `base_size`, `gap`, `max_rotation` | 0.40, 0.015, 40 |
| `outline` | `{"width": 0.025, "color": "#000000"}`: `prepare` strokes the silhouette of every raw symbol with a solid border (the extras are copied as they are). `width` is a fraction of the symbol's long side; small sprites are upscaled to `min_size` (600 px) first so the stroke stays round. `prepare --outline WIDTH` / `--no-outline` override it | none |

### Adding a theme

1. Create `themes/<name>/theme.json` with at least `{"name": "<name>"}`.
2. Put the images into `themes/<name>/raw/`. Already transparent PNGs: set `"raw_ext": "png"`
   and `"transparent": true`. White-background photos or artwork: leave `transparent` off and
   `prepare` removes the white connected to the image border; list enclosed white pockets in
   `pockets` if some remain.
3. Make the count come out right: either provide exactly 7, 13, 31, 57 or 133 images, or list
   the ones to use in `selection` and top up with `extras`.
4. Optionally add a back image and point `back` at it.
5. `uv run dobble prepare <name>`, then `uv run dobble build <name> --pdf`.

### Included themes

Only the **fairytale** theme ships with its images; the others have to be fetched or filled
locally because of copyright.

- **fairytale**: 57 fairy-tale motifs (Grimm, Andersen, Perrault and friends) plus a card back,
  all generated with OpenAI's gpt-image-2 in September 2026 and picked by hand from three
  candidates each. They are committed as a sample set, so `uv run dobble prepare fairytale`
  followed by `uv run dobble build fairytale --pdf` works straight after cloning. The prompts,
  the style reference image and the generation script live next to them;
  `dobble fetch fairytale` runs the script to generate candidates for new concepts. See
  [themes/fairytale/README.md](themes/fairytale/README.md) for the AI notice and the workflow.
- **pokemon**: 53 Generation 1 Pokemon (official artwork from pokemondb.net, downloaded by
  `dobble fetch pokemon`) plus four extras that have to be placed into `themes/pokemon/extras/`
  by hand: `Pokeball.png`, `PokemonLogo.png`, `TeamRocket.png`, `ash-2.png`. The back image is
  `themes/pokemon/back.jpg`.
- **pokemon-sprites**: the same selection built from the transparent HOME sprites
  (`dobble fetch pokemon-sprites`). It `extends` pokemon and reuses its extras and back.
- **dinos**: the 28 dinosaur restorations listed on
  [dinosaurs.wiki](https://dinosaurs.wiki/articles_list/dinosaur.php), downloaded by
  `dobble fetch dinos` into `themes/dinos/raw/` as `NNN_<name>.png` in list order. Some are
  transparent already, most sit on a white background, and a few are photos or paintings with a
  scene behind them; `theme.json` selects 13 of the clean ones (a 4-symbol deck of 13 cards).
  To get a 31-symbol deck, extend `selection` with more of the 24 usable numbers and add extras
  (or images from the site's marine and pterosaur lists) until the count is 31. There is no
  back image; add one and point `back` at it if you want double-sided cards.
