import os

import pytest

os.environ.setdefault("LINEAGEGATE_GRAPH", "acme_test")


@pytest.fixture(scope="session", autouse=True)
def seeded_graph():
    from lineagegate import config
    from lineagegate.graph.client import db
    from lineagegate.seed.load import load

    config.GRAPH_NAME = os.environ["LINEAGEGATE_GRAPH"]
    try:
        db().connection.ping()
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"FalkorDB not reachable: {exc}")
    stats = load(config.GRAPH_NAME)
    yield stats
    db().select_graph(config.GRAPH_NAME).delete()
