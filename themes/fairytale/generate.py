#!/usr/bin/env python3
"""Generate fairy-tale symbol candidates with OpenAI's gpt-image-2 from a concept list and a
style reference image.

Normally run through `dobble fetch fairytale`, which passes `--out themes/fairytale/raw`; every
other flag goes through unchanged:

    uv run dobble fetch fairytale --dry-run --limit 2
    uv run dobble fetch fairytale --only "Frog Prince"
    uv run dobble fetch fairytale --yes

Every concept in symbols.txt gets `--variants` (default 3) candidate PNGs written to
<out>/NNN-<slug>/<slug>-NN.png. Pick one per concept and copy it to <out>/NNN_<name>.png, which is
what `dobble prepare` reads (it ignores the subfolders). The style comes from prompt.txt plus the
reference image, which is sent to the images/edit endpoint as the image to restyle. Every finished
call is logged to <out>/manifest.jsonl.

Live generation needs the `openai` package (`uv sync --group generate`), network access and an
`OPENAI_API_KEY` environment variable. A full default run creates 171 images (57 concepts x 3
variants), so live runs require `--yes` when more than 12 new images are planned.
"""

from __future__ import annotations

import argparse
import base64
import concurrent.futures
import json
import os
import re
import struct
import sys
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_LIST = SCRIPT_DIR / "symbols.txt"
DEFAULT_PROMPT = SCRIPT_DIR / "prompt.txt"
DEFAULT_REFERENCE = SCRIPT_DIR / "reference" / "cinderella-black-outline.png"
DEFAULT_OUTPUT_DIR = SCRIPT_DIR / "raw"
DEFAULT_BASE_URL = "https://eu.api.openai.com/v1"    # EU data residency; --base-url overrides
PROMPT_START = "Copy/paste prompt"
PROMPT_END = "Example subject fields"
PLACEHOLDERS = {
    "[CONCEPT]": lambda concept: concept,
    "[2 OR 3 DISTINCTIVE FEATURES]": lambda concept: (
        f"the two or three most recognizable visual features traditionally associated with {concept}"
    ),
    "[SIMPLE VIEW OR POSE]": lambda concept: (
        f"the simplest iconic view or pose that gives {concept} a strong silhouette"
    ),
    "[2 OR 3 CONCEPT-APPROPRIATE COLORS]": lambda concept: (
        f"two or three bright, high-contrast colors traditionally associated with {concept}"
    ),
}
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
MANIFEST_LOCK = threading.Lock()
PRINT_LOCK = threading.Lock()


@dataclass(frozen=True)
class Job:
    index: int
    concept: str
    slug: str
    prompt: str
    targets: tuple[Path, ...]


@dataclass(frozen=True)
class Settings:
    reference: Path
    output_dir: Path
    model: str
    size: str
    quality: str
    background: str
    max_attempts: int
    timeout: float
    force: bool


def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return parsed


def variants_count(value: str) -> int:
    parsed = positive_int(value)
    if parsed > 10:
        raise argparse.ArgumentTypeError("must not exceed 10")
    return parsed


def parse_concepts(path: Path) -> list[str]:
    """Read numbered entries, or fall back to non-empty plain-text lines."""
    text = path.read_text(encoding="utf-8")
    numbered: list[str] = []
    plain: list[str] = []

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or set(line) <= {"=", "-", "_"}:
            continue

        match = re.match(r"^\d+[.)]\s+(.+?)\s*$", line)
        if match:
            numbered.append(match.group(1))
        else:
            plain.append(line)

    concepts = numbered if numbered else plain
    unique: list[str] = []
    seen: set[str] = set()
    for concept in concepts:
        key = concept.casefold()
        if key not in seen:
            unique.append(concept)
            seen.add(key)

    if not unique:
        raise ValueError(f"No concepts found in {path}")
    return unique


