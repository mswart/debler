import os.path

from ..builder import Package, Dependency, \
    Install, Symlink, \
    InstallContent, DebianContent, \
    RuleAction


class BundlerAppIntegrator():
    def __init__(self, pkger, app, builder):
        self.pkger = pkger
        self.app = app
        self.builder = builder
        self.gem_metadatas = {}
        self.binaries = []
        self.natives = []
        self.load_paths = {'all': (self.builder.deb_name, [])}

    @staticmethod
    def gemnam2deb(name):
        return 'debler-rubygem-' + name.replace('_', '--')

    @property
    def rubies(self):
        for ruby in self.pkger.rubies:
            yield self.builder.deb_name + '-ruby' + ruby, ruby

    def generate_control_content(self):
        deb_name = self.builder.deb_name
        for name, gem in self.app.gems.items():
            if not gem.version:  # included by path
                assert gem.path is not None, 'gem "{!s}" does not have any ' \
                    'version, but no path: {!r}!'.format(gem.name, gem)
                continue
            info = self.pkger.gem_info(name)
            if info.get('buildgem', False):
                # not needed during runtime
                continue
            slot = info.slot_for_version(gem.version)
            self.gem_metadatas[name] = slot.metadata
            gem_slot_name = '{}-{}'.format(name, slot.version)
            yield Symlink(
                deb_name,
                '/usr/share/rubygems-debler/{}/{}.gemspec'.format(gem_slot_name, name),
                '/usr/share/{}/.debler/gems/specifications/{}-{}.gemspec'.format(self.app.name, name, str(gem.version))
            )
            deb_dep = self.gemnam2deb(gem_slot_name)
            for path in slot.metadata.get('require_paths', []):
                self.load_paths['all'][1].append(
                    '/usr/share/rubygems-debler/{name}/{}/'.format(
                        path, name=gem_slot_name))
            for binary in slot.metadata.get('binaries', []):
                self.binaries.append((binary.split('/', 1)[1],
                                      os.path.join(
                                          '/usr/share/rubygems-debler',
                                          gem_slot_name, binary),
                                      slot.metadata.get('require', [])))
            if info.native:
                self.natives.append((deb_dep, gem_slot_name))
            if gem.revision:
                yield Dependency(deb_name,
                                 self.gemnam2deb(name) + '-' + gem.revision)
            elif gem.constraints:
                for constraint in gem.constraints:
                    if ' ' not in constraint:
                        constraint = '= ' + constraint
                    op, vers = constraint.split(' ')
                    if op == '~>':
                        up = vers.split('.')
                        yield Dependency(deb_name,
                                         '{} (>= {})'.format(deb_dep, vers))
                        if len(up) > info.level:
                            up[-1] = '0'
                            up[-2] = str(int(up[-2]) + 1)
                            yield Dependency(
                                deb_name,
                                '{} (<= {})'.format(deb_dep, '.'.join(up)))
                    else:
                        yield Dependency(
                            deb_name,
                            '{} ({} {})'.format(
                                deb_dep,
                                {'=': '>=', '>': '>='}.get(op, op), vers))
            else:
                yield Dependency(deb_name, deb_dep)
        yield Dependency(deb_name, ' | '.join([
            deb_name + '-ruby' + ruby for ruby in self.pkger.rubies]))

        for deb, ruby in self.rubies:
            self.load_paths[ruby + '.0'] = (deb, [])
            yield Package(
                package=deb,
                architecture='all',
                section='ruby',
                description=self.app.app.description.split('\n')[0] +
                ' - ruby {}'.format(ruby) +
                '\n Needed dependencies and executables for Ruby' + ruby
            )
            yield Dependency(deb, 'ruby' + ruby)
            for deb_dep, gem_slot_name in self.natives:
                yield Dependency(deb, '{}-ruby{}'.format(deb_dep, ruby))
                self.load_paths[ruby + '.0'][1].append(
                    '/usr/lib/ARCH/rubygems-debler/''{v}.0/{name}/'.format(
                        v=ruby, name=gem_slot_name))
            yield Dependency(deb, '${shlibs:Depends}')
            yield Dependency(deb, '${misc:Depends}')

    def generate_rules_content(self):
        for name, gem in self.app.gems.items():
            if not gem.version:  # included by path
                self.load_paths['all'][1].append(
                    '/usr/share/{name}/{path}/{}'.format('lib',
                                                         name=self.app.name,
                                                         path=gem.path))
                yield Install(self.builder.deb_name, gem.path,
                              '/usr/share/{name}/{path}'.format(
                                  'lib',
                                  name=self.app.name,
                                  path=os.path.dirname(gem.path)))
        for version in self.load_paths:
            if version == 'all':
                continue
            yield RuleAction('build', [
                'sed',
                '--in-place',
                '--expression=s:/ARCH/:/${DEB_BUILD_MULTIARCH}/:',
                'debian/data/{}'.format(version)])

        for version, (deb, paths) in self.load_paths.items():
            yield InstallContent(
                deb,
                name=os.path.join('data', version),
                dest='/usr/share/{}/.debler/load_paths/'.format(self.app.name),
                mode=0o755,
                content='\n'.join(paths) + '\n'
            )

        if self.app.bundler_laucher:
            for deb, ruby in self.rubies:
                yield InstallContent(
                    deb,
                    name='bin/' + self.app.name + ruby,
                    dest='/usr/bin',
                    mode=0o755,
                    content='''#!/usr/bin/ruby{ruby}\n
Dir.chdir("/usr/share/{name}")
ENV['HOME'] = '/tmp'  # will be fixed later
ENV['RAILS_ENV'] ||= '{default_env}'
ENV['GEM_PATH'] = '/usr/share/{name}/.debler/gems'
$LOAD_PATH << '/usr/share/{name}/.debler/lib'
File.readlines("/usr/share/{name}/.debler/load_paths/all").each do |dir|
  $LOAD_PATH << dir.strip
end
File.readlines("/usr/share/{name}/.debler/load_paths/{ruby}.0").each do |dir|
  $LOAD_PATH << dir.strip
end
require "bundler"
exe = ARGF.argv.shift
if File.exist? exe
  load exe
else
  binaries = {{
{binaries}
  }}
  if binaries.key? exe
    binaries[exe][1].each do |torequire|
      require torequire
    end
    load binaries[exe][0]
  end
end
'''.format(
                        ruby=ruby,
                        name=self.app.name,
                        default_env=self.app.default_env,
                        binaries='\n'.join([
                            '''    '{}' => ["{}", ["{}"]],'''.format(
                                exe, path, '", "'.join(requires))
                            for exe, path, requires in self.binaries
                        ]))
                )

                yield DebianContent(
                    name='{}-ruby{}.postinst'.format(self.app.name, ruby),
                    mode=0o755,
                    content='''#!/bin/sh
set -e

update-alternatives --install /usr/bin/{app} {app} /usr/bin/{app}{ruby} {prio}

#DEBHELPER#

exit 0
'''.format(
                        app=self.app.name,
                        ruby=ruby,
                        prio='9' + ruby.replace('.', '')))

                yield DebianContent(
                    name='{}-ruby{}.prerm'.format(self.app.name, ruby),
                    mode=0o755,
                    content='''#!/bin/sh
set -e

case "$1" in
  remove|deconfigure)
    update-alternatives --remove {app} /usr/bin/{app}{ruby}
    ;;

  upgrade|failed-upgrade)
    ;;

  *)
    echo "prerm called with unknown argument `$1'" >&2
    exit 0
    ;;

esac

#DEBHELPER#

exit 0
'''.format(app=self.app.name, ruby=ruby))

            yield Install(self.builder.deb_name,
                          os.path.join('debian', 'lib'),
                          '/usr/share/{}/.debler'.format(self.app.name))

            yield DebianContent(
                name='lib/bundler/setup.rb',
                mode=0o755,
                content='require "bundler"\n',
            )

            bundler_content = '''class Bundler
  def self.require(*groups)
    groups = groups.map(&:to_s)
'''
            for name in self.app.gemfile.sorted_gems:
                gem = self.app.gemfile.gems[name]
                if not gem.require:
                    continue
                if gem.require is not True:  # specific require!
                    bundler_content += '    Kernel.require "{}"\n'.format(
                        gem.require)
                    continue
                for require in self.gem_metadatas.get(
                        name, {'require': [name.replace('-', '/')]}) \
                        .get('require', []):
                    if 'default' in gem.envs:
                        bundler_content += '    Kernel.require "{}"\n' \
                            .format(require)
                    else:
                        bundler_content += '    Kernel.require "{}"'
                        ' unless (groups & ["{}"]).empty?\n'.format(
                            require, '", "'.join(gem.envs))
            bundler_content += '''  end

  def self.setup(*args)
  end
  def self.with_clean_env
    yield
  end
end
'''

            yield DebianContent(
                name='lib/bundler.rb',
                mode=0o755,
                content=bundler_content)
