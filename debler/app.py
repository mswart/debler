import yaml
from datetime import datetime
import os
import os.path
import subprocess

from debian.changelog import Changelog
from dateutil.tz import tzlocal

from debler.builder import BaseBuilder, \
    SourceControl, Package, \
    BuildDependency, Dependency, \
    InstallInto
from debler import config


class AppInfo():
    def __init__(self, db, name, version, basedir, *, gemfile=None,
                 homepage=None, description=None,
                 files=[], dirs=[],
                 **pkgers):
        self.db = db
        self.name = name
        if type(version) is list:
            self.version = version
        else:
            self.version = tuple(int(i) for i in str(version).split('.'))
        self.basedir = basedir
        self.homepage = homepage
        self.description = description
        self.dirs = dirs
        self.files = files
        self.pkgers = []

        for pkger, cfg in pkgers.items():
            self.pkgers.append(db.get_pkger(pkger).appInfo(self, **cfg))

    @classmethod
    def fromyml(cls, db, filename):
        data = yaml.load(open(filename).read().format(**os.environ))
        if 'basedir' not in data:
            data['basedir'] = os.path.dirname(os.path.realpath(filename))
        return cls(db, **data)

    def schedule_dep_builds(self):
        for pkger in self.pkgers:
            pkger.schedule_dep_builds()


class BasePackagerAppInfo():
    def __init__(self, pkger, app):
        self.pkger = pkger
        self.app = app

    def appIntegrator(self, builder):
        return self.pkger.appIntegrator(self, builder)


class AppBuilder(BaseBuilder):
    def __init__(self, db, tmp_dir, app):
        self.db = db
        self.tmp_dir = tmp_dir
        self.app = app
        self.orig_name = app.name
        self.deb_name = app.name
        self.package_upload = config.app_package_upload
        self.packagers = []
        for pkger in self.app.pkgers:
            self.packagers.append(pkger.appIntegrator(self))

    @property
    def pkg_dir(self):
        return os.path.join(
            self.slot_dir,
            self.app.name)

    @property
    def slot_dir(self):
        return self.tmp_dir

    def generate_changelog_file(self):
        changelog = self.debian_file('changelog')
        if os.path.isfile(changelog):
            changes = Changelog(file=open(changelog, 'r'))
            deb_version = changes.get_version()
            deb_version.debian_revision = str(
                int(deb_version.debian_revision) + 1)
            change = 'Rebuild with newer debler'
        else:
            changes = Changelog()
            deb_version = '.'.join([str(v) for v in self.app.version]) + '-1'
            change = 'Build with debler'
        changes.new_block(package=self.deb_name, version=deb_version,
                          distributions=config.distribution, urgency='low',
                          author=config.maintainer,
                          date=datetime.now(tz=tzlocal())
                          .strftime('%a, %d %b %Y %H:%M:%S %z'))
        self.deb_version = deb_version
        changes.add_change('\n  * ' + change + '\n')
        with open(changelog, 'w') as f:
            changes.write_to_open_file(f)

    def generate_control_content(self):
        yield SourceControl(
            source=self.deb_name,
            priority='optional',
            maintainer=config.maintainer,
            homepage=self.app.homepage,
            standards_version='3.9.6',
        )
        yield BuildDependency('debhelper')

        yield Package(
            package=self.deb_name,
            architecture='all',
            section='ruby',  # TODO fix this
            description=self.app.description,
        )
        yield Dependency(self.deb_name, '${shlibs:Depends}')
        yield Dependency(self.deb_name, '${misc:Depends}')

        for pkger in self.packagers:
            yield from pkger.generate_control_content()

    def generate_rules_content(self):
        for dir in self.app.dirs:
            yield InstallInto(self.deb_name, dir,
                              '/usr/share/{}'.format(self.app.name))
        for file in self.app.files:
            yield InstallInto(self.deb_name, file,
                              '/usr/share/{}'.format(self.app.name))

        for pkger in self.packagers:
            yield from pkger.generate_rules_content()

    @property
    def orig_tar(self):
        return os.path.join(self.slot_dir, '{}_{}.orig.tar.xz'.format(
            self.deb_name, '.'.join(str(v) for v in self.app.version)))

    def build_orig_tar(self):
        if os.path.isfile(self.orig_tar):
            return
        if os.path.isfile(os.path.join('.git', 'HEAD')):
            git_archive = subprocess.Popen(['git', 'archive',
                                            '--format=tar', 'HEAD'],
                                           stdout=subprocess.PIPE)
            with open(self.orig_tar, 'w') as f:
                xz = subprocess.Popen(['xz', '-9'], stdin=git_archive.stdout,
                                      stdout=f)
                git_archive.stdout.close()
                xz.wait()
                assert xz.returncode == 0
        else:
            subprocess.check_call([
                'tar', '--create',
                '--directory', self.app.basedir,
                '--xz',
                '--file', self.orig_tar,
                '.'])
