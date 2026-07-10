"""
Stream-filter the raw DLD Transactions.csv down to a recent slice of Sales
transactions small enough to fit Neo4j AuraDB Free (200K nodes / 400K rels).

Strategy:
  1. Pass 1: scan the whole file, tally Sales-transaction counts per (year, month).
  2. Pick the most recent trailing run of months whose cumulative row count is the
     largest that stays under TRANSACTION_BUDGET (each transaction fans out to a
     handful of reference-entity relationships, so bounding transaction count
     bounds both nodes and relationships with headroom to spare).
  3. Pass 2: re-scan, keep only Sales rows in the selected months, clean/rename
     columns, write data/processed/transactions_recent.csv.
  4. Compute exact distinct reference-entity counts + edge counts over the kept
     rows and write data/processed/manifest.json.
"""

import csv
import json
import os
from collections import Counter
from datetime import datetime

csv.field_size_limit(2**31 - 1)

HERE = os.path.dirname(os.path.abspath(__file__))
RAW_PATH = os.path.join(HERE, "..", "data", "raw", "Transactions.csv")
OUT_CSV = os.path.join(HERE, "..", "data", "processed", "transactions_recent.csv")
OUT_MANIFEST = os.path.join(HERE, "..", "data", "processed", "manifest.json")

TRANSACTION_BUDGET = 55_000  # ~6 edges/txn -> ~330K rels, ~63K nodes total: safe headroom under 400K/200K

REF_FIELDS = [
    "area_name_en",
    "building_name_en",
    "project_name_en",
    "master_project_en",
    "property_type_en",
    "property_sub_type_en",
    "nearest_metro_en",
    "nearest_mall_en",
    "nearest_landmark_en",
]


def clean(v):
    if v is None:
        return None
    v = v.strip()
    if v == "" or v.lower() == "null":
        return None
    return v


def to_iso_date(v):
    v = clean(v)
    if v is None:
        return None
    try:
        return datetime.strptime(v, "%d-%m-%Y").strftime("%Y-%m-%d")
    except ValueError:
        return None


def to_float(v):
    v = clean(v)
    if v is None:
        return None
    try:
        return float(v)
    except ValueError:
        return None


def month_key(iso_date):
    return iso_date[:7]  # "YYYY-MM"


def pass1_month_counts():
    counts = Counter()
    with open(RAW_PATH, encoding="utf-8") as f:
        r = csv.DictReader(f)
        for row in r:
            if row["trans_group_en"] != "Sales":
                continue
            d = to_iso_date(row["instance_date"])
            if d is None:
                continue
            counts[month_key(d)] += 1
    return counts


def select_months(counts):
    months_desc = sorted(counts.keys(), reverse=True)
    selected = []
    total = 0
    for m in months_desc:
        if total + counts[m] > TRANSACTION_BUDGET and selected:
            break
        selected.append(m)
        total += counts[m]
        if total >= TRANSACTION_BUDGET:
            break
    return set(selected), total


