import pytest

from c7n.varfmt import VarFormat
from c7n.utils import parse_date, format_string_values


def test_format_mixed():
    assert VarFormat().format("{x} abc {Y}", x=2, Y='a') == '2 abc a'


def test_format_pass_list():
    assert VarFormat().format("{x}", x=[1, 2, 3]) == [1, 2, 3]


def test_format_pass_int():
    assert VarFormat().format("{x}", x=2) == 2


def test_format_pass_empty():
    assert VarFormat().format("{x}", x=[]) == []
    assert VarFormat().format("{x}", x=None) is None
    assert VarFormat().format("{x}", x={}) == {}
    assert VarFormat().format("{x}", x=0) == 0


def test_format_string_values_empty():
    formatter = VarFormat().format
    assert format_string_values({'a': '{x}'}, x=None, formatter=formatter) == {
        'a': None
    }
    assert format_string_values({'a': '{x}'}, x={}, formatter=formatter) == {'a': {}}
    assert format_string_values({'a': '{x}'}, x=[], formatter=formatter) == {'a': []}
    assert format_string_values({'a': '{x}'}, x=0, formatter=formatter) == {'a': 0}


def test_format_manual_to_auto():
    # coverage check for stdlib impl behavior
    with pytest.raises(ValueError) as err:
        VarFormat().format("{0} {}", 1, 2)
    assert str(err.value) == (
        'cannot switch from manual field specification to automatic field numbering'
    )


def test_format_auto_to_manual():
    # coverage check for stdlib impl behavior
    with pytest.raises(ValueError) as err:
        VarFormat().format('{} {1}', 'a', 'b')
    assert str(err.value) == (
        'cannot switch from manual field specification to automatic field numbering'
    )


def test_format_date_fmt():
    d = parse_date("2018-02-02 12:00")
    assert VarFormat().format("{:%Y-%m-%d}", d, "2018-02-02")
    assert VarFormat().format("{}", d) == d


def test_load_policy_var_retain_type(test):
    p = test.load_policy(
        {
            'name': 'x',
            'resource': 'aws.sqs',
            'filters': [
                {'type': 'value', 'key': 'why', 'op': 'in', 'value': "{my_list}"},
                {'type': 'value', 'key': 'why_not', 'value': "{my_int}"},
                {'key': "{my_date:%Y-%m-%d}"},
            ],
        }
    )

    p.expand_variables(
        dict(my_list=[1, 2, 3], my_int=22, my_date=parse_date('2022-02-01 12:00'))
    )
    test.assertJmes('filters[0].value', p.data, [1, 2, 3])
    test.assertJmes('filters[1].value', p.data, 22)
    test.assertJmes('filters[2].key', p.data, "2022-02-01")
