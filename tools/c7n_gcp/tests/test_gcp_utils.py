# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import pytest

from c7n_gcp.utils import (
    CloudLoggingOverlap,
    canonicalize_cloud_logging_filter,
    compare_cloud_logging_filters,
    parse_cloud_logging_filter,
)


@pytest.mark.parametrize(
    "operator,expression",
    [
        ("=", 'jsonPayload.user = "alice"'),
        ("!=", 'jsonPayload.user != "alice"'),
        (">", "httpRequest.status > 199"),
        (">=", "httpRequest.status >= 200"),
        ("<", "httpRequest.status < 500"),
        ("<=", "httpRequest.status <= 499"),
        (":", 'textPayload : "timeout"'),
        ("=~", 'labels.env =~ "^prod"'),
        ("!~", 'protoPayload.methodName !~ "Delete"'),
    ],
)
def test_parse_cloud_logging_filter_each_comparison_operator(operator, expression):
    parsed = parse_cloud_logging_filter(expression)
    assert {p["op"] for p in parsed["predicates"]} == {operator}
    assert parsed["comparison_operators"] == [operator]
    assert parsed["logical_operators"] == []


@pytest.mark.parametrize(
    "logical_op,expression",
    [
        ("and", 'severity>=ERROR AND resource.type="gce_instance"'),
        ("or", 'severity>=ERROR OR resource.type="gce_instance"'),
        ("not", 'NOT resource.type="gce_instance"'),
    ],
)
def test_parse_cloud_logging_filter_each_logical_operator(logical_op, expression):
    parsed = parse_cloud_logging_filter(expression)
    assert parsed["logical_operators"] == [logical_op]


def test_parse_cloud_logging_filter_all_operators_together():
    expression = (
        'NOT (severity>=ERROR AND resource.type="gce_instance") '
        'OR textPayload:"timeout" '
        'AND jsonPayload.user!="root" '
        'AND labels.env=~"^prod" '
        'AND protoPayload.methodName!~"Delete" '
        'AND httpRequest.status<500 '
        'AND httpRequest.status>199 '
        'AND sample=1 '
        'AND retries<=2'
    )
    parsed = parse_cloud_logging_filter(expression)

    assert parsed["logical_operators"] == ["and", "not", "or"]
    assert parsed["comparison_operators"] == sorted(
        ["=", "!=", ">", ">=", "<", "<=", ":", "=~", "!~"]
    )


def test_canonicalize_cloud_logging_filter_normalizes_structure():
    first = (
        'NOT (resource.type="gce_instance" OR severity<ERROR) '
        'AND textPayload:"timeout"'
    )
    second = (
        'textPayload:"timeout" AND '
        'NOT (severity<ERROR OR resource.type="gce_instance")'
    )

    assert (
        canonicalize_cloud_logging_filter(first)
        == canonicalize_cloud_logging_filter(second)
    )


@pytest.mark.parametrize("expression", ["", None, "  ", "-- only a comment"])
def test_parse_cloud_logging_filter_empty_expression_matches_everything(expression):
    parsed = parse_cloud_logging_filter(expression)
    assert parsed["ast"] == {"type": "all"}
    assert parsed["terms"] == []
    assert parsed["predicates"] == []
    assert parsed["logical_operators"] == []
    assert parsed["comparison_operators"] == []
    assert canonicalize_cloud_logging_filter(expression) == ""


def test_parse_cloud_logging_filter_handles_escaped_quote_in_string():
    parsed = parse_cloud_logging_filter('textPayload="a\\\"b"')
    assert parsed["predicates"][0]["op"] == "="
    assert parsed["predicates"][0]["rhs"] == '"a\\"b"'


def test_parse_cloud_logging_filter_fallback_token_for_uncommon_punctuation():
    parsed = parse_cloud_logging_filter("!")
    assert parsed["terms"] == ["!"]
    assert parsed["predicates"] == []


def test_parse_cloud_logging_filter_unparsed_token_raises():
    with pytest.raises(ValueError, match="Unable to parse full Cloud Logging filter expression"):
        parse_cloud_logging_filter('severity>=ERROR)')


