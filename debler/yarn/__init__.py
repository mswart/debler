from ..pkger import Packager

from .appinfo import YarnAppInfo
from .appintegrator import YarnAppIntegrator
from .builder import YarnBuilder


class YarnPackager(Packager):
    wrapped = {
        'appInfo': YarnAppInfo.parse,
        'appIntegrator': YarnAppIntegrator,
        'builder': YarnBuilder,
    }

    def pkg_info(self, name, autocreate=False):
        try:
            return self.db.pkg_info(self.id, name, self.name2deb(name))
        except ValueError as e:
            if not autocreate:
                raise e
            self.db.register_pkg(self.id, name, {})
            return self.db.pkg_info(self.id, name, self.name2deb(name))

    def name2deb(self, name):
        return 'debler-yarn-' + name.lower().replace('_', '--')

pkgerInfo = YarnPackager
