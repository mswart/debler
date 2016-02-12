#!/usr/bin/env python3
import sys
import os.path
import traceback

sys.path.insert(0, os.path.realpath(os.path.join(__file__, '..', '..')))

from debler.db import Database
from debler.gem import GemBuilder, GemVersion
from debler.builder import publish

db = Database()


def header(content, color=33):
    print()
    print('#'*80)
    print('#'*80)
    print("##### \033[1;{}m{:^68}\033[0m #####".format(color, content))
    print('#'*80)
    print('#'*80)


for data in db.scheduled_builds():
    task = '{}:{} in version {}-{}'.format(data[0], GemVersion(data[1]), GemVersion(data[2]), data[3])
    header(task)
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
        header(task, color=32)
    except Exception:
        db.update_build(*data, state='failed')
        header(task, color=31)
        traceback.print_exc()
        if '--fail-fast' in sys.argv:
            break

publish('gem')
