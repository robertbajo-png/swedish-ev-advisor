import json
import re
import sys
from pathlib import Path
from xml.etree import ElementTree

from generate_sitemap import PUBLIC_STATUSES, SEGMENTS, SITE_URL, load_public_variants, public_variant_urls


ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
OUT_JSON = ROOT / "data/mvp/programmatic_seo_report.json"
STATIC_PATHS = ["/", "/bilar", "/jamfor", *[f"/{segment}" for segment in SEGMENTS]]
DUPLICATE_NAME_PATTERNS = (
    "ex30-ex30",
    "ev9-ev9",
    "eqa-eqa",
    "id-4-id-4",
    "explorer-explorer",
    "q4-e-tron-audi",
    "a6-e-tron-a6",
)


def route_file(path: str) -> Path:
    if path == "/":
        return DIST / "index.html"
    return DIST / path.strip("/") / "index.html"


def sitemap_paths(path: Path) -> set[str]:
    if not path.exists():
        return set()
    tree = ElementTree.parse(path)
    namespace = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    paths = set()
    for loc in tree.findall(".//sm:loc", namespace):
        text = loc.text or ""
        if text.startswith(SITE_URL):
            paths.add(text.removeprefix(SITE_URL) or "/")
    return paths


def json_ld_payload(html: str):
    match = re.search(r'<script type="application/ld\+json" data-prerender="page">(.*?)</script>', html, re.S)
    if not match:
        return None
    return json.loads(match.group(1))


def json_ld_types(payload) -> set[str]:
    if isinstance(payload, list):
        return {str(item.get("@type")) for item in payload if isinstance(item, dict)}
    if isinstance(payload, dict):
        return {str(payload.get("@type"))}
    return set()


def check_route(path: str) -> list[str]:
    errors = []
    file_path = route_file(path)
    if not file_path.exists():
        return [f"missing_prerender_file:{path}"]

    html = file_path.read_text(encoding="utf-8")
    canonical = f'{SITE_URL}{path}'
    if f'<link rel="canonical" href="{canonical}"' not in html:
        errors.append(f"missing_or_wrong_canonical:{path}")
    for tag in ("og:title", "og:description", "og:url"):
        if f'property="{tag}"' not in html:
            errors.append(f"missing_open_graph:{path}:{tag}")
    for tag in ("twitter:title", "twitter:description"):
        if f'name="{tag}"' not in html:
            errors.append(f"missing_twitter_meta:{path}:{tag}")
    if not re.search(r"<title>[^<]{12,}</title>", html):
        errors.append(f"missing_title:{path}")
    if not re.search(r'<meta name="description" content="[^"]{50,}"', html):
        errors.append(f"missing_description:{path}")
    try:
        payload = json_ld_payload(html)
    except json.JSONDecodeError:
        payload = None
        errors.append(f"invalid_json_ld:{path}")
    if not payload:
        errors.append(f"missing_json_ld:{path}")
    types = json_ld_types(payload)
    if path.startswith("/bilar/") and payload and "Vehicle" not in types:
        errors.append(f"vehicle_route_without_vehicle_json_ld:{path}")
    if path.startswith("/bilar/") and payload and "BreadcrumbList" not in types:
        errors.append(f"vehicle_route_without_breadcrumb_json_ld:{path}")
    if path in STATIC_PATHS and path not in {"/", "/bilar", "/jamfor"} and payload and "ItemList" not in types:
        errors.append(f"segment_route_without_item_list_json_ld:{path}")
    if any(pattern in path for pattern in DUPLICATE_NAME_PATTERNS):
        errors.append(f"duplicate_name_slug:{path}")
    return errors


def main() -> None:
    variants = load_public_variants()
    non_public = [row for row in variants if row.get("validation_status") not in PUBLIC_STATUSES]
    expected_paths = []
    for path in [*STATIC_PATHS, *public_variant_urls(variants)]:
        if path not in expected_paths:
            expected_paths.append(path)

    errors = []
    if non_public:
        errors.append(f"non_public_rows_in_public_export:{len(non_public)}")
    for path in expected_paths:
        errors.extend(check_route(path))

    public_sitemap = sitemap_paths(ROOT / "public/sitemap.xml")
    dist_sitemap = sitemap_paths(DIST / "sitemap.xml")
    expected_set = set(expected_paths)
    missing_public_sitemap = sorted(expected_set - public_sitemap)
    missing_dist_sitemap = sorted(expected_set - dist_sitemap)
    if missing_public_sitemap:
        errors.append(f"public_sitemap_missing:{missing_public_sitemap[:5]}")
    if missing_dist_sitemap:
        errors.append(f"dist_sitemap_missing:{missing_dist_sitemap[:5]}")

    report = {
        "expected_routes": len(expected_paths),
        "vehicle_routes": len([path for path in expected_paths if path.startswith("/bilar/")]),
        "public_sitemap_urls": len(public_sitemap),
        "dist_sitemap_urls": len(dist_sitemap),
        "errors": errors,
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if errors:
        sys.exit("Programmatic SEO contract failed")


if __name__ == "__main__":
    main()
