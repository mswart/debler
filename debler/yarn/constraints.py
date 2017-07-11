from functools import partial
import re

from debler.constraints import GreaterThan, GreaterEqual, \
    LessThan, LessEqual, Exact, \
    buildAnd, buildOr, All, all


class Version():
    def __init__(self, parts):
        self.parts = parts
        while parts and parts[-1] == 'x':
            parts.pop()

    @property
    def special(self):
        return len(self.parts) > 3

    @property
    def partial(self):
        return len(self.parts) < 3

    def incLatest(self):
        self.parts[-1] = str(int(self.parts[-1]) + 1)

    def __str__(self):
        if self.special:
            return '.'.join(str(r) for r in self.parts[:3]) + '-' + self.parts[-1]
        return '.'.join(str(r) for r in self.parts)

    def __repr__(self):
        return 'v' + str(self)

    def __eq__(self, other):
        return str(self) == str(other)


def parseVersion(version):
    version = version.strip()
    if version == '*':
        return all
    if '-' in version:
        main, special = version.split('-', 1)
        return Version(main.split('.') + [special])
    else:
        return Version(version.split('.'))


def eval_caret(version):
    yield GreaterEqual(version)
    upperVersion = Version([])
    for part in version.parts:
        if part == '0':
            upperVersion.parts.append(part)
        else:
            upperVersion.parts.append(int(part) + 1)
            yield LessThan(upperVersion)
            return
    # we have only 0 as parts (like ^0.0 or ^0.0.x)
    yield LessThan(Version(['0', '1']))


def eval_tilde(version):
    yield GreaterEqual(version)
    if len(version.parts) == 1:
        upperVersion = Version(version.parts[:1])
    else:
        upperVersion = Version(version.parts[:2])
    upperVersion.incLatest()
    yield LessThan(upperVersion)


def eval_equal(version):
    if version.partial:
        yield GreaterEqual(version)
        version = Version(list(version.parts))
        version.incLatest()
        yield LessThan(version)
    else:
        yield Exact(version)


def eval_terminal(klass, version):
    yield klass(version)


eval_by_op = {
    '^': eval_caret,
    '~': eval_tilde,
    '=': eval_equal,
    '': eval_equal,
    '>': partial(eval_terminal, GreaterThan),
    '>=': partial(eval_terminal, GreaterEqual),
    '<': partial(eval_terminal, LessThan),
    '<=': partial(eval_terminal, LessEqual),
}


def parseConstraints(constraints):
    if not constraints.strip():
        return all
    if constraints.strip() == '*':
        return all
    # move range versions into own token:
    constraints = constraints.replace(' - ', '#')
    if ' ' in constraints:
        constraints = re.sub(r'([!^<>=]+) +', '\\1', constraints)
    orRawParts = [orPart.strip() for orPart in constraints.split('||')]
    orParts = []
    for part in orRawParts:
        andParts = []
        for part in part.split(' '):
            if '#' in part:  # range
                a, b = part.split('#')
                andParts.append(GreaterEqual(parseVersion(a)))
                b = parseVersion(b)
                if b.partial:
                    b.incLatest()
                    andParts.append(LessThan(b))
                else:
                    andParts.append(LessEqual(b))
            else:
                opLen = 0
                while not part[opLen].isdigit():
                    opLen += 1
                op, version = part[:opLen], part[opLen:]
                andParts.extend(eval_by_op[op](parseVersion(version)))
        orParts.append(buildAnd(andParts))
    return buildOr(orParts)
