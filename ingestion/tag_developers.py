"""
One-time (re-runnable) enrichment: tags Project and MasterProject nodes with
a `developer` property when the developer's own name appears literally in
the project name.

Deliberately precision-over-recall: only developers who brand explicitly
(DAMAC, Azizi, Binghatti, etc.) get tagged. Large master developers who use
sub-brand/community names instead of their own name (Emaar's "Downtown",
Nakheel's "Palm Jumeirah", Meraas's "City Walk") are NOT guessed at --
string-matching a community name to a developer is unreliable enough that a
wrong guess (misrouting a customer to the wrong company) is worse than an
honest "developer unknown". A real fix needs DLD's actual Projects/Developer
registry data, not name matching.

Patterns were chosen by checking real matches against the live graph before
committing to them (see the AqarIQ Public Assistant plan) -- each pattern
below was verified to produce clean, unambiguous matches, not just guessed.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from neo4j_client import run_read, run_write  # noqa: E402

DEVELOPER_PATTERNS = {
    "DAMAC": ["damac"],
    "Azizi": ["azizi"],
    "Binghatti": ["binghatti"],
    "Samana": ["samana"],
    "Sobha": ["sobha"],
    "Danube": ["danube"],
    "Omniyat": ["omniyat"],
    "Ellington": ["ellington"],
    "Meteora": ["meteora"],
    "Reef": ["reef"],
    "Iman": ["by iman"],
    "Al Habtoor": ["al habtoor", "habtoor"],
    "Deyaar": ["deyaar"],
    "Emaar": ["emaar"],
}


def match_developer(name: str):
    if not name:
        return None
    lower = name.lower()
    for developer, patterns in DEVELOPER_PATTERNS.items():
        if any(p in lower for p in patterns):
            return developer
    return None


def tag_label(label: str):
    rows = run_read(f"MATCH (n:{label}) RETURN n.name AS name")
    tagged = 0
    for row in rows:
        developer = match_developer(row["name"])
        if developer:
            run_write(
                f"MATCH (n:{label} {{name: $name}}) SET n.developer = $developer",
                name=row["name"],
                developer=developer,
            )
            tagged += 1
    return tagged, len(rows)


def main():
    for label in ["Project", "MasterProject"]:
        tagged, total = tag_label(label)
        print(f"{label}: tagged {tagged} / {total} ({tagged / total:.0%})")


if __name__ == "__main__":
    main()
