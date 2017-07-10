from .appinfo import YarnAppInfo
from .appintegrator import YarnAppIntegrator
from ..pkger import Packager


class YarnPackager(Packager):
    wrapped = {
        'appInfo': YarnAppInfo.parse,
        'appIntegrator': YarnAppIntegrator,
    }

    def pkg_info(self, name, autocreate=False):
        try:
            return self.db.pkg_info(self.id, name)
        except ValueError as e:
            if not autocreate:
                raise e
            self.db.register_pkg(self.id, name, {})
            return self.db.pkg_info(self.id, name)

pkgerInfo = YarnPackager
