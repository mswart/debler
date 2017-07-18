from debler.yarn.constraints import parseConstraints
from debler import constraints as c


def test_star():
    assert parseConstraints('*') is c.all


def test_implicit_star():
    assert parseConstraints('') is c.all


def test_caret():
    assert parseConstraints('^1.2.3') == \
        c.And([c.GreaterEqual('1.2.3'), c.LessThan('2')])
    assert parseConstraints('^0.2.3') == \
        c.And([c.GreaterEqual('0.2.3'), c.LessThan('0.3')])
    assert parseConstraints('^0.0.3') == \
        c.And([c.GreaterEqual('0.0.3'), c.LessThan('0.0.4')])
    assert parseConstraints('^1.2.3-beta.2') == \
        c.And([c.GreaterEqual('1.2.3-beta.2'), c.LessThan('2')])
    assert parseConstraints('^0.0.3-beta') == \
        c.And([c.GreaterEqual('0.0.3-beta'), c.LessThan('0.0.4')])


def test_caret_with_x():
    assert parseConstraints('^1.2.x') == \
        c.And([c.GreaterEqual('1.2'), c.LessThan('2')])
    assert parseConstraints('^0.0.x') == \
        c.And([c.GreaterEqual('0.0'), c.LessThan('0.1')])
    assert parseConstraints('^0.0') == \
        c.And([c.GreaterEqual('0.0'), c.LessThan('0.1')])


def test_caret_with_spaces():
    assert parseConstraints('^ 1.2.3') == \
        c.And([c.GreaterEqual('1.2.3'), c.LessThan('2')])


def test_ranges():
    assert parseConstraints('1.2.3 - 2.3.4') == \
        c.And([c.GreaterEqual('1.2.3'), c.LessEqual('2.3.4')])
    assert parseConstraints('1.2 - 2.3.4') == \
        c.And([c.GreaterEqual('1.2'), c.LessEqual('2.3.4')])


def test_partial_ranges():
    assert parseConstraints('1.2.3 - 2.3') == \
        c.And([c.GreaterEqual('1.2.3'), c.LessThan('2.4')])
    assert parseConstraints('1.2.3 - 2') == \
        c.And([c.GreaterEqual('1.2.3'), c.LessThan('3')])


def test_partial_equal():
    assert parseConstraints('1') == \
        c.And([c.GreaterEqual('1'), c.LessThan('2')])
    assert parseConstraints('1.2') == \
        c.And([c.GreaterEqual('1.2'), c.LessThan('1.3')])


def test_tilde():
    assert parseConstraints('~1.2.3') == \
        c.And([c.GreaterEqual('1.2.3'), c.LessThan('1.3')])
    assert parseConstraints('~1.2') == \
        c.And([c.GreaterEqual('1.2'), c.LessThan('1.3')])
    assert parseConstraints('~1') == \
        c.And([c.GreaterEqual('1'), c.LessThan('2')])


def test_tilde_leading_zeros():
    assert parseConstraints('~0.2.3') == \
        c.And([c.GreaterEqual('0.2.3'), c.LessThan('0.3')])
    assert parseConstraints('~0.2') == \
        c.And([c.GreaterEqual('0.2'), c.LessThan('0.3')])
    assert parseConstraints('~0') == \
        c.And([c.GreaterEqual('0'), c.LessThan('1')])


def test_simplified_ands():
    assert parseConstraints('^2.3.0 > 2.3.6') == \
        c.And([c.GreaterThan('2.3.6'), c.LessThan('3')])
    assert parseConstraints('^2.3.0 >= 2.3.6') == \
        c.And([c.GreaterEqual('2.3.6'), c.LessThan('3')])


def test_merged_ors():
    assert parseConstraints('^2.3.0 || 3.x || 4 || 5') == \
        c.And([c.GreaterEqual('2.3.0'), c.LessThan('6')])
    assert parseConstraints('^1.8.3 || ^2.0') == \
        c.And([c.GreaterEqual('1.8.3'), c.LessThan('3')])

    assert parseConstraints('^2.0.0 || ^1.1.13') == \
        c.And([c.GreaterEqual('1.1.13'), c.LessThan('3')])
