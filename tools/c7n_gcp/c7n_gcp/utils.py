import re
from dataclasses import dataclass


_COMPARISON_OPERATORS = {'>=', '<=', '!=', '=~', '!~', '=', '>', '<', ':'}
_SEVERITY_ORDER = {
    "default": 0,
    "debug": 100,
    "info": 200,
    "notice": 300,
    "warning": 400,
    "error": 500,
    "critical": 600,
    "alert": 700,
    "emergency": 800,
}


# Regex tokenizer for Cloud Logging filter expressions.
# Two-character operators must appear before their single-character prefixes so
# that alternation priority resolves them correctly (e.g. ">=" before ">").
_TOKEN_RE = re.compile(
    r'(?P<STRING>"(?:[^"\\]|\\.)*"|\'(?:[^\'\\]|\\.)*\')'
    r'|(?P<LPAREN>\()'
    r'|(?P<RPAREN>\))'
    r'|(?P<OP>>=|<=|!=|=~|!~|[=><:])'
    r'|(?P<WORD>[^\s()=><:!~]+)'
    r'|(?P<UNKNOWN>[^\s])'  # catch-all: tolerate uncommon punctuation (but not whitespace)
)
_LOGICAL_WORDS = {'AND', 'OR', 'NOT'}


def _tokenize_cloud_logging_filter(expression):
    tokens = []
    for m in _TOKEN_RE.finditer(expression):
        kind, value = m.lastgroup, m.group()
        if kind == 'WORD' and value.upper() in _LOGICAL_WORDS:
            tokens.append(('LOGIC', value.upper()))
        elif kind == 'UNKNOWN':
            tokens.append(('WORD', value))  # tolerate uncommon punctuation
        else:
            tokens.append((kind, value))
    return tokens


class _TokenStream:
    def __init__(self, tokens):
        self.tokens = tokens
        self.index = 0

    def peek(self):
        if self.index >= len(self.tokens):
            return None
        return self.tokens[self.index]

    def consume(self):
        token = self.peek()
        if token is not None:
            self.index += 1
        return token


