"""The fairytale theme's generation script: concept list, prompt template, paths and the API job."""
import base64
import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

THEME = Path(__file__).resolve().parent.parent / "themes" / "fairytale"
spec = importlib.util.spec_from_file_location("fairytale_generate", THEME / "generate.py")
generator = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = generator
spec.loader.exec_module(generator)

TRANSPARENT_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEgQH/qwKqVwAAAABJRU5ErkJggg=="
)


def test_parse_numbered_concepts_ignores_heading():
    concepts = generator.parse_concepts(THEME / "symbols.txt")
    assert len(concepts) == 57
    assert concepts[0] == "Cinderella"
    assert concepts[-1] == "Magic mushroom"


def test_extracts_only_copy_paste_prompt():
    template = generator.extract_prompt_template(THEME / "prompt.txt")
    assert "Primary request:" in template
    assert "[CONCEPT]" in template
    assert "How to use" not in template
    assert "Example subject fields" not in template


def test_render_prompt_resolves_fields():
    template = generator.extract_prompt_template(THEME / "prompt.txt")
    prompt = generator.render_prompt(template, "Frog Prince", 3)
    assert "Frog Prince" in prompt
    assert "Every returned result must be a standalone icon" in prompt
    assert "[CONCEPT]" not in prompt
    assert "[2 OR 3" not in prompt
    assert "[SIMPLE" not in prompt


def test_output_paths_are_stable():
    paths = generator.output_paths(Path("out"), 8, "Puss in Boots", 3)
    assert paths == (
        Path("out/008-puss-in-boots/puss-in-boots-01.png"),
        Path("out/008-puss-in-boots/puss-in-boots-02.png"),
        Path("out/008-puss-in-boots/puss-in-boots-03.png"),
    )


def test_defaults_point_into_the_theme_and_fetch_style_out_flag_is_accepted():
    args = generator.build_parser().parse_args([])
    assert args.list_path == THEME / "symbols.txt" and args.list_path.is_file()
    assert args.prompt_path == THEME / "prompt.txt" and args.prompt_path.is_file()
    assert args.reference == THEME / "reference" / "cinderella-black-outline.png" and args.reference.is_file()
    assert args.output_dir == THEME / "raw"
    assert generator.build_parser().parse_args(["--out", "x"]).output_dir == Path("x")


def test_transparent_square_png_passes_validation():
    width, height, has_alpha = generator.png_info(TRANSPARENT_PNG)
    assert (width, height, has_alpha) == (1, 1, True)
    generator.validate_png(TRANSPARENT_PNG, require_alpha=True)


def test_generate_job_writes_three_images_and_manifest(tmp_path):
    encoded = base64.b64encode(TRANSPARENT_PNG).decode("ascii")

    class FakeImages:
        def __init__(self):
            self.arguments = None

        def edit(self, **arguments):
            self.arguments = arguments
            return SimpleNamespace(data=[SimpleNamespace(b64_json=encoded) for _ in range(arguments["n"])])

    class FakeClient:
        def __init__(self):
            self.images = FakeImages()

    reference = tmp_path / "reference.png"
    reference.write_bytes(TRANSPARENT_PNG)
    output_dir = tmp_path / "output"
    targets = generator.output_paths(output_dir, 9, "Frog Prince", 3)
    job = generator.Job(index=9, concept="Frog Prince", slug="frog-prince", prompt="rendered prompt", targets=targets)
    settings = generator.Settings(
        reference=reference, output_dir=output_dir, model="gpt-image-2", size="1024x1024", quality="medium",
        background="transparent", max_attempts=1, timeout=30, force=False,
    )
    client = FakeClient()

    result = generator.generate_job(job, settings, output_dir / "manifest.jsonl", client)

    assert result["status"] == "generated"
    assert client.images.arguments["n"] == 3
    assert client.images.arguments["background"] == "transparent"
    assert all(path.read_bytes() == TRANSPARENT_PNG for path in targets)
    manifest = (output_dir / "manifest.jsonl").read_text(encoding="utf-8")
    assert '"reference": "reference.png"' in manifest
