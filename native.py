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
from dateutil.tz import tzlocal


def construct_ruby_object(loader, suffix, node):
    return loader.construct_yaml_map(node)

yaml.add_multi_constructor(u"!ruby/object:", construct_ruby_object)

db = {
    'pg': 'libpq-dev'
}


gem = sys.argv[1]
version = sys.argv[2]
level = int(sys.argv[3])
rubies = ['2.2', '2.1']

if not os.path.isdir(gem):
    os.mkdir(gem)
if not os.path.isfile(os.path.join(gem, version + '.gem')):
    subprocess.check_call(['wget',
                           'https://rubygems.org/downloads/{}-{}.gem'.format(gem, version),
                           '-O', os.path.join(gem, version + '.gem')])

with tempfile.TemporaryDirectory() as d:
    with tarfile.open(name=os.path.join(gem, version + '.gem')) as t:
        metadata = gzip.GzipFile(fileobj=t.extractfile('metadata.gz')).read()
        metadata = yaml.load(metadata)
        pprint(metadata)

        version_parts = metadata['version']['version'].split('.')
        own_name = 'debler-rubygem-' + metadata['name']
        if level > 0:
            own_name += '-' + '.'.join(version_parts[:level])
        own_version = metadata['version']['version'] + '-1'
        shutil.copyfile(os.path.join(gem, version + '.gem'),
                        os.path.join(d, '{}_{}.orig.tar'.format(
                            own_name, metadata['version']['version'])))
        os.makedirs(os.path.join(d, own_name, 'debian', 'source'))

        with open(os.path.join(d, own_name, 'debian', 'source', 'format'), 'w') as f:
            f.write("3.0 (quilt)\n")

        with open(os.path.join(d, own_name, 'debian', 'compat'), 'w') as f:
            f.write("9\n")

        with open(os.path.join(d, own_name, 'debian', 'copyright'), 'w') as f:
            f.write(
"""Format: http://dep.debian.net/deps/dep5
Upstream-Name: {}

Files: debian/*
Copyright: 2016 Malte Swart
Licence: See LICENCE file
  [LICENCE TEXT]
""".format(own_name))

        with open(os.path.join(d, own_name, 'debian', 'changelog'), 'w') as f:
            f.write(
"""{} ({}) {}; urgency=low

  * Build with debler

 -- Malte Swart <packages@devtation.de>  {}
""".format(own_name, own_version, 'trusty', datetime.now(tz=tzlocal()).strftime('%a, %d %b %Y %H:%M:%S %z')))

        build_deps = [
            'debhelper',
            'python3',
            'python3-yaml',
        ]
        for ruby in rubies:
            build_deps.append('ruby{}'.format(ruby))
            build_deps.append('ruby{}-dev'.format(ruby))

        if metadata['name'] in db:
            build_deps.append(db[metadata['name']])
        control_file = open(os.path.join(d, own_name, 'debian', 'control'), 'wb')

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
        deps.append(' | '.join([own_name + '-ruby' + ruby for ruby in rubies]))

        control['Depends'] = ', '.join(deps)
        control['Section'] = 'ruby'
        control['Homepage'] = metadata['homepage']
        control['Description'] = metadata['summary']
        control['Description'] += ('\n' + metadata['description']).replace('\n\n', '\n.\n').replace('\n', '\n ')

        control_file.write(b'\n')
        control.dump(control_file)

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
        rules['build'].append(' v'.join(['mkdir'] + rubies))
        assert len(metadata['extensions']) == 1
        for ruby in rubies:
            rules['build'].append('cd v{v} && ruby{v} ../src/{}'.format(metadata['extensions'][0], v=ruby))
        for ruby in rubies:
            rules['build'].append('make -C v{v}'.format(v=ruby))

        rules['install'] = []
        for ruby in rubies:
            rules['install'].append(' '.join([
                'dh_install',
                '-p{package}',
                'v{v}/*.so',
                '/usr/lib/${{DEB_BUILD_MULTIARCH}}/ruby/debler-rubygems/{name}/{v}.0/']).format(
                    v=ruby, name=own_name[15:], package=own_name + '-ruby' + ruby))

        with open(os.path.join(d, own_name, 'debian', 'rules'), 'w') as f:
            f.write("#!/usr/bin/make -f\n%:\n\tdh $@")
            for target in rules:
                f.write('\noverride_dh_auto_{target}:\n\t'.format(target=target))
                f.write('\n\t'.join(rules[target]))

        subprocess.check_call(['gzip', '-1', os.path.join(d, '{}_{}.orig.tar'.format(
                               own_name, metadata['version']['version']))])

        os.makedirs(os.path.join(d, 'usr', 'lib', 'ruby', 'debler-rubygems', control['Package'][15:]))
        with open(os.path.join(d, own_name, 'debian', own_name + '.install'), 'w') as f:
            with tarfile.open(fileobj=t.extractfile('data.tar.gz')) as dt:
                members = dt.getmembers()
                for member in members:
                    for path in metadata['require_paths']:
                        if member.name.startswith(path):
                            break
                    else:
                        continue
                    f.write('src/{file} /usr/lib/ruby/debler-rubygems/{name}/{dir}\n'.format(
                        name=control['Package'][15:],
                        file=member.name,
                        dir=os.path.dirname(member.name)))

    os.chdir(os.path.join(d, own_name))

    subprocess.call(['find', '.'])
    subprocess.call(['cat', 'debian/control'])
    subprocess.call(['cat', 'debian/changelog'])
    subprocess.call(['cat', 'debian/{}.install'.format(own_name)])
    subprocess.call(['cat', 'debian/rules'])
    subprocess.check_call(['dpkg-source', '-b', '.'])

    os.chdir(os.path.join(d))
    subprocess.check_call(['sbuild', '--dist', 'trusty', '{}_{}.dsc'.format(own_name, own_version)])
