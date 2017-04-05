import lepl

from debler.gem import GemVersion


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

    def __repr__(self):
        v = str(self.version)
        if self.constraints:
            v += ' (' + ', '.join(self.constraints) + ')'
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

string = (lepl.Drop('\'') & lepl.Star(lepl.AnyBut('\'')) & lepl.Drop('\'')) > build_str
symbol = lepl.Drop(':') & lepl.Star(lepl.AnyBut('\':\t\n ')) > build_str

line_comment = lepl.Literal('#') & lepl.Star(lepl.AnyBut('\n'))
newline = lepl.Drop(lepl.Star(lepl.Space()) & lepl.Optional(line_comment) & lepl.Literal('\n') & lepl.Star(lepl.Space()))

# define ruby line
ruby = lepl.Drop('ruby') & ~lepl.Space() & string >> ret(None)

# define gem line
gem = lepl.Drop('gem') & ~lepl.Space() & string
# optional version constraints
gem_constraints = lepl.Star(~lepl.Star(lepl.Space()) & ~lepl.Drop(',') & ~lepl.Star(lepl.Space()) & string) > tuple
gem &= gem_constraints
# optional keywords
true = lepl.Literal('true') >> ret(True)
false = lepl.Literal('false') >> ret(False)
value = true | false | symbol | string
keyword_name = lepl.Star(lepl.AnyBut(':\t ')) > build_str
keyword = keyword_name & lepl.Drop(':') & ~lepl.Space() & value > tuple
keywords = lepl.Star(~lepl.Drop(',') & ~lepl.Space() & keyword) > dict
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

parser = lepl.Star(source | ruby | gem | group | newline)


class Parser():
    def __init__(self, gemfile):
        self.gems = {}
        self.parse_gemfile(gemfile)
        self.parse_gemlock(gemfile + '.lock')
        # ignore bundler listing
        self.gems.pop('bundler', None)
        self.sorted_gems = list(self.sort_gems())

    def sort_gems(self):
        loaded = set()
        gems_yield = True
        while gems_yield:
            gems_yield = False
            for gem in sorted(self.gems):
                if gem in loaded:
                    continue
                if len(set(self.gems[gem].deps.keys()).difference(loaded)) == 0:
                    loaded.add(gem)
                    gems_yield = True
                    yield gem

    def parse_gemfile(self, file):
        d = parser.parse(open(file, 'r'))
        for o in d:
            if type(o) is GemfileGem:
                self.gems[o.name] = Gem(o.name, None, o.constraints,
                                        o.opts['envs'], o.opts.get('require', True),
                                        o.opts.get('path', None))
            elif type(o) is tuple:
                for os in o:
                    self.gems[os.name] = Gem(os.name, None, os.constraints,
                                             os.opts['envs'], os.opts.get('require', True),
                                             os.opts.get('path', None))

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
        current_gem = None
        for line in lines[2:]:
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
