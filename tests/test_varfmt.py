from c7n.varfmt import VarFormat
from c7n.utils import FormatDate, parse_date


def test_format_mixed():
    assert VarFormat().format("{x} abc {Y}", x=2, Y='a') == '2 abc a'


def test_format_pass_list():
    assert VarFormat().format("{x}", x=[1, 2, 3]) == [1, 2, 3]


def test_format_pass_str():
    assert VarFormat().format("{x}", x=2) == 2


def test_format_date_fmt():
    d = FormatDate(parse_date("2018-02-02 12:00"))
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
            ],
        }
    )

    p.expand_variables(dict(my_list=[1, 2, 3], my_int=22))
    test.assertJmes('filters[0].value', p.data, [1, 2, 3])
    test.assertJmes('filters[1].value', p.data, 22)