def extract_prompt_template(path: Path) -> str:
    """Extract the copy/paste section from Prompt V2 when it is present."""
    text = path.read_text(encoding="utf-8")
    start = text.find(PROMPT_START)
    if start == -1:
        template = text.strip()
    else:
        template = text[start + len(PROMPT_START) :]
        template = re.sub(r"^\s*[-=]+\s*", "", template, count=1)
        end = template.find(PROMPT_END)
        if end != -1:
            template = template[:end]
        template = template.strip()

    if not template:
        raise ValueError(f"Prompt template is empty: {path}")
    if "[CONCEPT]" not in template:
        raise ValueError(f"Prompt template must contain [CONCEPT]: {path}")
    return template


def render_prompt(template: str, concept: str, _variants: int) -> str:
    prompt = template
    for placeholder, replacement in PLACEHOLDERS.items():
        prompt = prompt.replace(placeholder, replacement(concept))

    unresolved = sorted(set(re.findall(r"\[[A-Z0-9][A-Z0-9 _-]*\]", prompt)))
    if unresolved:
        raise ValueError(f"Unresolved placeholders for {concept}: {', '.join(unresolved)}")

    return (
        f"{prompt}\n\n"
        "Variant guidance: Every returned result must be a standalone icon, never a "
        "contact sheet, grid, sequence, or multi-panel composition. Across variations, "
        "change only small pose, orientation, or faceted-color details while keeping "
        "the approved style consistent."
    )


def slugify(value: str) -> str:
    normalized = value.casefold().replace("'", "")
    slug = re.sub(r"[^a-z0-9]+", "-", normalized).strip("-")
    return slug or "concept"


def output_paths(output_dir: Path, index: int, concept: str, variants: int) -> tuple[Path, ...]:
    slug = slugify(concept)
    concept_dir = output_dir / f"{index:03d}-{slug}"
    return tuple(concept_dir / f"{slug}-{variant:02d}.png" for variant in range(1, variants + 1))


def png_info(data: bytes) -> tuple[int, int, bool]:
    """Return PNG width, height, and whether an alpha mechanism is present."""
    if len(data) < 33 or not data.startswith(PNG_SIGNATURE):
        raise ValueError("API response is not a valid PNG")
    if data[12:16] != b"IHDR" or struct.unpack(">I", data[8:12])[0] != 13:
        raise ValueError("PNG is missing a valid IHDR chunk")

    width, height, _depth, color_type, _compression, _filter, _interlace = struct.unpack(">IIBBBBB", data[16:29])
    has_alpha = color_type in {4, 6}

    offset = 8
    while offset + 12 <= len(data):
        length = struct.unpack(">I", data[offset : offset + 4])[0]
        chunk_type = data[offset + 4 : offset + 8]
        if chunk_type == b"tRNS":
            has_alpha = True
        offset += 12 + length
        if chunk_type == b"IEND":
            break

    return width, height, has_alpha


def validate_png(data: bytes, require_alpha: bool) -> None:
    width, height, has_alpha = png_info(data)
    if width != height:
        raise ValueError(f"Expected a square PNG, received {width}x{height}")
    if require_alpha and not has_alpha:
        raise ValueError("Expected a transparent PNG, but no alpha channel was returned")


def atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_bytes(data)
    temporary.replace(path)


def append_manifest(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, ensure_ascii=False, sort_keys=True)
    with MANIFEST_LOCK:
        with path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")


def is_retryable(error: Exception) -> bool:
    status_code = getattr(error, "status_code", None)
    if status_code in {408, 409, 429}:
        return True
    if isinstance(status_code, int) and 500 <= status_code < 600:
        return True
    return error.__class__.__name__ in {
        "APIConnectionError",
        "APITimeoutError",
        "InternalServerError",
        "RateLimitError",
    }


def create_client(timeout: float, base_url: str | None = DEFAULT_BASE_URL) -> Any:
    try:
        from openai import OpenAI
    except ImportError as error:
        raise RuntimeError("The openai package is required. Install it with: uv sync --group generate") from error
    return OpenAI(base_url=base_url, timeout=timeout, max_retries=0)


def decode_response(response: Any, expected: int, require_alpha: bool) -> list[bytes]:
    items = list(getattr(response, "data", []) or [])
    if len(items) != expected:
        raise ValueError(f"Expected {expected} images, API returned {len(items)}")

    decoded: list[bytes] = []
    for item in items:
        encoded = getattr(item, "b64_json", None)
        if not encoded:
            raise ValueError("API response image is missing b64_json")
        try:
            data = base64.b64decode(encoded, validate=True)
        except (ValueError, TypeError) as error:
            raise ValueError("API returned invalid base64 image data") from error
        validate_png(data, require_alpha=require_alpha)
        decoded.append(data)
    return decoded


