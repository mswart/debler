import os
import tarfile
import gzip
import yaml
from struct import pack, unpack
import subprocess
import re
from shutil import move
from glob import glob

from debian.changelog import Changelog

from debler import config
from debler.builder import BaseBuilder, \
    SourceControl, Package, \
    BuildDependency, Dependency, Provide, \
    Install, InstallContent, RuleAction


def construct_ruby_object(loader, suffix, node):
    return loader.construct_yaml_map(node)


def construct_binary_object(loader, suffix, node):
    return loader.construct_scalar(node)


yaml.add_multi_constructor(u"!ruby/object:", construct_ruby_object)
yaml.add_multi_constructor(u'!binary', construct_binary_object)


class GemVersion():
    def __init__(self, parts):
        self.parts = parts

    @classmethod
    def fromstr(cls, s):
        parts = []
        for part in s.split('.'):
            if part.isdecimal():
                parts.append(int(part))
            elif part.startswith('rev'):
                parts.append(-2)
                part = part[3:]
                assert len(part) == 40
                while len(part) > 0:
                    i = int(part[:8], 16)
                    parts.append(unpack('i', pack('I', i))[0])
                    part = part[8:]
                parts.append(0)
            else:
                parts.append(-1)
                for char in part:
                    parts.append(ord(char))
                parts.append(0)
        return cls(parts)

    def __str__(self):
        s = ''
        needdot = False
        instr = False
        inrev = False
        for part in self.parts:
            if needdot:
                s += '.'
            else:
                needdot = True
            if part == 0 and (instr or inrev):
                instr = False
            elif instr:
                s += chr(part)
                needdot = False
            elif inrev:
                s += '{:08x}'.format(unpack('I', pack('i', part))[0])
                needdot = False
            elif part >= 0:
                s += str(part)
            elif part == -1:
                instr = True
                needdot = False
            elif part == -2:
                inrev = True
                needdot = False
                s += 'rev'
            elif part == -9:
                s += 'beta'
                needdot = False
            elif part == -8:
                s += 'xikolo'
            elif part == -7:
                s += 'openhpi'
        return s

    def todb(self):
        return self.parts

    def limit(self, l):
        return GemVersion(self.parts[:l])


class GemInfo():
    pass


