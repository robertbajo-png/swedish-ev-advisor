import csv
import html.parser
import argparse
import re
from pathlib import Path
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]


class LinkParser(html.parser.HTMLParser):
    def __init__(self):
        super().__init__()
        self.links: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag != "a":
            return
        for key, value in attrs:
            if key == "href" and value:
                self.links.append(value)


def tokens(value: str) -> list[str]:
    return [part for part in re.sub(r"[^a-zA-Z0-9åäöÅÄÖ]+", " ", value).lower().split() if len(part) > 1]


def fetch_links(url: str, timeout: int) -> list[str]:
    request = Request(url, headers={"User-Agent": "swedish-ev-advisor/0.1"})
    with urlopen(request, timeout=timeout) as response:
        body = response.read().decode("utf-8", errors="replace")
    parser = LinkParser()
    parser.feed(body)
    return [urljoin(url, link) for link in parser.links]


def same_host(a: str, b: str) -> bool:
    return urlparse(a).netloc.lower().replace("www.", "") == urlparse(b).netloc.lower().replace("www.", "")


def score_link(link: str, brand: str, model: str) -> int:
    haystack = link.lower()
    score = 0
    for token in tokens(model):
        if token in haystack:
            score += 4
    for token in ("el", "electric", "elbilar", "modeller", "bilar", "pris"):
        if token in haystack:
            score += 1
    return score


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int)
    parser.add_argument("--timeout", type=int, default=8)
    args = parser.parse_args()
    source_path = ROOT / "data/canonical/manufacturer_sources_validated.csv"
    rows = list(csv.DictReader(source_path.open(encoding="utf-8")))
    discovered = []
    candidates = [
        row
        for row in rows
        if row.get("source_validation") == "needs_discovery" and "ev_advisor_discovery_query=" in row["url"]
    ]
    if args.limit:
        candidates = candidates[: args.limit]
    for row in candidates:
        base = row["url"].split("?")[0]
        try:
            links = [link for link in fetch_links(base, args.timeout) if same_host(base, link)]
        except Exception as error:
            discovered.append({**row, "discovered_url": "", "discovery_status": f"failed:{error}"})
            continue
        ranked = sorted(links, key=lambda link: score_link(link, row["brand"], row["model"]), reverse=True)
        best = ranked[0] if ranked and score_link(ranked[0], row["brand"], row["model"]) > 0 else ""
        discovered.append({**row, "discovered_url": best, "discovery_status": "candidate_found" if best else "no_candidate"})

    out_path = ROOT / "data/canonical/manufacturer_sources_discovery_candidates.csv"
    if discovered:
        with out_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(discovered[0].keys()))
            writer.writeheader()
            writer.writerows(discovered)
    print(f"Discovery candidates written: {sum(1 for row in discovered if row.get('discovered_url'))}/{len(discovered)}")


if __name__ == "__main__":
    main()
