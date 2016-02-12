#!/usr/bin/env python3
import sys
import os.path

sys.path.insert(0, os.path.realpath(os.path.join(__file__, '..', '..')))

from debler.app import AppInfo, AppBuilder
from debler.builder import publish
from debler.db import Database

db = Database()
app = AppInfo.fromyml(db, sys.argv[1])

app.schedule_gemdeps_builds()

builder = AppBuilder(db, app)
builder.generate()
builder.build()

publish('app')