def test_parse_cloud_logging_filter_not_without_expression_raises():
    with pytest.raises(ValueError, match="Unexpected end of Cloud Logging filter expression"):
        parse_cloud_logging_filter("NOT")


def test_parse_cloud_logging_filter_missing_closing_paren_raises():
    with pytest.raises(ValueError, match="Missing closing parenthesis"):
        parse_cloud_logging_filter('(severity>=ERROR AND resource.type="gce_instance"')


def test_parse_cloud_logging_filter_empty_group_raises():
    with pytest.raises(ValueError, match="Empty predicate"):
        parse_cloud_logging_filter("()")


def test_parse_cloud_logging_filter_malformed_comparison_raises():
    with pytest.raises(ValueError, match="Malformed comparison"):
        parse_cloud_logging_filter("severity=")


def test_parse_cloud_logging_filter_handles_parenthesized_rhs_expression():
    parsed = parse_cloud_logging_filter('resource.type=("gce_instance")')
    assert parsed["predicates"] == [
        {"lhs": "resource.type", "op": "=", "rhs": '"gce_instance"'}
    ]


def test_parse_cloud_logging_filter_distributes_rhs_value_list():
    parsed = parse_cloud_logging_filter('resource.type=("gce_instance" OR "k8s_container")')
    assert parsed["predicates"] == [
        {"lhs": "resource.type", "op": "=", "rhs": '"gce_instance"'},
        {"lhs": "resource.type", "op": "=", "rhs": '"k8s_container"'},
    ]
    assert canonicalize_cloud_logging_filter(
        'resource.type=("gce_instance" OR "k8s_container")'
    ) == canonicalize_cloud_logging_filter(
        'resource.type="k8s_container" OR resource.type="gce_instance"'
    )


def test_parse_cloud_logging_filter_empty_rhs_value_list_raises():
    with pytest.raises(ValueError, match="Malformed comparison"):
        parse_cloud_logging_filter("resource.type=()")


def test_parse_cloud_logging_filter_lowercase_logical_words_are_search_terms():
    parsed = parse_cloud_logging_filter('severity>=ERROR and resource.type="gce_instance"')
    assert parsed["terms"] == ["and"]
    assert len(parsed["predicates"]) == 2


def test_canonicalize_cloud_logging_filter_implicit_and_matches_explicit_and():
    assert canonicalize_cloud_logging_filter(
        'severity>=ERROR resource.type="gce_instance"'
    ) == canonicalize_cloud_logging_filter(
        'severity>=ERROR AND resource.type="gce_instance"'
    )
    assert canonicalize_cloud_logging_filter(
        'a=1 (b=2 OR c=3)'
    ) == canonicalize_cloud_logging_filter('a=1 AND (b=2 OR c=3)')


def test_canonicalize_cloud_logging_filter_or_binds_tighter_than_and():
    # Example from the Cloud Logging query language docs.
    assert canonicalize_cloud_logging_filter(
        '"a" OR NOT "b" AND NOT "c" OR "d"'
    ) == canonicalize_cloud_logging_filter(
        '("a" OR (NOT "b")) AND ((NOT "c") OR "d")'
    )


@pytest.mark.parametrize(
    "minus,not_",
    [
        ('-resource.type="gce_instance"', 'NOT resource.type="gce_instance"'),
        ('-(a=1 OR b=2)', 'NOT (a=1 OR b=2)'),
        ('severity>=ERROR -resource.type="gce_instance"',
         'severity>=ERROR AND NOT resource.type="gce_instance"'),
    ],
)
def test_canonicalize_cloud_logging_filter_minus_is_not(minus, not_):
    assert canonicalize_cloud_logging_filter(minus) == canonicalize_cloud_logging_filter(not_)


def test_parse_cloud_logging_filter_minus_after_operator_is_a_value():
    parsed = parse_cloud_logging_filter("httpRequest.latency>-1 AND sample=-0.5")
    assert [p["rhs"] for p in parsed["predicates"]] == ["-1", "-0.5"]
    assert "not" not in parsed["logical_operators"]


