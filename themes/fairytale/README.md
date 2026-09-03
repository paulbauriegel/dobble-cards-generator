# fairytale theme

57 fairy-tale motifs, a card back and a style reference image. This is the only theme whose
images are committed, so that a deck can be built straight after cloning:

```
uv run dobble prepare fairytale
uv run dobble build fairytale --pdf
```

## AI-generated images

Every image in this folder (`raw/`, `reference/`, `back.jpg`) was generated with OpenAI's
**gpt-image-2** (medium quality, 1024 px, transparent background) in September 2026 and was not
drawn by hand. The symbols were produced by `generate.py` from the concept list in `symbols.txt`
and the prompt template in `prompt.txt`, with `reference/cinderella-black-outline.png` as the
style reference; that reference itself came from the prompt in `reference/prompt.txt`. Each
concept got three candidates, one was picked by hand, and a few concepts were added, dropped or
regenerated afterwards, so the files in `raw/` do not map one-to-one onto `symbols.txt`.

The motifs are the public-domain tales (Grimm, Andersen, Perrault, Russian and English folk
tales); the prompt explicitly asks for original designs that do not imitate any film, studio or
copyrighted adaptation. Treat the images as AI output: check them before using them beyond a
home-printed game.

## Files

| file | content |
|---|---|
| `raw/NNN_name.png` | the 57 symbols, transparent PNGs, `prepare` only trims them |
| `back.jpg` | card back; `back_zoom` 1.1 pushes its navy ring past the cut line so small duplex shifts stay hidden |
| `symbols.txt` | numbered concept list read by `generate.py` |
| `prompt.txt` | prompt template; the block after "Copy/paste prompt" is sent, with the bracketed fields filled per concept |
| `reference/` | style reference image and the prompt that produced it |
| `generate.py` | generation script, see below |

## Generating more symbols

`dobble fetch fairytale` runs `generate.py` with `--out themes/fairytale/raw`; every other flag
is passed through. It needs the `openai` package (`uv sync --group generate`) and an
`OPENAI_API_KEY`. Calls go to the EU endpoint by default; set `OPENAI_BASE_URL` or pass
`--base-url` to change that.

```
uv run dobble fetch fairytale --dry-run --limit 2      # show the prompt and the planned files
uv run dobble fetch fairytale --only "Frog Prince"     # three candidates for one concept
uv run dobble fetch fairytale --yes                    # everything missing (171 paid images)
```

Candidates land in `raw/NNN-<slug>/<slug>-NN.png` and every call is logged to
`raw/manifest.jsonl`; both are git-ignored. Pick one candidate per concept and copy it to
`raw/NNN_<name>.png`, which is what `prepare` reads (it ignores the subfolders). The deck needs
exactly 7, 13, 31, 57 or 133 symbols, so add or remove files in pairs with that in mind, or list
the ones to use in `selection` in `theme.json`.