def generate_job(job: Job, settings: Settings, manifest: Path, client: Any) -> dict[str, Any]:
    missing = list(job.targets) if settings.force else [p for p in job.targets if not p.exists()]
    if not missing:
        return {"concept": job.concept, "status": "skipped", "paths": job.targets}

    last_error: Exception | None = None

    for attempt in range(1, settings.max_attempts + 1):
        try:
            with settings.reference.open("rb") as reference_file:
                response = client.images.edit(
                    model=settings.model,
                    image=reference_file,
                    prompt=job.prompt,
                    n=len(missing),
                    size=settings.size,
                    quality=settings.quality,
                    background=settings.background,
                    output_format="png",
                )
            images = decode_response(
                response,
                expected=len(missing),
                require_alpha=settings.background == "transparent",
            )
            for target, image in zip(missing, images, strict=True):
                atomic_write(target, image)

            record = {
                "completed_at": datetime.now(timezone.utc).isoformat(),
                "concept": job.concept,
                "index": job.index,
                "model": settings.model,
                "paths": [str(path.relative_to(settings.output_dir)) for path in missing],
                "prompt": job.prompt,
                "quality": settings.quality,
                "reference": settings.reference.name,
                "size": settings.size,
                "status": "generated",
            }
            append_manifest(manifest, record)
            return {"concept": job.concept, "status": "generated", "paths": missing}
        except Exception as error:
            last_error = error
            if attempt >= settings.max_attempts or not is_retryable(error):
                break
            delay = min(2 ** (attempt - 1), 30)
            with PRINT_LOCK:
                print(
                    f"Retrying {job.concept!r} in {delay}s after {error.__class__.__name__}",
                    file=sys.stderr,
                )
            time.sleep(delay)

    assert last_error is not None
    append_manifest(
        manifest,
        {
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "concept": job.concept,
            "error": f"{last_error.__class__.__name__}: {last_error}",
            "index": job.index,
            "status": "failed",
        },
    )
    raise RuntimeError(f"{job.concept}: {last_error}") from last_error


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--list", dest="list_path", type=Path, default=DEFAULT_LIST)
    parser.add_argument("--prompt", dest="prompt_path", type=Path, default=DEFAULT_PROMPT)
    parser.add_argument("--reference", type=Path, default=DEFAULT_REFERENCE)
    parser.add_argument("--out", "--output-dir", dest="output_dir", type=Path, default=DEFAULT_OUTPUT_DIR,
                        help="folder for the candidates and manifest.jsonl (dobble fetch passes the raw folder)")
    parser.add_argument("--variants", type=variants_count, default=3)
    parser.add_argument("--model", default="gpt-image-2")
    parser.add_argument("--base-url", default=os.environ.get("OPENAI_BASE_URL", DEFAULT_BASE_URL),
                        help="API endpoint (default $OPENAI_BASE_URL or the EU endpoint)")
    parser.add_argument("--size", default="1024x1024")
    parser.add_argument("--quality", choices=("low", "medium", "high", "auto"), default="medium")
    parser.add_argument("--background", choices=("transparent", "opaque", "auto"), default="transparent")
    parser.add_argument("--workers", type=positive_int, default=1)
    parser.add_argument("--max-attempts", type=positive_int, default=3)
    parser.add_argument("--timeout", type=float, default=900.0)
    parser.add_argument("--limit", type=positive_int)
    parser.add_argument(
        "--only",
        action="append",
        default=[],
        metavar="CONCEPT",
        help="generate only an exact concept name; may be repeated",
    )
    parser.add_argument("--force", action="store_true", help="regenerate existing files")
    parser.add_argument("--dry-run", action="store_true", help="make no API calls or files")
    parser.add_argument(
        "--yes",
        action="store_true",
        help="confirm a live run that plans more than 12 new images",
    )
    return parser


