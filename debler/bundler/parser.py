import lepl
import os
from string import ascii_letters, digits

from .builder import GemVersion


def build_str(s):
    return ''.join(s)


class Source():
    def __init__(self, source):
        self.source = source

    def __repr__(self):
        return 'Source({})'.format(self.source)


class GemfileGem():
    def __init__(self, name, constraints, opts):
        self.name = name
        self.constraints = constraints
        self.opts = opts
        self.opts['envs'] = ['default']

    def __repr__(self):
        return 'Gem({}, {}, {})'.format(self.name, self.constraints, self.opts)


class Gem():
    def __init__(self, name, version, constraints, envs, require=False, path=None):
        self.name = name
        self.version = version
        self.constraints = constraints
        self.envs = envs
        self.deps = {}
        self.require = require
        self.path = path
        self.revision = None
        self.remote = None

    def __repr__(self):
        v = str(self.version)
        if self.constraints:
            v += ' (' + ', '.join(self.constraints) + ')'
        if self.revision:
            v += ' (rev={})'.format(self.revision)
        return 'Gem({}, v={}, require={}, envs={}, deps={})'.format(
            self.name, v, self.require, ','.join(self.envs) or '-', self.deps)


class Group():
    def __init__(self, envs, *gems):
        self.envs = envs
        self.gems = gems

    def __repr__(self):
        return 'Group({}, {})'.format(self.envs, self.gems)


def build_gems(envs, *gems):
    for gem in gems:
        gem.opts['envs'] = envs
    return gems


def expand(cls):
    def call(args):
        return cls(*args)
    return call


def ret(v):
    def call(arg):
        return v
    return call


def fetch_env(env):
    return os.environ.get(env)


def eval_conditional(cont, expr, alternative):
    if cont:
        return expr
    else:
        return alternative


class Assignment():
    def __init__(self, name, value):
        self.name = name
        self.value = value


class VariableAccess():
    def __init__(self, name):
        self.name = name


maybespace = lepl.Drop(lepl.Optional(lepl.Space()))

singlestring = (lepl.Drop('\'') & lepl.Star(lepl.AnyBut('\'')) & lepl.Drop('\'')) > build_str
douplestring = (lepl.Drop('"') & lepl.Star(lepl.AnyBut('"')) & lepl.Drop('"')) > build_str
string = singlestring | douplestring
symbol = lepl.Drop(':') & lepl.Star(lepl.AnyBut('\':\t\n ')) > build_str
identifier = lepl.Any(ascii_letters + '_') & lepl.Star(lepl.Any(ascii_letters + '_' + digits)) & lepl.Optional(lepl.Any('?!')) > build_str
variable_read = identifier > expand(VariableAccess)

line_comment = lepl.Literal('#') & lepl.Star(lepl.AnyBut('\n'))
newline = lepl.Drop(lepl.Star(lepl.Space()) & lepl.Optional(line_comment) & lepl.Literal('\n') & lepl.Star(lepl.Space()))

# define ruby line
spaces = lepl.Star(lepl.Space())
breakablespaces = spaces | (lepl.Literal('\n ') & spaces )

ruby = lepl.Drop('ruby') & ~lepl.Space() & string >> ret(None)

expr = lepl.Delayed()

true = lepl.Literal('true') >> ret(True)
false = lepl.Literal('false') >> ret(False)
constant_value = true | false | symbol | string | variable_read

env_expr = lepl.Drop('ENV[') & maybespace & string & maybespace & lepl.Drop(']') > expand(fetch_env)

parentheses_expr = lepl.Drop('(') & maybespace & expr  & maybespace & lepl.Drop(')')
simple_expr = parentheses_expr | env_expr | constant_value

conditional_expr = simple_expr & maybespace & lepl.Drop('?') & maybespace & simple_expr & maybespace & lepl.Drop(':') & maybespace & expr > expand(eval_conditional)
expr += conditional_expr | simple_expr

keywoard_value = simple_expr
keyword_name = lepl.Star(lepl.AnyBut(':\t=> ')) > build_str
keyword_newstyle = keyword_name & lepl.Drop(':') & ~spaces & keywoard_value > tuple
keyword_oldstyle = lepl.Drop(':') & keyword_name & ~spaces & lepl.Drop('=>') & ~spaces & keywoard_value > tuple
keyword = keyword_oldstyle | keyword_newstyle
keywords = lepl.Star(~lepl.Drop(',') & ~breakablespaces & keyword) > dict

