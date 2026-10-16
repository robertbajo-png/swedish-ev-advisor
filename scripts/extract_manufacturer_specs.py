import argparse
import csv
import hashlib
import html
import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from pypdf import PdfReader
from supabase_client import load_local_env


ROOT = Path(__file__).resolve().parents[1]
APPROVED_SOURCE_VALIDATIONS = {"reachable_official_model_source", "reachable_eu_official_source", "reachable_approved_source"}
load_local_env()
DEFAULT_MODEL = os.environ.get("OPENAI_MODEL", "gpt-5.4-mini")
MAX_SOURCE_CHARS = 45000
MIN_SOURCE_CHARS = 500

STRICT_EXTRACTION_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "variants": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "variant_name": {"type": "string"},
                    "price_sek": {"type": ["integer", "null"]},
                    "price_type": {"type": ["string", "null"], "enum": ["list_price", "campaign_price", "dealer_offer", None]},
                    "price_valid_until": {"type": ["string", "null"]},
                    "wltp_range_km": {"type": ["integer", "null"]},
                    "wltp_consumption_kwh_100km": {"type": ["number", "null"]},
                    "battery_kwh": {"type": ["number", "null"]},
                    "dc_charge_kw": {"type": ["integer", "null"]},
                    "ac_charge_kw": {"type": ["integer", "null"]},
                    "boot_liters": {"type": ["integer", "null"]},
                    "tow_kg": {"type": ["integer", "null"]},
                    "seats": {"type": ["integer", "null"]},
                    "drivetrain": {"type": ["string", "null"]},
                    "source_quote": {"type": ["string", "null"]},
                    "confidence": {"type": "number"},
                },
                "required": [
                    "variant_name",
                    "price_sek",
                    "price_type",
                    "price_valid_until",
                    "wltp_range_km",
                    "wltp_consumption_kwh_100km",
                    "battery_kwh",
                    "dc_charge_kw",
                    "ac_charge_kw",
                    "boot_liters",
                    "tow_kg",
                    "seats",
                    "drivetrain",
                    "source_quote",
                    "confidence",
                ],
            },
        }
    },
    "required": ["variants"],
}


def fetch_bytes(url: str) -> tuple[bytes, str]:
    request = Request(url, headers={"User-Agent": "swedish-ev-advisor/0.1"})
    with urlopen(request, timeout=45) as response:
        content_type = response.headers.get("content-type", "")
        return response.read(), content_type


def html_to_text(content: bytes) -> str:
    raw = content.decode("utf-8", errors="replace")
    raw = re.sub(r"(?is)<(script|style|noscript).*?</\1>", " ", raw)
    raw = re.sub(r"(?s)<[^>]+>", " ", raw)
    raw = html.unescape(raw)
    return re.sub(r"\s+", " ", raw).strip()


def pdf_to_text(content: bytes) -> str:
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as handle:
        handle.write(content)
        pdf_path = handle.name
    try:
        reader = PdfReader(pdf_path)
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    finally:
        Path(pdf_path).unlink(missing_ok=True)


def fetch_source_text(url: str) -> tuple[str, str]:
    content, content_type = fetch_bytes(url)
    if "pdf" in content_type.lower() or url.lower().endswith(".pdf"):
        text = pdf_to_text(content)
    else:
        text = html_to_text(content)
    return text, hashlib.sha256(content).hexdigest()


def source_text_from_row(row: dict) -> tuple[str, str]:
    source_text_path = row.get("source_text_path")
    if source_text_path:
        text = Path(source_text_path).read_text(encoding="utf-8")
        source_hash = hashlib.sha256(text.strip().encode("utf-8")).hexdigest()
        expected_hash = row.get("content_hash") or row.get("source_hash")
        if expected_hash and source_hash != expected_hash:
            raise RuntimeError("Rendered source text hash does not match batch content_hash")
        return text, source_hash
    return fetch_source_text(row["url"])


