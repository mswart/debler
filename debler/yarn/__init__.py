import functools

from .appinfo import YarnAppInfo
from .appintegrator import YarnAppIntegrator
from ..pkger import Packager


class YarnPackager(Packager):
    wrapped = {
      'appInfo': YarnAppInfo.parse,
      'appIntegrator': YarnAppIntegrator,
    }

    def __getattr__(self, name):
        if name in self.wrapped:
            return functools.partial(self.wrapped[name], self)

pkgerInfo = YarnPackager
