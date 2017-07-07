import json

from ..pkger import Packager
from .appinfo import BundlerAppInfo
from .appintegrator import BundlerAppIntegrator
from .builder import GemBuilder


class BundlerPackager(Packager):
    wrapped = {
      'appInfo': BundlerAppInfo.parse,
      'appIntegrator': BundlerAppIntegrator,
      'builder': GemBuilder,
    }

    def gem_info(self, name, autocreate=False):
        try:
            return self.db.pkg_info(self.id, name)
        except ValueError as e:
            if not autocreate:
                raise e
            print('Configure {}:'.format(name))
            from urllib.request import urlopen
            url = 'https://rubygems.org/api/v1/versions/{}.json'.format(name)
            data = urlopen(url).read()
            versions = json.loads(data.decode('utf-8'))
            for version in versions:
                print(version['number'] + ' ' + version['created_at'])
            level = int(input('Level (1): ') or '1')
            native = {
                't': True,
                'f': False,
                'n': False,
                'y': True,
                '': None}[input('Native?: ')]
            self.db.register_pkg(self.id, name, {
                'default': {
                    'level': level,
                    'native': native
                }
            })
            return self.db.pkg_info(self.id, name)

pkgerInfo = BundlerPackager
