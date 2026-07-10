# AqarIQ — Dubai Real Estate Market Intelligence (Neo4j + MCP + Web App)

A Neo4j graph of real Dubai Land Department (DLD) sale transactions, exposed
two ways:

- **`mcp_server/`** — an MCP server for Claude Code / Claude Desktop
- **`webapp/`** — **AqarIQ**, a standalone public product (FastAPI + OpenAI
  function calling): a chat assistant, an analytics dashboard, a live graph
  explorer, and a system-health view, all password-protected and deployable
  to Render

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

Every successful `ingestion/load_neo4j.py` run also writes a
`(:DatasetVersion {loaded_at, row_count, date_range_start, date_range_end, source})`
node — a persistent, queryable ingestion history living in the graph itself
(`graph_queries.dataset_versions()`, shown on the AqarIQ dashboard).

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

## AqarIQ web app (`webapp/`) — sales enablement product

A FastAPI backend that runs an OpenAI tool-calling loop over `graph_queries.py`,
positioned as an internal tool for a real estate developer's sales team
(individual rep accounts, not a shared password), with five panels:

- **Chat** — natural-language Q&A over the graph, with quick-prompt shortcuts
  and a copy button on replies for pasting into a client WhatsApp/email
  mid-call
- **Dashboard** — KPI cards + top-areas and citywide price-trend charts
  (Chart.js), the current `DatasetVersion` for provenance, and a
  Print/Save-as-PDF button for a client-ready one-pager
- **Graph Explorer** — pick an area, see its live subgraph (buildings,
  project/master project, metro, mall, property types) rendered with
  vis-network. All Neo4j access stays server-side (`/api/graph/area-subgraph`)
  — the browser never receives DB credentials
- **Team** *(admin only)* — add/deactivate rep accounts, see per-rep message
  counts and last-active timestamps
- **System Health** *(admin only)* — in-process request/latency/error
  metrics and an estimated OpenAI spend, from `webapp/metrics.py` (resets on
  redeploy — team activity in the Team panel is durable, stored in Neo4j)

`run_cypher` is intentionally **not** exposed here (no raw-Cypher surface for
end users) — only the domain-specific tools.

### Accounts

Users are `(:User)` nodes in the same Neo4j graph (bcrypt-hashed passwords,
`admin` or `rep` role) — see `webapp/user_store.py`. Bootstrap the first
admin account once:

```bash
python webapp/create_admin.py <email> <name> <password> admin
```

After that, admins can add/deactivate reps from the Team panel. Deactivating
a user locks them out immediately (every request re-checks their status in
Neo4j, not just on next login).

### Run locally

```bash
python3 -m pip install -r webapp/requirements.txt
```

Add to `.env`: `OPENAI_API_KEY`, `OPENAI_MODEL` (default `gpt-4o`),
`SESSION_SECRET` (random string), `COOKIE_SECURE` (`false` locally, `true`
in production).

```bash
python3 -m uvicorn webapp.main:app --reload
```

Open http://127.0.0.1:8000 and sign in with an account created via
`create_admin.py`.

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
