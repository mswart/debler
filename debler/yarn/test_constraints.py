from debler.yarn.constraints import parseConstraints
from debler import constraints


def test_star():
    assert parseConstraints('*') is constraints.all


def test_implicit_star():
    assert parseConstraints('') is constraints.all

# ^2.3.0 || 3.x || 4 || 5 ==> >> 2.3.0, < 6
# jquery - ^1.8.3 || ^2.0 ==> < 3
