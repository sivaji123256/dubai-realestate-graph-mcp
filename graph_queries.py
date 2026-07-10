"""
Query functions against the Dubai real-estate Neo4j graph (official DLD Sales
transactions). Plain functions, no framework decorators -- shared by both
mcp_server/server.py (wrapped as MCP tools) and webapp/ (wrapped as OpenAI
function-calling tools).

Name resolution: DLD uses its own official registry names for areas, which
often differ from popular marketing names (e.g. "Marsa Dubai" = "Dubai
Marina"). Rather than relying on the LLM to know/guess these mappings,
`_resolve` below fixes typos and known aliases server-side, deterministically,
before any Cypher runs -- so results are consistent no matter which model is
asking.
"""

import difflib
import threading
from typing import Optional

from neo4j_client import run_read

# Best-effort popular-name -> official DLD registry name aliases. Not
# exhaustive -- unmapped names still fall through to fuzzy matching below.
AREA_ALIASES = {
    "dubai marina": "Marsa Dubai",
    "the marina": "Marsa Dubai",
    "downtown dubai": "Burj Khalifa",
    "downtown": "Burj Khalifa",
    "dubai hills estate": "Hadaeq Sheikh Mohammed Bin Rashid",
    "dubai hills": "Hadaeq Sheikh Mohammed Bin Rashid",
    "meydan": "Nad Al Shiba First",
}

_cache_lock = threading.Lock()
_name_cache = {}


def _cached_names(label: str, cypher: str) -> list:
    if label not in _name_cache:
        with _cache_lock:
            if label not in _name_cache:
                _name_cache[label] = [r["name"] for r in run_read(cypher)]
    return _name_cache[label]


def _get_area_names() -> list:
    return _cached_names("Area", "MATCH (a:Area) RETURN a.name AS name")


def _get_metro_names() -> list:
    return _cached_names("MetroStation", "MATCH (m:MetroStation) RETURN m.name AS name")


def _resolve(name: Optional[str], candidates: list, aliases: Optional[dict] = None, cutoff: float = 0.72) -> Optional[str]:
    """Resolve a user-supplied name to the closest real entity name: exact
    match, then alias table, then fuzzy match. Falls back to the original
    string unchanged if nothing matches closely (so the caller still gets an
    honest "no results" rather than a silently wrong guess)."""
    if not name:
        return name
    lower_map = {c.lower(): c for c in candidates}
    key = name.strip().lower()
    if key in lower_map:
        return lower_map[key]
    if aliases and key in aliases and aliases[key].lower() in lower_map:
        return aliases[key]
    close = difflib.get_close_matches(key, lower_map.keys(), n=1, cutoff=cutoff)
    if close:
        return lower_map[close[0]]
    return name


def resolve_area(area: Optional[str]) -> Optional[str]:
    return _resolve(area, _get_area_names(), AREA_ALIASES)


def resolve_metro(metro: Optional[str]) -> Optional[str]:
    return _resolve(metro, _get_metro_names())


def graph_schema() -> dict:
    """Node labels, relationship types, and their counts currently in the
    graph, plus the transaction date range."""
    labels = run_read("MATCH (n) RETURN labels(n)[0] AS label, count(*) AS count ORDER BY count DESC")
    rels = run_read(
        "MATCH ()-[r]->() RETURN type(r) AS type, count(*) AS count ORDER BY count DESC"
    )
    date_range = run_read(
        "MATCH (t:Transaction) RETURN min(t.date) AS earliest, max(t.date) AS latest"
    )
    return {
        "node_labels": labels,
        "relationship_types": rels,
        "transaction_date_range": date_range[0] if date_range else None,
        "note": "Data is Dubai Land Department Sales transactions, official DLD registry, currently covering a recent trailing window (see transaction_date_range).",
    }


def list_areas() -> list:
    """Every area/community name present in the graph. DLD uses its own
    official registry names, which sometimes differ from popular marketing
    names (e.g. "Marsa Dubai" is the DLD name for the area popularly called
    "Dubai Marina")."""
    return run_read("MATCH (a:Area) RETURN a.name AS name ORDER BY name")


