#!/usr/bin/env python3
import sys
import os
import tempfile
import tarfile
import gzip
import yaml
import subprocess
from pprint import pprint
from debian.deb822 import Deb822


def construct_ruby_object(loader, suffix, node):
    return loader.construct_yaml_map(node)

yaml.add_multi_constructor(u"!ruby/object:", construct_ruby_object)


gem = sys.argv[1]
version = sys.argv[2]
level = int(sys.argv[3])

if not os.path.isdir(gem):
    os.mkdir(gem)
if not os.path.isfile(os.path.join(gem, version + '.gem')):
    subprocess.check_call(['wget',
                     'https://rubygems.org/downloads/{}-{}.gem'.format(gem, version),
                     '-O', os.path.join(gem, version + '.gem')])

with tempfile.TemporaryDirectory() as d:
    with tarfile.open(name=os.path.join(gem, version + '.gem')) as t:
        os.mkdir(os.path.join(d, 'DEBIAN'))
        metadata = gzip.GzipFile(fileobj=t.extractfile('metadata.gz')).read()
        metadata = yaml.load(metadata)
        pprint(metadata)
        control = Deb822()
        version_parts = metadata['version']['version'].split('.')
        control['Package'] = 'debler-rubygem-' + metadata['name']
        if level > 0:
            control['Package'] += '-' + '.'.join(version_parts[:level])
            priovide = []
            priovide.append('debler-rubygem-{}'.format(metadata['name']))
            for l in range(1, level):
                priovide.append('debler-rubygem-{}-{}'.format(metadata['name'], '.'.join(version_parts[:l])))
            control['Provide'] = ', '.join(priovide)
        control['Version'] = metadata['version']['version']
        control['Architecture'] = 'all'
        control['Maintainer'] = ', '.join(['{} <{}>'.format(*p) for p in zip(metadata['authors'], metadata['email'])])
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
        control['Depends'] = ', '.join(deps)
        control['Section'] = 'ruby'
        control['Priority'] = 'optional'
        control['Homepage'] = metadata['homepage']
        control['Description'] = metadata['summary']
        control['Description'] += ('\n' + metadata['description']).replace('\n\n', '\n.\n').replace('\n', '\n ')

        control.dump(open(os.path.join(d, 'DEBIAN', 'control'), 'wb'))
        os.makedirs(os.path.join(d, 'usr', 'lib', 'ruby', 'debler-rubygems', control['Package'][15:]))
        with tarfile.open(fileobj=t.extractfile('data.tar.gz')) as dt:
            members = dt.getmembers()
            for path in metadata['require_paths']:
                our_members = filter(lambda v: v.name.startswith(path), members)
                dt.extractall(
                    path=os.path.join(d, 'usr', 'lib', 'ruby', 'debler-rubygems', control['Package'][15:]),
                    members=our_members)

        subprocess.call(['find', d])
        subprocess.call(['cat', os.path.join(d, 'DEBIAN', 'control')])
        subprocess.call(['dpkg-deb', '--build', str(d), control['Package'] + '_' + control['Version'] + '_all.deb'])
