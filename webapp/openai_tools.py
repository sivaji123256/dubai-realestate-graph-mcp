from . import config  # noqa: F401  (ensures project root is on sys.path before importing below)
import graph_queries as gq

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "graph_schema",
            "description": "Node labels, relationship types, and their counts currently in the graph, plus the transaction date range currently loaded. Call this if you need to know what time period the data covers.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_areas",
            "description": 'Every area/community name present in the graph. DLD uses its own official registry names, which sometimes differ from popular marketing names (e.g. "Marsa Dubai" is the DLD name for the area popularly called "Dubai Marina"). Call this to find the correct name before using area_market_summary/compare_areas/price_trend/search_transactions.',
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_metro_stations",
            "description": 'Every metro station name present in the graph. Some real-world zone/freezone names (e.g. "DMCC", "JLT") don\'t textually resemble their actual station name ("Jumeirah Lakes Towers"). Call this if top_areas_near_metro comes back with zero results, instead of guessing a station name.',
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "area_market_summary",
            "description": "Market summary for a Dubai area/community: transaction count, average price, average price per sqm, min/max price, and top property types.",
            "parameters": {
                "type": "object",
                "properties": {"area": {"type": "string", "description": "Official DLD area name"}},
                "required": ["area"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_transactions",
            "description": 'Search individual sale transactions with optional filters. rooms is a free-text label from DLD data (e.g. "Studio", "1 B/R", "2 B/R").',
            "parameters": {
                "type": "object",
                "properties": {
                    "area": {"type": "string"},
                    "property_type": {"type": "string"},
                    "min_price": {"type": "number"},
                    "max_price": {"type": "number"},
                    "rooms": {"type": "string"},
                    "limit": {"type": "integer", "default": 20},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "compare_areas",
            "description": "Side-by-side market stats (transaction count, avg price, avg price/sqm, avg size) for a list of area/community names.",
            "parameters": {
                "type": "object",
                "properties": {"areas": {"type": "array", "items": {"type": "string"}}},
                "required": ["areas"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "top_areas_near_metro",
            "description": "Areas with the most sale transactions near a given metro station -- useful for exploring metro-proximity effects on Dubai's property market.",
            "parameters": {
                "type": "object",
                "properties": {
                    "metro": {"type": "string", "description": 'e.g. "Business Bay Metro Station"'},
                    "limit": {"type": "integer", "default": 10},
                },
                "required": ["metro"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "project_lookup",
            "description": "Look up a development project: its master project, developer (when confidently known -- null if not), buildings, and aggregate transaction stats for units sold within it.",
            "parameters": {
                "type": "object",
                "properties": {"project_name": {"type": "string"}},
                "required": ["project_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "price_trend",
            "description": "Monthly transaction count and average price/sqm trend for an area, over the months currently loaded in the graph.",
            "parameters": {
                "type": "object",
                "properties": {"area": {"type": "string"}},
                "required": ["area"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "developer_contact",
            "description": "Verified official contact info (website/email/phone) for a developer, e.g. after project_lookup identifies one. Only call this once you have an actual developer name -- if project_lookup returned developer: null, do not guess a developer name to pass here.",
            "parameters": {
                "type": "object",
                "properties": {"developer_name": {"type": "string"}},
                "required": ["developer_name"],
            },
        },
    },
]

DISPATCH = {
    "graph_schema": lambda: gq.graph_schema(),
    "list_areas": lambda: gq.list_areas(),
    "list_metro_stations": lambda: gq.list_metro_stations(),
    "area_market_summary": lambda area: gq.area_market_summary(area),
    "search_transactions": lambda **kw: gq.search_transactions(**kw),
    "compare_areas": lambda areas: gq.compare_areas(areas),
    "top_areas_near_metro": lambda metro, limit=10: gq.top_areas_near_metro(metro, limit),
    "project_lookup": lambda project_name: gq.project_lookup(project_name),
    "price_trend": lambda area: gq.price_trend(area),
    "developer_contact": lambda developer_name: gq.developer_contact(developer_name),
}


def call_tool(name: str, arguments: dict):
    fn = DISPATCH.get(name)
    if fn is None:
        raise ValueError(f"Unknown tool: {name}")
    return fn(**arguments)


# Human-readable "doing X..." lines shown live while the agent works (used by
# the streaming /public assistant -- see webapp/chat.py's run_chat_loop).
FRIENDLY_TOOL_LABELS = {
    "graph_schema": lambda a: "Checking what data is currently available...",
    "list_areas": lambda a: "Looking up official DLD area names...",
    "list_metro_stations": lambda a: "Looking up official metro station names...",
    "area_market_summary": lambda a: f"Pulling market stats for {a.get('area', 'this area')}...",
    "search_transactions": lambda a: "Searching recent transactions...",
    "compare_areas": lambda a: f"Comparing {', '.join(a.get('areas', []) or ['areas'])}...",
    "top_areas_near_metro": lambda a: f"Finding areas near {a.get('metro', 'this station')}...",
    "project_lookup": lambda a: f"Looking up {a.get('project_name', 'this project')}...",
    "price_trend": lambda a: f"Pulling the price trend for {a.get('area', 'this area')}...",
    "developer_contact": lambda a: f"Finding contact info for {a.get('developer_name', 'the developer')}...",
}


def friendly_tool_label(name: str, arguments: dict) -> str:
    fn = FRIENDLY_TOOL_LABELS.get(name)
    return fn(arguments) if fn else f"Running {name}..."


def summarize_result(result) -> str:
    if isinstance(result, list):
        return f"Found {len(result)} result{'s' if len(result) != 1 else ''}"
    if isinstance(result, dict):
        if result.get("error"):
            return "No data found"
        return "Done"
    return "Done"
