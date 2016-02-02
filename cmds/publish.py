#!/usr/bin/env python3
import sys
import os.path

sys.path.insert(0, os.path.realpath(os.path.join(__file__, '..', '..')))

from debler import gem2dsc

gem2dsc.publish()
