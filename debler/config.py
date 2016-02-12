import os.path
import yaml

data = yaml.load(open(os.path.expanduser('~/.debler.yml')))

appdir = data['appdir']
gemdir = data['gemdir']
keyid = hex(data['keyid'])
maintainer = data['maintainer']
rubygems = data['rubygems']
rubies = [str(r) for r in data['rubies']]
gem_format = data['gem_format']

del data
