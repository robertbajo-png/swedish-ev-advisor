import hashlib
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS_DIR = ROOT / "database" / "migrations"
OUTPUT_PATH = ROOT / "database" / "supabase_migration_bundle.sql"


def migration_files() -> list[Path]:
    return sorted(MIGRATIONS_DIR.glob("*.sql"))


def build_bundle(files: list[Path] | None = None) -> str:
    files = files or migration_files()
    generated_at = datetime.now(timezone.utc).isoformat()
    lines = [
        "-- Swedish EV Advisor Supabase migration bundle",
        f"-- Generated at: {generated_at}",
        "-- Apply in Supabase SQL Editor or via psql against the project database.",
        "-- Migrations are kept idempotent where possible.",
        "",
    ]

    for path in files:
        sql = path.read_text(encoding="utf-8").strip()
        digest = hashlib.sha256(sql.encode("utf-8")).hexdigest()
        lines.extend(
            [
                "",
                f"-- BEGIN {path.name}",
                f"-- sha256: {digest}",
                sql,
                f"-- END {path.name}",
                "",
            ]
        )

    return "\n".join(lines).rstrip() + "\n"


def main() -> None:
    files = migration_files()
    if not files:
        raise SystemExit("No migration files found.")
    bundle = build_bundle(files)
    OUTPUT_PATH.write_text(bundle, encoding="utf-8")
    print(f"Wrote {OUTPUT_PATH.relative_to(ROOT)} with {len(files)} migrations.")


if __name__ == "__main__":
    main()
