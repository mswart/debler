#!/usr/bin/env python3
import sys
import os
import tempfile
import tarfile
import gzip
import yaml
import subprocess
import shutil
from datetime import datetime
from pprint import pprint
from debian.deb822 import Deb822, Dsc
from debian.changelog import Changelog
from dateutil.tz import tzlocal


def construct_ruby_object(loader, suffix, node):
    return loader.construct_yaml_map(node)

yaml.add_multi_constructor(u"!ruby/object:", construct_ruby_object)

db = yaml.load(open(os.path.realpath(os.path.join(__file__, '..', 'db.yml'))))

gem = sys.argv[1]
version = sys.argv[2]
level = db[gem]['level']
rubies = ['2.2', '2.1']

if not os.path.isdir(gem):
    os.mkdir(gem)
if not os.path.isdir(os.path.join(gem, version)):
    os.mkdir(os.path.join(gem, version))
if not os.path.isfile(os.path.join(gem, version, 'orig.gem')):
    subprocess.check_call(['wget',
                           'https://rubygems.org/downloads/{}-{}.gem'.format(gem, version),
                           '-O', os.path.join(gem, version, 'orig.gem')])
    subprocess.check_call(['xz', '--compress', '--verbose', '--keep', '--best', os.path.join(gem, version, 'orig.gem')])

os.chdir(os.path.join(gem, version))

