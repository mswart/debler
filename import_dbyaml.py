#!/usr/bin/env python3
import sys
import os.path
import yaml

sys.path.insert(0, os.path.realpath(os.path.join(__file__, '..')))

from debler.db import Database


yamldb = yaml.load(open(os.path.realpath(os.path.join(__file__, '..', 'db.yml'))))

db = Database()
for gem, data in yamldb.items():
    db.register_gem(gem, data['level'], data.get('builddeps', None))
