import yaml
from datetime import datetime
import os
import os.path
import subprocess

from debian.changelog import Changelog
from dateutil.tz import tzlocal
from debian.deb822 import Deb822, Dsc


from debler.gemfile import Parser as GemfileParser
from debler.builder import BaseBuilder
from debler import config


class AppInfo():
    def __init__(self, db, name, version, basedir, *, gemfile=None,
                 homepage=None, description=None, executables=[], dirs=[],
                 bundler_laucher=False, files=[], default_env=None):
        self.db = db
        self.name = name
        if type(version) is list:
            self.version = version
        else:
            self.version = tuple(int(i) for i in str(version).split('.'))
        self.basedir = basedir
        if gemfile is not None:
            self.gemfile = GemfileParser(os.path.join(self.basedir, gemfile))
        self.homepage = homepage
        self.description = description
        self.executables = executables
        self.dirs = dirs
        self.files = files
        self.bundler_laucher = bundler_laucher
        self.default_env = default_env

    @classmethod
    def fromyml(cls, db, filename):
        data = yaml.load(open(filename).read().format(**os.environ))
        if 'basedir' not in data:
            data['basedir'] = os.path.dirname(os.path.realpath(filename))
        return cls(db, **data)

    def schedule_gemdeps_builds(self):
        for name, gem in self.gems.items():
            if not gem.version:
                continue
            level, builddeps, native, slots = self.db.gem_info(name)
            slot = tuple(gem.version.limit(level).todb())
            if slot not in slots:
                self.db.create_gem_slot(name, slot)
                self.db.create_gem_version(
                    name, slot,
                    version=gem.version.todb(), revision=1,
                    changelog='Import newly into debler', distribution=config.distribution)

    @property
    def gems(self):
        return self.gemfile.gems


