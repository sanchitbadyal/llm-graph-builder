import re


_RELATIONSHIP_PATTERN = re.compile(
    r"^\s*(?P<variable>(?:`(?:``|[^`])+`|[A-Za-z_][A-Za-z0-9_]*)?)"
    r"\s*:(?P<types>.*)$",
    re.DOTALL,
)
_SAFE_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")


def _skip_quoted_text(query: str, start: int) -> int:
    quote = query[start]
    index = start + 1
    while index < len(query):
        if quote != "`" and query[index] == "\\":
            index += 2
        elif query[index] == quote:
            if index + 1 < len(query) and query[index + 1] == quote:
                index += 2
            else:
                return index + 1
        else:
            index += 1
    return len(query)


def _skip_comment(query: str, start: int) -> int:
    if query.startswith("//", start):
        newline = query.find("\n", start + 2)
        return len(query) if newline == -1 else newline + 1
    comment_end = query.find("*/", start + 2)
    return len(query) if comment_end == -1 else comment_end + 2


def _find_bracket_end(query: str, start: int) -> int | None:
    depth = 1
    index = start + 1
    while index < len(query):
        if query[index] in "'\"`":
            index = _skip_quoted_text(query, index)
        elif query.startswith("//", index):
            index = _skip_comment(query, index)
        elif query.startswith("/*", index):
            index = _skip_comment(query, index)
        elif query[index] == "[":
            depth += 1
            index += 1
        elif query[index] == "]":
            depth -= 1
            if depth == 0:
                return index
            index += 1
        else:
            index += 1
    return None


def _split_type_expression(types: str) -> tuple[str, str]:
    index = 0
    while index < len(types):
        if types[index] == "`":
            index = _skip_quoted_text(types, index)
        elif types[index] == "*":
            return types[:index], types[index:]
        elif types[index].isspace():
            where_match = re.match(r"\s+WHERE\b", types[index:], re.IGNORECASE)
            if where_match:
                suffix_start = index + where_match.start()
                return types[:suffix_start], types[suffix_start:]
            index += 1
        else:
            index += 1
    return types, ""


def _quote_relationship_type(type_expression: str) -> str:
    leading = type_expression[: len(type_expression) - len(type_expression.lstrip())]
    trailing = type_expression[len(type_expression.rstrip()):]
    token = type_expression.strip()
    if not token:
        return type_expression

    negation = "!" if token.startswith("!") else ""
    name = token[len(negation):]
    if name.startswith("`") and name.endswith("`"):
        return type_expression
    if _SAFE_IDENTIFIER.fullmatch(name):
        return type_expression

    escaped_name = name.replace("`", "``")
    return f"{leading}{negation}`{escaped_name}`{trailing}"


def _rewrite_relationship_types(content: str) -> str:
    if "//" in content or "/*" in content:
        return content

    match = _RELATIONSHIP_PATTERN.fullmatch(content)
    if not match:
        return content

    types, suffix = _split_type_expression(match.group("types"))
    rewritten_types = []
    start = 0
    index = 0
    while index < len(types):
        if types[index] == "`":
            index = _skip_quoted_text(types, index)
        elif types[index] in "|&":
            rewritten_types.append(_quote_relationship_type(types[start:index]))
            rewritten_types.append(types[index])
            index += 1
            start = index
        else:
            index += 1
    rewritten_types.append(_quote_relationship_type(types[start:]))

    return content[: match.start("types")] + "".join(rewritten_types) + suffix


def _rewrite_cypher(query: str) -> str:
    parts = []
    index = 0
    while index < len(query):
        if query[index] in "'\"`":
            end = _skip_quoted_text(query, index)
            parts.append(query[index:end])
            index = end
        elif query.startswith("//", index) or query.startswith("/*", index):
            end = _skip_comment(query, index)
            parts.append(query[index:end])
            index = end
        elif query[index] == "[":
            end = _find_bracket_end(query, index)
            if end is None:
                parts.append(query[index:])
                break
            content = query[index + 1:end]
            parts.extend(("[", _rewrite_relationship_types(content), "]"))
            index = end + 1
        else:
            parts.append(query[index])
            index += 1
    return "".join(parts)


def quote_cypher_relationship_types(query: str) -> str:
    """Backtick-quote unsafe relationship type identifiers in generated Cypher."""
    fence = re.fullmatch(
        r"(?is)(\s*```(?:cypher)?\s*)(.*?)(\s*```\s*)",
        query,
    )
    if fence:
        return f"{fence.group(1)}{_rewrite_cypher(fence.group(2))}{fence.group(3)}"
    return _rewrite_cypher(query)
