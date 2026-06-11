# Canonical resolution log

Decisions taken when resolving Mobility Sweden model bundling against canonical EV models.

## Source of truth

- **`data/canonical/model_aliases_resolved.csv`** — authoritative mapping from Mobility Sweden raw names to canonical models.
- `data/canonical/model_aliases_seed.csv` — raw alias dictionary (preserves original Mobility Sweden naming for reproducibility); alias_rule column reflects resolution status.
- `data/canonical/canonical_models_seed.csv` — canonical EV models including newly added split variants.
- `data/canonical/manufacturer_sources_seed.csv` — verified manufacturer URLs per canonical model.

## Decisions

### 1. EV-only filter eliminates four ambiguities

Mobility Sweden bundles EV and ICE/PHEV under shared model names (`VOLVO EX/XC40`, `VOLVO EC/C40`, `MERCEDES CLA`, `RENAULT SCENIC`). Since `data/mobility-sweden/processed/market_models.csv` is pre-filtered to `fuel_type_raw=EL`, all rows in this dataset are exclusively the EV variant. Mapping rule: `fuel_type_raw=EL && bundled_name -> canonical_ev_name`. Confidence: **high**.

| Mobility Sweden | Canonical | YTD |
|---|---|---|
| VOLVO EX/XC40 | Volvo EX40 | 2 945 |
| VOLVO EC/C40 | Volvo EC40 | 594 |
| MERCEDES CLA | Mercedes-Benz CLA EQ | 460 |
| RENAULT SCENIC | Renault Scenic E-Tech | 179 |

**Total resolved at high confidence: 4 178 registrations (71.7 % of flagged volume).**

### 2. Body-variant splits cannot be quantified

Two cases bundle body variants that have separate URLs and specifications on the manufacturer site but cannot be split at the registration level without VIN data:

- **VW ID.7 / ID.7 TOURER** (1 436 YTD) — Sedan and Tourer bundled in Mobility Sweden. Sedan treated as primary canonical for registration attribution; Tourer added as secondary canonical with its own source URLs (volkswagen.se/sv/modeller/id7-tourer.html) but no direct registration count. Total volume credited to ID.7 family.
- **MERCEDES EQE** (124 YTD) — Sedan and SUV bundled. Same treatment: Sedan primary, SUV secondary canonical pointing to /passengercars/models/suv/eqe/overview.html.

**Confidence: medium.** Per-variant attribution becomes possible if Trafikverket's vehicle register or a future Mobility Sweden split is integrated.

### 3. Volvo ÖVRIGA left in quarantine

`VOLVO ÖVRIGA` (92 YTD) bundles low-volume Volvo EVs not split out individually — potentially EM90 imports, special editions, or fleet-only variants. Cannot be safely attributed without inspecting raw XLSX detail tabs from Mobility Sweden.

**Status: needs_review.** Held in quarantine — does not block other publishing. Add review ticket: "Resolve VOLVO ÖVRIGA monthly composition by inspecting source XLSX detail tabs."

## Newly added canonical models

| Brand | Model | Reason |
|---|---|---|
| Volvo | EX40 | EV variant of (former) XC40 Recharge |
| Volvo | EC40 | EV variant of (former) C40 Recharge |
| Volkswagen | ID.7 Tourer | Body split from ID.7 sedan |
| Mercedes-Benz | CLA EQ | EV variant of CLA family |
| Renault | Scenic E-Tech | EV-only Scenic generation |
| Mercedes-Benz | EQE Sedan | Body split (was bundled with SUV) |
| Mercedes-Benz | EQE SUV | Body split (was bundled with Sedan) |

## Resolution summary

| Status | Registrations YTD | Share |
|---|---|---|
| High confidence resolved | 4 178 | 71.7 % |
| Medium confidence (family-level) | 1 560 | 26.8 % |
| Needs review (ÖVRIGA) | 92 | 1.6 % |
| **Total flagged volume** | **5 830** | **100 %** |

**Phase 3 unblocked for 98.4 % of flagged registration volume** (5 738 of 5 830). Remaining 92 registrations held in review queue without blocking downstream publishing.

## Pipeline integration notes

When `validate_manufacturer_sources.py` (Phase 4 entry point) joins market data to canonical models, it should:

1. Read `model_aliases_resolved.csv` first to apply EV-only filter mappings.
2. Fall back to `model_aliases_seed.csv` for unflagged 1:1 mappings.
3. Treat alias_rule values `resolved_ev_only_filter` and `resolved_split_into_two_canonicals` as authoritative.
4. Skip rows where alias_rule is `manual_mapping_required` (currently only `VOLVO ÖVRIGA` and `ÖVRIGA FABRIKAT`).
