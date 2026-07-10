"""
MCP server exposing a Dubai real-estate knowledge graph (Neo4j) built from
official DLD transaction records (Dec 2025 - Feb 2026 Sales).

Every tool queries the live graph on each call -- there is no caching layer,
so results always reflect whatever is currently loaded in Neo4j. The graph
itself is refreshed by re-running the ingestion pipeline (ingestion/), not by
this server -- see README.md for the "real-time" caveat.

Query logic lives in graph_queries.py (project root) so it can be shared with
webapp/ (the public OpenAI-powered chat app) without duplicating Cypher.

Run: python mcp_server/server.py   (stdio transport)
"""

import os
import sys
from typing import Optional

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from mcp.server.fastmcp import FastMCP

import graph_queries as gq
from neo4j_client import run_read

mcp = FastMCP("aqariq")

_WRITE_KEYWORDS = (
    "CREATE",
    "MERGE",
    "DELETE",
    "SET",
    "REMOVE",
    "DROP",
    "DETACH",
    "CALL {",
    "LOAD CSV",
)


@mcp.tool()
def graph_schema() -> dict:
    """Return the node labels, relationship types, and their counts currently
    in the graph -- call this first to orient yourself before writing Cypher
    with run_cypher."""
    return gq.graph_schema()


@mcp.tool()
def run_cypher(query: str, params: Optional[dict] = None) -> list:
    """Run an arbitrary read-only Cypher query against the graph. Write
    clauses (CREATE/MERGE/DELETE/SET/REMOVE/DROP/...) are rejected. Use
    graph_schema() first if you're unsure what labels/relationships exist."""
    upper = query.upper()
    for kw in _WRITE_KEYWORDS:
        if kw in upper:
            raise ValueError(f"Write operation '{kw}' is not allowed via run_cypher (read-only tool).")
    return run_read(query, **(params or {}))


@mcp.tool()
def list_areas() -> list:
    """List every area/community name present in the graph. DLD uses its own
    official registry names, which sometimes differ from popular marketing
    names (e.g. "Marsa Dubai" is the DLD name for the area popularly called
    "Dubai Marina"). Call this to find the correct name before using
    area_market_summary/compare_areas/price_trend/search_transactions."""
    return gq.list_areas()


@mcp.tool()
def area_market_summary(area: str) -> dict:
    """Market summary for a Dubai area/community: transaction count, average
    price, average price per sqm, min/max price, and top property types."""
    return gq.area_market_summary(area)


@mcp.tool()
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
    return gq.search_transactions(area, property_type, min_price, max_price, rooms, limit)


@mcp.tool()
def compare_areas(areas: list) -> list:
    """Side-by-side market stats (transaction count, avg price, avg price/sqm,
    avg size) for a list of area/community names."""
    return gq.compare_areas(areas)


@mcp.tool()
def top_areas_near_metro(metro: str, limit: int = 10) -> list:
    """Areas with the most sale transactions near a given metro station --
    useful for exploring metro-proximity effects on Dubai's property market."""
    return gq.top_areas_near_metro(metro, limit)


@mcp.tool()
def project_lookup(project_name: str) -> dict:
    """Look up a development project: its master project, buildings, and
    aggregate transaction stats for units sold within it."""
    return gq.project_lookup(project_name)


@mcp.tool()
def price_trend(area: str) -> list:
    """Monthly transaction count and average price/sqm trend for an area,
    over the months currently loaded in the graph."""
    return gq.price_trend(area)


if __name__ == "__main__":
    mcp.run()
