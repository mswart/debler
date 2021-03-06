#!/usr/bin/env python3
from collections import namedtuple, OrderedDict
import logging
import os
import subprocess

from debian.deb822 import Deb822, Dsc

from debler import config


class BuildFailError(Exception):
    pass


class SourceControl(OrderedDict):
    pass

Dependency = namedtuple('Dependecy', 'package dependency')
BuildDependency = namedtuple('BuildDepency', 'dependency')
Provide = namedtuple('Provide', 'package provide')
Symlink = namedtuple('Symlink', 'package dest src')
Package = namedtuple('Package', 'package architecture section description')
Install = namedtuple('Install', 'package obj dest')
InstallInto = namedtuple('InstallInto', 'package obj dir')
InstallContent = namedtuple('InstallContent', 'package name dest content mode')
DebianContent = namedtuple('InstallContent', 'name content mode')
RuleAction = namedtuple('RuleAction', 'target cmd')
RuleOverride = namedtuple('RuleOverride', 'target')
FastBuild = namedtuple('FastBuild', 'possible')

log = logging.getLogger(__file__)


class BaseBuilder():
    @staticmethod
    def npm2deb(name):
        return 'debler-yarn-' + name.lower().replace('_', '--')

    def debian_file(self, arg, *extra_args):
        return os.path.join(self.pkg_dir, 'debian', arg, *extra_args)

    def extract_orig_tar(self):
        os.makedirs(self.pkg_dir, exist_ok=True)
        os.chdir(self.pkg_dir)
        subprocess.call(['tar', '--extract', '--file', self.orig_tar])

    def gen_debian_package(self):
        os.makedirs(self.debian_file('source'), exist_ok=True)
        self.fast_build = None
        self.generate_source_format()
        self.generate_compat_file()
        self.generate_copyright_file()
        self.generate_changelog_file()
        self.generate_control_file()
        self.generate_rules_file()

    def generate_source_format(self):
        with open(self.debian_file('source', 'format'), 'w') as f:
            f.write("3.0 (quilt)\n")

    def generate_compat_file(self):
        with open(self.debian_file('compat'), 'w') as f:
            f.write("9\n")

    def generate_copyright_file(self):
        with open(self.debian_file('copyright'), 'w') as f:
            f.write("""Format: http://dep.debian.net/deps/dep5
Upstream-Name: {}

Files: debian/*
Copyright: 2016 Malte Swart
Licence: See LICENCE file
  [LICENCE TEXT]
""".format(self.orig_name))

    def generate_control_file(self):
        dsc = Dsc()
        build_deps = []
        packages = OrderedDict()
        self.installs = {}
        self.symlinks = {}

        for item in self.generate_control_content():
            log.debug(repr(item))
            if isinstance(item, SourceControl):
                for key, value in item.items():
                    key = '-'.join([k.capitalize() for k in key.split('_')])
                    if key == 'Description':
                        value = value.strip() \
                                     .replace('\n\n', '\n.\n') \
                                     .replace('\n', '\n ')
                    dsc[key] = value
            elif isinstance(item, BuildDependency):
                build_deps.append(item.dependency)
            elif isinstance(item, Package):
                control = Deb822()
                for key, value in item._asdict().items():
                    key = '-'.join([k.capitalize() for k in key.split('_')])
                    if key == 'Description':
                        value = value.strip() \
                                     .replace('\n\n', '\n.\n') \
                                     .replace('\n', '\n ')
                    control[key] = value
                packages[item.package] = (control, [], [])
                self.installs[item.package] = []
                self.symlinks[item.package] = []
            elif isinstance(item, Dependency):
                packages[item.package][1].append(item.dependency)
            elif isinstance(item, Provide):
                packages[item.package][2].append(item.provide)
            elif isinstance(item, Symlink):
                self.symlinks[item.package].append((item.dest, item.src))
            elif isinstance(item, FastBuild):
                if self.fast_build is None:
                    self.fast_build = item.possible
                else:
                    self.fast_build = self.fast_build and item.possible
            else:
                raise NotImplementedError('Got unexcepted action item'
                                          ' on control generation {!r}'.format(
                                            item))
        if self.installs:
            build_deps.append('dh-exec')

        with open(self.debian_file('control'), 'wb') as control_file:
            dsc['Build-Depends'] = ', '.join(build_deps)
            dsc.dump(control_file)

            for control, deps, provides in packages.values():
                if deps:
                    control['Depends'] = ', '.join(deps)
                if provides:
                    control['Provides'] = ', '.join(provides)
                control_file.write(b'\n')
                control.dump(control_file)

    def generate_rules_file(self):
        rules = {}
        for item in self.generate_rules_content():
            log.debug(repr(item))
            if isinstance(item, Install):
                self.installs[item.package].append(
                    '{item.obj} => {item.dest}'.format(item=item))
            elif isinstance(item, InstallInto):
                if ' ' not in item.obj:
                    self.installs[item.package].append(
                        '{item.obj} {item.dir}/'.format(item=item))
                else:
                    # https://bugs.debian.org/cgi-bin/bugreport.cgi?bug=198507
                    # https://bugs.debian.org/cgi-bin/bugreport.cgi?bug=867866
                    rules.setdefault('install', [])
                    rules['install'].append(
                        ('mkdir -p "debian/{item.package}/{item.dir}" && ' +
                         ' cp "{item.obj}" "debian/{item.package}/{item.dir}"')
                        .format(item=item))
            elif isinstance(item, Symlink):
                self.symlinks[item.package].append((item.dest, item.src))
            elif isinstance(item, RuleOverride):
                if item.target not in rules:
                    rules[item.target] = []
            elif isinstance(item, RuleAction):
                if item.target not in rules:
                    rules[item.target] = []
                if isinstance(item.cmd, list):
                    cmd = ' '.join(item.cmd)
                else:
                    cmd = item.cmd
                rules[item.target].append(cmd)
            elif isinstance(item, InstallContent):
                os.makedirs(os.path.dirname(self.debian_file(item.name)),
                            exist_ok=True)
                with open(self.debian_file(item.name), 'w') as f:
                    f.write(item.content)
                os.chmod(self.debian_file(item.name), item.mode)
                self.installs[item.package].append(
                    'debian/{item.name} {item.dest}'.format(item=item)
                )
            elif isinstance(item, DebianContent):
                os.makedirs(os.path.dirname(self.debian_file(item.name)),
                            exist_ok=True)
                with open(self.debian_file(item.name), 'w') as f:
                    f.write(item.content)
                os.chmod(self.debian_file(item.name), item.mode)
            elif isinstance(item, FastBuild):
                if self.fast_build is None:
                    self.fast_build = item.possible
                else:
                    self.fast_build = self.fast_build and item.possible
            else:
                raise NotImplementedError('Got unexcepted action item'
                                          ' on rules generation {!r}'.format(
                                              item))

        with open(self.debian_file('rules'), 'w') as f:
            f.write("#!/usr/bin/make -f\n%:\n\tdh $@\n")
            for target in rules:
                f.write('\noverride_dh_auto_{}:\n\t'.format(target))
                f.write('\n\t'.join(rules[target]))
                f.write('\n')
        os.chmod(self.debian_file('rules'), 0o755)

        for deb, installs in self.installs.items():
            with open(self.debian_file(deb + '.install'), 'w') as f:
                f.write('#!/usr/bin/dh-exec\n')
                f.write('\n'.join(installs))
                f.write('\n')
            os.chmod(self.debian_file(deb + '.install'), 0o755)

        for deb, symlinks in self.symlinks.items():
            if not symlinks:
                continue
            with open(self.debian_file(deb + '.links'), 'w') as f:
                for file, dir in symlinks:
                    f.write('{} {}\n'.format(file, dir))

    def create_source_package(self):
        os.chdir(self.pkg_dir)
        subprocess.check_call(['dpkg-buildpackage', '-S', '-sa', '-d'])

    def changes_path(self, arch):
        changes = '{}_{}_{}.changes'.format(
            self.deb_name, self.deb_version, arch)
        return os.path.join(self.tmp_dir, changes)

    def generate(self):
        self.build_orig_tar()
        self.extract_orig_tar()
        self.gen_debian_package()
        self.create_source_package()

    def run(self):
        if self.fast_build:
            self.build_native()
        else:
            self.build_with_sbuild()

    def build_with_sbuild(self):
        os.chdir(self.slot_dir)
        # sbuild would try to resign source changes; rename it tempoarily
        os.rename(self.changes_path('source'), self.changes_path('tmp'))
        try:
            subprocess.check_call(['sbuild',
                                   '--nolog',
                                   '--dist', config.distribution,
                                   '--keyid', config.keyid,
                                   '--maintainer', config.maintainer,
                                   '{}_{}.dsc'.format(self.deb_name,
                                                      self.deb_version)])
        except subprocess.CalledProcessError:
            raise BuildFailError()
        os.rename(self.changes_path('tmp'), self.changes_path('source'))

    def build_native(self):
        os.chdir(self.pkg_dir)
        subprocess.check_call(['dpkg-buildpackage',
                               '-b',  # build binary packages
                               '-m' + config.maintainer,
                               '-us',  # no signing of source changes
                               '-rfakeroot',  # use fakeroot as sudo cmd
                               ])

    def upload(self):
        subprocess.check_call(['dput',
                               self.package_upload,
                               self.changes_path('source')])
        subprocess.check_call(['dput',
                               self.package_upload,
                               self.changes_path('amd64')])
