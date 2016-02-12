#!/usr/bin/env python3
import os
import subprocess

from debler import config


class BaseBuilder():
    @staticmethod
    def gemnam2deb(name):
        return 'debler-rubygem-' + name.replace('_', '--')

    def debian_file(self, arg, *extra_args):
        return os.path.join(self.pkg_dir, 'debian', arg, *extra_args)

    def gen_debian_package(self):
        os.makedirs(self.debian_file('source'), exist_ok=True)
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

    def create_source_package(self):
        os.chdir(self.pkg_dir)
        subprocess.check_call(['dpkg-source', '-b', '.'])

    def build(self):
        os.chdir(self.slot_dir)

        subprocess.check_call(['sbuild',
                               '--dist', 'trusty',
                               '--keyid', config.keyid,
                               '--maintainer', config.maintainer,
                               '{}_{}.dsc'.format(self.deb_name, self.deb_version)])


def publish(dir):
    os.chdir(getattr(config, dir + 'dir'))
    subprocess.check_call(['apt-ftparchive', 'packages', '.'], stdout=open('Packages', 'wb'))
    subprocess.check_call(['apt-ftparchive', 'release', '.'], stdout=open('Release', 'wb'))
    subprocess.check_call(['gpg', '--clearsign', '-u', config.keyid, '-o', 'InRelease.new', 'Release'])
    subprocess.check_call(['gpg', '-abs', '-u', config.keyid, '-o', 'Release.gpg.new', 'Release'])
    os.rename('InRelease.new', 'InRelease')
    os.rename('Release.gpg.new', 'Release.gpg')
