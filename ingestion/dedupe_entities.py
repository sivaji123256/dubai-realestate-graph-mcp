"""
One-time (re-runnable) cleanup, two passes:

1. Case-collision duplicates -- e.g. "Business Bay" and "BUSINESS BAY" --
   caused by ingestion/sync_buyorsell24.py writing whatever casing
   BuyOrSell24 sends. Now fixed at ingestion time too, so shouldn't recur.

2. Alias-level duplicates -- e.g. "DUBAI MARINA" (a real node BuyOrSell24
   created) vs "Marsa Dubai" (the official DLD name, used by the original
   dataset). These don't collide case-insensitively at all -- only
   graph_queries.AREA_ALIASES knows they're the same place. Also now fixed
   at ingestion time (sync_buyorsell24.py runs graph_queries.resolve_area()
   before creating a node), but that fix can't self-correct a node that
   already exists -- an exact match on the existing stray node wins before
   the alias table is even checked, which is why this cleanup pass is still
   needed for anything that landed before the fix.

Canonical pick: whichever variant has more incoming Transaction relationships
(the one actually in use); ties broken toward the non-all-caps spelling.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from graph_queries import AREA_ALIASES  # noqa: E402
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


def dedupe_area_aliases():
    """For each known AREA_ALIASES entry, if a stray node exists matching
    the alias text exactly (e.g. "DUBAI MARINA" for alias key "dubai
    marina") and the canonical target also exists as a real node, merge the
    stray one into the canonical one."""
    existing = {a["name"].lower(): a["name"] for a in run_read("MATCH (a:Area) RETURN a.name AS name")}
    for alias_key, canonical in AREA_ALIASES.items():
        stray = existing.get(alias_key)
        if not stray or stray == canonical:
            continue
        if canonical.lower() not in existing:
            continue  # canonical doesn't exist as a real node -- nothing to merge into
        print(f"Area (alias): '{stray}' -> canonical='{canonical}'")
        merge_loser_into_canonical("Area", stray, canonical)


def main():
    for label in LABELS:
        dedupe_label(label)
    dedupe_area_aliases()


if __name__ == "__main__":
    main()
