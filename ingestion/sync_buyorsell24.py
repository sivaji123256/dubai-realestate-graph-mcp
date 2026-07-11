"""
Incremental daily sync from the BuyOrSell24 API (api.buyorsell24.com) --
a third-party product built on official DLD data via Dubai Pulse Open Data,
empirically verified to have transactions as recent as days old (unlike the
Kaggle mirror ingestion/check_and_refresh.py watches, which only updates
whenever its uploader feels like it).

Deliberately forward-only: the graph's existing Dec 2025-Feb 2026 window
(from the original Kaggle-based bulk load) is left as-is. This script syncs
NEW data from "now" onward and does not attempt to backfill the gap in
between -- doing so would add 100K+ transactions and blow past AuraDB
Free's 200K node cap. See the "Incremental Live Sync" plan for the reasoning.

Free tier: 35 requests/day, 20 records/page (~700 records/day) -- close to
Dubai's actual daily citywide transaction volume, so this is designed to
self-correct if a single day's volume exceeds the budget (see the pagination
strategy below) rather than assuming it always fits.

Requires NEO4J_URI / NEO4J_USER / NEO4J_PASSWORD / BUYORSELL24_API_KEY in
the environment.
"""

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
sys.path.insert(0, ROOT)

from neo4j_client import run_read, run_write  # noqa: E402

API_BASE = "https://api.buyorsell24.com/api/v1"
PER_PAGE = 20
REQUEST_BUDGET = 30  # out of a 35/day cap -- leaves headroom for manual debugging
PACE_SECONDS = 7  # their limit is 10/min; 7s keeps us safely under that

MERGE_QUERY = """
UNWIND $rows AS row
MERGE (t:Transaction {id: row.id})
SET t.date = date(row.date),
    t.price = row.price,
    t.price_per_sqm = row.price_per_sqm,
    t.area_sqm = row.area_sqm,
    t.rooms = row.rooms,
    t.has_parking = row.has_parking

FOREACH (_ IN CASE WHEN row.area IS NOT NULL THEN [1] ELSE [] END |
  MERGE (a:Area {name: row.area})
  MERGE (t)-[:IN_AREA]->(a)
)
FOREACH (_ IN CASE WHEN row.building IS NOT NULL THEN [1] ELSE [] END |
  MERGE (b:Building {name: row.building})
  MERGE (t)-[:IN_BUILDING]->(b)
)
FOREACH (_ IN CASE WHEN row.building IS NOT NULL AND row.project IS NOT NULL THEN [1] ELSE [] END |
  MERGE (b2:Building {name: row.building})
  MERGE (p2:Project {name: row.project})
  MERGE (b2)-[:PART_OF]->(p2)
)
FOREACH (_ IN CASE WHEN row.project IS NOT NULL AND row.master_project IS NOT NULL THEN [1] ELSE [] END |
  MERGE (p3:Project {name: row.project})
  MERGE (mp:MasterProject {name: row.master_project})
  MERGE (p3)-[:PART_OF]->(mp)
)
FOREACH (_ IN CASE WHEN row.property_type IS NOT NULL THEN [1] ELSE [] END |
  MERGE (pt:PropertyType {name: row.property_type})
  MERGE (t)-[:OF_TYPE]->(pt)
)
FOREACH (_ IN CASE WHEN row.property_sub_type IS NOT NULL THEN [1] ELSE [] END |
  MERGE (pst:PropertySubType {name: row.property_sub_type})
  MERGE (t)-[:OF_SUBTYPE]->(pst)
)
"""


def none_if_blank(v):
    return v if v not in (None, "") else None


def api_get(path, params, retries=3):
    api_key = os.environ["BUYORSELL24_API_KEY"]
    qs = urllib.parse.urlencode(params)
    url = f"{API_BASE}{path}?{qs}"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {api_key}"})
    last_error = None
    for attempt in range(retries):
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8")
        if raw.strip():
            return json.loads(raw)
        # Empirically an intermittent upstream/Cloudflare caching glitch (HTTP 200
        # with an empty body) rather than a real error -- retry with backoff.
        last_error = "empty response body"
        time.sleep(3 * (attempt + 1))
    raise RuntimeError(f"api_get failed after {retries} attempts: {last_error}")


def fetch_page(cursor_date, page):
    body = api_get("/transactions", {"date_from": cursor_date, "per_page": PER_PAGE, "page": page})
    time.sleep(PACE_SECONDS)
    return body


def map_record(rec):
    if rec.get("trans_group_en") != "Sales":
        return None
    instance_date = rec.get("instance_date")
    if not instance_date:
        return None
    date_part = instance_date.split(" ")[0]
    return {
        "id": f"bos24-{rec['id']}",
        "date": date_part,
        "area": none_if_blank(rec.get("area_name_en")),
        "building": none_if_blank(rec.get("building_name_en")),
        "project": none_if_blank(rec.get("project_name_en")),
        "master_project": none_if_blank(rec.get("master_project_en")),
        "property_type": none_if_blank(rec.get("property_type_en")),
        "property_sub_type": none_if_blank(rec.get("property_sub_type_en")),
        "rooms": none_if_blank(rec.get("rooms_en")),
        "has_parking": bool(rec.get("has_parking")),
        "area_sqm": rec.get("procedure_area"),
        "price": rec.get("actual_worth"),
        "price_per_sqm": rec.get("meter_sale_price"),
    }


