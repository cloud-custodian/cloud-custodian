import functools
import logging
import math
import re
from dataclasses import dataclass
from enum import Enum

import jmespath


log = logging.getLogger('c7n_gcp.utils')


_REGEX_OPERATORS = {'=~', '!~'}
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


_STRING_PATTERN = r'"(?:[^"\\]|\\.)*"|\'(?:[^\'\\]|\\.)*\''
# A word may contain quoted segments, e.g. the field path jsonPayload."my key".
_WORD_PATTERN = rf'[^\s()=><:!~"\'](?:[^\s()=><:!~"\']|{_STRING_PATTERN})*'
# Regex tokenizer for Cloud Logging filter expressions.
# Two-character operators must appear before their single-character prefixes so
# that alternation priority resolves them correctly (e.g. ">=" before ">").
_TOKEN_RE = re.compile(
    rf'(?P<STRING>{_STRING_PATTERN})'
    r'|(?P<COMMENT>--[^\n]*)'  # "--" starts a comment that runs to the end of the line
    r'|(?P<LPAREN>\()'
    r'|(?P<RPAREN>\))'
    r'|(?P<OP>>=|<=|!=|=~|!~|[=><:])'
    rf'|(?P<FUNC>{_WORD_PATTERN}(?=\())'  # a function name directly followed by "("
    rf'|(?P<WORD>{_WORD_PATTERN})'
    r'|(?P<UNKNOWN>[^\s])'  # catch-all: tolerate uncommon punctuation (but not whitespace)
)
# Logical operators are case-sensitive: lowercase and/or/not are search terms.
_LOGICAL_WORDS = {'AND', 'OR', 'NOT'}
_NEGATIVE_NUMBER_RE = re.compile(r'-\d')
# One segment of a field path, which may contain quoted parts.
_FIELD_SEGMENT_RE = re.compile(rf'(?:{_STRING_PATTERN}|[^."\'])+')
# LogEntry fields whose sub-fields are map or struct keys.
_KEYED_FIELDS = {'labels', 'jsonpayload', 'protopayload'}
_ESCAPED_QUOTE_RE = re.compile(r'\\(["\'\\])')


