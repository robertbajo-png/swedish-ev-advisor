import json
import sqlite3
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB_PATH = ROOT / "data/local/ev_advisor.sqlite"
SQLITE_SCHEMA_PATH = ROOT / "database/sqlite_schema.sql"


def connect(db_path: Path = DEFAULT_DB_PATH) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    connection.execute("pragma foreign_keys = on")
    return connection


def apply_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(SQLITE_SCHEMA_PATH.read_text(encoding="utf-8"))
    connection.commit()


def serialize_value(value):
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, bool):
        return int(value)
    return value


def upsert_rows(connection: sqlite3.Connection, table: str, rows: list[dict], conflict_columns: list[str]) -> None:
    if not rows:
        return
    columns = list(rows[0].keys())
    placeholders = ", ".join("?" for _ in columns)
    column_sql = ", ".join(columns)
    conflict_sql = ", ".join(conflict_columns)
    update_columns = [column for column in columns if column not in conflict_columns and column != "id"]
    update_sql = ", ".join(f"{column}=excluded.{column}" for column in update_columns)
    sql = f"insert into {table} ({column_sql}) values ({placeholders}) on conflict ({conflict_sql}) do update set {update_sql}"
    values = [[serialize_value(row.get(column)) for column in columns] for row in rows]
    connection.executemany(sql, values)
    connection.commit()


def fetch_id_map(connection: sqlite3.Connection, table: str, key_columns: list[str]) -> dict[tuple, int]:
    columns = ", ".join(["id", *key_columns])
    rows = connection.execute(f"select {columns} from {table}").fetchall()
    return {tuple(row[column] for column in key_columns): row["id"] for row in rows}


def public_variant_rows(connection: sqlite3.Connection) -> list[dict]:
    rows = connection.execute("select * from public_ev_variants order by brand, model, variant_name").fetchall()
    return [dict(row) for row in rows]
