"""
Query functions against the Dubai real-estate Neo4j graph (official DLD Sales
transactions). Plain functions, no framework decorators -- shared by both
mcp_server/server.py (wrapped as MCP tools) and webapp/ (wrapped as OpenAI
function-calling tools).
"""

from typing import Optional

from neo4j_client import run_read


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
    return run_read(
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
        areas=areas,
    )


def top_areas_near_metro(metro: str, limit: int = 10) -> list:
    """Areas with the most sale transactions near a given metro station --
    useful for exploring metro-proximity effects on Dubai's property market."""
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
