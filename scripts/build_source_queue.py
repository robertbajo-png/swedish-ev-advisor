import csv
import json
import re
import unicodedata
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.parse import quote_plus


BRAND_CANONICAL = {
    "VW": "Volkswagen",
    "MERCEDES": "Mercedes-Benz",
    "LYNK & CO": "Lynk & Co",
    "MG": "MG",
    "DS": "DS",
    "BMW": "BMW",
    "BYD": "BYD",
}

OFFICIAL_SWEDISH_DOMAINS = {
    "ALFA": "https://www.alfaromeo.se",
    "AUDI": "https://www.audi.se",
    "BMW": "https://www.bmw.se",
    "BYD": "https://www.byd.com/se",
    "CADILLAC": "https://www.cadillaceurope.com/se",
    "CITROEN": "https://www.citroen.se",
    "CUPRA": "https://www.cupraofficial.se",
    "DS": "https://www.dsautomobiles.se",
    "FIAT": "https://www.fiat.se",
    "FORD": "https://www.ford.se",
    "HYUNDAI": "https://www.hyundai.com/se",
    "JEEP": "https://www.jeep.se",
    "KIA": "https://www.kia.com/se",
    "LEAPMOTOR": "https://www.leapmotor.se",
    "LEXUS": "https://www.lexus.se",
    "LOTUS": "https://www.lotuscars.com/sv-SE",
    "LYNK & CO": "https://www.lynkco.com/sv-se",
    "MAZDA": "https://www.mazda.se",
    "MERCEDES": "https://www.mercedes-benz.se",
    "MG": "https://mgmotor.eu/sv-SE",
    "MINI": "https://www.mini.se",
    "NISSAN": "https://www.nissan.se",
    "OPEL": "https://www.opel.se",
    "PEUGEOT": "https://www.peugeot.se",
    "POLESTAR": "https://www.polestar.com/se",
    "PORSCHE": "https://www.porsche.com/sweden",
    "RENAULT": "https://www.renault.se",
    "SKODA": "https://www.skoda.se",
    "SMART": "https://se.smart.com",
    "SSANGYONG": "https://www.kgmobility.se",
    "SUBARU": "https://www.subaru.se",
    "SUZUKI": "https://www.suzuki.se",
    "TESLA": "https://www.tesla.com/sv_SE",
    "TOYOTA": "https://www.toyota.se",
    "VOLVO": "https://www.volvocars.com/se",
    "VW": "https://www.volkswagen.se",
    "XPENG": "https://www.xpeng.com/se",
    "ZEEKR": "https://www.zeekr.eu/se-se",
}

