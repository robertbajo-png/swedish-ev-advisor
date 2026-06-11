import json
import os
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]


def load_local_env() -> None:
    for path in (ROOT / ".env.local", ROOT / ".env"):
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, raw_value = stripped.split("=", 1)
            key = key.strip()
            if key and key not in os.environ:
                os.environ[key] = raw_value.strip().strip("'\"")


class SupabaseRestClient:
    def __init__(self, url: str | None = None, service_role_key: str | None = None):
        load_local_env()
        self.url = (url or os.environ.get("SUPABASE_URL") or "").rstrip("/")
        self.key = service_role_key or os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or ""
        if not self.url or not self.key:
            raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are required")

    def _request(self, method: str, path: str, payload=None, query: dict | None = None, prefer: str | None = None):
        query_string = f"?{urlencode(query, doseq=True)}" if query else ""
        data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers = {
            "apikey": self.key,
            "Authorization": f"Bearer {self.key}",
            "Content-Type": "application/json",
        }
        if prefer:
            headers["Prefer"] = prefer
        request = Request(f"{self.url}/rest/v1/{path}{query_string}", data=data, headers=headers, method=method)
        try:
            with urlopen(request, timeout=60) as response:
                body = response.read().decode("utf-8")
                return json.loads(body) if body else None
        except HTTPError as error:
            body = error.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Supabase {method} {path} failed with HTTP {error.code}: {body}") from error

    def upsert(self, table: str, rows: list[dict], on_conflict: str, returning: bool = True, batch_size: int = 500):
        if not rows:
            return []
        columns = []
        for row in rows:
            for key in row:
                if key not in columns:
                    columns.append(key)
        normalized_rows = [{key: row.get(key) for key in columns} for row in rows]
        returned = []
        for start in range(0, len(normalized_rows), batch_size):
            batch = normalized_rows[start : start + batch_size]
            prefer = "resolution=merge-duplicates"
            prefer += ",return=representation" if returning else ",return=minimal"
            result = self._request(
                "POST",
                table,
                batch,
                query={"on_conflict": on_conflict},
                prefer=prefer,
            )
            if returning and result:
                returned.extend(result)
        return returned

    def select(self, table: str, columns: str = "*", filters: dict | None = None):
        query = {"select": columns}
        if filters:
            query.update(filters)
        return self._request("GET", table, query=query)
