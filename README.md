# dobble-generator

Generate a printable Dobble (Spot It) deck from any set of symbol images. A deck is a finite
projective plane: with 57 symbols you get 57 round cards of 8 symbols each, and any two cards
share exactly one symbol (see [docs/algorithm.md](docs/algorithm.md)).

Symbol sets are *themes* under `themes/<name>/`. Images are not committed to this repository;
each theme documents where its images come from.

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
uv run dobble fetch pokemon            # download raw images (theme-specific)
uv run dobble prepare pokemon          # raw images -> transparent, trimmed symbol PNGs
uv run dobble build pokemon --pdf      # render the cards and a printable PDF into out/pokemon/
uv run dobble pdf pokemon              # re-lay out an existing build as PDF
uv run dobble circles -d 8 -n 6        # blank circle templates
```

`build` renders `out/<theme>/cards/card_NN.png` and `out/<theme>/cards.json` (which symbol sits
where on every card, plus coverage statistics). `--pdf` or the `pdf` command lay the cards out on
A4 (or A3, Letter) with a cutting circle around each card; if the theme has a back image, every
page of fronts is followed by a mirrored page of backs for long-edge duplex printing.

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
| `transparent` | raw files already have an alpha channel, `prepare` only trims them | `false` |
| `selection` | numeric prefixes of the raw files to use | all raw files |
| `extras` | `{"file.png": "output_stem"}` copied from `extras_dir` | `{}` |
| `pockets` | `{"NNN": [[x, y], ...]}` seed pixels of white background pockets enclosed by the drawing | `{}` |
| `background` | `white_level` / `opaque_level` thresholds for background removal | 245 / 200 |
| `back`, `back_zoom` | card back image and how much to enlarge it past the cut line | none, 1.0 |
| `fetch` | `{"script": "fetch.py", "args": [...]}`, run by `dobble fetch` with `--out <raw_dir>` | none |
| `render` | defaults for `build`: `base_size`, `gap`, `max_rotation` | 0.40, 0.015, 40 |

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

No images are committed to this repository (copyright). Each theme has to be fetched or
filled locally.

- **pokemon**: 53 Generation 1 Pokemon (official artwork from pokemondb.net, downloaded by
  `dobble fetch pokemon`) plus four extras that have to be placed into `themes/pokemon/extras/`
  by hand: `Pokeball.png`, `PokemonLogo.png`, `TeamRocket.png`, `ash-2.png`. The back image is
  `themes/pokemon/back.jpg`.
- **pokemon-sprites**: the same selection built from the transparent HOME sprites
  (`dobble fetch pokemon-sprites`). It `extends` pokemon and reuses its extras and back.
- **dinos**: scaffold only. Drop transparent PNGs into `themes/dinos/raw/` (7, 13, 31 or 57 of
  them), add `themes/dinos/back.png`, then `prepare` and `build`.
