from functools import partial
import re

from debler.constraints import GreaterThan, GreaterEqual, \
    LessThan, LessEqual, Exact, \
    buildAnd, all


def eval_tilde(version):
    yield GreaterEqual(version)

    # remove prerelease suffix:
    version, *prerelease = re.split('[^0-9.]', version, maxsplit=1)
    segments = version.split('.')
    if len(segments) > 1:  # do not require major version
        segments.pop()
    segments[-1] = str(int(segments[-1]) + 1)
    max_version = '.'.join(segments)
    yield LessThan(max_version)


def eval_equal(version):
    yield Exact(version)


def eval_unequal(version):
    # use for now a newer version
    # TODO implement proper mapping
    yield GreaterThan(version)


def eval_terminal(klass, version):
    yield klass(version)


eval_by_op = {
    '~>': eval_tilde,
    '=': eval_equal,
    '!=': eval_unequal,
    '>': partial(eval_terminal, GreaterThan),
    '>=': partial(eval_terminal, GreaterEqual),
    '<': partial(eval_terminal, LessThan),
    '<=': partial(eval_terminal, LessEqual),
}


def parseConstraints(requirements):
    constraints = []
    for requirement in requirements:
        op = requirement[0]
        version = re.sub('\.([^0-9])', '.~\\1', requirement[1]['version'])
        constraints.extend(eval_by_op[op](version))
    if not constraints:
        return all
    return buildAnd(constraints)
