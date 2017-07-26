import pytest

from debler.yarn.lock import YarnLockParser


def test_error_on_empty_file():
    with pytest.raises(ValueError):
        YarnLockParser('')
