import os.path
import yaml

data = yaml.load(open(os.path.expanduser('~/.debler.yml')))

workdir = data['workdir']
keyid = hex(data['keyid'])
maintainer = data['maintainer']
rubygems = data['rubygems']

del data
