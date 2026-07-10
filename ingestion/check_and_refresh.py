"""
Checks whether the Kaggle mirror of the DLD transactions dataset has a newer
snapshot than what's currently loaded, and if so, re-runs the full ingestion
pipeline (fetch -> filter -> load). Designed to run on a schedule (see the
"AqarIQ Data Freshness" cloud routine) so the graph stays as current as its
best available free source, without manual intervention.

This is the honest version of "live": not a real-time stream (DLD doesn't
publish one), but a standing agent that keeps the graph in sync with
whatever the source has, automatically, instead of a one-time snapshot.

Requires NEO4J_URI / NEO4J_USER / NEO4J_PASSWORD in the environment.
"""

import json
import os
import subprocess
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
sys.path.insert(0, ROOT)

DATASET_REF = "waelr1985/dubai-real-estate-transaction"
LIST_URL = "https://www.kaggle.com/api/v1/datasets/list?search=dubai%20real%20estate&pageSize=20"


def get_remote_last_updated():
    with urllib.request.urlopen(LIST_URL) as resp:
        data = json.load(resp)
    for entry in data:
        if entry.get("ref") == DATASET_REF:
            return entry["lastUpdated"]
    raise RuntimeError(f"Dataset {DATASET_REF} not found in Kaggle search results")


def get_local_source_updated_at():
    from neo4j_client import run_read

    rows = run_read(
        """
        MATCH (v:DatasetVersion)
        WHERE v.source_updated_at IS NOT NULL
        RETURN v.source_updated_at AS source_updated_at
        ORDER BY v.loaded_at DESC LIMIT 1
        """
    )
    return rows[0]["source_updated_at"] if rows else None


def stamp_source_updated_at(remote_last_updated):
    from neo4j_client import run_write

    run_write(
        """
        MATCH (v:DatasetVersion)
        WITH v ORDER BY v.loaded_at DESC LIMIT 1
        SET v.source_updated_at = $ts
        """,
        ts=remote_last_updated,
    )


def run_pipeline():
    for script in ["fetch_data.py", "filter_transactions.py", "load_neo4j.py"]:
        path = os.path.join(HERE, script)
        print(f"--- running {script} ---", flush=True)
        subprocess.run([sys.executable, path], check=True, cwd=ROOT)


def main():
    remote = get_remote_last_updated()
    local = get_local_source_updated_at()
    print(f"Remote Kaggle snapshot last updated: {remote}")
    print(f"Local graph synced from snapshot dated: {local or '(never recorded)'}")

    if local is not None and remote <= local:
        print("No newer snapshot available -- graph is already current. Skipping refresh.")
        return

    print("Newer snapshot detected -- refreshing the graph...")
    run_pipeline()
    stamp_source_updated_at(remote)
    print(f"Refresh complete. Graph now synced from snapshot dated {remote}.")


if __name__ == "__main__":
    main()
