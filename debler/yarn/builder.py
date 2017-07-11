import gzip
import lzma
import json
import os
import subprocess
import tarfile

from debian.changelog import Changelog

from debler import config
from debler.builder import BaseBuilder, \
    SourceControl, Package, \
    BuildDependency, Dependency, Provide, \
    Install, RuleOverride
from .appinfo import YarnAppInfo
from .constraints import parseConstraints
from ..constraints import dependencies4Constraints


class YarnBuilder(BaseBuilder):
    def __init__(self, pkger, tmp_dir, build_id):
        self.pkger = pkger
        self.db = pkger.db
        self.tmp_dir = tmp_dir

        self.build = self.db.build_data(build_id)
        assert self.build.pkger == 'yarn'

        self.orig_name = self.build.pkg

        self.pkg_name = self.build.pkg
        self.pkg_slot = self.build.slot
        if self.pkg_slot:
            self.pkg_name += '-' + self.pkg_slot
        self.pkg_version = self.build.version

        self.deb_name = self.npm2deb(self.pkg_name)
        self.deb_version = self.build.revision

        self.pkg_dir = tmp_dir + '/' + self.orig_name + '-' + self.pkg_slot
        self.package_upload = config.npm_package_upload

    def generate(self):
        self.create_dirs()
        self.fetch_source()
        self.parse_metadata()

        super().generate()

    def parse_metadata(self):
        with tarfile.open(name=self.src_file, mode='r:gz') as t:
            metadata = t.extractfile('package/package.json').read().decode('utf-8')
            self.metadata = YarnAppInfo(self.pkger, None, lock=None, dir=None, **json.loads(metadata))
            print(self.metadata.dependencies)

    def create_dirs(self):
        os.makedirs(os.path.dirname(self.src_file), exist_ok=True)

    @property
    def src_file(self):
        return os.path.join(config.npmdir, 'versions', self.orig_name, self.pkg_version + '.tar.gz')

    @property
    def tarxz_file(self):
        return os.path.join(config.npmdir, 'versions', self.orig_name, self.pkg_version + '.tar.xz')

    @property
    def orig_tar(self):
        return os.path.join(self.slot_dir, '{}_{}.orig.tar.xz'.format(self.deb_name,
                                                                      self.pkg_version))

    def fetch_source(self):
        if not os.path.isfile(self.src_file):
            subprocess.check_call(['wget',
                                   'https://registry.yarnpkg.com/{pkg}/-/{pkg}-{version}.tgz'
                                  .format(pkg=self.orig_name, version=self.pkg_version),
                                   '-O', self.src_file])

    @property
    def slot_dir(self):
        return self.tmp_dir

    def build_tarxz(self):
        if os.path.isfile(self.tarxz_file):
            return
        with gzip.open(self.src_file, 'rb') as indata:
            with lzma.open(self.tarxz_file, 'wb', preset=9) as outdata:
                outdata.write(indata.read())

    def extract_orig_tar(self):
        os.makedirs(self.pkg_dir, exist_ok=True)
        os.chdir(self.pkg_dir)
        subprocess.call([
            'tar',
            '--extract',
            '--strip-components', '1',
            '--file', self.orig_tar])

    def build_orig_tar(self):
        if os.path.isfile(self.orig_tar):
            return
        self.build_tarxz()
        os.symlink(self.tarxz_file, self.orig_tar)

    def generate_control_content(self):
        # define source metadata
        yield SourceControl(
            source=self.deb_name,
            priority='optional',
            maintainer=config.maintainer,
            standards_version='3.9.8',
            section='universe/web',
        )
        yield BuildDependency('debhelper')

        # define package
        yield Package(
            package=self.deb_name,
            architecture='all',
            section='universe/web',
            description='not known ...',
        )
        yield Provide(self.deb_name, self.npm2deb(self.orig_name))
        if self.build.version != self.build.slot:
            yield Provide(self.deb_name, self.npm2deb(self.build.pkg) + '-' + self.build.version)
        version_parts = self.build.version.split('.')
        if version_parts[0] != '0':
            yield Provide(self.deb_name, self.npm2deb(self.build.pkg) +
                '-' + '.'.join(version_parts[:2]))
        yield Provide(self.deb_name, self.npm2deb(self.build.pkg) +
                '-' + self.build.version)
        yield Dependency(self.deb_name, 'nodejs')

        # todo
        for name, constraints in self.metadata.dependencies.items():
            yield from dependencies4Constraints(self.deb_name, self.pkger.pkg_info(name),
                                                parseConstraints(constraints))
        #new_deps, self.symlinks = self.metadata.needed_relations('/usr/share/node-debler/{}/'.format(self.pkg_name))

        yield Dependency(self.deb_name, '${shlibs:Depends}')
        yield Dependency(self.deb_name, '${misc:Depends}')

    def generate_changelog_file(self):
        changes = Changelog()
        for version, scheduled_at, change, distribution in \
                self.db.changelog_entries(self.build.id):
            changes.new_block(
                package=self.deb_name,
                version=version,
                distributions=distribution,
                urgency='low',
                author=config.maintainer,
                date=scheduled_at.strftime('%a, %d %b %Y %H:%M:%S %z'))
            changes.add_change('\n  * ' + change + '\n')
        with open(self.debian_file('changelog'), 'w') as f:
            changes.write_to_open_file(f)

    def generate_rules_content(self):
        yield RuleOverride('clean')
        yield RuleOverride('build')
        yield RuleOverride('test')

        with tarfile.open(self.tarxz_file, 'r:xz') as t:
            members = t.getmembers()
            for member in members:
                if member.name.endswith('.un~'):
                    continue
                yield Install(
                    self.deb_name,
                    '/'.join(member.name.split('/')[1:]),
                    'usr/share/node-debler/{name}/{dir}'.format(
                        name=self.pkg_name,
                        dir='/'.join(os.path.dirname(member.name)
                                     .split('/')[1:])))
