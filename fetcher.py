"""Phase 1: daily EDGAR full-text search fetcher for SC TO-T / S-4 filings."""

import argparse
import json
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

import requests

# --- Config (single place for the User-Agent, per CLAUDE.md) ---
USER_AGENT = "Andy Maru Andymaru17@gmail.com"
SEARCH_URL = "https://efts.sec.gov/LATEST/search-index"
FORMS = "SC TO-T,S-4"
PAGE_SIZE = 100
RATE_LIMIT_SLEEP = 0.15  # combined cap across www.sec.gov and efts.sec.gov is 10 req/s
RAW_DIR = Path("data/raw")

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": USER_AGENT})


def _request_page(date: str, offset: int) -> dict:
    params = {"q": "", "forms": FORMS, "startdt": date, "enddt": date, "from": offset}
    prepared = SESSION.prepare_request(requests.Request("GET", SEARCH_URL, params=params))
    print(f"[fetch] GET {prepared.url}")
    resp = SESSION.send(prepared, timeout=30)
    resp.raise_for_status()
    time.sleep(RATE_LIMIT_SLEEP)
    return resp.json()


def _flatten(pages: list[dict]) -> list[dict]:
    hits = []
    for page in pages:
        hits.extend(page["hits"]["hits"])
    return hits


def fetch_filings(date: str, force: bool = False) -> list[dict]:
    """Fetch all SC TO-T / S-4 filings for a given date, paginating as needed.

    Returns the flattened list of hit dicts. Caches the complete raw API
    response(s) to data/raw/{date}.json before any processing; reuses that
    cache on subsequent calls unless force=True.
    """
    raw_path = RAW_DIR / f"{date}.json"

    if raw_path.exists() and not force:
        print(f"[fetch] cache hit: loading {raw_path}")
        cached = json.loads(raw_path.read_text())
        return _flatten(cached["pages"])

    pages = []
    offset = 0
    total = None
    while total is None or offset < total:
        page = _request_page(date, offset)
        pages.append(page)
        total = page["hits"]["total"]["value"]
        offset += len(page["hits"]["hits"])
        print(f"[fetch] got {offset}/{total} hits")
        if not page["hits"]["hits"]:
            break  # safety valve against an infinite loop on an unexpected empty page

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    raw_path.write_text(json.dumps({"date": date, "pages": pages}, indent=2))
    print(f"[fetch] saved raw response to {raw_path}")

    return _flatten(pages)


def dedupe_filings(hits: list[dict]) -> tuple[list[dict], dict]:
    """Group filings sharing a file_num into one deal record per group.

    Does NOT assign acquirer/target roles - that requires the index page
    labels and is Phase 2 work.
    """
    pre_dedup_counts = Counter(h["_source"]["form"] for h in hits)

    groups = defaultdict(list)
    for h in hits:
        file_nums = h["_source"].get("file_num") or []
        key = file_nums[0] if file_nums else h["_source"]["adsh"]
        groups[key].append(h)

    deals = []
    for file_num, group_hits in groups.items():
        non_amendments = [h for h in group_hits if "/A" not in h["_source"]["form"]]
        if non_amendments:
            original = min(non_amendments, key=lambda h: h["_source"]["file_date"])
        else:
            original = min(group_hits, key=lambda h: h["_source"]["file_date"])

        amendment_count = sum(1 for h in group_hits if "/A" in h["_source"]["form"])
        src = original["_source"]

        deals.append({
            "form": src["form"],
            "file_date": src["file_date"],
            "adsh": src["adsh"],
            "file_num": file_num,
            "ciks": [str(c).zfill(10) for c in src["ciks"]],
            "display_names": src["display_names"],
            "amendment_count": amendment_count,
        })

    post_dedup_counts = Counter()
    for deal in deals:
        base_form = deal["form"].split("/")[0]
        post_dedup_counts[base_form] += 1

    summary = {
        "total_hits": len(hits),
        "pre_dedup_counts": dict(pre_dedup_counts),
        "post_dedup_counts": {"total_deals": len(deals), **dict(post_dedup_counts)},
    }

    return deals, summary


def main():
    parser = argparse.ArgumentParser(description="Fetch and dedupe daily EDGAR SC TO-T / S-4 filings.")
    parser.add_argument("date", help="Date to query, YYYY-MM-DD")
    parser.add_argument("--force", action="store_true", help="Re-fetch even if a cached raw file exists")
    args = parser.parse_args()

    hits = fetch_filings(args.date, force=args.force)
    deals, summary = dedupe_filings(hits)

    print()
    print("=== Checkpoint 1 summary ===")
    print(f"Date: {args.date}")
    print(f"Total hits: {summary['total_hits']}")
    print(f"Pre-dedup counts by form: {summary['pre_dedup_counts']}")
    print(f"Unique deals after dedup: {summary['post_dedup_counts']['total_deals']}")
    print(f"Post-dedup counts by base form: "
          f"{ {k: v for k, v in summary['post_dedup_counts'].items() if k != 'total_deals'} }")
    print()
    print("=== Deals ===")
    for deal in sorted(deals, key=lambda d: d["file_date"]):
        companies = "; ".join(deal["display_names"])
        print(f"{deal['file_date']}  {deal['form']:<12}  {companies}  "
              f"(amendments: {deal['amendment_count']})")


if __name__ == "__main__":
    main()
