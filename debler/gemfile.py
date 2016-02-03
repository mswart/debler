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
            self.gems[name] = version

    def parse_PLATFORMS(self, lines):
        assert lines[0].strip() == 'ruby'

    def parse_DEPENDENCIES(self, lines):
        self.dependencies = {}
        for line in lines:
            assert line[-1] != '!'
            if '(' not in line:
                self.dependencies[line.strip()] = []
                continue
            name, const = line[2:].split(' ', 1)
            const = const[1:-1].split(', ')
            self.dependencies[name] = const

if __name__ == '__main__':
    import sys
    from pprint import pprint
    pprint(Parser(open(sys.argv[1])).__dict__)