# define gem line
gem = lepl.Drop('gem') & ~lepl.Space() & string
# optional version constraints
gem_constraint_value = variable_read | string
gem_constraints = lepl.Star(~spaces & ~lepl.Drop(',') & ~spaces & ~lepl.Lookahead(keyword) & gem_constraint_value) > tuple
gem &= gem_constraints
# optional keywords
gem &= keywords
# comment
gem &= lepl.Drop(lepl.Star(lepl.Space()) & lepl.Optional(line_comment))
gem = gem > expand(GemfileGem)

# gem group
group_envs = symbol & lepl.Star(lepl.Drop(',') & ~lepl.Space() & symbol) > tuple
group_start = ~lepl.Literal('group') & ~lepl.Space() & group_envs & ~lepl.Space() & ~lepl.Literal('do')
group_content = lepl.Star(gem | newline)
group_end = ~lepl.Literal('end')
group = group_start & group_content & group_end > expand(build_gems)

source = ~lepl.Literal('source') & ~lepl.Space() & string > expand(Source)

var_assignment = identifier & maybespace & lepl.Drop('=') & maybespace & expr > expand(Assignment)


parser = lepl.Star(source | var_assignment | ruby | gem | group | newline)


class Parser():
    def __init__(self, gemfile, ignore_gems=[]):
        self.gems = {}
        self.parse_gemfile(gemfile)
        self.parse_gemlock(gemfile + '.lock')

        # ignore bundler listing:
        self.gems.pop('bundler', None)
        # ignore custom gems:
        for gem in ignore_gems:
            self.gems.pop(gem, None)

    def parse_gemfile(self, file):
        d = parser.parse(open(file, 'r'))
        assignments = {}
        self.required_gems = []
        for o in d:
            if type(o) is Assignment:
                assignments[o.name] = o.value
            elif type(o) is GemfileGem:
                self.required_gems.append(o.name)
                self.gems[o.name] = Gem(o.name, None, self.resolve(assignments, o.constraints),
                                        o.opts['envs'], o.opts.get('require', True),
                                        o.opts.get('path', None))
            elif type(o) is tuple:
                for os in o:
                    self.required_gems.append(os.name)
                    self.gems[os.name] = Gem(os.name, None, self.resolve(assignments, os.constraints),
                                             os.opts['envs'], os.opts.get('require', True),
                                             os.opts.get('path', None))

    def resolve(self, assignments, constraints):
        return tuple(assignments[c.name] if type(c) is VariableAccess else c for c in constraints)

    def parse_gemlock(self, file):
        current_state = None
        current_lines = []
        for line in open(file, 'r'):
            if not line.strip():
                continue
            if line[0] != ' ':
                if current_state is not None:
                    getattr(self, 'parse_' + current_state.replace(' ', '_'))(current_lines)
                current_state = line.strip()
                current_lines = []
            else:
                current_lines.append(line.rstrip())

    def parse_GEM(self, lines):
        assert lines[0][0:10] == '  remote: '
        self.remote = lines[0][10:]
        assert lines[1][0:8] == '  specs:'
        self.parse_specs(lines[2:])

    def parse_GIT(self, lines):
        for pos, line in enumerate(lines):
            if line.startswith('  revision: '):
                revision = line[12:]
            if line.startswith('  remote: '):
                repository = line[10:]
            if line.startswith('  specs:'):
                break
        current_gem = self.parse_specs(lines[pos+1:])
        current_gem.remote = repository
        current_gem.revision = revision

    def parse_specs(self, lines):
        current_gem = None
        for line in lines:
            if line[4] == ' ':  # skip dependencies
                a, b = (line.strip() + ' ').split(' ', 1)
                current_gem.deps[a] = b[1:-2] if b else True
                continue
            name, version = line.strip().split(' ', 1)
            version = version[1:-1]
            if version.endswith('-java'):
                continue
            if name in self.gems:
                self.gems[name].version = GemVersion.fromstr(version)
            else:
                self.gems[name] = Gem(name, GemVersion.fromstr(version),
                                      tuple(), tuple())
            current_gem = self.gems[name]
        return current_gem

    def parse_PLATFORMS(self, lines):
        platforms = [s.strip() for s in lines]
        for platform in platforms:
            assert platform in ['ruby', 'java']

    def parse_DEPENDENCIES(self, lines):
        self.dependencies = {}
        for line in lines:
            if line[-1] == '!':
                continue
            if '(' not in line:
                self.dependencies[line.strip()] = []
                continue
            name, const = line[2:].split(' ', 1)
            const = const[1:-1].split(', ')
            self.dependencies[name] = const

    def parse_PATH(self, lines):
        pass

    def parse_RUBY_VERSION(self, lines):
        pass

if __name__ == '__main__':
    import sys
    from pprint import pprint
    pprint(Parser(open(sys.argv[1])).__dict__)
