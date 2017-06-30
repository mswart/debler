import json
import os.path

from .lock import YarnLockParser
from debler.app import BasePackagerAppInfo


class YarnAppInfo(BasePackagerAppInfo):
    def __init__(self, pkger, app, *, subdir='.',
                 name, version, lock,
                 private=True, directories=None,
                 scripts=None, repository=None, engines=None, author=None,
                 license=None,
                 dependencies=None,
                 devDependencies=None, withDevDependencies=False,
                 description=None,
                 keywords=None, **extra):
        super().__init__(pkger, app)

        self.subdir = dir
        self.name = name
        self.version = version
        self.description = description
        self.private = private
        self.directories = directories or {}
        self.scripts = scripts or {}
        self.repository = repository
        self.keywords = keywords or []
        self.engines = engines or {}
        self.author = author
        self.license = license
        self.runtimeDependencies = dependencies or {}
        self.devDependencies = devDependencies or {}
        self.dependencies = {}
        self.dependencies.update(self.runtimeDependencies)
        if withDevDependencies:
            self.dependencies.update(self.devDependencies)

    @classmethod
    def parse(cls, pkger, app, *, subdir='.', withDevDependencies=True):
        basedir = os.path.join(app.basedir, subdir)
        with open(os.path.join(basedir, 'package.json'), 'r') as f:
            opts = json.loads(f.read())
        with open(os.path.join(basedir, 'yarn.lock'), 'r') as f:
            lock = YarnLockParser(f.read())
        return cls(pkger, app,
                   subdir=subdir,
                   withDevDependencies=withDevDependencies,
                   lock=lock,
                   **opts)

    def schedule_dep_builds(self):
        return
        for pkg, constraint in self.dependencies.items():
            _, slots = db.npm_info(pkg)
            print(pkg, '-', constraint)
            import pprint
            range.config.flatten().optimize_or().no_memoize()
            pprint.pprint(range.parse(constraint))
            if not constraint[0].isdigit():
                op = constraint[0]
                version = tuple(int(v) for v in constraint[1:].split('.'))
            else:
                op = '='
                version = tuple(int(v) for v in constraint.split('.'))
            if op == '^':
                slot = (version[0],)
            elif op in '=~':  # TODO iterate over slots
                slot = (version[0], version[1])
            else:
                raise NotImplementedError('unknown npm operator {} in ({}: {})'.format(op, pkg, constraint))
            if slot not in slots.keys():
                db.create_npm_slot(pkg, slot)
            versions = db.npm_slot_versions(pkg, slot)
            if not versions or versions[-1] < version:
                db.schedule_npm_version(
                    pkg, slot,
                    version=list(version), revision=1,
                    changelog='Import newly into debler',
                    distribution=config.distribution)
        raise ValueError()