@pytest.mark.parametrize(
    "first,second",
    [
        ('a=1 AND (b=2 AND c=3)', '(a=1 AND b=2) AND c=3'),
        ('a=1 OR (b=2 OR c=3)', '(a=1 OR b=2) OR c=3'),
        ('a=1 AND a=1', 'a=1'),
    ],
)
def test_canonicalize_cloud_logging_filter_flattens_nested_groups(first, second):
    assert canonicalize_cloud_logging_filter(first) == canonicalize_cloud_logging_filter(second)


def test_canonicalize_cloud_logging_filter_is_idempotent():
    expression = (
        'NOT (resource.type="gce_instance" OR severity<ERROR) '
        'textPayload:"timeout" -labels.env=("a" OR "b")'
    )
    canonical = canonicalize_cloud_logging_filter(expression)
    assert canonicalize_cloud_logging_filter(canonical) == canonical


@pytest.mark.parametrize(
    "first,second",
    [
        # String comparisons and search terms ignore letter case.
        ('logName="Foo"', 'logName="foo"'),
        ('severity>=ERROR', 'severity>=error'),
        ('"Timeout"', '"timeout"'),
        # Built-in field names ignore letter case.
        ('SEVERITY>=ERROR', 'severity>=ERROR'),
        ('Resource.Type="a"', 'resource.type="a"'),
        ('RESOURCE.LABELS.zone="a"', 'resource.labels.zone="a"'),
        ('JSONPAYLOAD.userId="a"', 'jsonPayload.userId="a"'),
    ],
)
def test_canonicalize_cloud_logging_filter_ignores_value_case(first, second):
    assert canonicalize_cloud_logging_filter(first) == canonicalize_cloud_logging_filter(second)


@pytest.mark.parametrize(
    "first,second",
    [
        # Map and struct keys are case-sensitive.
        ('labels.Env="prod"', 'labels.env="prod"'),
        ('jsonPayload.userId="a"', 'jsonPayload.userid="a"'),
        ('resource.labels.Zone="a"', 'resource.labels.zone="a"'),
        ('jsonPayload."My Key"="a"', 'jsonPayload."my key"="a"'),
        # Regular expressions are case-sensitive.
        ('labels.env=~"^Prod"', 'labels.env=~"^prod"'),
        ('labels.env!~Prod', 'labels.env!~prod'),
    ],
)
def test_canonicalize_cloud_logging_filter_keeps_case_sensitive_parts(first, second):
    assert canonicalize_cloud_logging_filter(first) != canonicalize_cloud_logging_filter(second)


def test_parse_cloud_logging_filter_handles_parenthesized_lhs_expression():
    parsed = parse_cloud_logging_filter("sample(insertId)=1")
    assert parsed["predicates"][0]["lhs"] == "sample(insertId)"
    assert parsed["predicates"][0]["op"] == "="
    assert parsed["predicates"][0]["rhs"] == "1"


def test_canonicalize_cloud_logging_filter_term_only_expression():
    assert canonicalize_cloud_logging_filter("UNSTRUCTURED_TERM") == "unstructured_term"


@pytest.mark.parametrize(
    "first,second",
    [
        # "--" starts a comment that runs to the end of the line.
        ('severity>=ERROR -- was severity=DEBUG', 'severity>=ERROR'),
        ('severity>=ERROR\n-- see (ticket\nresource.type="a"',
         'severity>=ERROR AND resource.type="a"'),
        # A leading minus applies to a quoted search term as a whole.
        ('-"foo bar"', 'NOT "foo bar"'),
        # Only a name directly followed by "(" is a function call.
        ('unicorn (a=1 OR b=2)', 'unicorn AND (a=1 OR b=2)'),
        # A value means the same quoted or not.
        ('resource.type=gce_instance', 'resource.type="gce_instance"'),
        ("labels.env='prod'", 'labels.env="prod"'),
    ],
)
def test_canonicalize_cloud_logging_filter_equivalent_forms(first, second):
    assert canonicalize_cloud_logging_filter(first) == canonicalize_cloud_logging_filter(second)


@pytest.mark.parametrize(
    "first,second",
    [
        # Whitespace inside a quoted string is significant.
        ('textPayload="a  b"', 'textPayload="a b"'),
        # "--" inside a quoted string is not a comment.
        ('textPayload="a -- b"', 'textPayload="a"'),
    ],
)
def test_canonicalize_cloud_logging_filter_distinct_forms(first, second):
    assert canonicalize_cloud_logging_filter(first) != canonicalize_cloud_logging_filter(second)


