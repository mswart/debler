#!/usr/bin/env python3
import sys
import os.path

sys.path.insert(0, os.path.realpath(os.path.join(__file__, '..', '..')))

from debler import gemfile
import debler.db

app_name = sys.argv[1]
app_deps = gemfile.Parser(open(sys.argv[2]))
db = debler.db.Database()

print(app_name)
for dep, version in app_deps.dependencies.items():
    version = [int(v) for v in version.split('.')]
    level, builddeps, slots = db.gem_info(dep)
    slot = tuple(version[:level])
    if slot not in slots:
        db.create_gem_slot(dep, slot)
        db.create_gem_version(
            dep, slot,
            version=version, revision=1,
            changelog='Import newly into debler', distribution='trusty')
    else:
        db