def area_market_summary(area: str) -> dict:
    """Market summary for a Dubai area/community: transaction count, average
    price, average price per sqm, min/max price, and top property types."""
    area = resolve_area(area)
    stats = run_read(
        """
        MATCH (t:Transaction)-[:IN_AREA]->(a:Area)
        WHERE toLower(a.name) = toLower($area)
        RETURN count(t) AS transaction_count,
               avg(t.price) AS avg_price,
               avg(t.price_per_sqm) AS avg_price_per_sqm,
               min(t.price) AS min_price,
               max(t.price) AS max_price
        """,
        area=area,
    )
    top_types = run_read(
        """
        MATCH (t:Transaction)-[:IN_AREA]->(a:Area)
        WHERE toLower(a.name) = toLower($area)
        OPTIONAL MATCH (t)-[:OF_TYPE]->(pt:PropertyType)
        RETURN pt.name AS property_type, count(t) AS count
        ORDER BY count DESC LIMIT 5
        """,
        area=area,
    )
    result = stats[0] if stats else {}
    result["resolved_area_name"] = area
    result["top_property_types"] = top_types
    return result


def search_transactions(
    area: Optional[str] = None,
    property_type: Optional[str] = None,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    rooms: Optional[str] = None,
    limit: int = 20,
) -> list:
    """Search individual sale transactions with optional filters. `rooms` is
    a free-text label from DLD data (e.g. "Studio", "1 B/R", "2 B/R")."""
    area = resolve_area(area)
    return run_read(
        """
        MATCH (t:Transaction)
        OPTIONAL MATCH (t)-[:IN_AREA]->(a:Area)
        OPTIONAL MATCH (t)-[:OF_TYPE]->(pt:PropertyType)
        WITH t, a, pt
        WHERE ($area IS NULL OR toLower(a.name) = toLower($area))
          AND ($property_type IS NULL OR toLower(pt.name) = toLower($property_type))
          AND ($min_price IS NULL OR t.price >= $min_price)
          AND ($max_price IS NULL OR t.price <= $max_price)
          AND ($rooms IS NULL OR t.rooms = $rooms)
        RETURN t.id AS id, toString(t.date) AS date, a.name AS area,
               pt.name AS property_type, t.rooms AS rooms,
               t.area_sqm AS area_sqm, t.price AS price,
               t.price_per_sqm AS price_per_sqm
        ORDER BY t.date DESC
        LIMIT $limit
        """,
        area=area,
        property_type=property_type,
        min_price=min_price,
        max_price=max_price,
        rooms=rooms,
        limit=limit,
    )


def compare_areas(areas: list) -> list:
    """Side-by-side market stats (transaction count, avg price, avg price/sqm,
    avg size) for a list of area/community names."""
    # Dedupe by resolved name -- if two inputs resolve to the same official
    # area (e.g. "Dubai Marina" and "Marsa Dubai" are the same place), only
    # query/return it once so counts aren't double-counted.
    seen = {}
    for original in areas:
        resolved = resolve_area(original)
        if resolved not in seen:
            seen[resolved] = original
    rows = run_read(
        """
        UNWIND $areas AS area_name
        OPTIONAL MATCH (t:Transaction)-[:IN_AREA]->(a:Area)
        WHERE toLower(a.name) = toLower(area_name)
        RETURN area_name,
               count(t) AS transaction_count,
               avg(t.price) AS avg_price,
               avg(t.price_per_sqm) AS avg_price_per_sqm,
               avg(t.area_sqm) AS avg_area_sqm
        """,
        areas=list(seen.keys()),
    )
    for row in rows:
        row["requested_as"] = seen.get(row["area_name"], row["area_name"])
    return rows


def top_areas_near_metro(metro: str, limit: int = 10) -> list:
    """Areas with the most sale transactions near a given metro station --
    useful for exploring metro-proximity effects on Dubai's property market."""
    metro = resolve_metro(metro)
    return run_read(
        """
        MATCH (t:Transaction)-[:NEAR_METRO]->(m:MetroStation)
        WHERE toLower(m.name) = toLower($metro)
        MATCH (t)-[:IN_AREA]->(a:Area)
        RETURN a.name AS area, count(t) AS transaction_count,
               avg(t.price_per_sqm) AS avg_price_per_sqm
        ORDER BY transaction_count DESC
        LIMIT $limit
        """,
        metro=metro,
        limit=limit,
    )


