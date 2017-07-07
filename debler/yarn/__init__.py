import functools

from .appinfo import YarnAppInfo
from .appintegrator import YarnAppIntegrator
from ..pkger import Packager


class YarnPackager(Packager):
    wrapped = {
      'appInfo': YarnAppInfo.parse,
      'appIntegrator': YarnAppIntegrator,
    }

pkgerInfo = YarnPackager
