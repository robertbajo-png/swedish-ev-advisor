import argparse
import csv
import json
from pathlib import Path

from canonical_model_names import normalize
from source_policy import source_is_publishable, source_priority


ROOT = Path(__file__).resolve().parents[1]


def read_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    fields: list[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def merge_sources(existing: list[dict], expansion: list[dict]) -> list[dict]:
    rows = {row.get("url"): row for row in existing if row.get("url")}
    for row in expansion:
        if row.get("url") and source_is_publishable(row):
            rows[row["url"]] = {**rows.get(row["url"], {}), **row}
    return sorted(rows.values(), key=lambda row: (normalize(row.get("brand")), normalize(row.get("model")), source_priority(row), row.get("url", "")))


def apply_images(models: list[dict], sources: list[dict]) -> list[dict]:
    candidates: dict[tuple[str, str], list[dict]] = {}
    for source in sources:
        if source.get("image_url") and source_is_publishable(source):
            key = (normalize(source.get("brand")), normalize(source.get("model")))
            candidates.setdefault(key, []).append(source)
    output = []
    for model in models:
        key = (model.get("normalized_brand"), model.get("normalized_model"))
        available = sorted(candidates.get(key, []), key=source_priority)
        if available:
            best = available[0]
            model = {
                **model,
                "image_url": best.get("image_url", ""),
                "image_source_url": best.get("image_source_url") or best.get("url", ""),
                "image_verified_at": best.get("image_verified_at", ""),
            }
        else:
            model = {**model, "image_url": model.get("image_url", ""), "image_source_url": model.get("image_source_url", ""), "image_verified_at": model.get("image_verified_at", "")}
        output.append(model)
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description="Merge validated expansion sources and exact model images into canonical seeds.")
    parser.add_argument("--sources", type=Path, default=ROOT / "data/expansion/expansion_sources.csv")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    expansion = read_csv(args.sources)
    seed_path = ROOT / "data/canonical/manufacturer_sources_seed.csv"
    model_path = ROOT / "data/canonical/canonical_models_seed.csv"
    merged = merge_sources(read_csv(seed_path), expansion)
    models = apply_images(read_csv(model_path), expansion)
    report = {
        "accepted_expansion_sources": sum(source_is_publishable(row) for row in expansion),
        "merged_sources": len(merged),
        "verified_model_images": sum(bool(row.get("image_url")) for row in models),
    }
    if not args.dry_run:
        write_csv(seed_path, merged)
        write_csv(model_path, models)
        (ROOT / "data/canonical/canonical_models_seed.json").write_text(json.dumps(models, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"dry_run": args.dry_run, **report}, indent=2))


if __name__ == "__main__":
    main()
