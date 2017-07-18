import json
import os.path

from .lock import YarnLockParser
from debler.app import BasePackagerAppInfo
from ..db import Version
from debler import config


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
        self.lock = lock

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
        for pkg in self.lock.pkgs:
            info = self.pkger.pkg_info(pkg.name, autocreate=True)
            slot = info.slot_for_version(pkg.version, create=True)
            versions = slot.versions()
            if len(versions) < 1:
                slot.create(
                    version=pkg.version, revision=1,
                    changelog='Import newly into debler',
                    distribution=config.distribution)
            elif Version(pkg.version) > versions[-1].version:
                slot.create(
                    version=pkg.version, revision=1,
                    changelog='Update to version used in application',
                    distribution=config.distribution)
