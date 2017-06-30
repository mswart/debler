

class Or():
    def __init__(self, ranges):
        self.ranges = ranges

    def __repr__(self):
        return 'Or({})'.format(', '.join(repr(r) for r in self.ranges))


class And():
    def __init__(self, ranges):
        self.ranges = ranges

    def needed_relation(self):
        for range in self.ranges:
            yield from range.needed_relation()

    def __repr__(self):
        return 'And({})'.format(', '.join(repr(r) for r in self.ranges))


class All():
    pass


all = All()
