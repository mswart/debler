from debler.constraints import GreaterThan, GreaterEqual, \
    LessThan, LessEqual, \
    And, \
    dependencies4Constraints
from debler.db import PkgInfo, SlotInfo
from debler.builder import Dependency
from debler.yarn.constraints import parseConstraints


def test_greater_than_eq():
    assert GreaterThan('2.3.6') == GreaterThan('2.3.6')
    assert GreaterThan('2.3.4') != GreaterThan('2.3.6')


def test_greater_equal_eq():
    assert GreaterEqual('2.3.6') == GreaterEqual('2.3.6')
    assert GreaterEqual('2.3.4') != GreaterEqual('2.3.6')


def test_greater_ne():
    assert GreaterEqual('2.3.4') != GreaterThan('2.3.4')


def test_less_than_eq():
    assert LessThan('2.3.6') == LessThan('2.3.6')
    assert LessThan('2.3.4') != LessThan('2.3.6')


def test_less_equal_eq():
    assert LessEqual('2.3.6') == LessEqual('2.3.6')
    assert LessEqual('2.3.4') != LessEqual('2.3.6')


def test_less_ne():
    assert LessEqual('2.3.4') != LessThan('2.3.4')


def test_ne():
    assert LessEqual('2.3.4') != GreaterEqual('2.3.4')
    assert LessThan('2.3.4') != GreaterThan('2.3.4')


def test_and_eq():
    assert And([GreaterEqual('2.3.4'), LessThan('3')]) == \
        And([GreaterEqual('2.3.4'), LessThan('3')])
    assert And([GreaterEqual('2.3.4'), LessThan('3')]) == \
        And([LessThan('3'), GreaterEqual('2.3.4')])


def build_pkg_info(dep_name, *slots):
    db = object()
    pkg_info = PkgInfo(db, None, dep_name, dep_name, {}, [])
    for slot in slots:
        pkg_info.slots.append(SlotInfo(db, pkg_info, None, slot, {}, {}))
    return pkg_info


def test_deps_for_all():
    pkg = build_pkg_info('bar', '1', '2')
    assert set(dependencies4Constraints('foo', pkg, parseConstraints('*'))) == \
        {Dependency('foo', 'bar')}


def test_deps_caret2():
    pkg = build_pkg_info('bar', '1.1', '1.2', '1.3', '1.4', '2.0', '2.1')
    assert set(dependencies4Constraints('foo', pkg, parseConstraints('^1.2.3'))) == \
        {Dependency('foo', 'bar-1.4 | bar-1.3 | bar-1.2 (>= 1.2.3)')}


def test_deps_eq():
    pkg = build_pkg_info('bar', '1.1')
    assert set(dependencies4Constraints('foo', pkg, parseConstraints('1.2.3'))) == \
        {Dependency('foo', 'bar-1.2.3')}


def test_deps_gt():
    pkg = build_pkg_info('bar', '1.1', '1.2', '1.3')
    assert set(dependencies4Constraints('foo', pkg, parseConstraints('>=1.2.3'))) == \
        {Dependency('foo', 'bar-1.3 | bar-1.2 (>= 1.2.3)')}
