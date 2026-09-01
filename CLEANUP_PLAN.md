# Cleanup and refactor plan

Goal: turn the Pokemon-only scripts into a small, theme-agnostic Dobble deck generator
where a theme (Pokemon, dinos, anything else) is data plus at most one theme-specific
fetch script, and every other piece of code is shared.

## 1. What is here today

| File | Role | Verdict |
|---|---|---|
| `dobble_cards.py` (700 lines) | plane construction, size ranks, packing, rendering, PDF, CLI | keep, split into modules |
| `make_transparent.py` | white-background removal; hard-codes the 57-Pokemon selection, pockets and extras | keep algorithm, move data into theme config |
| `download_gen1.py` | pokemondb.net scraper | keep as the Pokemon theme's fetch script |
| `circle_pdf.py` | blank-circle template PDF; `dobble_cards.write_pdf` only imports `PAGE_SIZES` from it and re-implements its grid math | merge grid math into one PDF module, keep circles as a subcommand |
| `algorithm.md` | projective-plane explanation | keep, move to `docs/` |
| `national.html` (600 KB) | scraped page cache | delete, gitignore, re-fetched on demand |
| `pokemon-ash-clipart-...png` (root) | same 215 040 bytes as `images/important/ash-2.png` | delete |
| `images/important/ash.png` | not referenced (EXTRAS uses `ash-2.png`) | keep anyway |
| `images/gen1/` (151 white-bg JPG sprites) | the default download variant, never read by any script | delete, keep the spite variant still|
| `cards.pdf`, `circles.pdf` | early experiments | delete |
| `deck.pdf`, `deck_sprites.pdf` (67 MB each) | build outputs | move to `out/`, gitignore |
| `images/cards/`, `images/cards_sprites/` | build outputs | move to `out/`, gitignore |
| `images/back/` | three unnamed back candidates | keep one per theme, named in the theme config |
| `__pycache__/` | | delete, gitignore |
| no git, no `.gitignore`, no `requirements.txt`, no README | | add |

Code smells inside `dobble_cards.py`:

- `N = 7` is a module constant. The plane order should come from the number of symbol images
  (57 -> 7, 31 -> 5, 13 -> 3) so a smaller dino set works without editing code.
- "Pokemon" appears in the docstring, help text and log lines of otherwise generic code.
- `SHAPE_REF = 0.43` is "the median of the Gen 1 artwork". It should be computed from the loaded
  symbol set so a theme with different artwork proportions behaves the same.
- `shape_factor()` is recomputed for every symbol on every card (8 x 57 times) instead of once.
- `write_pdf` and `circle_pdf.draw_circles` both compute the page grid (cols, rows, x0, y0).
- `main()` is 120 lines mixing argument parsing, loading, rendering, JSON writing and PDF output.
- `cards.json` stores `symbol_dir` with Windows backslashes.
- Card back is a raw `--back path` flag with no default; it belongs to the theme.
- `random_size_ranks` (`--no-balanced-sizes`) and `render_ring` (`--layout ring`, "the old layout")
  are fallbacks the packed layout has superseded. Candidates for removal, see open questions.

## 2. Target layout

```
dobble-generator/
  pyproject.toml            # deps: pillow, numpy, reportlab; console script "dobble"
  README.md                 # how to add a theme, how to build and print
  .gitignore                # out/, __pycache__/, *.pdf, themes/*/raw/, themes/*/cache/
  docs/algorithm.md
  dobble/                   # the shared package, no theme knowledge
    __init__.py
    plane.py                # dobble(n), verify(), order_for(symbol_count)
    ranks.py                # assign_size_ranks(), (random_size_ranks if kept)
    packing.py              # alpha_mask, dilate, edt, find_spot, gap_spot, pack_card
    render.py               # disc_card, scaled_rotated, fit_rotated, render_packed, (render_ring)
    pdf.py                  # PageGrid (shared cols/rows/slot math), write_deck_pdf, write_circles_pdf
    imaging.py              # to_transparent, border_connected, trim  (from make_transparent.py)
    theme.py                # Theme dataclass: load theme.json, resolve paths, validate symbol count
    cli.py                  # argparse with subcommands: fetch, prepare, build, pdf, circles, verify
  themes/
    pokemon/
      theme.json            # see below
      fetch.py              # today's download_gen1.py, minus the unused sprite variant
      raw/                  # downloaded artwork (gitignored)
      extras/               # Pokeball, logo, Team Rocket, Ash (transparent PNGs, committed)
      back.png
      symbols/              # 57 transparent PNGs produced by "dobble prepare pokemon"
    dinos/
      theme.json
      fetch.py              # only if there is a scrapable source; otherwise raw/ is filled by hand
      raw/ extras/ back.png symbols/
  out/                      # build output: out/<theme>/cards/*.png, cards.json, deck.pdf
```

`theme.json` holds everything that is currently a Python constant:

