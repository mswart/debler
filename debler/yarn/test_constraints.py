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


# ^2.3.0 || 3.x || 4 || 5 ==> >> 2.3.0, < 6
# jquery - ^1.8.3 || ^2.0 ==> < 3
