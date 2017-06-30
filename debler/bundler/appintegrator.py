import os.path

from debler import config
from ..builder import Dependency, Symlink


class BundlerAppIntegrator():
    def __init__(self, pkger, app, builder):
        self.pkger = pkger
        self.app = app
        self.builder = builder
        self.gem_metadatas = {}
        self.binaries = []
        self.natives = []
        self.load_paths = {'all': []}

    @staticmethod
    def gemnam2deb(name):
        return 'debler-rubygem-' + name.replace('_', '--')

    def generate_control_file(self):
        deb_name = self.builder.deb_name
        for name, gem in self.app.gems.items():
            if not gem.version:  # included by path
                assert gem.path is not None, 'gem "{!s}" does not have any ' \
                    'version, but no path: {!r}!'.format(gem.name, gem)
                self.load_paths['all'].append('/usr/share/{name}/{path}/{}'.format('lib', name=self.app.name, path=gem.path))
                self.installs['all'].append((gem.path, '/usr/share/{name}/{path}'.format('lib', name=self.app.name, path=os.path.dirname(gem.path))))
                continue
            info = self.pkger.gem_info(name)
            if info.get('buildgem', False):
                # not needed during runtime
                continue
            slot = info.slot_for_version(gem.version)
            self.gem_metadatas[name] = slot.metadata
            gem_slot_name = '{name}-{slot}'.format(name=name, slot=slot.version)
            yield Symlink(
                deb_name,
                '/usr/share/rubygems-debler/{}/{}.gemspec'.format(gem_slot_name, name),
                '/usr/share/{}/.debler/gems/specifications/{}-{}.gemspec'.format(self.app.name, name, str(gem.version))
            )
            deb_dep = self.gemnam2deb(gem_slot_name)
            for path in slot.metadata.get('require_paths', []):
                self.load_paths['all'].append('/usr/share/rubygems-debler/{name}/{}/'.format(path, name=gem_slot_name))
            for binary in slot.metadata.get('binaries', []):
                self.binaries.append((binary.split('/', 1)[1],
                                      os.path.join('/usr/share/rubygems-debler', gem_slot_name, binary),
                                      slot.metadata.get('require', [])))
            if info.native:
                self.natives.append((deb_dep, gem_slot_name))
            if gem.revision:
                yield Dependency(deb_name, self.gemnam2deb(name) + '-' + gem.revision)
            elif gem.constraints:
                for constraint in gem.constraints:
                    if ' ' not in constraint:
                        constraint = '= ' + constraint
                    op, vers = constraint.split(' ')
                    if op == '~>':
                        up = vers.split('.')
                        yield Dependency(deb_name, '{} (>= {})'.format(deb_dep, vers))
                        if len(up) > info.level:
                            up[-1] = '0'
                            up[-2] = str(int(up[-2]) + 1)
                            yield Dependency(deb_name, '{} (<= {})'.format(deb_dep, '.'.join(up)))
                    else:
                        yield Dependency(deb_name, '{} ({} {})'.format(deb_dep, {'=': '>=', '>': '>='}.get(op, op), vers))
            else:
                yield Dependency(deb_name, deb_dep)
        yield Dependency(deb_name, ' | '.join([deb_name + '-ruby' + ruby for ruby in config.rubies]))
