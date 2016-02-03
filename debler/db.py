import json

import psycopg2
from datetime import datetime
from dateutil.tz import tzlocal


class Database():
    current_debler_version = [1, 2]

    rubies = ('2.2', '2.1')

    def __init__(self):
        self.conn = psycopg2.connect('dbname=debler')

    def register_gem(self, name, level, builddeps=None):
        if builddeps is None:
            builddeps = '{}'
        else:
            builddeps = '{"default": ["%s"]}' % builddeps
        c = self.conn.cursor()
        c.execute("""INSERT INTO gems (name, level, builddeps)
             VALUES (%s, %s, %s);""", (name, level, builddeps))
        self.conn.commit()

    def create_gem_slot(self, name, slot):
        c = self.conn.cursor()
        c.execute("""INSERT INTO packages (name, slot)
             VALUES (%s, %s);""", (name, list(slot)))
        self.conn.commit()

    def gem_info(self, name):
        c = self.conn.cursor()
        c.execute('SELECT level, builddeps, native FROM gems WHERE name = %s', (name, ))
        level, builddeps, native = c.fetchone()
        builddeps = json.loads(builddeps)
        slots = []
        c.execute('SELECT slot FROM packages WHERE name = %s', (name, ))
        for slot in c:
            slots.append(tuple(slot[0]))
        return level, builddeps, native, slots

    def scheduled_builds(self):
        c = self.conn.cursor()
        c.execute('SELECT name, slot, version, revision FROM package_versions WHERE state = %s', ('scheduled', ))
        for pkg in c:
            print(pkg)
            yield pkg

    def update_build(self, name, slot, version, revision, state):
        c = self.conn.cursor()
        c.execute('UPDATE package_versions SET state = %s'
                  + ' WHERE name = %s AND slot = %s AND version = %s AND revision = %s',
                  (state, name, slot, version, revision))
        self.conn.commit()

    def create_gem_version(self, name, slot, *, version, revision,
                           debler_version=None, changelog, distribution):
        now = datetime.now(tz=tzlocal()).strftime('%Y-%m-%d %H:%M:%S %z')
        c = self.conn.cursor()
        c.execute("""INSERT INTO package_versions (name, slot, version, revision,
                debler_version, scheduled_at, changelog, distribution)
             VALUES (%s, %s, %s, %s, %s, %s, %s, %s);""",
                  (name, list(slot), version, revision, debler_version or self.current_debler_version,
                   now, changelog, distribution))
        self.conn.commit()

    def changelog_entries(self, name, slot):
        c = self.conn.cursor()
        c.execute("""SELECT version, revision, scheduled_at, changelog, distribution
            FROM package_versions
            WHERE name=%s and slot = %s
            ORDER BY version ASC, revision ASC;""", (name, list(slot)))
        for entry in c:
            yield entry

    def debler_format_rebuild(self, changelog):
        c = self.conn.cursor()
        c.execute("""SELECT name, slot, version, revision, dist
            FROM (
                SELECT DISTINCT name, slot,
                    first_value(version) OVER w AS version,
                    first_value(revision) OVER w AS revision,
                    first_value(distribution) OVER w AS dist,
                    first_value(debler_version) over w AS debler
                FROM package_versions
                WINDOW w AS (PARTITION BY name, slot ORDER BY version DESC, revision DESC)
            ) AS w
            WHERE debler < %s;""", (list(self.current_debler_version), ))
        for name, slot, version, revision, dist in c:
            self.create_gem_version(
                name, slot,
                version=version, revision=revision + 1,
                changelog=changelog, distribution=dist)
