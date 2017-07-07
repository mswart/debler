import functools


class Packager():
    def __init__(self, db, id):
        self.db = db
        self.id = id

    def __getattr__(self, name):
        if name in self.wrapped:
            return functools.partial(self.wrapped[name], self)
        else:
            raise AttributeError(name)