with tempfile.TemporaryDirectory() as d:
    with tarfile.open(name='orig.gem') as t:
        metadata = gzip.GzipFile(fileobj=t.extractfile('metadata.gz')).read()
        metadata = yaml.load(metadata)
        pprint(metadata)

        version_parts = metadata['version']['version'].split('.')
        own_name = 'debler-rubygem-' + metadata['name']
        if level > 0:
            own_name += '-' + '.'.join(version_parts[:level])
        gem_version = metadata['version']['version']

        orig_tar = '{}_{}.orig.tar.xz'.format(own_name,
                   metadata['version']['version'])
        if not os.path.islink(orig_tar):
            os.symlink('orig.gem.xz', orig_tar)

        os.makedirs(os.path.join(own_name, 'debian', 'source'), exist_ok=True)

        with open(os.path.join(own_name, 'debian', 'source', 'format'), 'w') as f:
            f.write("3.0 (quilt)\n")

        with open(os.path.join(own_name, 'debian', 'compat'), 'w') as f:
            f.write("9\n")

        with open(os.path.join(own_name, 'debian', 'copyright'), 'w') as f:
            f.write(
"""Format: http://dep.debian.net/deps/dep5
Upstream-Name: {}

Files: debian/*
Copyright: 2016 Malte Swart
Licence: See LICENCE file
  [LICENCE TEXT]
""".format(own_name))

        changelog = os.path.join(own_name, 'debian', 'changelog')
        if os.path.isfile(changelog):
            changes = Changelog(file=open(changelog, 'r'))
            deb_version = changes.get_version()
            deb_version.debian_revision = str(int(deb_version.debian_revision) + 1)
            change = 'Rebuild with newer debler'
        else:
            changes = Changelog()
            deb_version = gem_version + '-1'
            change = 'Build with debler'
        changes.new_block(package=own_name, version=deb_version,
                          distributions='trusty', urgency='low',
                          #change='  * ' + change,
                          author='Malte Swart <packages@devtation.de>',
                          date=datetime.now(tz=tzlocal()).strftime('%a, %d %b %Y %H:%M:%S %z'))
        changes.add_change('\n  * ' + change + '\n')
        with open(changelog, 'w') as f:
            changes.write_to_open_file(f)

        build_deps = [
            'debhelper',
        ]
        if len(metadata['extensions']) > 0:
            for ruby in rubies:
                build_deps.append('ruby{}'.format(ruby))
                build_deps.append('ruby{}-dev'.format(ruby))

        if db[metadata['name']].get('builddeps'):
            build_deps.append(db[metadata['name']]['builddeps'])
        control_file = open(os.path.join(own_name, 'debian', 'control'), 'wb')

        dsc = Dsc()
        dsc['Source'] = own_name
        dsc['Priority'] = 'optional'
        dsc['Maintainer'] = 'Malte Swart <mswart@devtation.de>'
        dsc['Homepage'] = metadata['homepage']
        dsc['Standards-Version'] = '3.9.6'
        dsc['Build-Depends'] = ', '.join(build_deps)

        dsc.dump(control_file)

        control_file.write(b'\n')

        control = Deb822()
        control['Package'] = own_name
        if level > 0:
            priovide = []
            priovide.append('debler-rubygem-{}'.format(metadata['name']))
            for l in range(1, level):
                priovide.append('debler-rubygem-{}-{}'.format(metadata['name'], '.'.join(version_parts[:l])))
            control['Provides'] = ', '.join(priovide)
        control['Architecture'] = 'all'
        deps = []
        for dep in metadata['dependencies']:
            if dep['type'] != ':runtime':
                continue
            req = 'debler-rubygem-' + dep['name']
            versioned_deps = False
            for version in dep['version_requirements']['requirements']:
                if version[0] == '>=' and version[1]['version'] == '0':
                    continue
                if version[0] == '~>':
                    deps.append('{} (>= {})'.format(req, version[1]['version']))
                    up = version[1]['version'].split('.')
                    up[-1] = '0'
                    up[-2] = str(int(up[-2]) + 1)
                    deps.append('{} (<= {})'.format(req, '.'.join(up)))
            if not versioned_deps:
                deps.append(req)
        deps.append('${shlibs:Depends}')
        deps.append('${misc:Depends}')
        if len(metadata['extensions']) > 0:
            deps.append(' | '.join([own_name + '-ruby' + ruby for ruby in rubies]))

        control['Depends'] = ', '.join(deps)
        control['Section'] = 'ruby'
        control['Homepage'] = metadata['homepage']
        control['Description'] = metadata['summary']
        control['Description'] += ('\n' + metadata['description']).replace('\n\n', '\n.\n').replace('\n', '\n ')

        control_file.write(b'\n')
        control.dump(control_file)

        if len(metadata['extensions']) > 0:
            for ruby in rubies:
                control = Deb822()
                control['Package'] = own_name + '-ruby' + ruby
                control['Architecture'] = 'any'
                control['Depends'] = '${shlibs:Depends}, ${misc:Depends}'
                control['Section'] = 'ruby'
                control['Description'] = metadata['summary']
                control['Description'] += '\n Native extension for ruby' + ruby
                control_file.write(b'\n')
                control.dump(control_file)
        control_file.close()

        rules = {}
        rules['build'] = []
        rules['build'].append('mkdir src')
        rules['build'].append('tar --extract --verbose --directory src --file data.tar.gz')
        if len(metadata['extensions']) > 0:
            rules['build'].append(' v'.join(['mkdir'] + rubies))
            assert len(metadata['extensions']) == 1
            for ruby in rubies:
                rules['build'].append('cd v{v} && ruby{v} ../src/{}'.format(metadata['extensions'][0], v=ruby))
            for ruby in rubies:
                rules['build'].append('make -C v{v}'.format(v=ruby))

        rules['install'] = []
        if len(metadata['extensions']) > 0:
            for ruby in rubies:
                rules['install'].append(' '.join([
                    'dh_install',
                    '-p{package}',
                    'v{v}/*.so',
                    '/usr/lib/${{DEB_BUILD_MULTIARCH}}/ruby/debler-rubygems/{v}.0/{name}/']).format(
                        v=ruby, name=own_name[15:], package=own_name + '-ruby' + ruby))

        with open(os.path.join(own_name, 'debian', 'rules'), 'w') as f:
            f.write("#!/usr/bin/make -f\n%:\n\tdh $@")
            for target in rules:
                f.write('\noverride_dh_auto_{target}:\n\t'.format(target=target))
                f.write('\n\t'.join(rules[target]))

        with open(os.path.join(own_name, 'debian', own_name + '.install'), 'w') as f:
            with tarfile.open(fileobj=t.extractfile('data.tar.gz')) as dt:
                members = dt.getmembers()
                for member in members:
                    for path in metadata['require_paths']:
                        if member.name.startswith(path):
                            break
                    else:
                        continue
                    f.write('src/{file} /usr/lib/ruby/debler-rubygems/{name}/{dir}\n'.format(
                        name=own_name[15:],
                        file=member.name,
                        dir=os.path.dirname(member.name)))

    os.chdir(own_name)
    subprocess.check_call(['dpkg-source', '-b', '.'])
    os.chdir('..')

    subprocess.check_call(['sbuild', '--dist', 'trusty', '{}_{}.dsc'.format(own_name, deb_version)])