def project_lookup(project_name: str) -> dict:
    """Look up a development project: its master project, buildings, and
    aggregate transaction stats for units sold within it."""
    result = run_read(
        """
        MATCH (p:Project)
        WHERE toLower(p.name) = toLower($project_name)
        OPTIONAL MATCH (b:Building)-[:PART_OF]->(p)
        OPTIONAL MATCH (t:Transaction)-[:IN_BUILDING]->(b)
        OPTIONAL MATCH (p)-[:PART_OF]->(mp:MasterProject)
        RETURN p.name AS project, mp.name AS master_project,
               collect(DISTINCT b.name) AS buildings,
               count(DISTINCT t) AS transaction_count,
               avg(t.price) AS avg_price
        """,
        project_name=project_name,
    )
    return result[0] if result else {}


def price_trend(area: str) -> list:
    """Monthly transaction count and average price/sqm trend for an area,
    over the months currently loaded in the graph."""
    area = resolve_area(area)
    return run_read(
        """
        MATCH (t:Transaction)-[:IN_AREA]->(a:Area)
        WHERE toLower(a.name) = toLower($area)
        WITH substring(toString(t.date), 0, 7) AS month, t
        RETURN month, count(t) AS transaction_count,
               avg(t.price_per_sqm) AS avg_price_per_sqm
        ORDER BY month
        """,
        area=area,
    )


def citywide_kpis() -> dict:
    """Overall KPIs across the whole graph: total transactions, avg price,
    avg price/sqm, distinct areas covered, and the transaction date range --
    for the dashboard's KPI cards."""
    stats = run_read(
        """
        MATCH (t:Transaction)
        RETURN count(t) AS total_transactions,
               avg(t.price) AS avg_price,
               avg(t.price_per_sqm) AS avg_price_per_sqm,
               toString(min(t.date)) AS earliest,
               toString(max(t.date)) AS latest
        """
    )
    area_count = run_read("MATCH (a:Area) RETURN count(a) AS c")
    result = stats[0] if stats else {}
    result["area_count"] = area_count[0]["c"] if area_count else 0
    return result


def top_areas_by_volume(limit: int = 10) -> list:
    """Areas ranked by sale transaction volume, with avg price/sqm -- for the
    dashboard's top-areas chart."""
    return run_read(
        """
        MATCH (t:Transaction)-[:IN_AREA]->(a:Area)
        RETURN a.name AS area, count(t) AS transaction_count,
               avg(t.price_per_sqm) AS avg_price_per_sqm
        ORDER BY transaction_count DESC
        LIMIT $limit
        """,
        limit=limit,
    )


def citywide_monthly_trend() -> list:
    """Citywide monthly transaction count and average price/sqm trend, across
    all areas -- for the dashboard's overview chart."""
    return run_read(
        """
        MATCH (t:Transaction)
        WITH substring(toString(t.date), 0, 7) AS month, t
        RETURN month, count(t) AS transaction_count,
               avg(t.price_per_sqm) AS avg_price_per_sqm
        ORDER BY month
        """
    )


def dataset_versions() -> list:
    """Ingestion run history -- when the graph was loaded/refreshed, and what
    date range and row count each run covered. Written by
    ingestion/load_neo4j.py on every successful load."""
    return run_read(
        """
        MATCH (v:DatasetVersion)
        RETURN toString(v.loaded_at) AS loaded_at, v.row_count AS row_count,
               toString(v.date_range_start) AS date_range_start,
               toString(v.date_range_end) AS date_range_end, v.source AS source
        ORDER BY v.loaded_at DESC
        """
    )