@pytest.mark.parametrize(
    "expression",
    [
        'LOG_ID("a") OR -LOG_ID("b")',
        'sample(insertId, 0.1)=1',
        'NOT(a=1 OR b=2)',
        'jsonPayload."my key"="x"',
        'textPayload="a  b"',
        'httpRequest.latency>-1',
    ],
)
def test_canonicalize_cloud_logging_filter_round_trips(expression):
    canonical = canonicalize_cloud_logging_filter(expression)
    assert canonicalize_cloud_logging_filter(canonical) == canonical


def test_parse_cloud_logging_filter_quoted_field_path_segment():
    parsed = parse_cloud_logging_filter('jsonPayload."my key"="x"')
    assert parsed["predicates"] == [{"lhs": 'jsonPayload."my key"', "op": "=", "rhs": '"x"'}]


def _compare(left, right):
    return compare_cloud_logging_filters(
        canonicalize_cloud_logging_filter(left),
        canonicalize_cloud_logging_filter(right),
    )


@pytest.mark.parametrize(
    "left,right",
    [
        ('severity>=ERROR AND resource.type="gce_instance"',
         'resource.type="gce_instance" AND severity>=ERROR'),
        ('', 'severity>=ERROR'),
        ('severity>=ERROR', ''),
        ('sample=1 AND sample>0', 'sample<=2'),
        ('sample>0', 'sample<=10'),
        ('severity>=ERROR AND NOT resource.type="gce_instance"', 'severity>=ERROR'),
        # OR is evaluated per alternative, including RHS value lists.
        ('resource.type=("gce_instance" OR "k8s_container")', 'resource.type="gce_instance"'),
        # De Morgan: NOT (a AND b) holds when either is false.
        ('NOT (resource.type="a" AND severity>=ERROR)', 'resource.type="a"'),
        # Severity names only order the severity field.
        ('labels.level="error"', 'labels.level!="500"'),
        ('severity!=ERROR', 'severity>=WARNING'),
        # Severity is always present, so a negated range is its complement.
        ('NOT severity<ERROR', 'severity>=WARNING'),
        # Numbers compare by value.
        ('sample=5', 'sample=5.0'),
        ('severity=ERROR', 'severity=500'),
        # The same string written with different escapes.
        ('labels.k="a\\"b"', "labels.k='a\"b'"),
        # Comments are ignored.
        ('severity>=ERROR -- was severity>=WARNING', 'severity>=ERROR'),
    ],
)
def test_compare_cloud_logging_filters_proven_overlap(left, right):
    assert _compare(left, right) is CloudLoggingOverlap.OVERLAP
    assert _compare(right, left) is CloudLoggingOverlap.OVERLAP


@pytest.mark.parametrize(
    "left,right",
    [
        ('resource.type="gce_instance"', 'resource.type="k8s_container"'),
        ('httpRequest.status<200', 'httpRequest.status>=500'),
        ('severity>=ERROR', 'severity<ERROR'),
        ('resource.type="gce_instance"', 'resource.type!="gce_instance"'),
        ('resource.type!="gce_instance"', 'resource.type="gce_instance"'),
        ('sample>=10', 'sample<5'),
        ('sample<5', 'sample>5'),
        ('NOT resource.type="gce_instance"', 'resource.type="gce_instance"'),
        ('-resource.type="gce_instance"', 'resource.type="gce_instance"'),
        ('severity>=ERROR resource.type="gce_instance"', 'resource.type="k8s_container"'),
        ('resource.type=("gce_instance" OR "k8s_container")',
         'resource.type="cloud_run_revision"'),
        ('NOT (resource.type="a" OR resource.type="b")', 'resource.type="b"'),
        # Shape of the GCP-managed _Required and _Default sinks.
        ('LOG_ID("a") OR LOG_ID("b")', 'NOT LOG_ID("a") AND NOT LOG_ID("b")'),
        # A negated range is complemented once the field must be present.
        ('NOT severity>=ERROR', 'severity>=CRITICAL'),
        ('NOT sample!=1 AND sample>0', 'sample=2'),
        # Unevaluable literals don't hide a contradiction elsewhere.
        ('textPayload:"timeout" AND resource.type="a"', 'resource.type="b"'),
        # Severity is one of a fixed set of levels.
        ('severity>ERROR', 'severity<CRITICAL'),
        ('sample=1', 'sample!=1.0'),
        # An inclusive bound doesn't widen an exclusive one at the same value.
        ('severity>WARNING', 'severity=WARNING'),
        ('sample>5', 'sample=5'),
        ('sample<5', 'sample=5'),
        ('sample>5', 'sample>=5 AND sample<=5'),
        ('sample<5', 'sample>=5 AND sample<=5'),
        # Built-in field names ignore letter case.
        ('SEVERITY>=ERROR', 'severity<ERROR'),
        # Only escaped quotes and backslashes are decoded.
        ('labels.k="a\\"b"', 'labels.k="ab"'),
    ],
)
def test_compare_cloud_logging_filters_proven_disjoint(left, right):
    assert _compare(left, right) is CloudLoggingOverlap.DISJOINT
    assert _compare(right, left) is CloudLoggingOverlap.DISJOINT