def pass2_filter_and_write(selected_months):
    ref_sets = {f: set() for f in REF_FIELDS}
    edge_counts = Counter()
    row_count = 0

    os.makedirs(os.path.dirname(OUT_CSV), exist_ok=True)
    out_fields = [
        "id",
        "date",
        "area",
        "building",
        "project_number",
        "project",
        "master_project",
        "property_type",
        "property_sub_type",
        "nearest_metro",
        "nearest_mall",
        "nearest_landmark",
        "rooms",
        "has_parking",
        "area_sqm",
        "price",
        "price_per_sqm",
    ]

    with open(RAW_PATH, encoding="utf-8") as fin, open(
        OUT_CSV, "w", newline="", encoding="utf-8"
    ) as fout:
        reader = csv.DictReader(fin)
        writer = csv.DictWriter(fout, fieldnames=out_fields)
        writer.writeheader()

        for row in reader:
            if row["trans_group_en"] != "Sales":
                continue
            d = to_iso_date(row["instance_date"])
            if d is None or month_key(d) not in selected_months:
                continue

            area = clean(row["area_name_en"])
            building = clean(row["building_name_en"])
            project = clean(row["project_name_en"])
            master_project = clean(row["master_project_en"])
            ptype = clean(row["property_type_en"])
            psubtype = clean(row["property_sub_type_en"])
            metro = clean(row["nearest_metro_en"])
            mall = clean(row["nearest_mall_en"])
            landmark = clean(row["nearest_landmark_en"])

            out = {
                "id": row["transaction_id"],
                "date": d,
                "area": area,
                "building": building,
                "project_number": clean(row["project_number"]),
                "project": project,
                "master_project": master_project,
                "property_type": ptype,
                "property_sub_type": psubtype,
                "nearest_metro": metro,
                "nearest_mall": mall,
                "nearest_landmark": landmark,
                "rooms": clean(row["rooms_en"]),
                "has_parking": clean(row["has_parking"]),
                "area_sqm": to_float(row["procedure_area"]),
                "price": to_float(row["actual_worth"]),
                "price_per_sqm": to_float(row["meter_sale_price"]),
            }
            writer.writerow(out)
            row_count += 1

            if area:
                ref_sets["area_name_en"].add(area)
                edge_counts["IN_AREA"] += 1
            if building:
                ref_sets["building_name_en"].add(building)
                edge_counts["IN_BUILDING"] += 1
            if project:
                ref_sets["project_name_en"].add(project)
            if master_project:
                ref_sets["master_project_en"].add(master_project)
            if ptype:
                ref_sets["property_type_en"].add(ptype)
                edge_counts["OF_TYPE"] += 1
            if psubtype:
                ref_sets["property_sub_type_en"].add(psubtype)
                edge_counts["OF_SUBTYPE"] += 1
            if metro:
                ref_sets["nearest_metro_en"].add(metro)
                edge_counts["NEAR_METRO"] += 1
            if mall:
                ref_sets["nearest_mall_en"].add(mall)
                edge_counts["NEAR_MALL"] += 1
            if landmark:
                ref_sets["nearest_landmark_en"].add(landmark)
                edge_counts["NEAR_LANDMARK"] += 1

    # static reference edges (Building-PART_OF->Project, Project-PART_OF->MasterProject)
    # approximated here as <= number of distinct buildings / projects (exact count
    # computed by the loader itself since it dedups pairs while streaming the CSV)
    node_total = row_count + sum(len(s) for s in ref_sets.values())
    rel_total = sum(edge_counts.values()) + len(ref_sets["building_name_en"]) + len(
        ref_sets["project_name_en"]
    )

    manifest = {
        "generated_at": datetime.now().isoformat(),
        "source": "kaggle:waelr1985/dubai-real-estate-transaction (DLD Transactions.csv)",
        "filter": {"trans_group_en": "Sales", "months": sorted(selected_months)},
        "row_count": row_count,
        "distinct_reference_entities": {k: len(v) for k, v in ref_sets.items()},
        "estimated_node_count": node_total,
        "estimated_relationship_count": rel_total,
        "aura_free_limits": {"nodes": 200_000, "relationships": 400_000},
    }
    with open(OUT_MANIFEST, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    return manifest


def main():
    print(f"Pass 1: tallying Sales transactions per month from {RAW_PATH} ...")
    counts = pass1_month_counts()
    total_sales = sum(counts.values())
    print(f"  total Sales rows in file: {total_sales:,} across {len(counts)} months")

    selected_months, projected_rows = select_months(counts)
    print(
        f"Selected {len(selected_months)} months "
        f"({min(selected_months)}..{max(selected_months)}), "
        f"~{projected_rows:,} transactions (budget {TRANSACTION_BUDGET:,})"
    )

    print("Pass 2: filtering + writing processed CSV ...")
    manifest = pass2_filter_and_write(selected_months)

    print(f"Wrote {manifest['row_count']:,} rows -> {OUT_CSV}")
    print(
        f"Estimated nodes: {manifest['estimated_node_count']:,} / 200,000  |  "
        f"Estimated relationships: {manifest['estimated_relationship_count']:,} / 400,000"
    )
    print(f"Manifest -> {OUT_MANIFEST}")


if __name__ == "__main__":
    main()
