import json
import re
from pathlib import Path


PROHIBITED_IMAGE_REFERENCES = (
    "unsplash",
    "images.unsplash",
    "source.unsplash",
    "pexels",
    "pixabay",
)


def normalize_image_key(value):
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", str(value or "").lower())).strip()


def public_records(path):
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return payload
    return payload.get("records", [])


def official_image_keys(src):
    match = re.search(r"const officialModelImages = \{(?P<body>.*?)\n\};", src, re.S)
    if not match:
        return set()
    return set(re.findall(r"\n\s*'([^']+)'\s*:", match.group("body")))


def fallback_image_urls(src):
    match = re.search(r"const fallbackCars = \[(?P<body>.*?)\n\];", src, re.S)
    if not match:
        return []
    body = match.group("body")
    return re.findall(r"image:\s*['\"](https?://[^'\"]+)['\"]", body)


def build_report(root):
    root = Path(root)
    src = (root / "src/main.jsx").read_text(encoding="utf-8")
    rows = public_records(root / "public/data/public_ev_variants.json")
    keys = official_image_keys(src)

    expected_keys = {
        f"{normalize_image_key(row.get('brand'))}|{normalize_image_key(row.get('model'))}"
        for row in rows
    }
    missing_model_image_keys = sorted(expected_keys - keys)
    prohibited_image_references = sorted(
        token for token in PROHIBITED_IMAGE_REFERENCES if token in src.lower()
    )

    return {
        "public_records": len(rows),
        "public_model_keys": len(expected_keys),
        "official_image_keys": len(keys),
        "missing_model_image_keys": missing_model_image_keys,
        "fallback_image_urls": fallback_image_urls(src),
        "prohibited_image_references": prohibited_image_references,
        "strict_null_fallback": "return officialModelImages[key] || null;" in src,
        "public_uses_exact_lookup": "image: officialImageFor(row.brand, row.model)" in src,
    }


def main():
    report = build_report(Path(__file__).resolve().parents[1])
    print(json.dumps(report, ensure_ascii=False, indent=2))
    errors = []
    if report["missing_model_image_keys"]:
        errors.append("missing exact image keys")
    if report["fallback_image_urls"]:
        errors.append("fallback image URLs")
    if report["prohibited_image_references"]:
        errors.append("prohibited stock image references")
    if not report["strict_null_fallback"]:
        errors.append("officialImageFor must return null when exact match is missing")
    if not report["public_uses_exact_lookup"]:
        errors.append("public transform must use exact brand/model image lookup")
    if errors:
        raise SystemExit("Image contract failed: " + ", ".join(errors))


if __name__ == "__main__":
    main()
