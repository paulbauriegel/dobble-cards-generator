# dobble-generator

Generate a printable Dobble (Spot It) deck from any set of symbol images. A deck is a finite
projective plane: with 57 symbols you get 57 round cards of 8 symbols each, and any two cards
share exactly one symbol (see [docs/algorithm.md](docs/algorithm.md)).

Symbol sets are *themes* under `themes/<name>/`. Images are not committed to this repository;
each theme documents where its images come from.

## Setup

```bash
pip install -e .
```

## Usage

```bash
dobble verify 7                 # check the plane construction
dobble fetch pokemon            # download raw images (theme-specific)
dobble prepare pokemon          # raw images -> transparent, trimmed symbol PNGs
dobble build pokemon --pdf      # render the cards and a printable PDF into out/pokemon/
dobble pdf pokemon              # re-lay out an existing build as PDF
dobble circles -d 8 -n 6        # blank circle templates
```

See the "Themes" section below for how to add your own set of images.
