"""
Batch-load data/processed/transactions_recent.csv into Neo4j (AuraDB Free or
any Neo4j 5.x instance). Idempotent: safe to re-run for future refreshes since
every write is a MERGE keyed on a natural key.

Requires NEO4J_URI / NEO4J_USER / NEO4J_PASSWORD in the environment (.env).
"""

import csv
import os

from dotenv import load_dotenv
from neo4j import GraphDatabase

HERE = os.path.dirname(os.path.abspath(__file__))
CSV_PATH = os.path.join(HERE, "..", "data", "processed", "transactions_recent.csv")
SCHEMA_PATH = os.path.join(HERE, "schema.cypher")

BATCH_SIZE = 1000

LOAD_QUERY = """
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
FOREACH (_ IN CASE WHEN row.nearest_metro IS NOT NULL THEN [1] ELSE [] END |
  MERGE (ms:MetroStation {name: row.nearest_metro})
  MERGE (t)-[:NEAR_METRO]->(ms)
)
FOREACH (_ IN CASE WHEN row.nearest_mall IS NOT NULL THEN [1] ELSE [] END |
  MERGE (ml:Mall {name: row.nearest_mall})
  MERGE (t)-[:NEAR_MALL]->(ml)
)
FOREACH (_ IN CASE WHEN row.nearest_landmark IS NOT NULL THEN [1] ELSE [] END |
  MERGE (l:Landmark {name: row.nearest_landmark})
  MERGE (t)-[:NEAR_LANDMARK]->(l)
)
"""


def none_if_blank(v):
    return v if v not in (None, "") else None


def to_float_or_none(v):
    v = none_if_blank(v)
    return float(v) if v is not None else None


def read_rows():
    with open(CSV_PATH, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            yield {
                "id": row["id"],
                "date": row["date"],
                "area": none_if_blank(row["area"]),
                "building": none_if_blank(row["building"]),
                "project": none_if_blank(row["project"]),
                "master_project": none_if_blank(row["master_project"]),
                "property_type": none_if_blank(row["property_type"]),
                "property_sub_type": none_if_blank(row["property_sub_type"]),
                "nearest_metro": none_if_blank(row["nearest_metro"]),
                "nearest_mall": none_if_blank(row["nearest_mall"]),
                "nearest_landmark": none_if_blank(row["nearest_landmark"]),
                "rooms": none_if_blank(row["rooms"]),
                "has_parking": row["has_parking"] == "1",
                "area_sqm": to_float_or_none(row["area_sqm"]),
                "price": to_float_or_none(row["price"]),
                "price_per_sqm": to_float_or_none(row["price_per_sqm"]),
            }


def batched(iterable, size):
    batch = []
    for item in iterable:
        batch.append(item)
        if len(batch) >= size:
            yield batch
            batch = []
    if batch:
        yield batch


def apply_schema(driver):
    with open(SCHEMA_PATH, encoding="utf-8") as f:
        statements = [s.strip() for s in f.read().split(";") if s.strip() and not s.strip().startswith("//")]
    with driver.session() as session:
        for stmt in statements:
            session.run(stmt)


def load(driver):
    total = 0
    with driver.session() as session:
        for batch in batched(read_rows(), BATCH_SIZE):
            session.run(LOAD_QUERY, rows=batch)
            total += len(batch)
            print(f"  loaded {total:,} transactions...", end="\r")
    print()
    return total


def report_counts(driver):
    with driver.session() as session:
        node_count = session.run("MATCH (n) RETURN count(n) AS c").single()["c"]
        rel_count = session.run("MATCH ()-->() RETURN count(*) AS c").single()["c"]
        by_label = session.run(
            "MATCH (n) RETURN labels(n)[0] AS label, count(*) AS c ORDER BY c DESC"
        ).data()
    print(f"\nFinal graph: {node_count:,} nodes / {rel_count:,} relationships")
    print(f"  (AuraDB Free limits: 200,000 nodes / 400,000 relationships)")
    for row in by_label:
        print(f"    {row['label']}: {row['c']:,}")


def record_dataset_version(driver, row_count):
    """Persist a record of this ingestion run in the graph itself -- a real,
    queryable history of when the data was refreshed and what it covered."""
    with driver.session() as session:
        date_range = session.run(
            "MATCH (t:Transaction) RETURN min(t.date) AS earliest, max(t.date) AS latest"
        ).single()
        session.run(
            """
            CREATE (:DatasetVersion {
                loaded_at: datetime(),
                row_count: $row_count,
                date_range_start: $start,
                date_range_end: $end,
                source: $source
            })
            """,
            row_count=row_count,
            start=date_range["earliest"],
            end=date_range["latest"],
            source="kaggle:waelr1985/dubai-real-estate-transaction (DLD Transactions.csv)",
        )
    print(f"Recorded DatasetVersion: {row_count:,} rows, {date_range['earliest']}..{date_range['latest']}")


def main():
    load_dotenv()
    uri = os.environ["NEO4J_URI"]
    user = os.environ.get("NEO4J_USER", "neo4j")
    password = os.environ["NEO4J_PASSWORD"]

    driver = GraphDatabase.driver(uri, auth=(user, password))
    try:
        driver.verify_connectivity()
        print("Applying schema constraints...")
        apply_schema(driver)

        print(f"Loading transactions from {CSV_PATH} ...")
        total = load(driver)
        print(f"Done: {total:,} transaction rows processed.")

        report_counts(driver)
        record_dataset_version(driver, total)
    finally:
        driver.close()


if __name__ == "__main__":
    main()
