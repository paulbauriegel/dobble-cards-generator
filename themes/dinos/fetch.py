"""Download the dinosaur restorations listed on dinosaurs.wiki.

Usage (normally run through `dobble fetch dinos`):
    python fetch.py --out <folder> [--cache <folder>]

The list https://dinosaurs.wiki/articles_list/dinosaur.php is paginated; every page is fetched
once and cached next to this script. Each entry links a full-size image on the site's CDN
(PNG, JPG or WEBP, some already transparent, most on a white background). Every image is saved
as `NNN_<slug>.png` in the output folder, numbered in the order of the list, so that
`selection` in theme.json can pick by number. Images with a photo or painted background are
downloaded too; leave them out of `selection`.
"""
import argparse
import io
import os
import re
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

from PIL import Image

LIST_URL = "https://dinosaurs.wiki/articles_list/dinosaur.php?cat=dinosaur&page={page}"
HERE = os.path.dirname(os.path.abspath(__file__))
UA = {"User-Agent": "Mozilla/5.0"}
MAX_PAGES = 20

ENTRY = re.compile(r'<a href="/articles/([^"/]+)\.php"><img src="(https://[^"?]+)\?class=thumbnail"')
PAGE_LINK = re.compile(r'href="\?cat=dinosaur&(?:amp;)?page=(\d+)"')


def get(url, retries=3, timeout=60):
    req = urllib.request.Request(url, headers=UA)
    err = None
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except Exception as ex:
            err = ex
            time.sleep(1 + attempt)
    raise RuntimeError(f"{url}: {err}")


def load_page(page, cache):
    path = os.path.join(cache, f"dinosaur_{page}.html")
    if not os.path.exists(path):
        url = LIST_URL.format(page=page)
        print(f"fetching {url} -> {path}")
        os.makedirs(cache, exist_ok=True)
        with open(path, "wb") as f:
            f.write(get(url))
    return open(path, encoding="utf-8").read()


def parse_list(cache):
    """[(slug, image_url), ...] over all pages of the list, in site order, without duplicates."""
    entries, seen, page, last = [], set(), 1, 1
    while page <= last:
        html = load_page(page, cache)
        last = max([last, *map(int, PAGE_LINK.findall(html))])
        last = min(last, MAX_PAGES)
        for slug, url in ENTRY.findall(html):
            if slug not in seen:
                seen.add(slug)
                entries.append((slug, url))
        page += 1
    return entries


def save_png(data, path):
    """Decode any image format Pillow knows and write it as PNG, keeping transparency."""
    img = Image.open(io.BytesIO(data))
    has_alpha = img.mode in ("RGBA", "LA") or "transparency" in img.info
    img = img.convert("RGBA" if has_alpha else "RGB")
    img.save(path, optimize=True)


def fetch_all(entries, out):
    os.makedirs(out, exist_ok=True)

    def fetch(item):
        n, (slug, url) = item
        path = os.path.join(out, f"{n:03d}_{slug}.png")
        if os.path.exists(path) and os.path.getsize(path) > 0:
            return n, slug, "skip"
        try:
            save_png(get(url), path)
            return n, slug, "ok"
        except Exception as ex:
            if os.path.exists(path):
                os.remove(path)
            return n, slug, f"FAIL {ex}"

    with ThreadPoolExecutor(max_workers=4) as ex:
        results = list(ex.map(fetch, enumerate(entries, 1)))
    ok = sum(1 for r in results if r[2] == "ok")
    skip = sum(1 for r in results if r[2] == "skip")
    fails = [r for r in results if r[2].startswith("FAIL")]
    print(f"-> {out}: ok {ok}, skipped {skip}, failed {len(fails)}")
    for r in fails:
        print("   ", r)
    return len(fails)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", required=True, help="folder for the downloaded images")
    ap.add_argument("--cache", default=os.path.join(HERE, "cache"), help="folder for the cached list pages")
    args = ap.parse_args()

    entries = parse_list(args.cache)
    print(f"found {len(entries)} dinosaurs")
    if not entries:
        sys.exit("no entries found; page layout may have changed")
    for n, (slug, _) in enumerate(entries, 1):
        print(f"  {n:03d} {slug}")
    sys.exit(1 if fetch_all(entries, args.out) else 0)


if __name__ == "__main__":
    main()