def area_subgraph(area: str, max_buildings: int = 25) -> dict:
    """Live subgraph around an area: its top buildings by transaction volume,
    their project/master project chain, and the metro stations, malls, and
    property types connected to transactions in the area. Transaction nodes
    themselves are excluded (there can be thousands -- not visually
    meaningful); this surfaces the reference-entity structure around the
    area instead. Node-to-node edges here are derived for visualization
    (aggregated from shared transactions), except Building-PART_OF->Project
    and Project-PART_OF->MasterProject, which are literal graph edges."""
    resolved = resolve_area(area)

    buildings = run_read(
        """
        MATCH (t:Transaction)-[:IN_AREA]->(a:Area)
        WHERE toLower(a.name) = toLower($area)
        MATCH (t)-[:IN_BUILDING]->(b:Building)
        WITH b, count(t) AS cnt
        ORDER BY cnt DESC
        LIMIT $max_buildings
        OPTIONAL MATCH (b)-[:PART_OF]->(p:Project)
        OPTIONAL MATCH (p)-[:PART_OF]->(mp:MasterProject)
        RETURN b.name AS building, cnt AS building_txn_count,
               p.name AS project, mp.name AS master_project
        """,
        area=resolved,
        max_buildings=max_buildings,
    )
    metros = run_read(
        """
        MATCH (t:Transaction)-[:IN_AREA]->(a:Area)
        WHERE toLower(a.name) = toLower($area)
        MATCH (t)-[:NEAR_METRO]->(m:MetroStation)
        RETURN m.name AS metro, count(t) AS cnt
        ORDER BY cnt DESC LIMIT 5
        """,
        area=resolved,
    )
    malls = run_read(
        """
        MATCH (t:Transaction)-[:IN_AREA]->(a:Area)
        WHERE toLower(a.name) = toLower($area)
        MATCH (t)-[:NEAR_MALL]->(ml:Mall)
        RETURN ml.name AS mall, count(t) AS cnt
        ORDER BY cnt DESC LIMIT 5
        """,
        area=resolved,
    )
    ptypes = run_read(
        """
        MATCH (t:Transaction)-[:IN_AREA]->(a:Area)
        WHERE toLower(a.name) = toLower($area)
        MATCH (t)-[:OF_TYPE]->(pt:PropertyType)
        RETURN pt.name AS property_type, count(t) AS cnt
        ORDER BY cnt DESC
        """,
        area=resolved,
    )

    nodes = {}
    edges = []

    def add_node(node_id, label, ntype, **extra):
        if node_id not in nodes:
            nodes[node_id] = {"id": node_id, "label": label, "type": ntype, **extra}
        return node_id

    area_id = add_node(f"area:{resolved}", resolved, "Area")

    for row in buildings:
        b_id = add_node(
            f"building:{row['building']}", row["building"], "Building",
            transaction_count=row["building_txn_count"],
        )
        edges.append({"from": area_id, "to": b_id, "label": "HAS_BUILDING"})
        if row["project"]:
            p_id = add_node(f"project:{row['project']}", row["project"], "Project")
            edges.append({"from": b_id, "to": p_id, "label": "PART_OF"})
            if row["master_project"]:
                mp_id = add_node(
                    f"masterproject:{row['master_project']}", row["master_project"], "MasterProject"
                )
                edges.append({"from": p_id, "to": mp_id, "label": "PART_OF"})

    for row in metros:
        m_id = add_node(
            f"metro:{row['metro']}", row["metro"], "MetroStation", transaction_count=row["cnt"]
        )
        edges.append({"from": area_id, "to": m_id, "label": "NEAR_METRO"})

    for row in malls:
        ml_id = add_node(
            f"mall:{row['mall']}", row["mall"], "Mall", transaction_count=row["cnt"]
        )
        edges.append({"from": area_id, "to": ml_id, "label": "NEAR_MALL"})

    for row in ptypes:
        pt_id = add_node(
            f"ptype:{row['property_type']}", row["property_type"], "PropertyType",
            transaction_count=row["cnt"],
        )
        edges.append({"from": area_id, "to": pt_id, "label": "OF_TYPE"})

    return {"resolved_area_name": resolved, "nodes": list(nodes.values()), "edges": edges}