def chunk_source_text(source_text: str, max_chars: int = MAX_SOURCE_CHARS) -> list[str]:
    text = re.sub(r"\s+", " ", source_text).strip()
    if len(text) <= max_chars:
        return [text]

    chunks = []
    start = 0
    while start < len(text):
        end = min(start + max_chars, len(text))
        if end < len(text):
            boundary = max(text.rfind(". ", start, end), text.rfind("\n", start, end), text.rfind(" ", start, end))
            if boundary > start + max_chars // 2:
                end = boundary + 1
        chunks.append(text[start:end].strip())
        start = end
    return [chunk for chunk in chunks if chunk]


def _number(value: str) -> int:
    return int(re.sub(r"\D", "", value))


def vehicle_price_match(text: str):
    patterns = (
        r"(?i)(?:rek\.?\s*pris\s*från|kontantpris)\s*([1-9][0-9\s.]{4,12})\s*kr",
        r"(?i)(?:pris\s+från|från)\s*([1-9][0-9\s.]{4,12})\s*kr",
    )
    for pattern in patterns:
        for match in re.finditer(pattern, text):
            trailing = text[match.end():match.end() + 12].lower()
            value = _number(match.group(1))
            if "/mån" not in trailing and "per månad" not in trailing and 100000 <= value <= 3000000:
                return match
    return None


def vehicle_range_match(text: str):
    pattern = r"(?i)(?:WLTP.{0,80}?|räckvidd.{0,80}?)(?:upp\s+till\s+)?([1-9][0-9]{2,3})\s*km"
    for match in re.finditer(pattern, text):
        value = int(match.group(1))
        prefix = text[max(0, match.start(1) - 5):match.start(1)]
        if value >= 150 and not re.search(r"0\s*[-–]\s*$", prefix):
            return match
    return None


def exact_wltp_consumption(text: str) -> float | None:
    normalized = re.sub(r"\s+", " ", text)
    unit = r"kwh\s*/\s*100\s*km"
    number = r"([0-9]{1,2}(?:[.,][0-9])?)"
    range_pattern = rf"{number}\s*(?:\([^)]*\)\s*)?[\-\u2013\u2014]\s*{number}\s*(?:\([^)]*\)\s*)?{unit}"
    if re.search(range_pattern, normalized, flags=re.IGNORECASE):
        return None

    values = {
        float(value.replace(",", "."))
        for value in re.findall(rf"{number}\s*{unit}", normalized, flags=re.IGNORECASE)
    }
    if len(values) != 1:
        return None
    value = values.pop()
    return round(value, 1) if 5 <= value <= 50 else None


def deterministic_extract(brand: str, model: str, source_text: str, source_authority: str) -> list[dict]:
    text = re.sub(r"\s+", " ", source_text).strip()
    normalized = text.lower()
    tokens = [token for token in re.findall(r"[a-z0-9]+", model.lower()) if len(token) > 1]
    if not tokens or not all(token in normalized for token in tokens):
        return []

    price_match = vehicle_price_match(text)
    range_match = vehicle_range_match(text)
    consumption = exact_wltp_consumption(text)
    if not price_match and not range_match:
        return []

    matches = [match for match in (price_match, range_match) if match]
    price = _number(price_match.group(1)) if price_match else None
    range_km = int(range_match.group(1)) if range_match else None
    if price is not None and not 100000 <= price <= 3000000:
        price = None
    if range_km is not None and not 50 <= range_km <= 1200:
        range_km = None
    if price is None and range_km is None:
        return []
    return [{
        "variant_name": model,
        "price_sek": price,
        "price_type": "dealer_offer" if source_authority == "authorized_dealer" and price is not None else "list_price" if price is not None else None,
        "price_valid_until": None,
        "wltp_range_km": range_km,
        "wltp_consumption_kwh_100km": consumption,
        "battery_kwh": None,
        "dc_charge_kw": None,
        "ac_charge_kw": None,
        "boot_liters": None,
        "tow_kg": None,
        "seats": None,
        "drivetrain": None,
        "source_quote": " … ".join(text[max(0, match.start() - 90):min(len(text), match.end() + 120)] for match in matches),
        "confidence": 0.93,
    }]


