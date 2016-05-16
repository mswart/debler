import os.path
import json


class Parser():
    def __init__(self, *, dir, name, version, private=True, directories=None,
                 scripts=None, repository=None, engines=None, author,
                 license, devDependencies={}, description=None):
        self.dir = dir
        self.name = name
        self.version = version
        self.description = description
        self.private = private
        self.directories = directories or {}
        self.scripts = scripts or {}
        self.repository = repository
        self.engines = engines or {}
        self.author = author
        self.license = license
        self.devDependencies = devDependencies or {}

    @classmethod
    def parse(cls, base, packages):
        with open(os.path.join(base, packages), 'r') as f:
            opts = json.loads(f.read())
            return cls(dir=os.path.dirname(packages) + '/', **opts)
