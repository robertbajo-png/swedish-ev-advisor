import csv
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def check_url(url: str) -> tuple[int | None, str | None, str | None, str | None]:
    if "ev_advisor_discovery_query=" in url or "google.com/search" in url:
        return None, "discovery_needed", None, None
    request = Request(url, headers={"User-Agent": "swedish-ev-advisor/0.1"})
    try:
        with urlopen(request, timeout=20) as response:
            body = response.read()
            return response.status, response.geturl(), hashlib.sha256(body).hexdigest(), datetime.now(timezone.utc).isoformat()
    except HTTPError as error:
        return error.code, None, None, None
    except (TimeoutError, URLError):
        return None, None, None, None


def main() -> None:
    source_path = Path("data/canonical/manufacturer_sources_seed.csv")
    out_path = Path("data/canonical/manufacturer_sources_validated.csv")
    rows = list(csv.DictReader(source_path.open(encoding="utf-8")))
    output = []
    for row in rows:
        status, final_url, content_hash, fetched_at = check_url(row["url"])
        row["http_status"] = "" if status is None else status
        row["final_url"] = final_url or ""
        row["content_hash"] = content_hash or ""
        row["fetched_at"] = fetched_at or ""
        row["source_validation"] = (
            "reachable_official_model_source"
            if status and 200 <= status < 400
            else "needs_discovery"
            if status is None
            else "unreachable_or_redirect_problem"
        )
        output.append(row)

    with out_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(output[0].keys()))
        writer.writeheader()
        writer.writerows(output)

    reachable = sum(1 for row in output if row["source_validation"] == "reachable_official_model_source")
    discovery = sum(1 for row in output if row["source_validation"] == "needs_discovery")
    broken = len(output) - reachable - discovery
    print(f"Reachable official model sources: {reachable}")
    print(f"Need source discovery: {discovery}")
    print(f"Unreachable/problem sources: {broken}")


if __name__ == "__main__":
    main()
