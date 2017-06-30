import os.path

from ..app import BasePackagerAppInfo
from debler import config
from ..db import Version
from .parser import Parser as GemfileParser


class BundlerAppInfo(BasePackagerAppInfo):
    def __init__(self, pkger, app, *,
                 subdir='.',
                 gemfile,
                 executables=[], bundler_laucher=False,
                 default_env=None, ignore_gems=[]):
        super().__init__(pkger, app)
        self.gemfile = gemfile
        self.executables = executables
        self.bundler_laucher = bundler_laucher
        self.default_env = default_env

    @property
    def name(self):
        return self.app.name

    @classmethod
    def parse(cls, pkger, app, *, subdir='.',
              executables=[], bundler_laucher=False,
              default_env=None, ignore_gems=[]):
        basedir = os.path.realpath(os.path.join(app.basedir, subdir))
        gemfile = GemfileParser(os.path.join(basedir, 'Gemfile'), ignore_gems)
        return cls(pkger, app,
                   subdir=subdir,
                   gemfile=gemfile,
                   executables=executables,
                   bundler_laucher=bundler_laucher,
                   default_env=default_env)

    def schedule_dep_builds(self):
        for name, gem in self.gems.items():
            if not gem.version:
                continue
            info = self.pkger.gem_info(name, autocreate=True)
            slot = info.slot_for_version(gem.version, create=True)
            if gem.revision:
                extra = {
                    'repository': gem.remote,
                    'revision': gem.revision
                }
                ourversion = str(gem.version) + '.rev' + gem.revision
            else:
                extra = {}
                ourversion = str(gem.version)
            versions = slot.versions()
            if gem.revision:
                for version in versions:
                    if ourversion == version.version:
                        break
                else:
                    slot.create(
                        version=ourversion, revision=1,
                        changelog='Build from upstream repository',
                        distribution=config.distribution,
                        extra=extra)
            elif not versions:
                slot.create(
                    version=ourversion, revision=1,
                    changelog='Import newly into debler',
                    distribution=config.distribution,
                    extra=extra)
            elif Version(ourversion) > versions[-1].version:
                slot.create(
                    version=ourversion, revision=1,
                    changelog='Update to version used in application',
                    distribution=config.distribution,
                    extra=extra)

    @property
    def gems(self):
        return self.gemfile.gems