class CloudLoggingFilterParser:
    """Parser for Cloud Logging query expressions.

    The parser supports logical operators (AND/OR/NOT), grouping parentheses,
    and all documented comparison/match operators used in sink filters.
    """

    comparison_operators = _COMPARISON_OPERATORS

    @classmethod
    def parse(cls, expression):
        normalized = (expression or "").strip()
        if not normalized:
            node = {"type": "term", "tokens": [("WORD", "true")]}
            return cls._build_result(node)

        stream = _TokenStream(_tokenize_cloud_logging_filter(normalized))
        ast = cls._parse_or(stream)
        if stream.peek() is not None:
            raise ValueError("Unable to parse full Cloud Logging filter expression")
        return cls._build_result(ast)

    @classmethod
    def canonicalize(cls, expression):
        parsed = cls.parse(expression)
        return cls._canonicalize_node(parsed["ast"])

    @classmethod
    def _parse_or(cls, stream):
        node = cls._parse_and(stream)
        children = [node]
        while True:
            token = stream.peek()
            if token and token[0] == "LOGIC" and token[1] == "OR":
                stream.consume()
                children.append(cls._parse_and(stream))
                continue
            break
        if len(children) == 1:
            return children[0]
        return {"type": "or", "children": children}

    @classmethod
    def _parse_and(cls, stream):
        node = cls._parse_not(stream)
        children = [node]
        while True:
            token = stream.peek()
            if token and token[0] == "LOGIC" and token[1] == "AND":
                stream.consume()
                children.append(cls._parse_not(stream))
                continue
            break
        if len(children) == 1:
            return children[0]
        return {"type": "and", "children": children}

    @classmethod
    def _parse_not(cls, stream):
        token = stream.peek()
        if token and token[0] == "LOGIC" and token[1] == "NOT":
            stream.consume()
            return {"type": "not", "expr": cls._parse_not(stream)}
        return cls._parse_primary(stream)

    @classmethod
    def _parse_primary(cls, stream):
        token = stream.peek()
        if token is None:
            raise ValueError("Unexpected end of Cloud Logging filter expression")

        if token[0] == "LPAREN":
            stream.consume()
            node = cls._parse_or(stream)
            closing = stream.consume()
            if not closing or closing[0] != "RPAREN":
                raise ValueError("Missing closing parenthesis in filter expression")
            return node
        return cls._parse_predicate(stream)

    @classmethod
    def _parse_predicate(cls, stream):
        # Single-pass: collect lhs tokens until an OP is seen at depth 0,
        # then switch to collecting rhs tokens.  A LOGIC token or an
        # unmatched RPAREN at depth 0 terminates the predicate.
        lhs, rhs = [], []  # left hand side and right hand side
        op = None  # operator
        depth = 0  # parenthesis depth
        target = lhs

        while True:
            token = stream.peek()
            if token is None:
                break
            kind, value = token
            if kind == 'RPAREN' and depth == 0:
                break
            if kind == 'LOGIC' and depth == 0:
                break
            stream.consume()
            if kind == 'LPAREN':
                depth += 1
                target.append((kind, value))
            elif kind == 'RPAREN':
                depth -= 1
                target.append((kind, value))
            elif kind == 'OP' and op is None and target is lhs and depth == 0:
                op = value
                target = rhs
            else:
                target.append((kind, value))

        if not lhs:
            raise ValueError('Empty predicate in Cloud Logging filter expression')
        if op is not None:
            if not rhs:
                raise ValueError('Malformed comparison in Cloud Logging filter expression')
            return {'type': 'predicate', 'lhs_tokens': lhs, 'op': op, 'rhs_tokens': rhs}
        return {'type': 'term', 'tokens': lhs}

    @classmethod
    def _build_result(cls, ast):
        operators = set()
        predicates = []
        terms = []

        def visit(node):
            node_type = node["type"]
            if node_type in ("and", "or"):
                operators.add(node_type)
                for child in node["children"]:
                    visit(child)
            elif node_type == "not":
                operators.add("not")
                visit(node["expr"])
            elif node_type == "predicate":
                operators.add(node["op"])
                predicates.append(
                    {
                        "lhs": cls._render_tokens(node["lhs_tokens"]),
                        "op": node["op"],
                        "rhs": cls._render_tokens(node["rhs_tokens"]),
                    }
                )
            elif node_type == "term":
                terms.append(cls._render_tokens(node["tokens"]))

        visit(ast)
        return {
            "ast": ast,
            "operators": sorted(operators),
            "predicates": predicates,
            "terms": terms,
        }

    @classmethod
    def _canonicalize_node(cls, node):
        node_type = node["type"]
        if node_type in ("and", "or"):
            children = sorted(cls._canonicalize_node(c) for c in node["children"])
            joiner = " and " if node_type == "and" else " or "
            return "(" + joiner.join(children) + ")"
        if node_type == "not":
            return f"not ({cls._canonicalize_node(node['expr'])})"
        if node_type == "predicate":
            lhs = cls._render_tokens(node["lhs_tokens"], canonical=True)
            rhs = cls._render_tokens(node["rhs_tokens"], canonical=True)
            return f"{lhs} {node['op']} {rhs}"
        return cls._render_tokens(node["tokens"], canonical=True)

    @classmethod
    def _render_tokens(cls, tokens, canonical=False):
        rendered = []
        for token_type, value in tokens:
            if canonical and token_type in ("WORD", "LOGIC"):
                rendered.append(value.lower())
            else:
                rendered.append(value)
        return re.sub(r"\s+", " ", " ".join(rendered)).strip()


def parse_cloud_logging_filter(expression):
    """Parse a Cloud Logging filter expression into parts and an AST."""
    return CloudLoggingFilterParser.parse(expression)


def canonicalize_cloud_logging_filter(expression):
    """Return a canonical string representation of a Cloud Logging filter."""
    return CloudLoggingFilterParser.canonicalize(expression)


def cloud_logging_filters_overlap(left_expression, right_expression):
    """Determine whether two Cloud Logging filters overlap.

    This helper is designed for sink relationship filters and can be reused by
    other logging-aware filters that need conservative overlap semantics.
    """
    if left_expression == right_expression:
        return True
    if left_expression == 'true' or right_expression == 'true':
        return True

    left = parse_cloud_logging_filter(left_expression)
    right = parse_cloud_logging_filter(right_expression)

    if _has_complex_cloud_logging_logic(left) or _has_complex_cloud_logging_logic(right):
        return False

    left_constraints = _group_cloud_logging_predicates(left['predicates'])
    right_constraints = _group_cloud_logging_predicates(right['predicates'])
    return not _cloud_logging_constraints_disjoint(left_constraints, right_constraints)


def _has_complex_cloud_logging_logic(parsed):
    """Return True if the filter contains logic the overlap analyser cannot evaluate.

    Filters with OR, NOT, or bare non-true terms are treated as "complex" and
    cloud_logging_filters_overlap conservatively returns False (non-overlapping).

    Known semantic gap — NOT:
        ``NOT resource.type="gce_instance"`` technically overlaps with any filter
        that matches a different resource type, but proving this requires enumerating
        the complete value domain for each field, which is unbounded.  Treating NOT
        as complex produces false negatives (sinks that actually overlap are reported
        as non-overlapping) rather than false positives.  The GCP-managed ``_Default``
        sink always uses a chain of NOT terms, so real projects will routinely hit
        this path.
    """
    operators = set(parsed.get('operators', ()))
    terms = parsed.get('terms', ())
    return (
        'or' in operators
        or 'not' in operators
        or any(t.lower() != 'true' for t in terms)
    )


