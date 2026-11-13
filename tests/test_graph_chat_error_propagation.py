from src import QA_integration


def test_graph_query_error_is_returned_in_response_info(monkeypatch):
    class FailingGraphChain:
        def invoke(self, _):
            raise RuntimeError("Neo4j syntax error")

    monkeypatch.setattr(
        QA_integration,
        "create_graph_chain",
        lambda *_: (FailingGraphChain(), object(), "test-model"),
    )

    response = QA_integration.process_graph_response(
        "test-model", object(), "question", [], object()
    )

    assert response["message"] == (
        "Graph query failed. See response details for the underlying error."
    )
    assert response["info"]["error"] == "RuntimeError: Neo4j syntax error"
