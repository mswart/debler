#!/usr/bin/env python3
import os
import tarfile
import gzip
import yaml
import subprocess
from debian.deb822 import Deb822, Dsc
from debian.changelog import Changelog


def construct_ruby_object(loader, suffix, node):
    return loader.construct_yaml_map(node)

yaml.add_multi_constructor(u"!ruby/object:", construct_ruby_object)

rubies = ['2.2', '2.1']


class Converter():
    WORKDIR = os.path.realpath(os.path.join(__file__, '..', '..', 'work'))

    def __init__(self, db, gem, slot, version, revision):
        self.db = db
        self.gem_name = gem
        self.gem_slot = slot
        self.gem_slot_s = '.'.join([str(s) for s in slot])
        self.gem_version = version
        self.gem_version_s = '.'.join([str(v) for v in version])
        self.revision = revision

        self.own_name = self.gem_name
        if self.gem_slot:
            self.own_name += '-' + self.gem_slot_s
        self.deb_name = self.gemnam2deb(self.own_name)

    def create_dirs(self):
        os.makedirs(os.path.dirname(self.src_file), exist_ok=True)
        os.makedirs(self.debian_file('source'), exist_ok=True)

    @property
    def src_file(self):
        return os.path.join(self.WORKDIR, self.gem_name, self.gem_version_s, 'orig.gem')

    def fetch_source(self):
        if not os.path.isfile(self.src_file):
            subprocess.check_call(['wget',
                                   'https://rubygems.org/downloads/{}-{}.gem'
                                  .format(self.gem_name, self.gem_version_s),
                                   '-O', self.src_file])

    def build_orig_tar(self):
        if os.path.isfile(self.src_file + '.xz'):
            return
        outtar = tarfile.open(name=self.src_file + '.xz', mode='w:xz')
        intar = tarfile.open(name=self.src_file)
        # 1. add metadata as yml file
        gz = gzip.GzipFile(fileobj=intar.extractfile('metadata.gz'))
        meta = intar.getmember('metadata.gz')
        meta.name = 'metadata.yml'
        outtar.addfile(meta, fileobj=gz)
        # 2. add data files under srv/
        datatardata = gzip.GzipFile(fileobj=intar.extractfile('data.tar.gz'))
        datatar = tarfile.open(fileobj=datatardata)
        for member in datatar.getmembers():
            data = datatar.extractfile(member.name)
            member.name = 'src/' + member.name
            outtar.addfile(member, fileobj=data)
        # 3. flush all
        outtar.close()

    @staticmethod
    def gemnam2deb(name):
        return 'debler-rubygem-' + name.replace('_', '--')

    @property
    def pkg_dir(self):
        return os.path.join(
            self.slot_dir,
            self.gem_name + '-' + self.gem_slot_s)

    @property
    def slot_dir(self):
        return os.path.join(
            self.WORKDIR,
            self.gem_name,
            'slot' + self.gem_slot_s)

    def debian_file(self, arg, *extra_args):
        return os.path.join(self.pkg_dir, 'debian', arg, *extra_args)

    def gen_debian_files(self):
        self.parse_metadata()
        self.symlink_orig_tar()
        self.generate_source_format()
        self.generate_compat_file()
        self.generate_copyright_file()
        self.generate_changelog_file()
        self.generate_control_file()
        self.generate_rules_file()

    def symlink_orig_tar(self):
        orig_tar = os.path.join(self.slot_dir,
                                '{}_{}.orig.tar.xz'.format(self.deb_name,
                                self.gem_version_s))
        if not os.path.islink(orig_tar):
            os.symlink(os.path.join('..', self.gem_version_s, 'orig.gem.xz'), orig_tar)

    def parse_metadata(self):
        with tarfile.open(name=self.src_file) as t:
            metadata = gzip.GzipFile(fileobj=t.extractfile('metadata.gz')).read()
            self.metadata = yaml.load(metadata)

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
""".format(self.gem_name))

    def generate_changelog_file(self):
        changes = Changelog()
        for version, revision, scheduled_at, change, distribution in self.db.changelog_entries(self.gem_name, self.gem_slot):
            deb_version = '.'.join([str(v) for v in version]) + '-' + str(revision)
            changes.new_block(package=self.deb_name, version='.'.join([str(v) for v in version]) + '-' + str(revision),
                              distributions=distribution, urgency='low',
                              author='Debler Automatic Rubygems Packager <debler@dxtt.de>',
                              date=scheduled_at.strftime('%a, %d %b %Y %H:%M:%S %z'))
            changes.add_change('\n  * ' + change + '\n')
            self.deb_version = deb_version
        with open(self.debian_file('changelog'), 'w') as f:
            changes.write_to_open_file(f)

    def generate_control_file(self):
        build_deps = [
            'debhelper',
        ]
        if len(self.metadata['extensions']) > 0:
            for ruby in rubies:
                build_deps.append('ruby{}'.format(ruby))
                build_deps.append('ruby{}-dev'.format(ruby))

        level, builddeps, _ = self.db.gem_info(self.gem_name)
        if builddeps:
            build_deps.extend(builddeps['default']['builddeps'])
        control_file = open(self.debian_file('control'), 'wb')

        dsc = Dsc()
        dsc['Source'] = self.deb_name
        dsc['Priority'] = 'optional'
        dsc['Maintainer'] = 'Debler Automatic Rubygems Packager <debler@dxtt.de>'
        dsc['Homepage'] = self.metadata['homepage']
        dsc['Standards-Version'] = '3.9.6'
        dsc['Build-Depends'] = ', '.join(build_deps)

        dsc.dump(control_file)

        control = Deb822()
        control['Package'] = self.deb_name
        if level > 0:
            priovide = []
            priovide.append(self.gemnam2deb(self.gem_name))
            for l in range(1, level):
                priovide.append(self.gemnam2deb(self.gem_name + '-' + '.'.join([str(v) for v in self.gem_version[:l]])))
            control['Provides'] = ', '.join(['{} (= {})'.format(p, self.gem_version_s) for p in priovide])
        control['Architecture'] = 'all'
        deps = []
        for dep in self.metadata['dependencies']:
            if dep['type'] != ':runtime':
                continue
            req = self.gemnam2deb(dep['name'])
            versioned_deps = False
            for version in dep['version_requirements']['requirements']:
                if version[0] == '>=' and version[1]['version'] == '0':
                    continue
                req_level, _, slots = self.db.gem_info(dep['name'])
                if version[0] == '~>':
                    versioned_deps = True
                    up = version[1]['version'].split('.')
                    if req_level > 0:
                        req += '-' + '.'.join(up[:req_level])
                    deps.append('{} (>= {})'.format(req, version[1]['version']))
                    up[-1] = '0'
                    up[-2] = str(int(up[-2]) + 1)
                    deps.append('{} (<= {})'.format(req, '.'.join(up)))
                else:
                    versioned_deps = True
                    tmp = []
                    for slot in slots:
                        if slot:
                            slot = '-' + '.'.join([str(s) for s in slot])
                        else:
                            slot = ''
                        tmp.append('{} (>= {})'.format(req + slot, version[1]['version']))
                    deps.append(' | '.join(tmp))
            if not versioned_deps:
                deps.append(req)
        deps.append('${shlibs:Depends}')
        deps.append('${misc:Depends}')
        if len(self.metadata['extensions']) > 0:
            deps.append(' | '.join([self.deb_name + '-ruby' + ruby for ruby in rubies]))

        control['Depends'] = ', '.join(deps)
        control['Section'] = 'ruby'
        control['Homepage'] = self.metadata['homepage']
        control['Description'] = self.metadata['summary']
        control['Description'] += ('\n' + self.metadata['description']).replace('\n\n', '\n.\n').replace('\n', '\n ')

        control_file.write(b'\n')
        control.dump(control_file)

        if len(self.metadata['extensions']) > 0:
            for ruby in rubies:
                control = Deb822()
                control['Package'] = self.deb_name + '-ruby' + ruby
                control['Architecture'] = 'any'
                control['Depends'] = '${shlibs:Depends}, ${misc:Depends}'
                control['Section'] = 'ruby'
                control['Description'] = self.metadata['summary']
                control['Description'] += '\n Native extension for ruby' + ruby
                control_file.write(b'\n')
                control.dump(control_file)
        control_file.close()

    def generate_rules_file(self):
        rules = {}
        rules['build'] = []
        rules['install'] = []
        if len(self.metadata['extensions']) == 1:
            rules['build'].append(' v'.join(['mkdir'] + rubies))
            for ruby in rubies:
                rules['build'].append('cd v{v} && ruby{v} ../src/{}'.format(self.metadata['extensions'][0], v=ruby))
            for ruby in rubies:
                rules['build'].append('make -C v{v}'.format(v=ruby))
            for ruby in rubies:
                rules['install'].append(' '.join([
                    'dh_install',
                    '-p{package}',
                    'v{v}/*.so',
                    '/usr/lib/${{DEB_BUILD_MULTIARCH}}/rubygems-debler/{v}.0/{name}/']).format(
                        v=ruby, name=self.own_name, package=self.deb_name + '-ruby' + ruby))

        elif len(self.metadata['extensions']) > 1:
            rules['build'].append(' '.join(['mkdir', '-p'] + ['v{ruby}/{ext}'.format(ext=ext.replace('/', '_'), ruby=ruby) for ext in self.metadata['extensions'] for ruby in rubies]))
            for ext in self.metadata['extensions']:
                for ruby in rubies:
                    rules['build'].append('cd v{v}/{ext} && ruby{v} ../../src/{}'.format(
                        ext, ext=ext.replace('/', '_'), v=ruby))
            for ext in self.metadata['extensions']:
                for ruby in rubies:
                    rules['build'].append('make -C v{v}/{ext}'.format(
                        ext=ext.replace('/', '_'), v=ruby))
            for ext in self.metadata['extensions']:
                for ruby in rubies:
                    rules['install'].append(' '.join([
                        'dh_install',
                        '-p{package}',
                        'v{v}/{ext}/*.so',
                        '/usr/lib/${{DEB_BUILD_MULTIARCH}}/rubygems-debler/{v}.0/{name}/']).format(
                            v=ruby, name=self.own_name, package=self.deb_name + '-ruby' + ruby,
                            ext=ext.replace('/', '_')))

        with open(self.debian_file('rules'), 'w') as f:
            f.write("#!/usr/bin/make -f\n%:\n\tdh $@\n")
            for target in rules:
                f.write('\noverride_dh_auto_{target}:\n\t'.format(target=target))
                f.write('\n\t'.join(rules[target]))
                f.write('\n')

        with open(self.debian_file(self.deb_name + '.install'), 'w') as f:
            with tarfile.open(self.src_file) as t, tarfile.open(fileobj=t.extractfile('data.tar.gz')) as dt:
                members = dt.getmembers()
                for member in members:
                    for path in self.metadata['require_paths']:
                        if member.name.startswith(path):
                            break
                    else:
                        continue
                    f.write('src/{file} /usr/share/rubygems-debler/{name}/{dir}\n'.format(
                        name=self.own_name,
                        file=member.name,
                        dir=os.path.dirname(member.name)))

    def build(self):
        os.chdir(self.pkg_dir)
        subprocess.check_call(['dpkg-source', '-b', '.'])
        os.chdir(self.slot_dir)

        subprocess.check_call(['sbuild',
                               '--dist', 'trusty',
                               '--keyid', '0xDAE2696E26F4ADC4',
                               '--maintainer', 'Debler Automatic Rubygems Packager <debler@dxtt.de>',
                               '{}_{}.dsc'.format(self.deb_name, self.deb_version)])