def call_openai(brand: str, model: str, source_url: str, source_text: str, source_authority: str = "manufacturer", chunk_index: int = 1, chunk_count: int = 1) -> dict:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is required for extraction")

    prompt = (
        "Extract Swedish EV model variant data only from the provided official source text. "
        "Do not infer missing values. Use null when the source text does not explicitly support a value. "
        "Prices must be SEK integers. Set price_type to list_price, campaign_price or dealer_offer. "
        "Use dealer_offer for prices from an authorized dealer source. Preserve an explicit validity date as YYYY-MM-DD. "
        "WLTP range is km. WLTP combined energy consumption is kWh/100 km. DC/AC charging are kW. "
        "Every non-null fact must be supported by source_quote. "
        "Return only variants for the requested model. "
        f"This is source chunk {chunk_index} of {chunk_count}; only extract facts present in this chunk.\n\n"
        f"Brand: {brand}\nModel: {model}\nSource authority: {source_authority}\nSource URL: {source_url}\n\nSOURCE TEXT:\n{source_text}"
    )
    payload = {
        "model": DEFAULT_MODEL,
        "input": [{"role": "user", "content": [{"type": "input_text", "text": prompt}]}],
        "text": {
            "format": {
                "type": "json_schema",
                "name": "ev_variant_extraction",
                "schema": STRICT_EXTRACTION_SCHEMA,
                "strict": True,
            }
        },
    }
    request = Request(
        "https://api.openai.com/v1/responses",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=90) as response:
        result = json.loads(response.read().decode("utf-8"))
    text_parts = []
    for item in result.get("output", []):
        for content in item.get("content", []):
            if content.get("type") == "output_text":
                text_parts.append(content.get("text", ""))
    if not text_parts:
        raise RuntimeError("OpenAI response did not contain output_text")
    return json.loads("".join(text_parts))


def variant_merge_key(variant: dict) -> str:
    return re.sub(r"\s+", " ", str(variant.get("variant_name", "")).strip().lower())


def merge_extracted_variants(extractions: list[dict]) -> list[dict]:
    merged: dict[str, dict] = {}
    for extraction in extractions:
        for variant in extraction.get("variants", []):
            key = variant_merge_key(variant)
            if not key:
                continue
            current = merged.get(key)
            if current is None or float(variant.get("confidence") or 0) > float(current.get("confidence") or 0):
                merged[key] = variant
    return list(merged.values())


def extract_variants_with_openai(brand: str, model: str, source_url: str, source_text: str, source_authority: str = "manufacturer") -> list[dict]:
    chunks = chunk_source_text(source_text)
    extractions = [
        call_openai(brand, model, source_url, chunk, source_authority=source_authority, chunk_index=index, chunk_count=len(chunks))
        for index, chunk in enumerate(chunks, start=1)
    ]
    return merge_extracted_variants(extractions)