def _tokenize_cloud_logging_filter(expression):
    tokens = []
    for m in _TOKEN_RE.finditer(expression):
        kind, value = m.lastgroup, m.group()
        if kind == 'COMMENT':
            continue
        if kind in ('WORD', 'FUNC') and value in _LOGICAL_WORDS:
            tokens.append(('LOGIC', value))
        elif (
            kind in ('WORD', 'FUNC')
            and value.startswith('-')
            and not (tokens and tokens[-1][0] == 'OP')
            and not _NEGATIVE_NUMBER_RE.match(value)
        ):
            # A leading minus on a term is shorthand for NOT, e.g.
            # -resource.type="gce_instance".  A minus after a comparison
            # operator or before a digit is part of the value.
            tokens.append(('LOGIC', 'NOT'))
            if kind == 'FUNC' and value[1:]:
                tokens.append(('FUNC', value[1:]))
            elif kind == 'WORD':
                # The rest may be a quoted string, e.g. -"foo bar".
                tokens.extend(_tokenize_cloud_logging_filter(value[1:]))
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

    The parser supports logical operators (AND/OR/NOT and the ``-`` shorthand
    for NOT), implicit AND between adjacent terms, grouping parentheses,
    parenthesized value lists on the right-hand side of a comparison, and all
    documented comparison/match operators used in sink filters.

    Cloud Logging gives NOT the highest precedence, followed by OR and then
    AND, so ``a OR b AND c`` means ``(a OR b) AND c``.
    """

    @classmethod
    def parse(cls, expression):
        tokens = _tokenize_cloud_logging_filter(expression or "")
        if not tokens:
            # An empty filter matches every log entry.
            return cls._build_result({"type": "all"})

        stream = _TokenStream(tokens)
        ast = cls._parse_and(stream, cls._parse_predicate)
        if stream.peek() is not None:
            raise ValueError("Unable to parse full Cloud Logging filter expression")
        return cls._build_result(ast)

    @classmethod
    def canonicalize(cls, expression):
        parsed = cls.parse(expression)
        return cls._canonicalize_node(parsed["ast"])

    # The boolean grammar is shared by whole expressions and by parenthesized
    # value lists, so each level takes the ``leaf`` parser to use for its
    # innermost operands.

    @classmethod
    def _parse_and(cls, stream, leaf):
        # AND has the lowest precedence.  Adjacent terms with no operator
        # between them are an implicit AND.
        children = [cls._parse_or(stream, leaf)]
        while True:
            token = stream.peek()
            if token is None or token[0] == "RPAREN":
                break
            if token == ("LOGIC", "AND"):
                stream.consume()
            children.append(cls._parse_or(stream, leaf))
        return cls._join("and", children)

    @classmethod
    def _parse_or(cls, stream, leaf):
        children = [cls._parse_not(stream, leaf)]
        while stream.peek() == ("LOGIC", "OR"):
            stream.consume()
            children.append(cls._parse_not(stream, leaf))
        return cls._join("or", children)

    @classmethod
    def _parse_not(cls, stream, leaf):
        if stream.peek() == ("LOGIC", "NOT"):
            stream.consume()
            return {"type": "not", "expr": cls._parse_not(stream, leaf)}
        return cls._parse_primary(stream, leaf)

    @classmethod
    def _parse_primary(cls, stream, leaf):
        token = stream.peek()
        if token is None:
            raise ValueError("Unexpected end of Cloud Logging filter expression")

        if token[0] == "LPAREN":
            stream.consume()
            node = cls._parse_and(stream, leaf)
            cls._expect_closing_paren(stream)
            return node
        return leaf(stream)

    @staticmethod
    def _join(node_type, children):
        # Flatten nested nodes of the same type so that equivalent
        # expressions with different grouping share one shape.
        flat = []
        for child in children:
            if child["type"] == node_type:
                flat.extend(child["children"])
            else:
                flat.append(child)
        if len(flat) == 1:
            return flat[0]
        return {"type": node_type, "children": flat}

    @staticmethod
    def _expect_closing_paren(stream):
        closing = stream.consume()
        if not closing or closing[0] != "RPAREN":
            raise ValueError("Missing closing parenthesis in filter expression")

    @classmethod
    def _parse_predicate(cls, stream):
        lhs = cls._parse_operand(stream)
        token = stream.peek()
        if token is None or token[0] != "OP":
            return {"type": "term", "tokens": lhs}
        op = stream.consume()[1]

        token = stream.peek()
        if token is None or token[0] not in ("WORD", "STRING", "LPAREN"):
            raise ValueError("Malformed comparison in Cloud Logging filter expression")
        if token[0] == "LPAREN":
            # The field and operator apply to each element of a value list,
            # e.g. resource.type=("gce_instance" OR "k8s_container").
            stream.consume()
            node = cls._parse_and(stream, lambda s: cls._parse_value(s, lhs, op))
            cls._expect_closing_paren(stream)
            return node
        return cls._parse_value(stream, lhs, op)

    @classmethod
    def _parse_operand(cls, stream):
        # A field path, value or search term.  A name directly followed by a
        # parenthesized argument list is a function call such as
        # sample(insertId, 0.1) or LOG_ID("...").
        token = stream.peek()
        if token is None or token[0] not in ("WORD", "STRING", "FUNC"):
            raise ValueError("Empty predicate in Cloud Logging filter expression")
        tokens = [stream.consume()]
        if token[0] == "FUNC":
            depth = 0
            while True:
                token = stream.consume()
                if token is None:
                    raise ValueError("Missing closing parenthesis in filter expression")
                tokens.append(token)
                if token[0] == "LPAREN":
                    depth += 1
                elif token[0] == "RPAREN":
                    depth -= 1
                    if depth == 0:
                        break
        return tokens

    @staticmethod
    def _parse_value(stream, lhs, op):
        token = stream.peek()
        if token is None or token[0] not in ("WORD", "STRING"):
            raise ValueError("Malformed comparison in Cloud Logging filter expression")
        stream.consume()
        return {"type": "predicate", "lhs_tokens": lhs, "op": op, "rhs_tokens": [token]}

    @classmethod
    def _build_result(cls, ast):
        logical_operators = set()
        comparison_operators = set()
        predicates = []
        terms = []

        def visit(node):
            node_type = node["type"]
            if node_type in ("and", "or"):
                logical_operators.add(node_type)
                for child in node["children"]:
                    visit(child)
            elif node_type == "not":
                logical_operators.add("not")
                visit(node["expr"])
            elif node_type == "predicate":
                comparison_operators.add(node["op"])
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
            "logical_operators": sorted(logical_operators),
            "comparison_operators": sorted(comparison_operators),
            "predicates": predicates,
            "terms": terms,
        }

    @classmethod
    def _canonicalize_node(cls, node):
        node_type = node["type"]
        # The canonical form must re-parse to the same expression, so logical
        # operators stay uppercase.
        if node_type in ("and", "or"):
            children = sorted({cls._canonicalize_node(c) for c in node["children"]})
            if len(children) == 1:
                return children[0]
            joiner = " AND " if node_type == "and" else " OR "
            return "(" + joiner.join(children) + ")"
        if node_type == "not":
            return f"NOT {cls._canonicalize_node(node['expr'])}"
        if node_type == "all":
            return ""
        # Comparisons ignore letter case except for regular expressions.
        if node_type == "predicate":
            lhs = cls._canonicalize_field(node["lhs_tokens"])
            rhs = cls._canonicalize_value(
                node["rhs_tokens"][0], lower=node["op"] not in _REGEX_OPERATORS
            )
            return f"{lhs} {node['op']} {rhs}"
        return cls._render_tokens(node["tokens"], lower=True)

    @classmethod
    def _canonicalize_field(cls, tokens):
        # Built-in LogEntry field names ignore letter case, but map and struct
        # keys are case-sensitive, so only the path up to the first keyed
        # field is lowercased, e.g. resource.labels.Zone keeps "Zone".
        if len(tokens) != 1 or tokens[0][0] != "WORD":
            return cls._render_tokens(tokens)
        path = tokens[0][1]
        end = 0
        for m in _FIELD_SEGMENT_RE.finditer(path):
            end = m.end()
            if m.group().lower() in _KEYED_FIELDS:
                break
        return path[:end].lower() + path[end:]

    @staticmethod
    def _canonicalize_value(token, lower):
        # A value means the same quoted or not, so render it double-quoted
        # where that doesn't need new escapes.
        token_type, value = token
        if token_type == "STRING" and value[0] == "'" and '"' not in value:
            value = f'"{value[1:-1]}"'
        elif token_type == "WORD" and not set(value) & set("\"'\\"):
            value = f'"{value}"'
        return value.lower() if lower else value

    @classmethod
    def _render_tokens(cls, tokens, lower=False):
        rendered = ""
        previous = None
        for token_type, value in tokens:
            if lower and token_type in ("WORD", "STRING", "FUNC"):
                value = value.lower()
            # A function name must stay directly followed by its "(".
            if rendered and previous not in ("FUNC", "LPAREN") and token_type != "RPAREN":
                rendered += " "
            rendered += value
            previous = token_type
        return rendered


def parse_cloud_logging_filter(expression):
    """Parse a Cloud Logging filter expression into parts and an AST.

    Returns a dict with ``ast``, ``logical_operators`` (``and``/``or``/
    ``not``), ``comparison_operators`` (e.g. ``=``, ``>=``, ``:``),
    ``predicates`` (``lhs``/``op``/``rhs`` dicts) and ``terms`` (bare search
    terms and function calls).
    """
    return CloudLoggingFilterParser.parse(expression)


def canonicalize_cloud_logging_filter(expression):
    """Return a canonical string representation of a Cloud Logging filter."""
    return CloudLoggingFilterParser.canonicalize(expression)


def normalize_cloud_logging_filter_spacing(expression):
    """Return a Cloud Logging filter with comments dropped and whitespace
    normalized outside quoted strings.

    Unlike canonicalization this doesn't parse the filter, so it also works
    on filters that don't parse.
    """
    tokens = _tokenize_cloud_logging_filter(expression or "")
    return CloudLoggingFilterParser._render_tokens(tokens)


class CloudLoggingOverlap(Enum):
    """Result of comparing two Cloud Logging filters."""

    # No log entry can match both filters.
    DISJOINT = 'disjoint'
    # The filters are not provably disjoint, but they contain comparisons the
    # analyser cannot evaluate, so overlap could not be proven either.
    POSSIBLE = 'possible'
    # Some log entry matches both filters.
    OVERLAP = 'overlap'


def compare_cloud_logging_filters(left_expression, right_expression):
    """Compare two Cloud Logging filters for overlap.

    Each filter is rewritten as an OR of AND-ed literals (disjunctive normal
    form), and every conjunction of one filter is combined with every
    conjunction of the other.

    A combined conjunction is provably unsatisfiable when it contains:

    - a literal and its negation, e.g. ``LOG_ID("x")`` and ``NOT LOG_ID("x")``;
    - two different equality values for one field, or an equality value that
      is also excluded with ``!=`` or ``NOT``;
    - numeric or severity ranges with no common value, including a range that
      is empty on its own, e.g. ``severity>=ERROR AND severity<=WARNING``.

    It is provably satisfiable when, in addition, every literal is an
    equality, inequality or numeric/severity range comparison.  Literals the
    analyser cannot evaluate, such as ``:`` and regular expression matches,
    global search terms and functions like ``LOG_ID``, leave the result
    ``POSSIBLE`` unless a contradiction is found.  Filters whose normal form
    grows beyond ``_MAX_DNF_CONJUNCTIONS`` are logged and also ``POSSIBLE``.

    ``jsonPayload`` and ``protoPayload`` fields may hold arrays, and a
    comparison on an array matches when any element matches, so conflicting
    comparisons on those fields give ``POSSIBLE`` rather than ``DISJOINT``.
    """
    left = _cloud_logging_filter_dnf(left_expression)
    right = _cloud_logging_filter_dnf(right_expression)
    if left is None or right is None:
        return CloudLoggingOverlap.POSSIBLE

    result = CloudLoggingOverlap.DISJOINT
    for left_conj in left:
        for right_conj in right:
            conj_result = _cloud_logging_conjunction_satisfiable(left_conj + right_conj)
            if conj_result is CloudLoggingOverlap.OVERLAP:
                return conj_result
            if conj_result is CloudLoggingOverlap.POSSIBLE:
                result = conj_result
    return result


_MAX_DNF_CONJUNCTIONS = 256


@functools.lru_cache(maxsize=1024)
def _cloud_logging_filter_dnf(expression):
    dnf = _to_cloud_logging_dnf(parse_cloud_logging_filter(expression)['ast'])
    if dnf is None:
        log.warning(
            "Cloud Logging filter is too complex to compare for overlap "
            f"(more than {_MAX_DNF_CONJUNCTIONS} conjunctions): {expression}")
    return dnf


def _to_cloud_logging_dnf(node, negated=False):
    """Return ``node`` as a list of conjunctions of ``(negated, leaf)`` literals.

    NOT is pushed down to the leaves with De Morgan's laws.  Returns None when
    the result would exceed ``_MAX_DNF_CONJUNCTIONS`` conjunctions.
    """
    node_type = node['type']
    if node_type == 'not':
        return _to_cloud_logging_dnf(node['expr'], not negated)
    if node_type == 'all':
        # One empty conjunction is always true; no conjunctions is never true.
        return [] if negated else [[]]
    if node_type not in ('and', 'or'):
        return [[(negated, node)]]

    parts = [_to_cloud_logging_dnf(child, negated) for child in node['children']]
    if any(part is None for part in parts):
        return None
    # A negated AND is an OR of the negated children, and vice versa.
    if (node_type == 'and') == negated:
        result = [conj for part in parts for conj in part]
    else:
        result = [[]]
        for part in parts:
            result = [conj + other for conj in result for other in part]
            if len(result) > _MAX_DNF_CONJUNCTIONS:
                return None
    if len(result) > _MAX_DNF_CONJUNCTIONS:
        return None
    return result


def _cloud_logging_conjunction_satisfiable(literals):
    """Return OVERLAP if the conjunction is provably satisfiable, DISJOINT if
    it is provably unsatisfiable, and POSSIBLE otherwise."""
    polarity = {}
    fields = {}
    result = CloudLoggingOverlap.OVERLAP
    for negated, node in literals:
        key = CloudLoggingFilterParser._canonicalize_node(node)
        if polarity.setdefault(key, negated) != negated:
            return CloudLoggingOverlap.DISJOINT
        if node['type'] == 'term':
            result = CloudLoggingOverlap.POSSIBLE
            continue
        field = CloudLoggingFilterParser._canonicalize_field(node['lhs_tokens'])
        value = _normalize_cloud_logging_rhs(
            CloudLoggingFilterParser._render_tokens(node['rhs_tokens'])
        )
        fields.setdefault(field, []).append((negated, node['op'], value))

    # Built-in field names are already lowercased, so paths that still
    # differ only in case differ in a map or struct key.  Don't rely on how
    # Cloud Logging matches the case of those keys.
    if len({field.lower() for field in fields}) < len(fields):
        result = CloudLoggingOverlap.POSSIBLE

    for field, constraints in fields.items():
        field_result = _cloud_logging_field_satisfiable(field, constraints)
        if field_result is CloudLoggingOverlap.DISJOINT:
            return field_result
        if field_result is CloudLoggingOverlap.POSSIBLE:
            result = field_result
    return result


# Comparisons that can only match when the field is present on the entry.
_PRESENCE_OPERATORS = {'=', '>', '>=', '<', '<='}
_ORDERED_OPERATORS = {'>', '>=', '<', '<='}
_COMPLEMENT_OPERATORS = {'=': '!=', '!=': '=', '>': '<=', '>=': '<', '<': '>=', '<=': '>'}


def _cloud_logging_field_satisfiable(field, constraints):
    result = _cloud_logging_single_value_satisfiable(field, constraints)
    # A payload field may be an array, and a comparison on an array matches
    # when any element matches, so one entry can satisfy x="a" AND x="b".
    # A single-element array behaves like a single value, so proven overlap
    # still holds.
    if result is CloudLoggingOverlap.DISJOINT and field.lower().startswith(
        _REPEATABLE_FIELD_PREFIXES
    ):
        return CloudLoggingOverlap.POSSIBLE
    return result


_REPEATABLE_FIELD_PREFIXES = ('jsonpayload.', 'protopayload.')


def _cloud_logging_single_value_satisfiable(field, constraints):
    # Built-in LogEntry field names ignore letter case.
    severity = field.lower() == 'severity'
    # Every entry has a severity: LogEntry.severity defaults to DEFAULT.
    present = severity or any(
        not negated and op in _PRESENCE_OPERATORS for negated, op, _ in constraints
    )
    understood = True
    effective = []
    for negated, op, value in constraints:
        if negated:
            if op == '=':
                # NOT field="x" holds when the field is absent or has another
                # value, so it always excludes "x".
                op = '!='
            elif present and op in _COMPLEMENT_OPERATORS:
                # Once another literal requires the field to be present, a
                # negated comparison is its complement.
                op = _COMPLEMENT_OPERATORS[op]
            else:
                # May hold only because the field is absent.
                understood = False
                continue
        if op in _ORDERED_OPERATORS:
            if _coerce_cloud_logging_ordered_value(value, severity) is None:
                understood = False
                continue
        elif op not in ('=', '!='):
            understood = False
            continue
        effective.append((op, value))

    def value_key(value):
        # Numbers compare by value, e.g. 5 and 5.0, or ERROR and 500 for severity.
        number = _coerce_cloud_logging_ordered_value(value, severity)
        return value if number is None else number

    eq = {value_key(value) for op, value in effective if op == '='}
    ne = {value_key(value) for op, value in effective if op == '!='}
    if len(eq) > 1 or eq & ne:
        return CloudLoggingOverlap.DISJOINT

    interval = _to_cloud_logging_numeric_interval(effective, severity)
    if interval is None and severity:
        # Severity is always one of the fixed levels, even unconstrained.
        interval = _Interval()
    if interval is not None:
        excluded = {value for value in ne if isinstance(value, float)}
        if severity:
            # Every entry has exactly one of the fixed severity levels.
            if not any(
                interval.contains(level) and level not in excluded
                for level in _SEVERITY_ORDER.values()
            ):
                return CloudLoggingOverlap.DISJOINT
        else:
            if interval.empty:
                return CloudLoggingOverlap.DISJOINT
            if interval.lower == interval.upper and interval.lower in excluded:
                return CloudLoggingOverlap.DISJOINT
            if any(interval.contains(v) for v in excluded):
                # Excluding values inside a range only leaves a match if the
                # field is not restricted to those values, e.g. integers.
                understood = False
        if any(not isinstance(v, float) for v in eq):
            # A non-numeric equality alongside a numeric range.
            understood = False

    return CloudLoggingOverlap.OVERLAP if understood else CloudLoggingOverlap.POSSIBLE


def _normalize_cloud_logging_rhs(rhs):
    value = rhs.strip()
    if (value.startswith('"') and value.endswith('"')) or (
        value.startswith("'") and value.endswith("'")
    ):
        # The same value can be written with different escapes, e.g.
        # "a\"b" and 'a"b'.
        value = _ESCAPED_QUOTE_RE.sub(r'\1', value[1:-1])
    return value.lower()


@dataclass
class _Interval:
    """Closed/open numeric interval used for Cloud Logging filter overlap checks."""
    lower: float = float('-inf')
    lower_inclusive: bool = True
    upper: float = float('inf')
    upper_inclusive: bool = True

    @property
    def empty(self):
        if self.lower > self.upper:
            return True
        return self.lower == self.upper and not (self.lower_inclusive and self.upper_inclusive)

    def contains(self, value):
        above = value > self.lower or (value == self.lower and self.lower_inclusive)
        below = value < self.upper or (value == self.upper and self.upper_inclusive)
        return above and below


def _to_cloud_logging_numeric_interval(predicates, severity=False):
    lower = float('-inf')
    lower_inclusive = True
    upper = float('inf')
    upper_inclusive = True
    has_numeric = False

    for op, value in predicates:
        if op not in ('=', '>', '>=', '<', '<='):
            continue
        numeric_value = _coerce_cloud_logging_ordered_value(value, severity)
        if numeric_value is None:
            continue

        has_numeric = True
        # Each comparison can only narrow the interval.  At an equal bound an
        # exclusive comparison is the narrower one, so an inclusive one never
        # replaces it.
        if op in ('=', '>', '>='):
            inclusive = op != '>'
            if numeric_value > lower or (numeric_value == lower and not inclusive):
                lower, lower_inclusive = numeric_value, inclusive
        if op in ('=', '<', '<='):
            inclusive = op != '<'
            if numeric_value < upper or (numeric_value == upper and not inclusive):
                upper, upper_inclusive = numeric_value, inclusive

    if not has_numeric:
        return None
    return _Interval(lower, lower_inclusive, upper, upper_inclusive)


def _coerce_cloud_logging_ordered_value(value, severity=False):
    try:
        number = float(value)
    except (TypeError, ValueError):
        pass
    else:
        # float() also accepts "inf" and "nan", which are not numbers here.
        if math.isfinite(number):
            return number

    # Severity names only order the top-level severity field.
    lowered = str(value).strip().lower()
    if severity and lowered in _SEVERITY_ORDER:
        return float(_SEVERITY_ORDER[lowered])
    return None


def filter_tree_has_key(node, key):
    """Check whether a policy filter structure references `key`.

    Recurses only through boolean clauses (and/or/not) so literal filter
    arguments are never mistaken for filters. Leaf `key` values may be
    JMESPath expressions, so parse them and look for a field reference to
    `key`; string literals within an expression do not count.
    """
    if isinstance(node, list):
        return any(filter_tree_has_key(item, key) for item in node)
    if not isinstance(node, dict):
        return False
    for op in ('and', 'or', 'not'):
        if op in node:
            return filter_tree_has_key(node[op], key)
    leaf_key = node.get('key')
    if not isinstance(leaf_key, str):
        return False
    try:
        ast = jmespath.compile(leaf_key).parsed
    except jmespath.exceptions.JMESPathError:
        return leaf_key == key
    return _ast_has_field(ast, key)


def _ast_has_field(ast, name):
    if ast.get('type') == 'field' and ast.get('value') == name:
        return True
    # slice nodes carry raw ints/None as children
    return any(_ast_has_field(child, name) for child in ast.get('children', ())
               if isinstance(child, dict))


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
