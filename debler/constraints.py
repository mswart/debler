import operator

from .builder import Dependency
from .db import Version


class Or():
    def __init__(self, ranges):
        self.ranges = ranges

    def __repr__(self):
        return 'Or({})'.format(', '.join(str(r) for r in self.ranges))


class And():
    def __init__(self, ranges):
        self.ranges = ranges

    def needed_relation(self):
        for range in self.ranges:
            yield from range.needed_relation()

    def __eq__(self, other):
        if type(self) != type(other):
            return NotImplemented

        def key(op):
            return (op.char, op.version)

        selfOperators = sorted(self.ranges, key=key)
        otherOperators = sorted(other.ranges, key=key)
        return selfOperators == otherOperators

    def __repr__(self):
        return 'And({})'.format(', '.join(str(r) for r in self.ranges))


class Operator():
    def __init__(self, version):
        self.version = version

    def __repr__(self):
        return '{}{}'.format(self.char, self.version)

    def __eq__(self, other):
        if type(self) != type(other):
            return NotImplemented
        return self.version == other.version


class GreaterThan(Operator):
    char = '>>'
    op = operator.gt


class GreaterEqual(Operator):
    char = '>='
    op = operator.ge


class LessThan(Operator):
    char = '<<'
    op = operator.lt


class LessEqual(Operator):
    char = '<='
    op = operator.le


class Exact(Operator):
    char = '='
    op = operator.eq


class All():
    pass


all = All()


def dependencies4Constraints(deb_name, pkg, constraints):
    if constraints is all:
        yield Dependency(deb_name, pkg.deb_name)
        return
    if type(constraints) is Or:
        raise NotImplementedError()
    if type(constraints) is And:
        ors = []
        for slot in pkg.slots:
            valid_constraints = []
            for op in constraints.ranges:
                lower = op.op(slot.min_version, Version(str(op.version)))
                upper = op.op(slot.max_version, Version(str(op.version)))
                if lower is upper is False:  # matches never
                    break
                if lower is upper is True:  # matches always
                    pass
                else:
                    valid_constraints.append(op)
            else:
                if not valid_constraints:
                    ors.append('{deb}-{slot}'.format(
                        deb=pkg.deb_name,
                        slot=slot.version))
                elif len(valid_constraints) == 1:
                    ors.append('{dep}-{slot} ({op} {version})'.format(
                        dep=pkg.deb_name,
                        slot=slot.version,
                        op=valid_constraints[0].char,
                        version=valid_constraints[0].version))
                else:
                    for op in valid_constraints:
                        yield Dependency(
                            deb_name,
                            '{dep}-{slot} ({op} {version})'.format(
                                dep=pkg.deb_name,
                                slot=slot.version,
                                op=op.char,
                                version=op.version))
                    break
        if ors:
            yield Dependency(deb_name, ' | '.join(ors))
        return
    raise ValueError(deb_name, pkg, constraints)