@pytest.mark.parametrize(
    "left,right",
    [
        ('textPayload:"timeout"', 'textPayload:"error"'),
        ('logName=~"^a"', 'logName=~"^b"'),
        ('labels.env>prod', 'labels.env<stage'),
        ('"timeout"', 'severity>=ERROR'),
        ('NOT LOG_ID("a") AND NOT LOG_ID("b")', 'severity>=ERROR'),
        # A negated range may hold only because the field is absent.
        ('NOT httpRequest.status>=500', 'resource.type="gce_instance"'),
        # Excluding a value inside a range may empty it for integer fields.
        ('httpRequest.status>199 AND httpRequest.status<201',
         'httpRequest.status!=200'),
        # Map keys that differ only in case.
        ('labels.Env="a"', 'labels.env="b"'),
        # A comparison on an array field matches when any element matches.
        ('protoPayload.authorizationInfo.permission="storage.objects.get"',
         'protoPayload.authorizationInfo.permission="storage.objects.list"'),
        ('jsonPayload.shoeSize<7', 'jsonPayload.shoeSize>9'),
        # "true" is an ordinary search term.
        ('NOT true', 'resource.type="a"'),
        # Values that are not severity levels, or not finite numbers.
        ('severity=BOGUS', ''),
        ('labels.mode="inf"', 'labels.mode<10'),
    ],
)
def test_compare_cloud_logging_filters_possible_overlap(left, right):
    assert _compare(left, right) is CloudLoggingOverlap.POSSIBLE
    assert _compare(right, left) is CloudLoggingOverlap.POSSIBLE


@pytest.mark.parametrize(
    "contradiction",
    [
        'severity>=ERROR AND severity<=WARNING',
        'severity>ERROR AND severity<ERROR',
        'resource.type="a" AND resource.type="b"',
        'textPayload:"x" AND NOT textPayload:"x"',
        # Every entry has a severity of at least DEFAULT.
        'NOT severity>=DEFAULT',
        # Every entry has one of the fixed severity levels.
        ' AND '.join(
            f'severity!={level}' for level in (
                'DEFAULT', 'DEBUG', 'INFO', 'NOTICE', 'WARNING',
                'ERROR', 'CRITICAL', 'ALERT', 'EMERGENCY',
            )
        ),
    ],
)
def test_compare_cloud_logging_filters_unsatisfiable_filter_overlaps_nothing(contradiction):
    assert _compare(contradiction, '') is CloudLoggingOverlap.DISJOINT
    assert _compare(contradiction, contradiction) is CloudLoggingOverlap.DISJOINT


def test_compare_cloud_logging_filters_oversized_normal_form_is_possible(caplog):
    # Nine ANDed two-way ORs expand to 2**9 conjunctions, past the cap.
    left = ' AND '.join(f'(oversized{i}="a" OR oversized{i}="b")' for i in range(9))
    right = ' AND '.join(f'oversized{i}="c"' for i in range(9))
    assert _compare(left, right) is CloudLoggingOverlap.POSSIBLE
    assert "too complex to compare" in caplog.text