KNOWN_MODEL_URLS = {
    ("TESLA", "MODEL Y"): "https://www.tesla.com/sv_SE/modely",
    ("TESLA", "MODEL 3"): "https://www.tesla.com/sv_SE/model3",
    ("TESLA", "MODEL S"): "https://www.tesla.com/sv_SE/models",
    ("TESLA", "MODEL X"): "https://www.tesla.com/sv_SE/modelx",
    ("VOLVO", "EX30"): "https://www.volvocars.com/se/cars/ex30-electric/",
    ("VOLVO", "EX90"): "https://www.volvocars.com/se/cars/ex90-electric/",
    ("VOLVO", "ES90"): "https://www.volvocars.com/se/cars/es90-electric/",
    ("POLESTAR", "2"): "https://www.polestar.com/se/polestar-2/",
    ("POLESTAR", "3"): "https://www.polestar.com/se/polestar-3/",
    ("POLESTAR", "4"): "https://www.polestar.com/se/polestar-4/",
    ("KIA", "EV3"): "https://www.kia.com/se/nya-bilar/ev3/upptack/",
    ("KIA", "EV4"): "https://www.kia.com/se/nya-bilar/ev4/upptack/",
    ("KIA", "EV5"): "https://www.kia.com/se/nya-bilar/ev5/upptack/",
    ("KIA", "EV6"): "https://www.kia.com/se/nya-bilar/ev6/upptack/",
    ("KIA", "EV9"): "https://www.kia.com/se/nya-bilar/ev9/upptack/",
    ("SKODA", "ENYAQ"): "https://www.skoda.se/modeller/enyaq/enyaq",
    ("SKODA", "ELROQ"): "https://www.skoda.se/modeller/elroq/elroq",
    ("VW", "ID.3"): "https://www.volkswagen.se/sv/modeller/id3.html",
    ("VW", "ID.4"): "https://www.volkswagen.se/sv/modeller/id4.html",
    ("VW", "ID.5"): "https://www.volkswagen.se/sv/modeller/id5.html",
    ("VW", "ID. BUZZ"): "https://www.volkswagen.se/sv/modeller/id-buzz.html",
    ("BMW", "IX1"): "https://www.bmw.se/sv/alla-modeller/bmw-i/ix1/2022/bmw-ix1-overview.html",
    ("BMW", "IX2"): "https://www.bmw.se/sv/alla-modeller/bmw-i/ix2/2023/bmw-ix2-overview.html",
    ("BMW", "I4"): "https://www.bmw.se/sv/alla-modeller/bmw-i/i4/2024/bmw-i4-overview.html",
    ("BMW", "I5"): "https://www.bmw.se/sv/alla-modeller/bmw-i/i5/bmw-i5-sedan-overview.html",
    ("AUDI", "Q4 E-TRON"): "https://www.audi.se/se/web/sv/models/q4-e-tron/q4-e-tron.html",
    ("AUDI", "Q6 E-TRON"): "https://www.audi.se/se/web/sv/models/q6-e-tron/q6-e-tron.html",
    ("AUDI", "A6 E-TRON"): "https://www.audi.se/se/web/sv/models/a6-e-tron/a6-e-tron.html",
    ("TOYOTA", "BZ4X"): "https://www.toyota.se/nya-bilar/bz4x",
    ("NISSAN", "ARIYA"): "https://www.nissan.se/fordon/nya-fordon/ariya.html",
    ("SUBARU", "SOLTERRA"): "https://www.subaru.se/solterra",
    ("PORSCHE", "TAYCAN"): "https://www.porsche.com/sweden/models/taycan/",
    ("PORSCHE", "MACAN"): "https://www.porsche.com/sweden/models/macan/macan-electric-models/",
    ("CUPRA", "BORN"): "https://www.cupraofficial.se/bilar/cupra-born",
    ("CUPRA", "TAVASCAN"): "https://www.cupraofficial.se/bilar/cupra-tavascan",
    ("LEXUS", "RZ"): "https://www.lexus.se/new-cars/rz",
    ("FORD", "EXPLORER"): "https://www.ford.se/personbilar/explorer-elektrisk",
    ("FORD", "CAPRI"): "https://www.ford.se/personbilar/nya-capri",
    ("FORD", "MUSTANG MACH-E"): "https://www.ford.se/personbilar/mustang-mach-e",
    ("HYUNDAI", "IONIQ 5"): "https://www.hyundai.com/se/sv/elbilar/ioniq-5.html",
    ("HYUNDAI", "IONIQ 9"): "https://www.hyundai.com/se/sv/elbilar/ioniq-9.html",
    ("HYUNDAI", "INSTER"): "https://www.hyundai.com/se/sv/elbilar/inster.html",
    ("HYUNDAI", "KONA"): "https://www.hyundai.com/se/sv/bilar/kona-electric.html",
    ("MAZDA", "6E"): "https://www.mazda.se/modeller/mazda6e/",
    ("RENAULT", "5"): "https://www.renault.se/elbilar/r5-e-tech-electric.html",
    ("RENAULT", "4"): "https://www.renault.se/elbilar/r4-e-tech-electric.html",
    ("RENAULT", "SCENIC"): "https://www.renault.se/elbilar/scenic-e-tech-electric.html",
}


@dataclass
class CanonicalModel:
    brand: str
    model: str
    normalized_brand: str
    normalized_model: str
    market_seen: bool
    available_confirmed: bool
    discontinued_candidate: bool
    coming_or_low_volume: bool
    validation_status: str


@dataclass
class ModelAlias:
    brand_raw: str
    model_raw: str
    normalized_brand: str
    normalized_model: str
    alias_rule: str
    model_group: str | None
    needs_mapping: bool
    confidence: float


@dataclass
class ManufacturerSource:
    brand: str
    model: str
    source_type: str
    url: str
    title: str
    country: str
    language: str
    extraction_status: str
    extraction_confidence: float | None


