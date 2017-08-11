import os.path

from debler.bundler.parser import Parser


def gemfile(name):
    return os.path.realpath(os.path.join(
        __file__,
        '..', '..', '..',
        'support', 'bundler', 'Gemfile-' + name))


def test_git_oldkeyword_double_string():
    p = Parser(gemfile('git-oldkeyword-double'))
    assert len(p.gems) == 10
