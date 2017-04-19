import os.path
import json
import os
import tarfile
import gzip
import lzma
import subprocess

from debian.deb822 import Deb822, Dsc
from debian.changelog import Changelog

from debler import config
from debler.builder import BaseBuilder


class Parser():
    def __init__(self, *, dir, name, version, private=True, directories=None,
                 scripts=None, repository=None, engines=None, author=None,
                 license=None, dependencies=None, devDependencies=None, description=None,
                 withDevDependencies=False, keywords=None, **extra):
        self.dir = dir
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
    def parse(cls, base, packages, withDevDependencies=True):
        with open(os.path.join(base, packages), 'r') as f:
            opts = json.loads(f.read())
            return cls(dir=os.path.dirname(packages) + '/',
                       withDevDependencies=withDevDependencies,
                       **opts)

    def schedule_deps_builds(self, db):
        for pkg, constraint in self.dependencies.items():
            _, slots = db.npm_info(pkg)
            if not constraint[0].isdigit():
                op = constraint[0]
                version = tuple(int(v) for v in constraint[1:].split('.'))
            else:
                op = '='
                version = tuple(int(v) for v in constraint.split('.'))
            if op == '^':
                slot = (version[0],)
            elif op in '=~':
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
                    changelog='Import newly into debler', distribution=config.distribution)

    def needed_relations(self, basedir):
        deps = []
        symlinks = []
        for pkg, constraint in self.dependencies.items():
            if not constraint[0].isdigit():
                op = constraint[0]
                version = constraint[1:]
            else:
                op = '='
                version = constraint
            if op == '^':
                if version.replace('.0', '') == version.split('.')[0]:
                    deps.append('{}-{}'.format(self.npm2deb(pkg), version.split('.')[0]))
                else:
                    deps.append('{}-{} (>= {})'.format(self.npm2deb(pkg), version.split('.')[0], version))
                symlinks.append((
                    '/usr/share/node-debler/{}-{}'.format(pkg, version.split('.')[0]),
                    '{}node_modules/{}'.format(basedir, pkg)
                ))
            elif op == '~':
                slot = '.'.join(version.split('.')[:2])
                if version.replace('.0', '') == slot:
                    deps.append('{}-{}'.format(self.npm2deb(pkg), slot))
                else:
                    deps.append('{}-{} (>= {})'.format(self.npm2deb(pkg), slot, version))
                symlinks.append((
                    '/usr/share/node-debler/{}-{}'.format(pkg, slot),
                    '{}node_modules/{}'.format(basedir, pkg)
                ))
            elif op == '=':
                deps.append('{}-{}'.format(self.npm2deb(pkg), version))
                symlinks.append((
                    '/usr/share/node-debler/{}-{}'.format(pkg, version),
                    '{}node_modules/{}'.format(basedir, pkg)
                ))
            else:
                raise NotImplementedError('unknown npm operator {} in ({}: {})'.format(op, pkg, constraint))
        return (deps, symlinks)

    @staticmethod
    def npm2deb(name):
        return 'debler-node-' + name.replace('_', '--')


