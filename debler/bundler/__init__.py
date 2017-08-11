from ..pkger import Packager
from .appinfo import BundlerAppInfo
from .appintegrator import BundlerAppIntegrator
from .builder import GemBuilder
from .webhook import RubygemsWebHook


class BundlerPackager(Packager):
    wrapped = {
        'appInfo': BundlerAppInfo.parse,
        'appIntegrator': BundlerAppIntegrator,
        'builder': GemBuilder,
        'webhook': RubygemsWebHook,
    }

    def __init__(self, *args, rubies,
                 rubygems: "https://rubygems.org",
                 rubygems_apikey: None):
        super().__init__(*args)
        self.rubies = rubies
        self.rubygems = rubygems
        self.rubygems_apikey = rubygems_apikey

    def gem_info(self, name, autocreate=False):
        try:
            return self.db.pkg_info(self.id, name, self.name2deb(name))
        except ValueError as e:
            if not autocreate:
                raise e
            self.db.register_pkg(self.id, name, {
                'default': {
                    'level': 1,
                    'native': None
                }
            })
            return self.db.pkg_info(self.id, name, self.name2deb(name))

    def name2deb(self, name):
        return 'debler-rubygem-' + name.lower().replace('_', '--')

pkgerInfo = BundlerPackager
