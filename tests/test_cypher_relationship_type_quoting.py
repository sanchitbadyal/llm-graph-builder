from src.cypher_utils import quote_cypher_relationship_types


def test_quotes_relationship_types_with_special_characters():
    query = "MATCH (org:Organization)-[:HAS_SUB-UNIT]->(unit) RETURN unit"

    assert quote_cypher_relationship_types(query) == (
        "MATCH (org:Organization)-[:`HAS_SUB-UNIT`]->(unit) RETURN unit"
    )


def test_quotes_unsafe_types_in_alternatives_and_preserves_quantifier():
    query = "MATCH (a)-[r:HAS-SUB-UNIT|OPERATES*1..2 WHERE r.active]->(b)"

    assert quote_cypher_relationship_types(query) == (
        "MATCH (a)-[r:`HAS-SUB-UNIT`|OPERATES*1..2 WHERE r.active]->(b)"
    )


def test_leaves_safe_and_already_quoted_types_unchanged():
    query = "MATCH (a)-[:OPERATES]->(b), (b)-[:`HAS-SUB-UNIT`]->(c)"

    assert quote_cypher_relationship_types(query) == query


def test_does_not_rewrite_strings_comments_or_non_relationship_brackets():
    query = (
        'RETURN "MATCH (a)-[:HAS-SUB-UNIT]->(b)" AS example, '
        "(a)-[:HAS-SUB-UNIT]->(b) // [:ALSO-IGNORED]\n"
        "RETURN [1, 2]"
    )

    assert quote_cypher_relationship_types(query) == (
        'RETURN "MATCH (a)-[:HAS-SUB-UNIT]->(b)" AS example, '
        "(a)-[:`HAS-SUB-UNIT`]->(b) // [:ALSO-IGNORED]\n"
        "RETURN [1, 2]"
    )


def test_quotes_relationship_types_inside_cypher_code_fences():
    query = "```cypher\nMATCH (a)-[:HAS-SUB-UNIT]->(b)\n```"

    assert quote_cypher_relationship_types(query) == (
        "```cypher\nMATCH (a)-[:`HAS-SUB-UNIT`]->(b)\n```"
    )