class AppBuilder(BaseBuilder):
    def __init__(self, db, tmp_dir, app):
        self.db = db
        self.tmp_dir = tmp_dir
        self.app = app
        self.orig_name = app.name
        self.deb_name = app.name
        self.package_upload = config.app_package_upload

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
            deb_version.debian_revision = str(int(deb_version.debian_revision) + 1)
            change = 'Rebuild with newer debler'
        else:
            changes = Changelog()
            deb_version = '.'.join([str(v) for v in self.app.version]) + '-1'
            change = 'Build with debler'
        changes.new_block(package=self.deb_name, version=deb_version,
                          distributions=config.distribution, urgency='low',
                          author=config.maintainer,
                          date=datetime.now(tz=tzlocal()).strftime('%a, %d %b %Y %H:%M:%S %z'))
        self.deb_version = deb_version
        changes.add_change('\n  * ' + change + '\n')
        with open(changelog, 'w') as f:
            changes.write_to_open_file(f)

    def generate_control_file(self):
        build_deps = [
            'debhelper',
        ]
        control_file = open(self.debian_file('control'), 'wb')

        dsc = Dsc()
        dsc['Source'] = self.deb_name
        dsc['Priority'] = 'optional'
        dsc['Maintainer'] = config.maintainer
        dsc['Homepage'] = self.app.homepage
        dsc['Standards-Version'] = '3.9.6'
        dsc['Build-Depends'] = ', '.join(build_deps)

        dsc.dump(control_file)

        control = Deb822()
        control['Package'] = self.deb_name
        control['Architecture'] = 'all'
        self.load_paths = {'all': []}
        self.installs = {'all': []}
        self.symlinks = {'all': []}
        self.gem_metadatas = {}
        self.binaries = []
        deps = []
        natives = []
        for name, gem in self.app.gems.items():
            if not gem.version:  # included by path
                assert gem.path is not None, 'gem "{!s}" does not have any version, but no path: {!r}!'.format(gem.name, gem)
                self.load_paths['all'].append('/usr/share/{name}/{path}/{}'.format('lib', name=self.app.name, path=gem.path))
                self.installs['all'].append((gem.path, '/usr/share/{name}/{path}'.format('lib', name=self.app.name, path=os.path.dirname(gem.path))))
                continue
            level, builddeps, native, slots = self.db.gem_info(name)
            slot = tuple(gem.version.limit(level).todb())
            metadata = slots[slot]
            self.gem_metadatas[name] = metadata
            gem_slot_name = name + '-' + '.'.join([str(s) for s in slot])
            self.symlinks['all'].append((
                '/usr/share/rubygems-debler/{}/{}.gemspec'.format(gem_slot_name, name),
                '/usr/share/{}/.debler/gems/specifications/{}-{}.gemspec'.format(self.app.name, name, str(gem.version))
            ))
            deb_dep = self.gemnam2deb(gem_slot_name)
            for path in metadata.get('require_paths', []):
                self.load_paths['all'].append('/usr/share/rubygems-debler/{name}/{}/'.format(path, name=gem_slot_name))
            for binary in metadata['binaries']:
                self.binaries.append((os.path.basename(binary),
                                      os.path.join('/usr/share/rubygems-debler', gem_slot_name, binary),
                                      metadata.get('require', [])))
            if native:
                natives.append((deb_dep, gem_slot_name))
            if gem.constraints:
                for constraint in gem.constraints:
                    if ' ' not in constraint:
                        constraint = '= ' + constraint
                    op, vers = constraint.split(' ')
                    if op == '~>':
                        up = vers.split('.')
                        deps.append('{} (>= {})'.format(deb_dep, vers))
                        if len(up) > level:
                            up[-1] = '0'
                            up[-2] = str(int(up[-2]) + 1)
                            deps.append('{} (<= {})'.format(deb_dep, '.'.join(up)))
                    else:
                        deps.append('{} ({} {})'.format(deb_dep, {'=': '>=', '>': '>='}.get(op, op), vers))
            else:
                deps.append(deb_dep)
        deps.append(' | '.join([self.deb_name + '-ruby' + ruby for ruby in config.rubies]))
        deps.append('${shlibs:Depends}')
        deps.append('${misc:Depends}')

        control['Depends'] = ', '.join(deps)
        control['Section'] = 'ruby'
        control['Description'] = self.app.description.replace('\n', '\n ').replace('\n \n', '\n .\n')

        control_file.write(b'\n')
        control.dump(control_file)

        for ruby in config.rubies:
            self.load_paths[ruby + '.0'] = []
            self.installs[ruby + '.0'] = []
            control = Deb822()
            control['Package'] = self.deb_name + '-ruby' + ruby
            control['Architecture'] = 'all'
            deps = ['ruby' + ruby]
            for deb_dep, gem_slot_name in natives:
                deps.append('{}-ruby{}'.format(deb_dep, ruby))
                self.load_paths[ruby + '.0'].append('/usr/lib/DEB_BUILD_MULTIARCH/rubygems-debler/{v}.0/{name}/'.format(v=ruby, name=gem_slot_name))
            deps.append('${shlibs:Depends}')
            deps.append('${misc:Depends}')

            control['Depends'] = ', '.join(deps)
            control['Section'] = 'ruby'
            control['Description'] = self.app.description.split('\n')[0] + ' - ruby {}'.format(ruby)
            control['Description'] += '\n Needed dependencies and executables for Ruby {}'.format(ruby)
            control_file.write(b'\n')
            control.dump(control_file)

        control_file.close()

    def generate_rules_file(self):
        with open(self.debian_file('rules'), 'w') as f:
            f.write("#!/usr/bin/make -f\n%:\n\tdh $@\n")

            f.write('\noverride_dh_auto_build:\n')
            for version in self.load_paths:
                if version == 'all':
                    continue
                f.write('\tsed --in-place --expression=s:/DEB_BUILD_MULTIARCH/:/${{DEB_BUILD_MULTIARCH}}/: debian/data/{} \n'.format(version))
        os.chmod(self.debian_file('rules'), 0o755)

        for dir in self.app.dirs:
            self.installs['all'].append((dir, '/usr/share/{}\n'.format(self.app.name)))
        for file in self.app.files:
            self.installs['all'].append((file, '/usr/share/{}\n'.format(self.app.name)))

        os.makedirs(self.debian_file('data'), exist_ok=True)
        os.makedirs(self.debian_file('bin'), exist_ok=True)
        for version, paths in self.load_paths.items():
            self.installs[version].append((os.path.join('debian', 'data', version), '/usr/share/{}/.debler/load_paths/'.format(self.app.name)))
            with open(self.debian_file('data', version), 'w') as f:
                f.write('\n'.join(paths) + '\n')

        for executable in self.app.executables:
            self.installs['all'].append((executable, '/usr/share/{}/{}'.format(self.app.name, os.path.dirname(executable))))
            for ruby in config.rubies:
                with open(self.debian_file('bin', os.path.basename(executable) + ruby), 'w') as f:
                    f.write('#!/usr/bin/ruby{}\n'.format(ruby))
                    f.write('File.readlines("/usr/share/{}/.debler/load_paths/all").each do |dir|\n'.format(self.app.name))
                    f.write('  $LOAD_PATH << dir.strip\n')
                    f.write('end\n')
                    f.write('File.readlines("/usr/share/{}/.debler/load_paths/{}.0").each do |dir|\n'.format(self.app.name, ruby))
                    f.write('  $LOAD_PATH << dir.strip\n')
                    f.write('end\n')
                    f.write('load "/usr/share/{}/{}"\n'.format(self.app.name, executable))
                self.installs[ruby + '.0'].append((os.path.join('debian', 'bin', os.path.basename(executable) + ruby), '/usr/bin'))
                os.chmod(self.debian_file('bin', os.path.basename(executable) + ruby), 0o755)

        if self.app.bundler_laucher:
            os.makedirs(self.debian_file('lib/bundler'), exist_ok=True)

            for ruby in config.rubies:
                with open(self.debian_file('bin', self.app.name + ruby), 'w') as f:
                    f.write('#!/usr/bin/ruby{}\n'.format(ruby))
                    f.write('Dir.chdir("/usr/share/{}")\n'.format(self.app.name))
                    f.write('ENV[\'HOME\'] = \'/tmp\'\n')  # will be fixed later
                    f.write('ENV[\'RAILS_ENV\'] ||= \'{}\'\n'.format(self.app.default_env))
                    f.write('ENV[\'GEM_PATH\'] = \'/usr/share/{}/.debler/gems\'\n'.format(self.app.name))
                    f.write('$LOAD_PATH << \'/usr/share/{}/.debler/lib\'\n'.format(self.app.name))
                    f.write('File.readlines("/usr/share/{}/.debler/load_paths/all").each do |dir|\n'.format(self.app.name))
                    f.write('  $LOAD_PATH << dir.strip\n')
                    f.write('end\n')
                    f.write('File.readlines("/usr/share/{}/.debler/load_paths/{}.0").each do |dir|\n'.format(self.app.name, ruby))
                    f.write('  $LOAD_PATH << dir.strip\n')
                    f.write('end\n')
                    f.write('exe = ARGF.argv.shift\n')
                    f.write('if File.exist? exe\n')
                    f.write('  load exe\n')
                    f.write('else\n')
                    f.write('  binaries = {\n')
                    for exe, path, requires in self.binaries:
                        f.write('    \'{}\' => [{}, "{}"],\n'.format(exe, path, '", "'.join(requires)))
                    f.write('  }\n')
                    f.write('  if binaries.key? exe\n')
                    f.write('    binaries[exe][1].each do |torequire|\n')
                    f.write('      require torequire\n')
                    f.write('    end\n')
                    f.write('    load binaries[exe][0]\n')
                    f.write('  end\n')
                    f.write('end\n')
                self.installs[ruby + '.0'].append((os.path.join('debian', 'bin', self.app.name + ruby), '/usr/bin'))
                os.chmod(self.debian_file('bin', self.app.name + ruby), 0o755)

                with open(self.debian_file('{}-ruby{}.postinst'.format(self.app.name, ruby)), 'w') as f:
                    f.write('#!/bin/sh\n')
                    f.write('set -e\n\n')
                    f.write('update-alternatives --install /usr/bin/{app} {app} /usr/bin/{app}{ruby} {priority}\n'.format(
                        app=self.app.name, ruby=ruby, priority='9' + ruby.replace('.', '')))
                    f.write('\n')
                    f.write('#DEBHELPER#\n\n')
                    f.write('exit 0\n')

                with open(self.debian_file('{}-ruby{}.prerm'.format(self.app.name, ruby)), 'w') as f:
                    f.write('#!/bin/sh\n')
                    f.write('set -e\n\n')
                    f.write('case "$1" in\n')
                    f.write('  remove|deconfigure)\n')
                    f.write('    update-alternatives --remove {app} /usr/bin/{app}{ruby}\n'.format(
                        app=self.app.name, ruby=ruby))
                    f.write('    ;;\n\n')
                    f.write('  upgrade|failed-upgrade)\n')
                    f.write('    ;;\n\n')
                    f.write('  *)\n')
                    f.write('    echo "prerm called with unknown argument \\`$1\'" >&2\n')
                    f.write('    exit 0\n')
                    f.write('    ;;\n\n')
                    f.write('esac\n\n')
                    f.write('#DEBHELPER#\n\n')
                    f.write('exit 0\n')

            self.installs['all'].append((os.path.join('debian', 'lib'), '/usr/share/{}/.debler'.format(self.app.name)))
            with open(self.debian_file('lib', 'bundler', 'setup.rb'), 'w') as f:
                f.write('require "bundler"\n')

            with open(self.debian_file('lib', 'bundler.rb'), 'w') as f:
                f.write('class Bundler\n')
                f.write('  def self.require(*groups)\n')

                for name in self.app.gemfile.sorted_gems:
                    gem = self.app.gemfile.gems[name]
                    if not gem.require:
                        continue
                    for require in self.gem_metadatas[name].get('require', []):
                        if 'default' in gem.envs:
                            f.write('    Kernel.require "{}"\n'.format(require))
                        else:
                            f.write('    Kernel.require "{}" unless (groups & ["{}"]).empty?\n'.format(require, '", "'.join(gem.envs)))
                f.write('  end\n')
                f.write('end\n')

        for version, installs in self.installs.items():
            if version == 'all':
                deb = self.deb_name
            else:
                deb = self.deb_name + '-ruby' + version[:-2]
            with open(self.debian_file(deb + '.install'), 'w') as f:
                for file, dir in installs:
                    f.write('{} {}\n'.format(file, dir))

        for version, symlinks in self.symlinks.items():
            if not symlinks:
                continue
            if version == 'all':
                deb = self.deb_name
            else:
                deb = self.deb_name + '-ruby' + version[:-2]
            with open(self.debian_file(deb + '.links'), 'w') as f:
                for file, dir in symlinks:
                    f.write('{} {}\n'.format(file, dir))

    @property
    def orig_tar(self):
        return os.path.join(self.slot_dir, '{}_{}.orig.tar.xz'.format(self.deb_name, '.'.join(str(v) for v in self.app.version)))

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
