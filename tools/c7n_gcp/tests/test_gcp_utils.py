# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import pytest

from c7n_gcp.utils import (
    canonicalize_cloud_logging_filter,
    cloud_logging_filters_overlap,
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
    assert operator in parsed["operators"]


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
    assert logical_op in parsed["operators"]


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
    operators = set(parsed["operators"])

    assert operators.issuperset(
        {"and", "or", "not", "=", "!=", ">", ">=", "<", "<=", ":", "=~", "!~"}
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


def test_parse_cloud_logging_filter_empty_expression_defaults_to_true_term():
    parsed = parse_cloud_logging_filter("")
    assert parsed["terms"] == ["true"]
    assert parsed["predicates"] == []
    assert parsed["operators"] == []


def test_parse_cloud_logging_filter_none_expression_defaults_to_true_term():
    parsed = parse_cloud_logging_filter(None)
    assert parsed["terms"] == ["true"]
    assert parsed["predicates"] == []
    assert parsed["operators"] == []


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
    assert parsed["predicates"][0]["lhs"] == "resource.type"
    assert parsed["predicates"][0]["op"] == "="
    assert parsed["predicates"][0]["rhs"] == '( "gce_instance" )'


def test_parse_cloud_logging_filter_handles_parenthesized_lhs_expression():
    parsed = parse_cloud_logging_filter("sample(insertId)=1")
    assert parsed["predicates"][0]["lhs"] == "sample ( insertId )"
    assert parsed["predicates"][0]["op"] == "="
    assert parsed["predicates"][0]["rhs"] == "1"


def test_canonicalize_cloud_logging_filter_term_only_expression():
    assert canonicalize_cloud_logging_filter("UNSTRUCTURED_TERM") == "unstructured_term"


def test_cloud_logging_filters_overlap_exact_equivalent_expressions():
    first = 'severity>=ERROR AND resource.type="gce_instance"'
    second = 'resource.type="gce_instance" AND severity>=ERROR'
    assert cloud_logging_filters_overlap(
        canonicalize_cloud_logging_filter(first),
        canonicalize_cloud_logging_filter(second),
    )


def test_cloud_logging_filters_overlap_true_overlaps_anything():
    assert cloud_logging_filters_overlap('true', 'severity>=ERROR')
    assert cloud_logging_filters_overlap('severity>=ERROR', 'true')


def test_cloud_logging_filters_overlap_detects_simple_disjoint_equality():
    left = canonicalize_cloud_logging_filter('resource.type="gce_instance"')
    right = canonicalize_cloud_logging_filter('resource.type="k8s_container"')
    assert not cloud_logging_filters_overlap(left, right)


def test_cloud_logging_filters_overlap_detects_simple_disjoint_numeric_ranges():
    left = canonicalize_cloud_logging_filter('httpRequest.status<200')
    right = canonicalize_cloud_logging_filter('httpRequest.status>=500')
    assert not cloud_logging_filters_overlap(left, right)


def test_cloud_logging_filters_overlap_detects_disjoint_severity_ranges():
    left = canonicalize_cloud_logging_filter('severity>=ERROR')
    right = canonicalize_cloud_logging_filter('severity<ERROR')
    assert not cloud_logging_filters_overlap(left, right)


def test_cloud_logging_filters_overlap_detects_eq_vs_not_eq_disjoint_left_eq():
    left = canonicalize_cloud_logging_filter('resource.type="gce_instance"')
    right = canonicalize_cloud_logging_filter('resource.type!="gce_instance"')
    assert not cloud_logging_filters_overlap(left, right)


def test_cloud_logging_filters_overlap_detects_eq_vs_not_eq_disjoint_right_eq():
    left = canonicalize_cloud_logging_filter('resource.type!="gce_instance"')
    right = canonicalize_cloud_logging_filter('resource.type="gce_instance"')
    assert not cloud_logging_filters_overlap(left, right)


def test_cloud_logging_filters_overlap_non_numeric_comparison_ops_fall_back_to_overlap():
    left = canonicalize_cloud_logging_filter('textPayload:"timeout"')
    right = canonicalize_cloud_logging_filter('textPayload:"error"')
    assert cloud_logging_filters_overlap(left, right)


def test_cloud_logging_filters_overlap_combined_numeric_constraints_are_supported():
    left = canonicalize_cloud_logging_filter('sample=1 AND sample>0')
    right = canonicalize_cloud_logging_filter('sample<=2')
    assert cloud_logging_filters_overlap(left, right)


def test_cloud_logging_filters_overlap_strict_greater_than_branch():
    left = canonicalize_cloud_logging_filter('sample>0')
    right = canonicalize_cloud_logging_filter('sample<=10')
    assert cloud_logging_filters_overlap(left, right)


def test_cloud_logging_filters_overlap_non_coercible_ordered_values_fall_back_to_overlap():
    left = canonicalize_cloud_logging_filter('labels.env>prod')
    right = canonicalize_cloud_logging_filter('labels.env<stage')
    assert cloud_logging_filters_overlap(left, right)


def test_cloud_logging_filters_overlap_complex_logic_default_is_conservative():
    left = canonicalize_cloud_logging_filter('NOT resource.type="gce_instance"')
    right = canonicalize_cloud_logging_filter('resource.type="gce_instance"')
    assert not cloud_logging_filters_overlap(left, right)


def test_cloud_logging_filters_overlap_disjoint_when_right_upper_less_than_left_lower():
    left = canonicalize_cloud_logging_filter('sample>=10')
    right = canonicalize_cloud_logging_filter('sample<5')
    assert not cloud_logging_filters_overlap(left, right)


def test_cloud_logging_filters_overlap_disjoint_on_exclusive_touching_bounds():
    left = canonicalize_cloud_logging_filter('sample<5')
    right = canonicalize_cloud_logging_filter('sample>5')
    assert not cloud_logging_filters_overlap(left, right)


def test_cloud_logging_filters_overlap_exclusion_not_clause_is_treated_as_complex():
    # A filter that combines a positive condition with a NOT exclusion is
    # treated as complex logic.  The default conservative behaviour is to
    # report no overlap so that sinks with exclusion clauses are never
    # incorrectly grouped with other sinks.
    left = canonicalize_cloud_logging_filter(
        'severity>=ERROR AND NOT resource.type="gce_instance"'
    )
    right = canonicalize_cloud_logging_filter('severity>=ERROR')
    assert not cloud_logging_filters_overlap(left, right)
