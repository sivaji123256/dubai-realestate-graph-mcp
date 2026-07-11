"""
One-time (re-runnable) cleanup: merges nodes that differ only by case --
e.g. "Business Bay" and "BUSINESS BAY" -- into a single canonical node.

Caused by ingestion/sync_buyorsell24.py writing whatever casing BuyOrSell24
sends without checking against existing nodes first (now fixed there too,
so this shouldn't recur going forward -- this script cleans up what already
landed in the graph before that fix).

Canonical pick: whichever variant has more incoming Transaction relationships
(the one actually in use); ties broken toward the non-all-caps spelling.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from neo4j_client import run_read, run_write  # noqa: E402

INCOMING_TRANSACTION_REL = {
    "Area": "IN_AREA",
    "Building": "IN_BUILDING",
}

LABELS = ["Area", "Building", "Project", "MasterProject"]


def find_colliding_groups(label):
    return run_read(
        f"""
        MATCH (n:{label})
        WITH toLower(n.name) AS lname, collect(n.name) AS names
        WHERE size(names) > 1
        RETURN lname, names
        """
    )


def pick_canonical(label, names):
    rel = INCOMING_TRANSACTION_REL.get(label)
    scored = []
    for name in names:
        count = 0
        if rel:
            count = run_read(
                f"MATCH (:Transaction)-[:{rel}]->(n:{label} {{name: $name}}) RETURN count(*) AS c",
                name=name,
            )[0]["c"]
        scored.append((count, name != name.upper(), name))
    # most transactions wins; tie-break: prefer not-all-uppercase
    scored.sort(key=lambda x: (-x[0], not x[1]))
    return scored[0][2]


def merge_loser_into_canonical(label, loser, canonical):
    rel = INCOMING_TRANSACTION_REL.get(label)
    if rel:
        run_write(
            f"""
            MATCH (t:Transaction)-[r:{rel}]->(loser:{label} {{name: $loser}})
            MATCH (canon:{label} {{name: $canonical}})
            MERGE (t)-[:{rel}]->(canon)
            DELETE r
            """,
            loser=loser,
            canonical=canonical,
        )
    # outgoing PART_OF (e.g. Building -> Project, Project -> MasterProject)
    run_write(
        f"""
        MATCH (loser:{label} {{name: $loser}})-[r:PART_OF]->(target)
        MATCH (canon:{label} {{name: $canonical}})
        MERGE (canon)-[:PART_OF]->(target)
        DELETE r
        """,
        loser=loser,
        canonical=canonical,
    )
    # incoming PART_OF (e.g. something -> Project, something -> MasterProject)
    run_write(
        f"""
        MATCH (source)-[r:PART_OF]->(loser:{label} {{name: $loser}})
        MATCH (canon:{label} {{name: $canonical}})
        MERGE (source)-[:PART_OF]->(canon)
        DELETE r
        """,
        loser=loser,
        canonical=canonical,
    )
    run_write(f"MATCH (loser:{label} {{name: $loser}}) DETACH DELETE loser", loser=loser)


def dedupe_label(label):
    groups = find_colliding_groups(label)
    if not groups:
        print(f"{label}: no duplicates")
        return
    for g in groups:
        names = g["names"]
        canonical = pick_canonical(label, names)
        losers = [n for n in names if n != canonical]
        print(f"{label}: {names} -> canonical='{canonical}'")
        for loser in losers:
            merge_loser_into_canonical(label, loser, canonical)


def main():
    for label in LABELS:
        dedupe_label(label)


if __name__ == "__main__":
    main()
