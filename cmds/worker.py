#!/usr/bin/env python3
import sys
import os.path

sys.path.insert(0, os.path.realpath(os.path.join(__file__, '..', '..')))

from debler import gem2dsc
import debler.db

db = debler.db.Database()

for data in db.scheduled_builds():
    #try:
        conv = gem2dsc.Converter(db, *data)
        conv.create_dirs()
        conv.fetch_source()
        conv.build_orig_tar()
        conv.gen_debian_files()
        conv.build()
    #except Exception as e:
    #    print(e)
    #finally:
        #break
