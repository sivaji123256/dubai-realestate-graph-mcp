# Dubai Real Estate Knowledge Graph (Neo4j + MCP + Web App)

A Neo4j graph of real Dubai Land Department (DLD) sale transactions, exposed
two ways:

- **`mcp_server/`** — an MCP server for Claude Code / Claude Desktop
- **`webapp/`** — a standalone public web app (FastAPI + OpenAI function
  calling + a simple chat UI), password-protected, deployable to Render

Both share the same query logic (`graph_queries.py`) against the same Neo4j
graph. Ask things like:

- "What's the average price per sqm in Business Bay?"
- "Compare JVC and Dubai Marina."
- "Which areas near the Burj Khalifa/Dubai Mall metro station have the most sales activity?"
- "Show me recent transactions in Dubai Marina under 2M AED."

## Data

Source: the official DLD transaction registry (1999–Feb 2026, 1.66M rows),
obtained via a public Kaggle mirror (`waelr1985/dubai-real-estate-transaction`,
MIT license) — not scraped listings, but the actual government transaction
record: price, size, rooms, area, building, project, master project, nearest
metro/mall/landmark, etc.

Neo4j AuraDB Free caps out at 200K nodes / 400K relationships, so the graph
holds a **recent trailing slice of Sales transactions** (currently ~47K rows,
see `data/processed/manifest.json` for the exact window and node/relationship
counts) rather than the full 1.66M-row history.

### "Real-time" — what this actually means

The MCP server queries the **live Neo4j graph on every call** — there's no
caching layer, so results always reflect exactly what's loaded right now.
It is **not** a live streaming feed: DLD doesn't expose one publicly. To keep
the graph current, re-run the ingestion pipeline periodically (see below) —
every write is a `MERGE` on a natural key, so re-running is idempotent and
safe.

## Graph schema

```
(:Transaction {id, date, price, price_per_sqm, area_sqm, rooms, has_parking})
  -[:IN_AREA]->(:Area {name})
  -[:IN_BUILDING]->(:Building {name})
  -[:OF_TYPE]->(:PropertyType {name})
  -[:OF_SUBTYPE]->(:PropertySubType {name})
  -[:NEAR_METRO]->(:MetroStation {name})
  -[:NEAR_MALL]->(:Mall {name})
  -[:NEAR_LANDMARK]->(:Landmark {name})

(:Building)-[:PART_OF]->(:Project {name})-[:PART_OF]->(:MasterProject {name})
```

## Setup

```bash
python3 -m pip install -r requirements.txt
```

1. Create a free Neo4j AuraDB instance at https://console.neo4j.io and copy
   its Connection URI, username, and generated password into `.env` (see
   `.env.example`).
2. Filter the raw dataset down to a budget-fitting recent slice:
   ```bash
   python3 ingestion/filter_transactions.py
   ```
3. Load it into Neo4j (applies constraints, then batched MERGE load):
   ```bash
   python3 ingestion/load_neo4j.py
   ```
4. Register the MCP server with Claude Code:
   ```bash
   claude mcp add dubai-realestate -- python3 <absolute-path>/mcp_server/server.py
   ```

## Public web app (`webapp/`)

A FastAPI backend that runs an OpenAI tool-calling loop over `graph_queries.py`,
served behind a simple password gate, plus a vanilla HTML/JS chat frontend.
`run_cypher` is intentionally **not** exposed here (no raw-Cypher surface for
public users) — only the domain-specific tools.

### Run locally

```bash
python3 -m pip install -r webapp/requirements.txt
```

Add to `.env`: `OPENAI_API_KEY`, `OPENAI_MODEL` (default `gpt-4o-mini`),
`APP_PASSWORD`, `SESSION_SECRET` (random string), `COOKIE_SECURE` (`false`
locally, `true` in production).

```bash
python3 -m uvicorn webapp.main:app --reload
```

Open http://127.0.0.1:8000, enter the password, chat.

### Deploy to Render

`render.yaml` at the project root defines the service (Python web service,
`webapp/requirements.txt`, `uvicorn webapp.main:app`). To deploy:

1. Push this repo to GitHub (already done if you're reading this from there).
2. On [render.com](https://render.com): **New +** → **Blueprint** → connect
   this repo. Render reads `render.yaml` automatically.
3. Fill in the env vars Render prompts for (marked `sync: false` in the
   blueprint): `OPENAI_API_KEY`, `NEO4J_URI`, `NEO4J_PASSWORD`, `APP_PASSWORD`,
   `SESSION_SECRET`.
4. Deploy. First request after idle may be slow (~30-60s cold start on the
   free tier).

## Refreshing with newer data

Re-run `ingestion/fetch_data.py` (pulls the latest Kaggle snapshot), then
`filter_transactions.py` and `load_neo4j.py` again — all writes are `MERGE`,
so it's safe to re-run on top of existing data.

## MCP tools

| Tool | Purpose |
|---|---|
| `graph_schema()` | Node/relationship labels + counts — orient yourself first |
| `list_areas()` | All area names in the graph — DLD uses official registry names, not marketing names |
| `run_cypher(query, params)` | Read-only Cypher escape hatch |
| `area_market_summary(area)` | Avg price, price/sqm, top property types for an area |
| `search_transactions(...)` | Filtered transaction search |
| `compare_areas(areas)` | Side-by-side stats for multiple areas |
| `top_areas_near_metro(metro)` | Sales activity by area near a metro station |
| `project_lookup(project_name)` | Buildings + transaction stats for a project |
| `price_trend(area)` | Monthly price/sqm trend for an area |

> **Naming note:** DLD uses its own official area registry names, which
> sometimes differ from popular marketing names — e.g. "Marsa Dubai" is the
> DLD name for the area popularly called "Dubai Marina". Call `list_areas()`
> if a lookup returns zero results.
