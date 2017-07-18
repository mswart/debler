import builtins
from collections import defaultdict
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
        self.version = Version(str(version))

    def __repr__(self):
        return '{}{}'.format(self.char, self.version)

    def __eq__(self, other):
        if type(self) != type(other):
            return NotImplemented
        return self.version == other.version


class GreaterThan(Operator):
    char = '>>'
    op = operator.gt
    group = '>'


class GreaterEqual(Operator):
    char = '>='
    op = operator.ge
    group = '>'


class LessThan(Operator):
    char = '<<'
    op = operator.lt
    group = '<'


class LessEqual(Operator):
    char = '<='
    op = operator.le
    group = '<'


class Exact(Operator):
    char = '='
    op = operator.eq
    group = '='


class All():
    pass


all = All()


def buildAnd(ops):
    if len(ops) == 1:
        return ops[0]
    by_group = defaultdict(list)
    for op in ops:
        by_group[op.group].append(op)
    if '=' in by_group:
        eq = by_group.pop('=')
        assert len(eq) == 1, 'multiple equals are not implemented yet'
        return eq[0]
    # simplify < constraints
    cleared = []
    if '>' in by_group:
        most_specifist = by_group['>'][0]
        for op in by_group['>'][1:]:
            if Version(str(op.version)) < Version(str(most_specifist.version)):
                continue
            if op.version == most_specifist.version and op.char == '>=':
                continue
            most_specifist = op
        cleared.append(most_specifist)
    if '<' in by_group:
        most_specifist = by_group['<'][0]
        for op in by_group['<'][1:]:
            if Version(str(op.version)) > Version(str(most_specifist.version)):
                continue
            if op.version == most_specifist.version and op.char == '>=':
                continue
            most_specifist = op
        cleared.append(most_specifist)
    if len(cleared) == 1:
        return cleared[0]
    else:
        return And(cleared)


def rstripZeros(version):
    parts = str(version).split('.')
    while parts[-1] == '0':
        parts.pop()
    return '.'.join(parts)


def buildOr(ands):
    if len(ands) == 1:
        return ands[0]
    if not builtins.all(isinstance(_and, And) for _and in ands):
        return Or(ands)
    ranges = sorted(ands, key=lambda range: (range.ranges[0].char, range.ranges[0].version))
    closedRanges = []
    current = ranges[0]
    closed = False
    for range in ranges[1:]:
        if closed:
            closedRanges.append(current)
            current = range
            continue
        if rstripZeros(current.ranges[1].version) == \
                rstripZeros(range.ranges[0].version):
            current = And([current.ranges[0], range.ranges[1]])
        else:
            closed = True
    if closed:
        closedRanges.append(current)
        current = range
    closedRanges.append(current)
    if len(closedRanges) < 2:
        return closedRanges[0]
    else:
        return Or(closedRanges)
    builtins
    asd
    by_group = defaultdict(list)
    for op in ops:
        by_group[op.group].append(op)
    if '=' in by_group:
        eq = by_group.pop('=')
        assert len(eq) == 1, 'multiple equals are not implemented yet'
        return eq[0]
    # simplify < constraints
    cleared = []
    if '>' in by_group:
        most_specifist = by_group['>'][0]
        for op in by_group['>'][1:]:
            if Version(str(op.version)) < Version(str(most_specifist.version)):
                continue
            if op.version == most_specifist.version and op.char == '>=':
                continue
            most_specifist = op
        cleared.append(most_specifist)
    if '<' in by_group:
        most_specifist = by_group['<'][0]
        for op in by_group['<'][1:]:
            if Version(str(op.version)) > Version(str(most_specifist.version)):
                continue
            if op.version == most_specifist.version and op.char == '>=':
                continue
            most_specifist = op
        cleared.append(most_specifist)
    if len(cleared) == 1:
        return cleared[0]
    else:
        return And(cleared)


def dependencies4Constraints(deb_name, pkg, constraints):
    if constraints is all:
        yield Dependency(deb_name, pkg.deb_name)
        return
    if type(constraints) is Or:
        raise NotImplementedError('Cannot generate dependencies for {}: {}'.format(constraints, [s.version for s in pkg.slots]))
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
    if type(constraints) is Exact:
        yield Dependency(
            deb_name,
            '{dep}-{version}'.format(
                dep=pkg.deb_name,
                version=constraints.version))
        return
    if isinstance(constraints, Operator):
        ors = []
        for slot in pkg.slots:
            lower = constraints.op(slot.min_version,
                                   Version(str(constraints.version)))
            upper = constraints.op(slot.max_version,
                                   Version(str(constraints.version)))
            if lower is upper is False:  # matches never
                continue
            if lower is upper is True:  # matches always
                ors.append('{dep}-{slot}'.format(
                    dep=pkg.deb_name,
                    slot=slot.version))
            else:
                ors.append('{dep}-{slot} ({op} {version})'.format(
                    dep=pkg.deb_name,
                    slot=slot.version,
                    op=constraints.char,
                    version=constraints.version))
        if ors:
            yield Dependency(deb_name, ' | '.join(ors))
        return
    raise ValueError(deb_name, pkg, constraints)