def resolve_jobs(args: argparse.Namespace) -> list[Job]:
    indexed_concepts = list(enumerate(parse_concepts(args.list_path), start=1))
    if args.only:
        requested = {value.casefold() for value in args.only}
        indexed_concepts = [(index, concept) for index, concept in indexed_concepts if concept.casefold() in requested]
        found = {concept.casefold() for _, concept in indexed_concepts}
        missing = sorted(requested - found)
        if missing:
            raise ValueError(f"Unknown --only concept(s): {', '.join(missing)}")
    if args.limit is not None:
        indexed_concepts = indexed_concepts[: args.limit]

    template = extract_prompt_template(args.prompt_path)
    return [
        Job(
            index=index,
            concept=concept,
            slug=slugify(concept),
            prompt=render_prompt(template, concept, args.variants),
            targets=output_paths(args.output_dir, index, concept, args.variants),
        )
        for index, concept in indexed_concepts
    ]


def validate_inputs(args: argparse.Namespace) -> None:
    for label, path in (
        ("list", args.list_path),
        ("prompt", args.prompt_path),
        ("reference image", args.reference),
    ):
        if not path.is_file():
            raise ValueError(f"Missing {label}: {path}")
    if args.reference.stat().st_size >= 50 * 1024 * 1024:
        raise ValueError("Reference image must be smaller than 50 MB")
    if args.timeout <= 0:
        raise ValueError("--timeout must be greater than zero")


def new_image_count(jobs: Sequence[Job], force: bool) -> int:
    if force:
        return sum(len(job.targets) for job in jobs)
    return sum(1 for job in jobs for target in job.targets if not target.exists())


def print_dry_run(jobs: Sequence[Job], count: int, args: argparse.Namespace) -> None:
    print(f"Concepts: {len(jobs)}")
    print(f"New images planned: {count}")
    print(f"Model: {args.model}")
    print(f"Reference: {args.reference}")
    print(f"Output directory: {args.output_dir}")
    if jobs:
        print("\nFirst rendered prompt:\n")
        print(jobs[0].prompt)
        print("\nFirst output files:")
        for target in jobs[0].targets:
            print(target)


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        validate_inputs(args)
        jobs = resolve_jobs(args)
    except (OSError, ValueError) as error:
        parser.error(str(error))

    planned = new_image_count(jobs, force=args.force)
    if args.dry_run:
        print_dry_run(jobs, planned, args)
        return 0
    if planned == 0:
        print("All requested images already exist; nothing to generate.")
        return 0
    if planned > 12 and not args.yes:
        parser.error(f"This live run plans {planned} paid images. Review with --dry-run, then pass --yes to confirm.")
    if not os.environ.get("OPENAI_API_KEY"):
        parser.error("OPENAI_API_KEY is not set")

    settings = Settings(
        reference=args.reference,
        output_dir=args.output_dir,
        model=args.model,
        size=args.size,
        quality=args.quality,
        background=args.background,
        max_attempts=args.max_attempts,
        timeout=args.timeout,
        force=args.force,
    )
    manifest = args.output_dir / "manifest.jsonl"
    failures: list[str] = []
    generated = 0
    skipped = 0

    try:
        client = create_client(args.timeout, args.base_url)
    except RuntimeError as error:
        parser.error(str(error))

    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as executor:
            future_to_job = {executor.submit(generate_job, job, settings, manifest, client): job for job in jobs}
            for future in concurrent.futures.as_completed(future_to_job):
                job = future_to_job[future]
                try:
                    result = future.result()
                except Exception as error:
                    failures.append(f"{job.concept}: {error}")
                    with PRINT_LOCK:
                        print(f"FAILED  {job.concept}: {error}", file=sys.stderr)
                    continue

                if result["status"] == "skipped":
                    skipped += 1
                    label = "SKIPPED"
                else:
                    generated += len(result["paths"])
                    label = "CREATED"
                with PRINT_LOCK:
                    print(f"{label:7} {job.index:03d} {job.concept}")
    finally:
        close = getattr(client, "close", None)
        if callable(close):
            close()

    print(f"Finished: {generated} images generated, {skipped} concepts skipped, {len(failures)} concepts failed.")
    if failures:
        print(f"See {manifest} for recorded failures.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
