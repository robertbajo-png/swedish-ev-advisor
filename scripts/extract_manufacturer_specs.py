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


ROOT = Path(__file__).resolve().parents[1]
APPROVED_SOURCE_VALIDATION = "reachable_official_model_source"
DEFAULT_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4.1-mini")


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
    return text[:50000], hashlib.sha256(content).hexdigest()


def call_openai(brand: str, model: str, source_url: str, source_text: str) -> dict:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is required for extraction")

    schema = {
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
                        "wltp_range_km": {"type": ["integer", "null"]},
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
                        "wltp_range_km",
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
    prompt = (
        "Extract Swedish EV model variant data only from the provided official source text. "
        "Do not infer missing values. Use null when the source text does not explicitly support a value. "
        "Prices must be SEK integers. WLTP range is km. DC/AC charging are kW. "
        "Return only variants for the requested model.\n\n"
        f"Brand: {brand}\nModel: {model}\nSource URL: {source_url}\n\nSOURCE TEXT:\n{source_text}"
    )
    payload = {
        "model": DEFAULT_MODEL,
        "input": [{"role": "user", "content": [{"type": "input_text", "text": prompt}]}],
        "text": {
            "format": {
                "type": "json_schema",
                "name": "ev_variant_extraction",
                "schema": schema,
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


def safe_extract(row: dict) -> list[dict]:
    text, source_hash = fetch_source_text(row["url"])
    if len(text) < 500:
        raise RuntimeError("Source text too short for reliable extraction")
    extraction = call_openai(row["brand"], row["model"], row["url"], text)
    drafts = []
    for variant in extraction.get("variants", []):
        drafts.append(
            {
                "brand": row["brand"],
                "model": row["model"],
                "variant_name": variant["variant_name"],
                "price_sek": variant["price_sek"],
                "wltp_range_km": variant["wltp_range_km"],
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


def write_outputs(drafts: list[dict]) -> None:
    out_dir = ROOT / "data/extraction"
    out_dir.mkdir(parents=True, exist_ok=True)
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
    args = parser.parse_args()

    rows = [
        row
        for row in csv.DictReader(args.source_file.open(encoding="utf-8"))
        if row.get("source_validation") == APPROVED_SOURCE_VALIDATION
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

    write_outputs(all_drafts)
    error_path = ROOT / "data/extraction/extraction_errors.json"
    error_path.parent.mkdir(parents=True, exist_ok=True)
    error_path.write_text(json.dumps(errors, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"drafts": len(all_drafts), "errors": len(errors), "completed_at": datetime.now(timezone.utc).isoformat()}, indent=2))


if __name__ == "__main__":
    main()