class GemBuilder(BaseBuilder):

    @staticmethod
    def gemname2deb(name):
        return 'debler-rubygem-' + name.replace('_', '--')

    def __init__(self, pkger, tmp_dir, build_id):
        self.pkger = pkger
        self.db = pkger.db
        self.tmp_dir = tmp_dir
        self.build = self.db.build_data(build_id)
        assert self.build.pkger == 'bundler'
        self.gem_name = self.build.pkg
        self.orig_name = self.build.pkg
        self.gem_slot = self.build.slot
        self.gem_version = self.build.version
        self.revision = self.build.revision
        self.deb_version = self.build.revision

        self.own_name = self.gem_name
        if self.gem_slot:
            self.own_name += '-' + str(self.gem_slot)
        self.deb_name = self.gemname2deb(self.own_name)

        self.pkg_dir = tmp_dir + '/' + self.gem_name + '-' + str(self.gem_slot)
        self.package_upload = config.gem_package_upload

    def generate(self):
        self.create_dirs()
        self.fetch_source()
        self.parse_metadata()

        super().generate()

    def parse_metadata(self):
        with tarfile.open(name=self.src_file) as t:
            metadata = gzip.GzipFile(fileobj=t.extractfile('metadata.gz')) \
                .read()
            self.metadata = yaml.load(metadata)

    def create_dirs(self):
        os.makedirs(os.path.dirname(self.src_file), exist_ok=True)

    @property
    def src_file(self):
        return os.path.join(
            config.gemdir,
            'versions',
            self.gem_name,
            str(self.gem_version) + '.gem')

    @property
    def tarxz_file(self):
        return os.path.join(
            config.gemdir,
            'versions',
            self.gem_name,
            str(self.gem_version) + '.tar.xz')

    @property
    def orig_tar(self):
        return os.path.join(
            self.slot_dir,
            '{}_{}.orig.tar.xz'.format(self.deb_name, str(self.gem_version))
        )

    def fetch_source(self):
        if os.path.isfile(self.src_file):
            return
        if 'revision' not in self.build.version_config:
            subprocess.check_call([
                'wget',
                '{}/gems/{}-{}.gem'.format(self.pkger.rubygems, self.gem_name,
                                           self.gem_version),
                '-O', self.src_file])
            return
        subprocess.check_call(['git', 'clone',
                               self.build.version_config['repository'],
                               os.path.join(self.tmp_dir, 'git')])
        subprocess.check_call([
            'git',
            '-C', os.path.join(self.tmp_dir, 'git'),
            'reset', '--hard',
            self.build.version_config['revision']])
        subprocess.check_call([
            'gem', 'build',
            *glob(os.path.join(self.tmp_dir, 'git', '*.gemspec'))],
            cwd=os.path.join(self.tmp_dir, 'git'))
        gem_file = glob(os.path.join(self.tmp_dir, 'git', '*.gem'))[0]
        move(gem_file, self.src_file)

    @property
    def slot_dir(self):
        return self.tmp_dir

    def build_tarxz(self):
        if os.path.isfile(self.tarxz_file):
            return
        outtar = tarfile.open(name=self.tarxz_file, mode='w:xz')
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

    def build_orig_tar(self):
        if os.path.isfile(self.orig_tar):
            return
        self.build_tarxz()
        os.symlink(self.tarxz_file, self.orig_tar)

    def generate_control_content(self):
        yield SourceControl(
            source=self.deb_name,
            priority='optional',
            maintainer=config.maintainer,
            standards_version='3.9.6',
        )
        if self.metadata['homepage']:
            yield SourceControl(homepage=self.metadata['homepage'])
        yield BuildDependency('debhelper')

        exts = self.extension_list()
        if len(exts) > 0:
            for ruby in self.pkger.rubies:
                yield BuildDependency('ruby{}'.format(ruby))
                yield BuildDependency('ruby{}-dev'.format(ruby))

        info = self.pkger.gem_info(self.gem_name)
        if info.native is None:  # auto-detect on first build
            info.native = bool(len(exts) > 0)
            self.db.set_gem_native(self.gem_name, info.native)
        assert info.native is (len(exts) > 0), 'Native flag value is wrong!'
        for builddep in info.get('builddeps', []):
            yield BuildDependency(builddep)

        yield Package(
            self.deb_name,
            architecture='all',
            section='ruby',
            description=self.metadata['summary'] + '\n' +
            (self.metadata.get('description', '') or ''),
        )

        if info.level > 0:
            yield Provide(self.deb_name, self.gemname2deb(self.gem_name))
            for l in range(1, info.level):
                yield Provide(self.deb_name,
                    self.gemname2deb(self.gem_name + '-' + str(self.gem_version.limit(l))))
        if 'revision' in self.build.version_config:
            yield Provide(self.deb_name, self.gemname2deb(self.gem_name) +
                          '-' + self.build.version_config['revision'])

        self.ext_load_paths = []
        for dep in self.metadata['dependencies']:
            if dep['type'] != ':runtime':
                continue
            depinfo = self.pkger.gem_info(dep['name'])
            if depinfo.get('ignore', False) or dep['name'] == 'bundler':
                continue
            req = self.gemname2deb(dep['name'])
            if depinfo.get('buildgem', False):
                # gem is only used during gem building,
                # no need for runtime dependency
                slot = list(depinfo.slots.keys())[-1]
                slot_s = '.'.join(str(s) for s in slot)
                yield BuildDependency(req + '-' + slot_s)
                for path in depinfo.slots[slot].get('require_paths', []):
                    self.ext_load_paths.append(
                        '/usr/share/rubygems-debler/{name}-{slot}/{}/'.format(
                            path, name=dep['name'], slot=slot_s))
                # TODO: implement version contraints
                continue
            versioned_deps = False
            for version in dep['version_requirements']['requirements']:
                if version[0] == '>=' and version[1]['version'] == '0':
                    continue
                if not depinfo.slots:
                    continue
                if version[0] != '=' and '.rc' in version[1]['version']:
                    version[1]['version'] = version[1]['version'][:version[1]['version'].find('.rc')]
                if version[0] == '~>':
                    versioned_deps = True
                    min_version = version[1]['version']
                    up = min_version.split('.')
                    fixed_components = len(up) - 1
                    if fixed_components > depinfo.level:
                        # we stay within one slot
                        # e.g. ~> 1.5 and slots = (0, 1, 2)
                        req += '-' + '.'.join(up[:depinfo.level])
                        yield Dependency(self.deb_name, '{} (>= {})'.format(req, min_version))
                        up[-1] = '0'
                        up[-2] = str(int(up[-2]) + 1)
                        yield Dependency(self.deb_name, '{} (<< {})'.format(req, '.'.join(up)))
                    elif fixed_components == depinfo.level:
                        # we are pinned to a specific slot
                        # e.g. ~> 1.5.1 and slots 1.5, 1.6
                        yield Dependency(self.deb_name, '{}-{}'.format(req, '.'.join(up[:fixed_components])))
                    elif fixed_components < depinfo.level:
                        # multiple slots fulfil the requirements
                        # e.g. ~> 1.0, and slots 1.5, 1.6, 1.7, 1.8
                        # depend on any of same (but prefer newer ones)
                        possible_deps = []
                        required_prefix = tuple(int(v) for v in up[:fixed_components])
                        for slot in reversed(sorted(depinfo.slots)):
                            if required_prefix != slot[:fixed_components]:
                                continue
                            possible_deps.append('{}-{}'.format(req, '.'.join(str(s) for s in slot)))
                        yield Dependency(self.deb_name, ' | '.join(possible_deps))
                elif version[0] == '!=':
                    # we need to exclude all debian revision of this version
                    # meaning << version or >> version +1
                    # 1. searching matching slot:
                    for slot in reversed(sorted(depinfo.slots)):
                        if slot != tuple(int(v) for v in version[1]['version'].split('.')[:len(slot)]):
                            continue
                        parts = version[1]['version'].split('.')
                        parts[-1] = str(int(parts[-1]) + 1)
                        yield Dependency(self.deb_name, '{pkg} (<< {max_ver}) | {pkg} (>> {min_ver})'.format(
                            pkg='{}-{}'.format(req, '.'.join(str(s) for s in slot)),
                            max_ver=version[1]['version'],
                            min_ver='.'.join(parts)
                        ))
                        break
                else:
                    if version[0] in ['<', '<=']:
                        up = version[1]['version'].split('.')
                        up[-1] = str(int(up[-1]) + 1)
                        v = '.'.join(up)
                    else:
                        v = re.sub('\.([^0-9])', '.~\\1', version[1]['version'])
                    versioned_deps = True
                    tmp = []
                    # todo simplify
                    for slot in depinfo.slots:
                        if str(slot.version):
                            slot = '-' + str(slot.version)
                        else:
                            slot = ''
                        tmp.append('{} ({} {})'.format(req + slot, {'>': '>=', '=': '>=', '<': '<='}.get(version[0], version[0]), v))
                    yield Dependency(self.deb_name, ' | '.join(tmp))
            if not versioned_deps:
                yield Dependency(self.deb_name, req)
        for dep in info.lookup('rundeps', default=[]):
            yield Dependency(self.deb_name, dep)
        yield Dependency(self.deb_name, '${shlibs:Depends}')
        yield Dependency(self.deb_name, '${misc:Depends}')
        if len(exts) > 0:
            binary_deps = ['{}-ruby{} (= ${{binary:Version}})'.format(
                           self.deb_name, ruby) for ruby in self.pkger.rubies]
            yield Dependency(self.deb_name, ' | '.join(binary_deps))

        if len(exts) > 0:
            for ruby in self.pkger.rubies:
                name = self.deb_name + '-ruby' + ruby
                yield Package(
                    name,
                    architecture='any',
                    section='ruby',
                    description=self.metadata['summary'] +
                    '\n Native extension for ruby' + ruby
                )
                yield Dependency(name, '${shlibs:Depends}')
                yield Dependency(name, '${misc:Depends}')

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

    def gemspec(self):
        yield '''# File auto-generated by debler gem-builder

Gem::Specification.new do |s|
  s.name = "{name}"
  s.version = "{version}"

  if s.respond_to? :required_rubygems_version=
    s.required_rubygems_version = Gem::Requirement.new(">= 0")
  end
  s.require_paths = ["{require_paths}"]
  s.authors = ["{authors}"]
  s.date = "{date}"
  s.description = "{description}"
  s.email = ["{email}"]
  s.homepage = "{homepage}"
  s.licenses = ["{licenses}"]
  s.summary = "{summary}"

'''.format(
                name=self.gem_name,
                version=self.metadata['version']['version'],
                require_paths='", "'.join(self.metadata['require_paths']),
                authors='", "'.join(self.metadata['authors']),
                date=self.metadata['date'].strftime('%Y-%m-%d'),
                description=(self.metadata.get('description', '') or '')
                            .replace('"', '\\"'),
                email='", "'.join(self.metadata['email'])
                      if type(self.metadata['email']) is list
                      else self.metadata['email'],
                homepage=self.metadata['homepage'],  # TODO: might be None!
                licenses='", "'.join(self.metadata['licenses']),
                summary=self.metadata.get('summary', '').replace('"', '\\"'))

        for dep in self.metadata['dependencies']:
            if dep['type'] == ':runtime':
                kind = 'add_dependency'
            else:
                kind = 'add_development_dependency'
            yield '  s.{kind}("{name}"'.format(kind=kind, name=dep['name'])
            for version in dep['version_requirements']['requirements']:
                yield ', "{op} {version}"'.format(
                    op=version[0],
                    version=version[1]['version'])
            yield ')\n'
        yield 'end\n'

    def generate_rules_content(self):
        metadata = {
            'binaries': [],
            'require_paths': self.metadata['require_paths'],
            'require': None
        }
        rules = {}
        rules['build'] = []
        rules['install'] = []
        exts = self.extension_list()
        info = self.pkger.gem_info(self.gem_name)
        ext_args = info.lookup('ext_args', '')
        subdir = info.get('so_subdir', '')
        rubyopts = ''
        for load_path in self.ext_load_paths:
            rubyopts += ' -I{path}'.format(path=load_path)
        if len(exts) == 1:
            yield RuleAction('build',
                             ' v'.join(['mkdir'] + list(self.pkger.rubies)))
            for ruby in self.pkger.rubies:
                yield RuleAction(
                    'build',
                    'cd v{v} && ruby{v} {rubyopts} ../src/{} {}'.format(
                        exts[0], ext_args, v=ruby, rubyopts=rubyopts))
            for ruby in self.pkger.rubies:
                yield RuleAction('build', 'make -C v{v}'.format(v=ruby))
            for ruby in self.pkger.rubies:
                yield RuleAction('build', ' '.join([
                    'dh_install',
                    '-p{package}',
                    'v{v}/*.so',
                    os.path.join('/', 'usr', 'lib',
                                 '${{DEB_BUILD_MULTIARCH}}',
                                 'rubygems-debler',
                                 '{v}.0',
                                 '{name}',
                                 subdir)]).format(
                    v=ruby, name=self.own_name,
                    package=self.deb_name + '-ruby' + ruby))

        elif len(exts) > 1:
            yield RuleAction('build', ' '.join(['mkdir', '-p'] + ['v{ruby}/{ext}'.format(ext=ext.replace('/', '_'), ruby=ruby) for ext in self.metadata['extensions'] for ruby in config.rubies]))
            for ext in exts:
                for ruby in self.pkger.rubies:
                    yield RuleAction('build', 'cd v{v}/{ext} && ruby{v} {rubyopts}../../src/{} {}'.format(
                        ext, ext_args, ext=ext.replace('/', '_'), v=ruby, rubyopts=rubyopts))
            for ext in exts:
                for ruby in self.pkger.rubies:
                    yield RuleAction('build', 'make -C v{v}/{ext}'.format(
                        ext=ext.replace('/', '_'), v=ruby))
            for ext in exts:
                for ruby in self.pkger.rubies:
                    yield RuleAction('build', ' '.join([
                        'dh_install',
                        '-p{package}',
                        'v{v}/{ext}/*.so',
                        os.path.join('/', 'usr', 'lib',
                                     '${{DEB_BUILD_MULTIARCH}}',
                                     'rubygems-debler',
                                     '{v}.0',
                                     '{name}',
                                     subdir)]).format(
                        v=ruby, name=self.own_name,
                        package=self.deb_name + '-ruby' + ruby,
                        ext=ext.replace('/', '_')))

        yield InstallContent(
            self.deb_name,
            name=self.gem_name + '.gemspec',
            dest='/usr/share/rubygems-debler/{}/'.format(self.own_name),
            mode=0o755,
            content=''.join(self.gemspec()))

        current_level = None
        require_files = []
        with tarfile.open(self.src_file) as t, \
                tarfile.open(fileobj=t.extractfile('data.tar.gz')) as dt:
            members = dt.getmembers()
            for member in members:
                # search for binaries
                if self.metadata['bindir'] and \
                        member.name.startswith(self.metadata['bindir'] + '/'):
                    metadata['binaries'].append(member.name)
                # search for require entry files (top level file ...)
                for path in self.metadata['require_paths']:
                    if member.name.startswith(path) \
                            and member.name.endswith('.rb'):
                        parts = member.name.split('/')
                        if current_level is None or len(parts) < current_level:
                            # strip extension
                            require_files = [member.name[len(path)+1:-3]]
                            current_level = len(parts)
                        elif len(parts) == current_level:  # should not happend
                            # strip extension + require path
                            require_files.append(member.name[len(path)+1:-3])
                for path in self.metadata['require_paths'] + \
                        [self.metadata['bindir'], 'data', 'vendor'] + \
                        info.get('extra_dirs', []):
                    if member.name.startswith(path):
                        break
                else:
                    continue
                yield Install(
                    self.deb_name,
                    os.path.join('src', member.name),
                    '/usr/share/rubygems-debler/{name}/{dir}'.format(
                        name=self.own_name,
                        dir=os.path.dirname(member.name)))
        if self.orig_name in require_files:
            metadata['require'] = [self.orig_name]
        elif self.orig_name.replace('-', '/') in require_files:
            metadata['require'] = [self.orig_name.replace('-', '/')]
        elif len(require_files) == 1:
            metadata['require'] = require_files
        elif not require_files:
            pass
        else:
            # not sure what to do ...
            metadata['require'] = require_files
        self.pkger.db.set_slot_metadata(self.build.slot_id, metadata)

    def extension_list(self):
        info = self.pkger.gem_info(self.gem_name)
        exts = list(self.metadata['extensions'])
        for ext in info.get('skip_exts', []):
            exts.remove(ext)
        return exts
