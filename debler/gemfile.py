from debler.gem import GemVersion


def build_str(s):
    return ''.join(s)


class Source():
    def __init__(self, source):
        self.source = source

    def __repr__(self):
        return 'Source({})'.format(self.source)


class Gem():
    def __init__(self, name, constraints, opts):
        self.name = name
        self.constraints = constraints
        self.opts = opts
        self.opts['envs'] = ['all']

    def __repr__(self):
        return 'Gem({}, {}, {})'.format(self.name, self.constraints, self.opts)


class Group():
    def __init__(self, envs, *gems):
        self.envs = envs
        self.gems = gems

    def __repr__(self):
        return 'Group({}, {})'.format(self.envs, self.gems)


def build_gems(envs, *gems):
    print(envs, gems)
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

import lepl
string = (lepl.Drop('\'') & lepl.Star(lepl.AnyBut('\'')) & lepl.Drop('\'')) > build_str
symbol = lepl.Drop(':') & lepl.Star(lepl.AnyBut('\':\t ')) > build_str

line_comment = lepl.Literal('#') & lepl.Star(lepl.AnyBut('\n'))
newline = lepl.Drop(lepl.Star(lepl.Space()) & lepl.Optional(line_comment) & lepl.Literal('\n') & lepl.Star(lepl.Space()))

# define gem line
gem = lepl.Drop('gem') & ~lepl.Space() & string
# optional version constraints
gem_constraints = lepl.Star(~lepl.Drop(',') & ~lepl.Space() & string) > tuple
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
gem = gem > expand(Gem)

# gem group
group_envs = symbol & lepl.Star(lepl.Drop(',') & ~lepl.Space() & symbol) > tuple
group_start = ~lepl.Literal('group') & ~lepl.Space() & group_envs & ~lepl.Space() & ~lepl.Literal('do')
group_content = lepl.Star(gem | newline)
group_end = ~lepl.Literal('end')
group = group_start & group_content & group_end > expand(build_gems)

source = ~lepl.Literal('source') & ~lepl.Space() & string > expand(Source)

parser = lepl.Star(source | gem | group | newline)


class Parser():
    def __init__(self, file):
        self.parse(file)

    def parse(self, file):
        current_state = None
        current_lines = []
        for line in file:
            if not line.strip():
                continue
            if line[0] != ' ':
                if current_state is not None:
                    getattr(self, 'parse_' + current_state)(current_lines)
                current_state = line.strip()
                current_lines = []
            else:
                current_lines.append(line.rstrip())

    def parse_GEM(self, lines):
        assert lines[0][0:10] == '  remote: '
        self.remote = lines[0][10:]
        assert lines[1][0:8] == '  specs:'
        self.gems = {}
        for line in lines[2:]:
            if line[4] == ' ':  # skip dependencies
                continue
            name, version = line.strip().split(' ', 1)
            version = version[1:-1]
            self.gems[name] = GemVersion.fromstr(version)

    def parse_PLATFORMS(self, lines):
        assert lines[0].strip() == 'ruby'

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

if __name__ == '__main__':
    import sys
    from pprint import pprint
    pprint(Parser(open(sys.argv[1])).__dict__)
