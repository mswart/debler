#!/usr/bin/env python3
import sys
import os.path

sys.path.insert(0, os.path.realpath(os.path.join(__file__, '..', '..')))

import debler.db

db = debler.db.Database()

msg = sys.argv[1]

gems = sys.argv[2:]

if gems:
    for gem in gems:
        db.gem_rebuild(gem, msg)
else:
    db.debler_format_rebuild(sys.argv[1])