def get_cursor_date():
    rows = run_read(
        "MATCH (s:SyncState {source: 'buyorsell24'}) RETURN toString(s.cursor_date) AS cursor_date"
    )
    return rows[0]["cursor_date"] if rows else None


def set_cursor_date(cursor_date_str):
    run_write(
        """
        MERGE (s:SyncState {source: 'buyorsell24'})
        SET s.cursor_date = date($cursor_date), s.last_synced_at = datetime()
        """,
        cursor_date=cursor_date_str,
    )


def load_records(records):
    mapped = [m for m in (map_record(r) for r in records) if m]
    if mapped:
        run_write(MERGE_QUERY, rows=mapped)
    return mapped


def report_graph_size():
    total_nodes = run_read("MATCH (n) RETURN count(n) AS c")[0]["c"]
    print(f"Total nodes in graph: {total_nodes:,}")
    if total_nodes > 150_000:
        print("WARNING: approaching AuraDB Free's 200,000 node limit.")


BOOTSTRAP_LOOKBACK_DAYS = 30  # BuyOrSell24's own pipeline has processing lag behind
# real-world "today" (empirically ~2 weeks when this was checked) -- starting the
# cursor at "yesterday" would find nothing yet. 30 days back comfortably covers that
# lag; the backlog-clearing pagination logic below safely handles however much (or
# little) data actually exists in that window either way.


def main():
    cursor_date = get_cursor_date()
    if cursor_date is None:
        cursor_date = (datetime.now(UTC).date() - timedelta(days=BOOTSTRAP_LOOKBACK_DAYS)).isoformat()
        print(
            f"No prior sync state -- starting fresh from {cursor_date} "
            f"({BOOTSTRAP_LOOKBACK_DAYS} days back, to comfortably cover BuyOrSell24's own "
            f"pipeline lag). The gap before this date is a deliberate, accepted trade-off, not a bug."
        )

    print(f"Syncing from cursor_date={cursor_date} ...")

    try:
        first_page = fetch_page(cursor_date, 1)
    except urllib.error.HTTPError as e:
        print(f"ERROR on initial request: HTTP {e.code} -- {e.read().decode(errors='replace')}")
        return

    total_pages = first_page["total_pages"]
    total_records = first_page["total"]
    print(f"  {total_records} records available since {cursor_date}, across {total_pages} pages")
    requests_used = 1

    if total_pages <= REQUEST_BUDGET:
        all_records = list(first_page["data"])
        completed = True
        for page in range(2, total_pages + 1):
            if requests_used >= REQUEST_BUDGET:
                completed = False
                break
            try:
                body = fetch_page(cursor_date, page)
            except urllib.error.HTTPError as e:
                print(f"  Stopping early: HTTP {e.code} on page {page}")
                completed = False
                break
            requests_used += 1
            all_records.extend(body["data"])

        mapped = load_records(all_records)
        if completed:
            # Every record in [cursor_date, now) has been seen (Sales or not) --
            # safe to advance the cursor past all of them, even if none were Sales.
            all_dates = [r["instance_date"].split(" ")[0] for r in all_records if r.get("instance_date")]
            max_date = max(all_dates, default=None)
            if max_date:
                next_cursor = (datetime.strptime(max_date, "%Y-%m-%d").date() + timedelta(days=1)).isoformat()
                set_cursor_date(next_cursor)
                print(f"Fully caught up. {len(mapped)} Sales transactions synced. Cursor advanced to {next_cursor}.")
            else:
                set_cursor_date(cursor_date)
                print("Fully caught up. No records at all since last sync.")
        else:
            # Ran out of budget partway through a range that would otherwise have
            # fit -- persist the same cursor (not advanced) so tomorrow resumes
            # here instead of re-bootstrapping the 30-day lookback from scratch.
            set_cursor_date(cursor_date)
            print(f"Partial progress: {len(mapped)} Sales transactions synced. Cursor held at {cursor_date}.")
    else:
        print(
            f"  Backlog ({total_pages} pages) exceeds today's budget ({REQUEST_BUDGET} requests) "
            f"-- clearing the oldest unfetched pages first; cursor stays put until fully caught up"
        )
        all_records = []
        page = total_pages
        while requests_used < REQUEST_BUDGET and page >= 1:
            try:
                body = fetch_page(cursor_date, page)
            except urllib.error.HTTPError as e:
                print(f"  Stopping early: HTTP {e.code} on page {page}")
                break
            requests_used += 1
            all_records.extend(body["data"])
            page -= 1

        mapped = load_records(all_records)
        set_cursor_date(cursor_date)  # persist so tomorrow resumes from here, not a fresh bootstrap
        print(
            f"Partial catch-up: {len(mapped)} Sales transactions synced from the oldest "
            f"{requests_used} pages. Will continue clearing backlog on the next run."
        )

    report_graph_size()


if __name__ == "__main__":
    main()
