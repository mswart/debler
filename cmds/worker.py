#!/usr/bin/env python3
import sys
import os.path

sys.path.insert(0, os.path.realpath(os.path.join(__file__, '..', '..')))

from debler.builder import GemBuilder, publish
from debler.db import Database

db = Database()

for data in db.scheduled_builds():
    try:
        db.update_build(*data, state='generating')
        conv = GemBuilder(db, *data)
        conv.create_dirs()
        conv.fetch_source()
        conv.build_orig_tar()
        conv.gen_debian_files()
        db.update_build(*data, state='building')
        conv.build()
        db.update_build(*data, state='finished')
    except Exception as e:
        db.update_build(*data, state='failed')
        raise

    #finally:
        #break

publish()