def _group_cloud_logging_predicates(predicates):
    grouped = {}
    for predicate in predicates:
        lhs = predicate['lhs'].strip().lower()
        grouped.setdefault(lhs, []).append(
            (predicate['op'], _normalize_cloud_logging_rhs(predicate['rhs']))
        )
    return grouped


def _normalize_cloud_logging_rhs(rhs):
    value = rhs.strip()
    if (value.startswith('"') and value.endswith('"')) or (
        value.startswith("'") and value.endswith("'")
    ):
        value = value[1:-1]
    return value.lower()


def _cloud_logging_constraints_disjoint(left_constraints, right_constraints):
    for lhs in set(left_constraints).intersection(right_constraints):
        left_predicates = left_constraints[lhs]
        right_predicates = right_constraints[lhs]
        if _cloud_logging_field_constraints_disjoint(left_predicates, right_predicates):
            return True
    return False


def _cloud_logging_field_constraints_disjoint(left_predicates, right_predicates):
    left_eq = {value for op, value in left_predicates if op == '='}
    right_eq = {value for op, value in right_predicates if op == '='}
    left_ne = {value for op, value in left_predicates if op == '!='}
    right_ne = {value for op, value in right_predicates if op == '!='}

    if left_eq and right_eq and left_eq.isdisjoint(right_eq):
        return True
    if left_eq and left_eq.issubset(right_ne):
        return True
    if right_eq and right_eq.issubset(left_ne):
        return True

    left_interval = _to_cloud_logging_numeric_interval(left_predicates)
    right_interval = _to_cloud_logging_numeric_interval(right_predicates)
    if left_interval and right_interval:
        return _cloud_logging_intervals_disjoint(left_interval, right_interval)
    return False


@dataclass
class _Interval:
    """Closed/open numeric interval used for Cloud Logging filter overlap checks."""
    lower: float = float('-inf')
    lower_inclusive: bool = True
    upper: float = float('inf')
    upper_inclusive: bool = True


def _to_cloud_logging_numeric_interval(predicates):
    lower = float('-inf')
    lower_inclusive = True
    upper = float('inf')
    upper_inclusive = True
    has_numeric = False

    for op, value in predicates:
        if op not in ('=', '>', '>=', '<', '<='):
            continue
        numeric_value = _coerce_cloud_logging_ordered_value(value)
        if numeric_value is None:
            continue

        has_numeric = True
        if op == '=':
            if numeric_value > lower or (numeric_value == lower and not lower_inclusive):
                lower, lower_inclusive = numeric_value, True
            if numeric_value < upper or (numeric_value == upper and not upper_inclusive):
                upper, upper_inclusive = numeric_value, True
            continue

        if op == '>':
            if numeric_value > lower or (numeric_value == lower and lower_inclusive):
                lower, lower_inclusive = numeric_value, False
        elif op == '>=':
            if numeric_value > lower or (numeric_value == lower and not lower_inclusive):
                lower, lower_inclusive = numeric_value, True
        elif op == '<':
            if numeric_value < upper or (numeric_value == upper and upper_inclusive):
                upper, upper_inclusive = numeric_value, False
        elif op == '<=':
            if numeric_value < upper or (numeric_value == upper and not upper_inclusive):
                upper, upper_inclusive = numeric_value, True

    if not has_numeric:
        return None
    return _Interval(lower, lower_inclusive, upper, upper_inclusive)


def _coerce_cloud_logging_ordered_value(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        pass

    lowered = str(value).strip().lower()
    if lowered in _SEVERITY_ORDER:
        return float(_SEVERITY_ORDER[lowered])
    return None


def _cloud_logging_intervals_disjoint(left: _Interval, right: _Interval) -> bool:
    if left.upper < right.lower:
        return True
    if right.upper < left.lower:
        return True
    if left.upper == right.lower and not (left.upper_inclusive and right.lower_inclusive):
        return True
    if right.upper == left.lower and not (right.upper_inclusive and left.lower_inclusive):
        return True
    return False


def get_firewall_port_ranges(firewall_resources):
    for r_index, r in enumerate(firewall_resources):
        action = "allowed" if "allowed" in r else "denied"
        for protocol_index, protocol in enumerate(r[action]):
            if "ports" in protocol:
                port_ranges = []
                for port in protocol["ports"]:
                    if "-" in port:
                        port_split = port.split("-")
                        port_ranges.append({"beginPort": port_split[0], "endPort": port_split[1]})
                    else:
                        port_ranges.append({"beginPort": port, "endPort": port})
                protocol['portRanges'] = port_ranges
                r[action][protocol_index] = protocol
        firewall_resources[r_index] = r
    return firewall_resources