def safe_extract(row: dict) -> list[dict]:
    text, source_hash = source_text_from_row(row)
    if len(text) < MIN_SOURCE_CHARS:
        raise RuntimeError("Source text too short for reliable extraction")
    deterministic_source_types = {
        "manufacturer_model_page", "manufacturer_specs_page", "manufacturer_price_list",
        "manufacturer_rendered_model_page",
        "model_page", "specs_page", "price_list", "price_list_pdf", "technical_pdf",
        "authorized_dealer_model_page",
    }
    variants = (
        deterministic_extract(row["brand"], row["model"], text, row.get("source_authority", "manufacturer"))
        if row.get("source_type") in deterministic_source_types
        else []
    )
    if not variants:
        variants = extract_variants_with_openai(
            row["brand"], row["model"], row["url"], text, source_authority=row.get("source_authority", "manufacturer")
        )
    drafts = []
    for variant in variants:
        drafts.append(
            {
                "brand": row["brand"],
                "model": row["model"],
                "variant_name": variant["variant_name"],
                "price_sek": variant["price_sek"],
                "price_type": variant.get("price_type"),
                "price_valid_until": variant.get("price_valid_until"),
                "wltp_range_km": variant["wltp_range_km"],
                "wltp_consumption_kwh_100km": variant["wltp_consumption_kwh_100km"],
                "battery_kwh": variant["battery_kwh"],
                "dc_charge_kw": variant["dc_charge_kw"],
                "ac_charge_kw": variant["ac_charge_kw"],
                "boot_liters": variant["boot_liters"],
                "tow_kg": variant["tow_kg"],
                "seats": variant["seats"],
                "drivetrain": variant["drivetrain"],
                "source_url": row["url"],
                "source_quote": variant["source_quote"],
                "source_hash": source_hash,
                "extraction_confidence": variant["confidence"],
                "extraction_payload": variant,
                "validation_status": "extracted",
                "validation_errors": None,
            }
        )
    return drafts


def draft_key(draft: dict) -> tuple[str, str, str, str]:
    return (draft["brand"], draft["model"], draft["variant_name"], draft["source_url"])


def merge_drafts(existing: list[dict], new_drafts: list[dict]) -> list[dict]:
    merged = {draft_key(draft): draft for draft in existing}
    for draft in new_drafts:
        merged[draft_key(draft)] = draft
    return list(merged.values())


def write_outputs(drafts: list[dict], append: bool = True) -> None:
    out_dir = ROOT / "data/extraction"
    out_dir.mkdir(parents=True, exist_ok=True)
    draft_path = out_dir / "extracted_variant_drafts.json"
    if append and draft_path.exists():
        drafts = merge_drafts(json.loads(draft_path.read_text(encoding="utf-8")), drafts)
    (out_dir / "extracted_variant_drafts.json").write_text(
        json.dumps(drafts, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    if drafts:
        with (out_dir / "extracted_variant_drafts.csv").open("w", newline="", encoding="utf-8") as handle:
            fieldnames = [key for key in drafts[0].keys() if key not in ("extraction_payload", "validation_errors")]
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            for draft in drafts:
                writer.writerow({key: draft.get(key) for key in fieldnames})


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int)
    parser.add_argument("--source-file", type=Path, default=ROOT / "data/canonical/manufacturer_sources_validated.csv")
    parser.add_argument("--no-append", action="store_true")
    args = parser.parse_args()

    rows = [
        row
        for row in csv.DictReader(args.source_file.open(encoding="utf-8"))
        if row.get("source_validation") in APPROVED_SOURCE_VALIDATIONS
        and row.get("preflight_status", row.get("source_validation")) in (*APPROVED_SOURCE_VALIDATIONS, "ready_for_ai_extraction")
    ]
    if args.limit:
        rows = rows[: args.limit]

    all_drafts = []
    errors = []
    for row in rows:
        try:
            all_drafts.extend(safe_extract(row))
            print(f"Extracted {row['brand']} {row['model']}")
        except (HTTPError, URLError, TimeoutError, RuntimeError, json.JSONDecodeError) as error:
            errors.append({"brand": row["brand"], "model": row["model"], "url": row["url"], "error": str(error)})
            print(f"Skipped {row['brand']} {row['model']}: {error}")

    write_outputs(all_drafts, append=not args.no_append)
    error_path = ROOT / "data/extraction/extraction_errors.json"
    error_path.parent.mkdir(parents=True, exist_ok=True)
    error_path.write_text(json.dumps(errors, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"drafts": len(all_drafts), "errors": len(errors), "completed_at": datetime.now(timezone.utc).isoformat()}, indent=2))


if __name__ == "__main__":
    main()
