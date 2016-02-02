#!/usr/bin/env python3
import sys
import os.path

sys.path.insert(0, os.path.realpath(os.path.join(__file__, '..', '..')))

import debler.db

db = debler.db.Database()

db.debler_format_rebuild(sys.argv[1])
