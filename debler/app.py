import yaml
from datetime import datetime
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
                 bundler_laucher=False, files=[]):
        self.db = db
        self.name = name
        if type(version) is list:
            self.version = version
        else:
            self.version = tuple(int(i) for i in str(version).split('.'))
        self.basedir = basedir
        if gemfile is None:
            self.gemfile = None
            self.gemfile_lock = None
        else:
            self.gemfile = None
            self.gemfile_lock = GemfileParser(open(os.path.join(self.basedir,
                                              gemfile + '.lock')))
        self.homepage = homepage
        self.description = description
        self.executables = executables
        self.dirs = dirs
        self.files = files
        self.bundler_laucher = bundler_laucher

    @classmethod
    def fromyml(cls, db, filename):
        data = yaml.load(open(filename))
        if 'basedir' not in data:
            data['basedir'] = os.path.dirname(os.path.realpath(filename))
        return cls(db, **data)

    def schedule_gemdeps_builds(self):
        for dep, version in self.gems.items():
            level, builddeps, native, slots = self.db.gem_info(dep)
            slot = tuple(version.limit(level).todb())
            if slot not in slots:
                self.db.create_gem_slot(dep, slot)
                self.db.create_gem_version(
                    dep, slot,
                    version=version.todb(), revision=1,
                    changelog='Import newly into debler', distribution='trusty')

    @property
    def gems(self):
        return self.gemfile_lock.gems

    @property
    def dependencies(self):
        return self.gemfile_lock.dependencies


class AppBuilder(BaseBuilder):
    def __init__(self, db, app):
        self.db = db
        self.app = app
        self.orig_name = app.name
        self.deb_name = app.name

    @property
    def pkg_dir(self):
        return os.path.join(
            self.slot_dir,
            self.app.name)

    @property
    def slot_dir(self):
        return os.path.join(
            config.appdir,
            self.app.name)

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
                          distributions='trusty', urgency='low',
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
        deps = []
        natives = []
        for dep, version in self.app.gems.items():
            level, builddeps, native, slots = self.db.gem_info(dep)
            slot = tuple(version.limit(level).todb())
            gem_slot_name = dep + '-' + '.'.join([str(s) for s in slot])
            self.symlinks['all'].append((
                '/usr/share/rubygems-debler/{}/{}.gemspec'.format(gem_slot_name, dep),
                '/usr/share/{}/.debler/gems/specifications/{}-{}.gemspec'.format(self.app.name, dep, str(version))
            ))
            deb_dep = self.gemnam2deb(gem_slot_name)
            self.load_paths['all'].append('/usr/share/rubygems-debler/{name}/{}/'.format('lib', name=gem_slot_name))
            if native:
                natives.append(deb_dep)
            constraints = self.app.dependencies.get(dep, [])
            if constraints:
                for constraint in constraints:
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
        deps.append(' | '.join([self.deb_name + '-ruby' + ruby for ruby in self.db.rubies]))
        deps.append('${shlibs:Depends}')
        deps.append('${misc:Depends}')

        control['Depends'] = ', '.join(deps)
        control['Section'] = 'ruby'
        control['Description'] = self.app.description.replace('\n', '\n ').replace('\n \n', '\n .\n')

        control_file.write(b'\n')
        control.dump(control_file)

        for ruby in self.db.rubies:
            self.load_paths[ruby + '.0'] = []
            self.installs[ruby + '.0'] = []
            control = Deb822()
            control['Package'] = self.deb_name + '-ruby' + ruby
            control['Architecture'] = 'all'
            deps = ['ruby' + ruby]
            for deb_dep in natives:
                deps.append('{}-ruby{}'.format(deb_dep, ruby))
                self.load_paths[ruby + '.0'].append('/usr/lib/${{DEB_BUILD_MULTIARCH}}/rubygems-debler/{v}.0/{name}/'.format(v=ruby, name=deb_dep))
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
            for ruby in self.db.rubies:
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
            for ruby in self.db.rubies:
                with open(self.debian_file('bin', self.app.name + ruby), 'w') as f:
                    f.write('#!/usr/bin/ruby{}\n'.format(ruby))
                    f.write('Dir.chdir("/usr/share/{}")\n'.format(self.app.name))
                    f.write('ENV[\'HOME\'] = \'/tmp\'\n')  # will be fixed later
                    f.write('File.readlines("/usr/share/{}/.debler/load_paths/all").each do |dir|\n'.format(self.app.name))
                    f.write('  $LOAD_PATH << dir.strip\n')
                    f.write('end\n')
                    f.write('File.readlines("/usr/share/{}/.debler/load_paths/{}.0").each do |dir|\n'.format(self.app.name, ruby))
                    f.write('  $LOAD_PATH << dir.strip\n')
                    f.write('end\n')
                    f.write('load ARGF.argv.shift\n')
                self.installs[ruby + '.0'].append((os.path.join('debian', 'bin', self.app.name + ruby), '/usr/bin'))
                os.chmod(self.debian_file('bin', self.app.name + ruby), 0o755)

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

    def build_orig_tar(self):
        orig_tar = os.path.join(self.slot_dir, '{}_{}.orig.tar.xz'.format(self.deb_name, '.'.join(str(v) for v in self.app.version)))
        if os.path.isfile(orig_tar):
            return
        subprocess.call([
            'tar', '--create',
            '--directory', self.app.basedir,
            '--xz',
            '--file', orig_tar,
            '.'])