class NpmBuilder(BaseBuilder):
    def __init__(self, db, tmp_dir, pkg, slot, version, revision):
        self.db = db
        self.tmp_dir = tmp_dir

        self.orig_name = pkg

        self.pkg_name = pkg
        self.pkg_slot = tuple(slot)
        self.pkg_slot_s = '.'.join(str(v) for v in self.pkg_slot)
        if self.pkg_slot:
            self.pkg_name += '-' + self.pkg_slot_s
        self.pkg_version = tuple(version)
        self.pkg_version_s = '.'.join(str(v) for v in self.pkg_version)

        self.deb_name = self.npm2deb(self.pkg_name)
        self.deb_revision = revision
        self.deb_version = self.pkg_version_s + '-' + str(revision)

        self.pkg_dir = tmp_dir + '/' + self.orig_name + '-' + self.pkg_slot_s
        self.package_upload = config.npm_package_upload

    def generate(self):
        self.create_dirs()
        self.fetch_source()
        self.parse_metadata()
        self.metadata.schedule_deps_builds(self.db)

        super().generate()

    def parse_metadata(self):
        with tarfile.open(name=self.src_file, mode='r:gz') as t:
            metadata = t.extractfile('package/package.json').read().decode('utf-8')
            self.metadata = Parser(dir=None, **json.loads(metadata))
            print(self.metadata.runtimeDependencies)
            print(self.metadata.devDependencies)
            print(self.metadata.dependencies)

    def create_dirs(self):
        os.makedirs(os.path.dirname(self.src_file), exist_ok=True)

    @property
    def src_file(self):
        return os.path.join(config.npmdir, 'versions', self.orig_name, self.pkg_version_s + '.tar.gz')

    @property
    def tarxz_file(self):
        return os.path.join(config.npmdir, 'versions', self.orig_name, self.pkg_version_s + '.tar.xz')

    @property
    def orig_tar(self):
        return os.path.join(self.slot_dir, '{}_{}.orig.tar.xz'.format(self.deb_name,
                                                                      self.pkg_version_s))

    def fetch_source(self):
        if not os.path.isfile(self.src_file):
            subprocess.check_call(['wget',
                                   'https://registry.npmjs.org/{pkg}/-/{pkg}-{version}.tgz'
                                  .format(pkg=self.orig_name, version=self.pkg_version_s),
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
        subprocess.call(['tar', '--extract', '--strip-components', '1', '--file', self.orig_tar])

    def build_orig_tar(self):
        if os.path.isfile(self.orig_tar):
            return
        self.build_tarxz()
        os.symlink(self.tarxz_file, self.orig_tar)

    def generate_control_file(self):
        build_deps = [
            'debhelper',
        ]

        control_file = open(self.debian_file('control'), 'wb')

        dsc = Dsc()
        dsc['Source'] = self.deb_name
        dsc['Priority'] = 'optional'
        dsc['Maintainer'] = config.maintainer
        dsc['Standards-Version'] = '3.9.6'
        dsc['Section'] = 'universe/web'
        dsc['Build-Depends'] = ','.join(build_deps)

        dsc.dump(control_file)

        control = Deb822()
        control['Package'] = self.deb_name
        priovide = []
        priovide.append(self.npm2deb(self.orig_name))
        if len(self.pkg_slot) > 1:
            priovide.append(self.npm2deb(self.orig_name) + '-' + self.pkg_version_s)
        control['Provides'] = ', '.join(priovide)
        control['Architecture'] = 'all'
        deps = ['nodejs']
        new_deps, self.symlinks = self.metadata.needed_relations('/usr/share/node-debler/{}/'.format(self.pkg_name))
        deps.extend(new_deps)

        deps.append('${shlibs:Depends}')
        deps.append('${misc:Depends}')

        control['Depends'] = ', '.join(deps)
        control['Section'] = 'universe/web'
        control['Description'] = 'not known ...'

        control_file.write(b'\n')
        control.dump(control_file)
        control_file.close()

    def generate_changelog_file(self):
        changes = Changelog()
        for version, revision, scheduled_at, change, distribution in self.db.changelog_entries('npm', self.orig_name, list(self.pkg_slot), list(self.pkg_version)):
            deb_version = str(version) + '-' + str(revision)
            changes.new_block(package=self.deb_name, version=deb_version,
                              distributions=distribution, urgency='low',
                              author=config.maintainer,
                              date=scheduled_at.strftime('%a, %d %b %Y %H:%M:%S %z'))
            changes.add_change('\n  * ' + change + '\n')
        with open(self.debian_file('changelog'), 'w') as f:
            changes.write_to_open_file(f)

    def generate_rules_file(self):
        rules = {}
        rules['build'] = []
        rules['install'] = []

        with open(self.debian_file('rules'), 'w') as f:
            f.write("#!/usr/bin/make -f\n%:\n\tdh $@\n")
            for target in rules:
                f.write('\noverride_dh_auto_{target}:\n\t'.format(target=target))
                f.write('\n\t'.join(rules[target]))
                f.write('\n')
        os.chmod(self.debian_file('rules'), 0o755)

        with open(self.debian_file(self.deb_name + '.install'), 'w') as f:
            with tarfile.open(self.tarxz_file, 'r:xz') as t:
                members = t.getmembers()
                for member in members:
                    f.write('{file} /usr/share/node-debler/{name}/{dir}\n'.format(
                        name=self.pkg_name,
                        file='/'.join(member.name.split('/')[1:]),
                        dir='/'.join(os.path.dirname(member.name).split('/')[1:])))

        with open(self.debian_file(self.deb_name + '.links'), 'w') as f:
            for file, dir in self.symlinks:
                f.write('{} {}\n'.format(file, dir))