```json
{
  "name": "pokemon",
  "raw_ext": "jpg",
  "selection": [1, 2, 3, 4, 5, 6, 7, 8, 9, 25, 26, "..."],
  "extras": {"Pokeball.png": "152_pokeball", "PokemonLogo.png": "153_pokemon-logo"},
  "pockets": {"5": [[506, 558]], "6": [[692, 439]]},
  "background": {"white_level": 245, "opaque_level": 200},
  "back": "back.png",
  "back_zoom": 1.0,
  "render": {"base_size": 0.40, "gap": 0.015, "max_rotation": 40}
}
```

Everything except `name` is optional. A dino theme whose images are already transparent needs
only `name`, `back` and a `symbols/` folder. `selection` and `pockets` stay opt-in for themes
that start from white-background JPGs. The order of the plane is derived from the symbol
count, and `prepare` fails early if `len(selection) + len(extras)` is not `n^2 + n + 1` for a
prime `n`.

CLI after the refactor (same flags as today where they still make sense):

```
dobble fetch pokemon [--variant artwork|png]
dobble prepare pokemon [--all] [--no-trim]
dobble build pokemon [--seed 42] [--size 1200] [--gap 0.015] ...   # cards + cards.json
dobble pdf pokemon [--diameter 8.5] [--page a4] [--no-mirror-back]  # from out/pokemon/cards
dobble build dinos --pdf                                            # build + pdf in one go
dobble circles -d 8 -n 6
dobble verify 7
```

## 3. Steps, in order

Each step leaves the project working. Step 2 is verified by regenerating with `--seed 42`
and diffing `cards.json` against the current one before any behaviour changes are made.

1. **Housekeeping.** `git init`, add `.gitignore`, `pyproject.toml`, README. Delete the stray
   files and unused assets from the table above. Move build outputs to `out/`. Rename
   `images/` to `themes/pokemon/{raw,extras,symbols}` and pick one back image.
2. **Split without changing behaviour.** Move functions from `dobble_cards.py` into the
   `dobble/` modules exactly as they are. Move `to_transparent` and `border_connected` into
   `imaging.py`. Keep a thin `cli.py`. Regenerate with seed 42 and confirm `cards.json`
   placements are byte-identical.
3. **Remove the Pokemon assumptions.** `order_for(count)` replaces `N`; `SHAPE_REF` becomes the
   median of the loaded set; "Pokemon" wording becomes "symbol"; `shape_factor` is computed
   once per symbol; `symbol_dir` in JSON becomes a posix relative path.
4. **Introduce `Theme`.** `theme.py` loads `theme.json`, resolves folders and the back image,
   and validates the symbol count. `prepare` takes `selection`, `extras`, `pockets` and
   background levels from it. `fetch` dispatches to `themes/<name>/fetch.py` if present.
5. **Dedupe PDF code.** One `PageGrid` class used by both the deck PDF and the circles PDF.
   `circle_pdf.py` disappears into `pdf.py` and the `circles` subcommand.
6. **Split `main()`.** `build` becomes: load theme -> load symbols -> plane + ranks -> render
   each card -> write JSON -> optional PDF, each a short function. The JSON becomes a
   `DeckManifest` written by one function.
7. **Prune fallbacks** (after answering the open questions below): ring layout,
   `--no-balanced-sizes`, `--pdf-only` (replaced by the `pdf` subcommand), `--shuffle-symbols`
   if unused.
8. **Scaffold `themes/dinos/`.** `theme.json`, empty `raw/` and `extras/`, and a fetch script
   once an image source is chosen. Run the full pipeline end to end on it.
9. **Tests** (small, fast): `verify(dobble(n))` for n in 2, 3, 5, 7; `assign_size_ranks`
   invariants; `order_for` rejects 20 or 40 symbols; `PageGrid` slot positions; one smoke test
   that packs a single card at `--grid 100` with a few generated blobs.

## 4. Open questions

These do not block steps 1 to 6. Defaults I will use unless told otherwise are in bold.

1. Keep the **ring** layout? It is documented as "the old evenly spaced layout". **Remove it.**
2. Keep `--no-balanced-sizes` (random ranks)? **Remove**; the balanced assignment always succeeds.
3. Keep the `sprites` variant (`images/gen1_png` -> `cards_sprites`)? **Keep** as a second
   Pokemon theme folder `themes/pokemon-sprites/` 
4. Where do the dino images come from? A public source with a scrapable index gets a
   `fetch.py`; a hand-collected folder just needs `raw/` filled. Symbol count decides the
   deck size: 57 for 8 per card, 31 for 6 per card (Dobble Kids), 13 for 4 per card.
5. Commit the prepared `symbols/` PNGs (19 MB for Pokemon) or treat them as build artefacts?
   **Don't commit any images** Due to uncertanty on copyright
6. Which of the three back images is the one you want? **`images/back/green_high.jpg`**.
