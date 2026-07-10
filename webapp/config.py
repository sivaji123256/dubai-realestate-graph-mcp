import os
import sys

from dotenv import load_dotenv

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)  # so `import graph_queries` / `import neo4j_client` resolve regardless of cwd
load_dotenv(os.path.join(ROOT, ".env"))

OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o")
SESSION_SECRET = os.environ["SESSION_SECRET"]
COOKIE_SECURE = os.environ.get("COOKIE_SECURE", "false").lower() == "true"
