import re

import lepl

import debler.constraints


def expand(cls):
    def call(args):
        return cls(*args)
    return call


def ret(v):
    def call(arg):
        return v
    return call


class Range():
    def __init__(self, start, end):
        self.start = start
        self.end = end

    def __repr__(self):
        return 'Range({!r}, {!r})'.format(self.start, self.end)


class Version():
    def __init__(self, parts):
        self.parts = parts
        while parts and parts[-1] == 'x':
            parts.pop()

    def special(self):
        return len(self.parts) > 3

    def __str__(self):
        if self.special():
            return '.'.join(str(r) for r in self.parts[:3]) + '-' + self.parts[-1]
        return '.'.join(str(r) for r in self.parts)

    def __eq__(self, other):
        return str(self) == str(other)


class Operator():
    def __init__(self, version):
        self.version = version

    def __repr__(self):
        return '{}{!r}'.format(self.char, self.version)

    def needed_relation(self):
        assert not self.version.special()
        yield self.char, self.version


class Caret(Operator):
    char = '^'

    def needed_relation(self):
        assert not self.version.special()
        yield '>=', self.version
        new_parts = list(self.version.parts)
        new_parts[-2] += 1
        yield '<', Version(new_parts)


class Tilde(Operator):
    char = '~'


class Gt(Operator):
    char = '>'


class Ge(Operator):
    char = '>='


class Lt(Operator):
    char = '<'


class Le(Operator):
    char = '<='


class Exact(Operator):
    char = '='


ops_by_char = {
    #'': Exact
}

for cls in Operator.__subclasses__():
    ops_by_char[cls.char] = cls


def select_operator(op, version):
    return ops_by_char[op](version)


nr = lepl.UnsignedInteger() > expand(int)
xr = lepl.Literal('x') | lepl.Literal('X') | lepl.Literal('*') | nr

part = nr | lepl.Plus(lepl.Literal('-') & lepl.Letter() | lepl.Digit())
parts = part & lepl.Star(lepl.Literal('.') & part)
build = parts
pre = parts
qualifier = lepl.Optional(lepl.Literal('-') & pre) \
    & lepl.Optional(lepl.Literal('+') & build)

partial = xr & lepl.Optional(
    ~lepl.Literal('.') & xr &
    lepl.Optional(~lepl.Literal('.') & xr & qualifier)) > Version
primitive = (
    lepl.Literal('>=') |
    lepl.Literal('<=') |
    lepl.Literal('<') |
    lepl.Literal('>') |
    lepl.Literal('=')) & ~lepl.Star(lepl.Space()) & partial > expand(select_operator)

eqbydefault = partial > expand(Exact)
caret = ~lepl.Literal('^') & partial > expand(Caret)
tilde = ~lepl.Literal('~') & partial > expand(Tilde)

simple = primitive | eqbydefault | tilde | caret
hyphen = partial & lepl.Drop(lepl.Literal(' - ')) & partial > Range
range = hyphen | simple & lepl.Star(lepl.Literal(' ') & simple) | lepl.Literal('') > debler.constraints.All
logicalOr = lepl.Star(lepl.Space()) & lepl.Literal('||') & lepl.Star(lepl.Space())
rangeSet = range & lepl.Star(lepl.Drop(logicalOr) & range) > debler.constraints.Or


def parseVersion(version):
    version = version.strip()
    if version == '*':
        return debler.constraints.all
    if '-' in version:
        main, special = version.split('-')
        return Version(main.split('.') + [special])
    else:
        return Version(version.split('.'))


def parseConstraints(constraints):
    if not constraints.strip():
        return debler.constraints.all
    if constraints.strip() == '*':
        return debler.constraints.all
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
                andParts.append(Ge(parseVersion(a)))
                andParts.append(Le(parseVersion(b)))
                continue
            if part.startswith('^'):
                version = parseVersion(part[1:])
                andParts.append(debler.constraints.GreaterEqual(version))
                upperVersion = Version([])
                for part in version.parts:
                    if part == '0':
                        upperVersion.parts.append(part)
                    else:
                        upperVersion.parts.append(int(part) + 1)
                        break
                else:  # we have only 0 as parts (like ^0.0 or ^0.0.x)
                    andParts.append(debler.constraints.LessThan(Version(['0', '1'])))
                    continue
                andParts.append(debler.constraints.LessThan(upperVersion))
                continue
            for op in ops_by_char:
                if part.startswith(op):
                    raise ValueError((op, part))
            andParts.append(Exact(parseVersion(part)))
        # todo range
        if len(andParts) == 1:
            orParts.append(andParts[0])
        else:
            orParts.append(debler.constraints.And(andParts))
    if len(orParts) == 1:
        return orParts[0]
    else:
        return debler.constraints.Or(orParts)
    # return rangeSet.parse(str)