def normalize(value: str) -> str:
    value = unicodedata.normalize("NFKD", value.upper())
    value = "".join(char for char in value if not unicodedata.combining(char))
    value = value.replace("&", " AND ")
    value = re.sub(r"[^A-Z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip().lower()


def display_brand(raw_brand: str) -> str:
    return BRAND_CANONICAL.get(raw_brand, raw_brand.title())


def display_model(raw_model: str) -> str:
    special = {"BZ4X": "bZ4X", "IX": "iX", "IX1": "iX1", "IX2": "iX2", "IX3": "iX3", "I4": "i4", "I5": "i5", "I7": "i7"}
    return " ".join(special.get(part, part.title()) for part in raw_model.split())


def is_ambiguous(row: dict) -> bool:
    raw = f"{row['brand_raw']} {row['model_raw']}".upper()
    return row.get("needs_mapping", "").lower() == "true" or "/" in raw or "ÖVRIGA" in raw or "OVRIGA" in normalize(raw).upper()


def official_source_for(brand_raw: str, model_raw: str) -> tuple[str, str]:
    known = KNOWN_MODEL_URLS.get((brand_raw, model_raw))
    if known:
        return known, "verified_known_model_url"
    domain = OFFICIAL_SWEDISH_DOMAINS.get(brand_raw)
    if not domain:
        query = quote_plus(f"{display_brand(brand_raw)} {display_model(model_raw)} official Sweden electric")
        return f"https://www.google.com/search?q={query}", "needs_official_domain"
    query = quote_plus(f"{display_brand(brand_raw)} {display_model(model_raw)} elbil pris Sverige")
    return f"{domain}?ev_advisor_discovery_query={query}", "official_domain_discovery_needed"


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        return
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    source_path = Path("data/mobility-sweden/processed/market_models.csv")
    out_dir = Path("data/canonical")
    rows = list(csv.DictReader(source_path.open(encoding="utf-8")))
    canonical_models: list[CanonicalModel] = []
    aliases: list[ModelAlias] = []
    sources: list[ManufacturerSource] = []
    seen = set()

    for row in rows:
        brand_raw = row["brand_raw"].strip()
        model_raw = row["model_raw"].strip()
        ambiguous = is_ambiguous(row)
        normalized_brand = normalize(BRAND_CANONICAL.get(brand_raw, brand_raw))
        normalized_model = normalize(model_raw)
        aliases.append(
            ModelAlias(
                brand_raw=brand_raw,
                model_raw=model_raw,
                normalized_brand=normalized_brand,
                normalized_model=normalized_model,
                alias_rule="mobility_sweden_exact_raw_name" if not ambiguous else "manual_mapping_required",
                model_group=f"{brand_raw} {model_raw}" if ambiguous else None,
                needs_mapping=ambiguous,
                confidence=1.0 if not ambiguous else 0.0,
            )
        )
        if ambiguous or brand_raw == "ÖVRIGA":
            continue

        key = (normalized_brand, normalized_model)
        if key in seen:
            continue
        seen.add(key)
        brand = display_brand(brand_raw)
        model = display_model(model_raw)
        ytd = int(row["registrations_ytd"])
        canonical_models.append(
            CanonicalModel(
                brand=brand,
                model=model,
                normalized_brand=normalized_brand,
                normalized_model=normalized_model,
                market_seen=True,
                available_confirmed=False,
                discontinued_candidate=False,
                coming_or_low_volume=ytd <= 5,
                validation_status="draft",
            )
        )
        url, rule = official_source_for(brand_raw, model_raw)
        sources.append(
            ManufacturerSource(
                brand=brand,
                model=model,
                source_type="manufacturer_page" if rule == "verified_known_model_url" else "importer_page",
                url=url,
                title=f"{brand} {model} official Swedish source candidate",
                country="SE",
                language="sv",
                extraction_status="draft",
                extraction_confidence=None,
            )
        )

    out_dir.mkdir(parents=True, exist_ok=True)
    write_csv(out_dir / "canonical_models_seed.csv", [asdict(row) for row in canonical_models])
    write_csv(out_dir / "model_aliases_seed.csv", [asdict(row) for row in aliases])
    write_csv(out_dir / "manufacturer_sources_seed.csv", [asdict(row) for row in sources])
    (out_dir / "canonical_models_seed.json").write_text(json.dumps([asdict(row) for row in canonical_models], ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / "manufacturer_sources_seed.json").write_text(json.dumps([asdict(row) for row in sources], ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Canonical draft models: {len(canonical_models)}")
    print(f"Model aliases: {len(aliases)}")
    print(f"Manufacturer source candidates: {len(sources)}")
    print(f"Manual mapping aliases: {sum(1 for row in aliases if row.needs_mapping)}")


if __name__ == "__main__":
    main()
