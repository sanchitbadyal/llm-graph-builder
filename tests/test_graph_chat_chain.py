from langchain_core.language_models.fake import FakeListLLM

from src import QA_integration


class FakeGraph:
    get_structured_schema = {
        "node_props": {},
        "rel_props": {},
        "relationships": [
            {"start": "Organization", "type": "HAS-SUB-UNIT", "end": "Plant"}
        ],
    }
    get_schema = "(:Organization)-[:HAS-SUB-UNIT]->(:Plant)"

    def __init__(self):
        self.queried_cypher = None

    def query(self, query, params=None):
        self.queried_cypher = query
        return []

    def refresh_schema(self):
        pass

    def add_graph_documents(self, graph_documents, include_source=False):
        pass


def test_graph_chain_quotes_unsafe_relationship_types_before_execution(monkeypatch):
    models = iter(
        [
            FakeListLLM(
                responses=[
                    "MATCH (org:Organization)-[:HAS-SUB-UNIT]->(plant:Plant) "
                    "RETURN plant"
                ]
            ),
            FakeListLLM(responses=["Found the plant."]),
        ]
    )
    monkeypatch.setattr(
        QA_integration, "get_llm", lambda _: (next(models), "test-model", None)
    )
    graph = FakeGraph()

    graph_chain, _, _ = QA_integration.create_graph_chain("test-model", graph)
    response = graph_chain.invoke({"query": "Find the plant."})

    assert graph.queried_cypher == (
        "MATCH (org:Organization)-[:`HAS-SUB-UNIT`]->(plant:Plant) RETURN plant"
    )
    assert response["result"] == "Found the plant."
