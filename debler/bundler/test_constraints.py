from debler.bundler.constraints import parseConstraints
from debler import constraints as c

def build(parts):
    for part in parts:
        op, v = part.split(' ', 1)
        yield op, {'version': v}

def parse(*parts):
    return parseConstraints(build(parts))


def test_tilde_major_version():
    assert parse('~> 1.2.3') == \
        c.And([c.GreaterEqual('1.2.3'), c.LessThan('1.3')])
    assert parse('~> 1.2') == \
        c.And([c.GreaterEqual('1.2'), c.LessThan('2')])
    assert parse('~> 1') == \
        c.And([c.GreaterEqual('1'), c.LessThan('2')])


def test_tilde_leading_zeros():
    assert parse('~> 0.2.3') == \
        c.And([c.GreaterEqual('0.2.3'), c.LessThan('0.3')])
    assert parse('~> 0.2') == \
        c.And([c.GreaterEqual('0.2'), c.LessThan('1')])
    assert parse('~> 0') == \
        c.And([c.GreaterEqual('0'), c.LessThan('1')])
