import csv
import re
import unicodedata
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CANONICAL_MODELS = ROOT / "data/canonical/canonical_models_seed.csv"


def normalize(value: str) -> str:
    value = unicodedata.normalize("NFKD", str(value or "").upper())
    value = "".join(char for char in value if not unicodedata.combining(char))
    value = value.replace("&", " AND ")
    value = re.sub(r"[^A-Z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip().lower()


def canonical_model_lookup(path: Path = DEFAULT_CANONICAL_MODELS) -> dict[tuple[str, str], str]:
    rows = {}
    if not path.exists():
        return rows
    with path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            rows[(normalize(row.get("brand")), normalize(row.get("model")))] = row.get("model")

    # Official/marketing names that should publish under the canonical model record.
    if ("renault", "5") in rows:
        rows[("renault", "5 e tech")] = rows[("renault", "5")]
    return rows


def canonicalize_model_row(row: dict, lookup: dict[tuple[str, str], str] | None = None) -> dict:
    lookup = lookup if lookup is not None else canonical_model_lookup()
    key = (normalize(row.get("brand")), normalize(row.get("model")))
    canonical_model = lookup.get(key)
    return {**row, "model": canonical_model} if canonical_model else row


def canonical_key_candidates(brand: str, model: str) -> list[tuple[str, str]]:
    normalized_brand = normalize(brand)
    normalized_model = normalize(model)
    candidates = [(normalized_brand, normalized_model)]
    lookup = canonical_model_lookup()
    canonical_model = lookup.get((normalized_brand, normalized_model))
    if canonical_model:
        candidates.append((normalized_brand, normalize(canonical_model)))
    return list(dict.fromkeys(candidates))
