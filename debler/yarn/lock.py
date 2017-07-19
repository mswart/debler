class PkgInfo():
    def __init__(self, name, constraints,
                 version, resolved,
                 dependencies={}, optionalDependencies={}):
        self.name = name
        self.constraints = constraints
        self.version = version
        self.resolved = resolved
        self.dependencies = dependencies

    def __repr__(self):
        return 'PkgInfo({!r}, {!r}, {!r}, {!r}, {!r})'.format(
            self.name,
            self.constraints,
            self.version,
            self.resolved,
            self.dependencies)


class YarnLockParser():
    def __init__(self, content):
        start = content.index('# yarn lockfile v1')
        self.pkgs = []
        pkgs = content[start+18:].strip().split('\n\n')
        for pkg in pkgs:
            self.parse_pkg(pkg)

    def parse_pkg(self, data):
        lines = data.strip().split('\n')
        what = lines.pop(0)
        assert what[-1] == ':'
        name = None
        constraints = []
        for part in what[:-1].split(', '):
            if part[0] == part[-1] == '"':
                part = part[1:-1]
            cur_name, cur_constraint = part.rsplit('@', 1)
            if name is None:
                name = cur_name
            else:
                assert cur_name == name
            constraints.append(cur_constraint)
        extras = {}
        cur = None
        for line in lines:
            if line[2] != ' ':  # top level
                cur = extras
            if line[-1] != ':':
                key, value = line.lstrip().split(' ', 1)
                if value[0] == value[-1] == '"':
                    value = value[1:-1]
                cur[key] = value
            else:
                cur = {}
                extras[line[2:-1].strip()] = cur
        if name[0] == '@':  # scoped module
            # we do not know how to correctly handle them,
            # so skip them for now
            return
        self.pkgs.append(PkgInfo(name, constraints, **extras))
