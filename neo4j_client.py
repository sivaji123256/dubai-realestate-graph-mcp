import os

from dotenv import load_dotenv
from neo4j import GraphDatabase

_ENV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
load_dotenv(_ENV_PATH)

_driver = None


def get_driver():
    global _driver
    if _driver is None:
        uri = os.environ["NEO4J_URI"]
        user = os.environ.get("NEO4J_USER", "neo4j")
        password = os.environ["NEO4J_PASSWORD"]
        _driver = GraphDatabase.driver(uri, auth=(user, password))
    return _driver


def run_read(query, **params):
    driver = get_driver()
    with driver.session(default_access_mode="READ") as session:
        result = session.run(query, **params)
        return [record.data() for record in result]
