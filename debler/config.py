import os.path
import yaml

data = yaml.load(open(os.path.expanduser('~/.debler.yml')))

database = data['database']
appdir = data['appdir']
gemdir = data['gemdir']
npmdir = data['npmdir']
keyid = hex(data['keyid'])
maintainer = data['maintainer']
rubygems = data['rubygems']
rubies = [str(r) for r in data['rubies']]
gem_format = [int(s) for s in str(data['gem_format']).split('.')]
distribution = data['distribution']
gem_package_upload = data['package_uploads']['gem']
app_package_upload = data['package_uploads']['app']
npm_package_upload = data['package_uploads']['npm']

del data
