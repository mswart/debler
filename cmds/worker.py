#!/usr/bin/env python3
import sys
import os.path

sys.path.insert(0, os.path.realpath(os.path.join(__file__, '..', '..')))

from debler import gem2dsc
import debler.db

db = debler.db.Database()

for data in db.scheduled_builds():
    try:
        db.update_build(*data, state='generating')
        conv = gem2dsc.Converter(db, *data)
        conv.create_dirs()
        conv.fetch_source()
        conv.build_orig_tar()
        conv.gen_debian_files()
        db.update_build(*data, state='building')
        conv.build()
        db.update_build(*data, state='finished')
    except Exception as e:
        db.update_build(*data, state='failed')
        print(e)
    #finally:
        #break

gem2dsc.publish()
