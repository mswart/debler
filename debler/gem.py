import os
import tarfile
import gzip
import yaml
import subprocess
from debian.deb822 import Deb822, Dsc
from debian.changelog import Changelog

from debler import config
from debler.builder import BaseBuilder


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
            if part.startswith('beta'):
                parts.append(-9)
                part = part[4:]
            parts.append(int(part))
        return cls(parts)

    def __str__(self):
        s = ''
        needdot = False
        for part in self.parts:
            if needdot:
                s += '.'
            else:
                needdot = True
            if part >= 0:
                s += str(part)
            elif part == -9:
                s += 'beta'
                needdot = False
        return s

    def todb(self):
        return self.parts

    def limit(self, l):
        return GemVersion(self.parts[:l])


class GemInfo():
    pass


class GemBuilder(BaseBuilder):
    def __init__(self, db, gem, slot, version, revision):
        self.db = db
        self.gem_name = gem
        self.orig_name = gem
        self.gem_slot = GemVersion(slot)
        self.gem_version = GemVersion(version)
        self.revision = revision
        self.deb_version = str(self.gem_version) + '-' + str(revision)

        self.own_name = self.gem_name
        if self.gem_slot:
            self.own_name += '-' + str(self.gem_slot)
        self.deb_name = self.gemnam2deb(self.own_name)

    def parse_metadata(self):
        with tarfile.open(name=self.src_file) as t:
            metadata = gzip.GzipFile(fileobj=t.extractfile('metadata.gz')).read()
            self.metadata = yaml.load(metadata)

    def create_dirs(self):
        super().create_dirs()
        os.makedirs(os.path.dirname(self.src_file), exist_ok=True)

    @property
    def src_file(self):
        return os.path.join(config.workdir, self.gem_name, str(self.gem_version), 'orig.gem')

    def fetch_source(self):
        if not os.path.isfile(self.src_file):
            subprocess.check_call(['wget',
                                   '{}/gems/{}-{}.gem'
                                  .format(config.rubygems, self.gem_name, self.gem_version),
                                   '-O', self.src_file])

    @property
    def pkg_dir(self):
        return os.path.join(
            self.slot_dir,
            self.gem_name + '-' + str(self.gem_slot))

    @property
    def slot_dir(self):
        return os.path.join(
            config.workdir,
            self.gem_name,
            'slot' + str(self.gem_slot))

    def symlink_orig_tar(self):
        orig_tar = os.path.join(self.slot_dir,
                                '{}_{}.orig.tar.xz'.format(self.deb_name,
                                str(self.gem_version)))
        if not os.path.islink(orig_tar):
            os.symlink(os.path.join('..', str(self.gem_version), 'orig.gem.xz'), orig_tar)

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

    def gen_debian_files(self):
        self.parse_metadata()
        self.symlink_orig_tar()
        super().gen_debian_files()

    def generate_control_file(self):
        build_deps = [
            'debhelper',
        ]
        exts = self.extension_list()
        if len(exts) > 0:
            for ruby in self.db.rubies:
                build_deps.append('ruby{}'.format(ruby))
                build_deps.append('ruby{}-dev'.format(ruby))

        level, opts, native, _ = self.db.gem_info(self.gem_name)
        assert native is (len(exts) > 0), 'Native flag value is wrong!'
        build_deps.extend(opts.get('default', {}).get('builddeps', []))
        control_file = open(self.debian_file('control'), 'wb')

        dsc = Dsc()
        dsc['Source'] = self.deb_name
        dsc['Priority'] = 'optional'
        dsc['Maintainer'] = config.maintainer
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
                priovide.append(self.gemnam2deb(self.gem_name + '-' + str(self.gem_version.limit(l))))
            control['Provides'] = ', '.join(priovide)
        control['Architecture'] = 'all'
        deps = []
        for dep in self.metadata['dependencies']:
            if dep['type'] != ':runtime':
                continue
            if dep['name'] == 'bundler':
                continue
            versioned_deps = False
            for version in dep['version_requirements']['requirements']:
                req = self.gemnam2deb(dep['name'])
                if version[0] == '>=' and version[1]['version'] == '0':
                    continue
                req_level, _, _, slots = self.db.gem_info(dep['name'])
                if not slots:
                    continue
                if version[0] != '=' and '.rc' in version[1]['version']:
                    version[1]['version'] = version[1]['version'][:version[1]['version'].find('.rc')]
                if version[0] == '~>':
                    versioned_deps = True
                    up = version[1]['version'].split('.')
                    if req_level > 0:
                        req += '-' + '.'.join(str(v) for v in slots[0][:req_level])
                    deps.append('{} (>= {})'.format(req, version[1]['version']))
                    if len(up) < 2:
                        continue
                    # TODO: skip if we leave our current slot
                    up[-1] = '0'
                    up[-2] = str(int(up[-2]) + 1)
                    deps.append('{} (<= {})'.format(req, '.'.join(up)))
                else:
                    if version[0] == '<':
                        up = version[1]['version'].split('.')
                        up[-1] = str(int(up[-1]) + 1)
                        v = '.'.join(up)
                    else:
                        v = version[1]['version']
                    versioned_deps = True
                    tmp = []
                    for slot in slots:
                        if slot:
                            slot = '-' + '.'.join([str(s) for s in slot])
                        else:
                            slot = ''
                        tmp.append('{} ({} {})'.format(req + slot, {'>': '>=', '=': '>=', '<': '<='}.get(version[0], version[0]), v))
                    deps.append(' | '.join(tmp))
            if not versioned_deps:
                deps.append(req)
        deps.append('${shlibs:Depends}')
        deps.append('${misc:Depends}')
        if len(exts) > 0:
            deps.append(' | '.join(['{}-ruby{} (= ${{binary:Version}})'.format(self.deb_name, ruby) for ruby in self.db.rubies]))

        control['Depends'] = ', '.join(deps)
        control['Section'] = 'ruby'
        control['Homepage'] = self.metadata['homepage']
        control['Description'] = self.metadata['summary']
        control['Description'] += ('\n' + (self.metadata['description'] or '')).replace('\n\n', '\n.\n').replace('\n', '\n ')

        control_file.write(b'\n')
        control.dump(control_file)

        if len(exts) > 0:
            for ruby in self.db.rubies:
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

    def generate_changelog_file(self):
        changes = Changelog()
        for version, revision, scheduled_at, change, distribution in self.db.changelog_entries(self.gem_name, self.gem_slot.todb()):
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
        exts = self.extension_list()
        _, opts, _, _ = self.db.gem_info(self.gem_name)
        ext_args = opts.get("default", {}).get('ext_args', '')
        if len(exts) == 1:
            rules['build'].append(' v'.join(['mkdir'] + list(self.db.rubies)))
            for ruby in self.db.rubies:
                rules['build'].append('cd v{v} && ruby{v} ../src/{} {}'.format(exts[0], ext_args, v=ruby))
            for ruby in self.db.rubies:
                rules['build'].append('make -C v{v}'.format(v=ruby))
            for ruby in self.db.rubies:
                rules['install'].append(' '.join([
                    'dh_install',
                    '-p{package}',
                    'v{v}/*.so',
                    '/usr/lib/${{DEB_BUILD_MULTIARCH}}/rubygems-debler/{v}.0/{name}/']).format(
                        v=ruby, name=self.own_name, package=self.deb_name + '-ruby' + ruby))

        elif len(exts) > 1:
            rules['build'].append(' '.join(['mkdir', '-p'] + ['v{ruby}/{ext}'.format(ext=ext.replace('/', '_'), ruby=ruby) for ext in self.metadata['extensions'] for ruby in self.db.rubies]))
            for ext in exts:
                for ruby in self.db.rubies:
                    rules['build'].append('cd v{v}/{ext} && ruby{v} ../../src/{} {}'.format(
                        ext, ext_args, ext=ext.replace('/', '_'), v=ruby))
            for ext in exts:
                for ruby in self.db.rubies:
                    rules['build'].append('make -C v{v}/{ext}'.format(
                        ext=ext.replace('/', '_'), v=ruby))
            for ext in exts:
                for ruby in self.db.rubies:
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

        with open(self.debian_file(self.gem_name + '.gemspec'), 'w') as f:
            f.write('''# File auto-generated by debler gem-builder

Gem::Specification.new do |s|
  s.name = "{name}"
  s.version = "{version}"

  s.required_rubygems_version = Gem::Requirement.new(">= 0") if s.respond_to? :required_rubygems_version=
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
                description=self.metadata['description'],
                email='", "'.join(self.metadata['email']),
                homepage=self.metadata['homepage'],
                licenses='", "'.join(self.metadata['licenses']),
                summary=self.metadata['summary']))
            for dep in self.metadata['dependencies']:
                if dep['type'] != ':runtime':
                    kind = 'add_dependency'
                else:
                    kind = 'add_development_dependency'
                f.write('  s.{kind}("{name}"'.format(kind=kind, name=dep['name']))
                for version in dep['version_requirements']['requirements']:
                    f.write(', "{op} {version}"'.format(op=version[0], version=version[1]['version']))
                f.write(')\n')
            f.write('end\n')

        with open(self.debian_file(self.deb_name + '.install'), 'w') as f:
            f.write('debian/{gem}.gemspec /usr/share/rubygems-debler/{name}/\n'.format(
                gem=self.gem_name, name=self.own_name))
            with tarfile.open(self.src_file) as t, tarfile.open(fileobj=t.extractfile('data.tar.gz')) as dt:
                members = dt.getmembers()
                for member in members:
                    for path in self.metadata['require_paths'] + [self.metadata['bindir'], 'data']:
                        if member.name.startswith(path):
                            break
                    else:
                        continue
                    f.write('src/{file} /usr/share/rubygems-debler/{name}/{dir}\n'.format(
                        name=self.own_name,
                        file=member.name,
                        dir=os.path.dirname(member.name)))

    def extension_list(self):
        _, opts, _, _ = self.db.gem_info(self.gem_name)
        exts = list(self.metadata['extensions'])
        for ext in opts.get('default', {}).get('skip_exts', []):
            exts.remove(ext)
        return exts
