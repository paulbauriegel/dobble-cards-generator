"""Download Generation 1 Pokemon images from pokemondb.net.

Usage:
    python download_gen1.py [--variant sprite|png|artwork|all] [--html national.html]

Variants (each goes into its own folder under images/):
    sprite   -> images/gen1          HOME sprite, 2x JPG, white background (as shown on the page)
    png      -> images/gen1_png      HOME sprite, 1x PNG, transparent background
    artwork  -> images/gen1_artwork  Official large artwork, JPG
    all      -> every variant above

The page HTML is fetched automatically if the --html file does not exist.
"""
import argparse, os, re, sys, time, urllib.request
from concurrent.futures import ThreadPoolExecutor

PAGE_URL = "https://pokemondb.net/pokedex/national"
BASE = os.path.dirname(os.path.abspath(__file__))
UA = {"User-Agent": "Mozilla/5.0"}

VARIANTS = {
    "sprite":  ("gen1",         "https://img.pokemondb.net/sprites/home/normal/2x/{slug}.jpg", "jpg"),
    "png":     ("gen1_png",     "https://img.pokemondb.net/sprites/home/normal/{slug}.png",    "png"),
    "artwork": ("gen1_artwork", "https://img.pokemondb.net/artwork/large/{slug}.jpg",         "jpg"),
}

def load_html(path):
    if not os.path.exists(path):
        print(f"fetching {PAGE_URL} -> {path}")
        req = urllib.request.Request(PAGE_URL, headers=UA)
        with urllib.request.urlopen(req, timeout=60) as r, open(path, "wb") as f:
            f.write(r.read())
    return open(path, encoding="utf-8").read()

def parse_gen1(html):
    # The slug in the sprite URL is what every variant URL is keyed on.
    pat = re.compile(
        r'src="https://img\.pokemondb\.net/sprites/home/normal/2x/([^"]+)\.jpg" alt="([^"]+)"[^>]*>.*?<small>#(\d{4})</small>',
        re.S)
    seen, gen1 = set(), []
    for slug, name, num in pat.findall(html):
        n = int(num)
        if n <= 151 and n not in seen:
            seen.add(n); gen1.append((n, name, slug))
    return gen1

def download(url, path):
    req = urllib.request.Request(url, headers=UA)
    err = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=30) as r, open(path, "wb") as f:
                f.write(r.read())
            return "ok"
        except Exception as ex:
            err = ex; time.sleep(1 + attempt)
    if os.path.exists(path): os.remove(path)
    return f"FAIL {err}"

def run_variant(variant, gen1):
    folder, url_tpl, ext = VARIANTS[variant]
    out = os.path.join(BASE, "images", folder)
    os.makedirs(out, exist_ok=True)

    def fetch(e):
        n, name, slug = e
        safe = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
        path = os.path.join(out, f"{n:03d}_{safe}.{ext}")
        if os.path.exists(path) and os.path.getsize(path) > 0:
            return (n, name, "skip")
        return (n, name, download(url_tpl.format(slug=slug), path))

    with ThreadPoolExecutor(max_workers=6) as ex:
        results = list(ex.map(fetch, gen1))
    ok = sum(1 for r in results if r[2] == "ok")
    skip = sum(1 for r in results if r[2] == "skip")
    fails = [r for r in results if r[2].startswith("FAIL")]
    print(f"[{variant}] -> images/{folder}: ok {ok}, skipped {skip}, failed {len(fails)}")
    for r in fails: print("   ", r)
    return len(fails)

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--variant", choices=[*VARIANTS, "all"], default="sprite")
    ap.add_argument("--html", default=os.path.join(BASE, "national.html"))
    args = ap.parse_args()

    gen1 = parse_gen1(load_html(args.html))
    print(f"found {len(gen1)} Gen 1 entries")
    if len(gen1) != 151:
        sys.exit("expected 151 entries; page layout may have changed")

    variants = list(VARIANTS) if args.variant == "all" else [args.variant]
    failed = sum(run_variant(v, gen1) for v in variants)
    sys.exit(1 if failed else 0)

if __name__ == "__main__":
    main()
