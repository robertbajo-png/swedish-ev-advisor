import json
import os
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class SupabaseRestClient:
    def __init__(self, url: str | None = None, service_role_key: str | None = None):
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
        with urlopen(request, timeout=60) as response:
            body = response.read().decode("utf-8")
            return json.loads(body) if body else None

    def upsert(self, table: str, rows: list[dict], on_conflict: str, returning: bool = True):
        if not rows:
            return []
        prefer = "resolution=merge-duplicates"
        prefer += ",return=representation" if returning else ",return=minimal"
        return self._request(
            "POST",
            table,
            rows,
            query={"on_conflict": on_conflict},
            prefer=prefer,
        )

    def select(self, table: str, columns: str = "*", filters: dict | None = None):
        query = {"select": columns}
        if filters:
            query.update(filters)
        return self._request("GET", table, query=query)
