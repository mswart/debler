import json

import psycopg2
from datetime import datetime
from dateutil.tz import tzlocal

from debler.gem import GemVersion
from debler import config


class Database():
    rubygems = 'https://rubygems.org'

    def __init__(self):
        self.conn = psycopg2.connect(config.database)

    def register_gem(self, name, level, native=None):
        c = self.conn.cursor()
        c.execute("""INSERT INTO gems (name, level, native)
             VALUES (%s, %s, %s);""", ('rubygem:' + name, level, native))
        self.conn.commit()

    def create_gem_slot(self, name, slot):
        c = self.conn.cursor()
        c.execute("""INSERT INTO packages (name, slot)
             VALUES (%s, %s);""", ('rubygem:' + name, list(slot)))
        self.conn.commit()

    def gem_info(self, name, autocreate=True):
        c = self.conn.cursor()
        c.execute('SELECT level, opts, native FROM gems WHERE name = %s', ('rubygem:' + name, ))
        result = c.fetchone()
        if result is None:
            if not autocreate:
                return None
            print('Configure {}:'.format(name))
            from urllib.request import urlopen
            url = '{}/api/v1/versions/{}.json'.format(self.rubygems, name)
            data = urlopen(url).read()
            versions = json.loads(data.decode('utf-8'))
            for version in versions:
                print(version['number'] + ' ' + version['created_at'])
            level = int(input('Level (1): ') or '1')
            native = {'t': True, 'f': False, 'n': False, 'y': True, '': None}[input('Native?: ')]
            self.register_gem(name, level, native=native)
            return self.gem_info(name)
        level, opts, native = result
        if type(opts) is str:
            opts = json.loads(opts)
        slots = {}
        c.execute('SELECT slot, metadata FROM packages WHERE name = %s', ('rubygem:' + name, ))
        for slot, metadata in c:
            if type(metadata) is str:
                metadata = json.loads(metadata)
            slots[tuple(slot)] = metadata
        return level, opts, native, slots

    def gem_slot_versions(self, name, slot):
        c = self.conn.cursor()
        c.execute('SELECT DISTINCT version FROM package_versions WHERE name = %s and slot = %s ORDER BY version ASC',
                  ('rubygem:' + name, list(slot)))
        versions = []
        for version in c:
            versions.append(list(version[0]))
        return versions

    def gem_extra(self, name, slot, version, revision):
        c = self.conn.cursor()
        c.execute('SELECT extra FROM package_versions'
                  + ' WHERE name = %s AND slot = %s AND version = %s AND revision = %s',
                  ('rubygem:' + name, slot, version, revision))
        result = c.fetchone()
        if result:
            return result[0]

    def register_npm(self, name):
        c = self.conn.cursor()
        c.execute("""INSERT INTO gems (name, level, native)
                     VALUES (%s, %s, %s);""", ('npm:' + name, 1, False))
        self.conn.commit()

    def create_npm_slot(self, name, slot):
        c = self.conn.cursor()
        c.execute("""INSERT INTO packages (name, slot)
             VALUES (%s, %s);""", ('npm:' + name, list(slot)))
        self.conn.commit()

    def npm_slot_versions(self, name, slot):
        c = self.conn.cursor()
        c.execute('''SELECT version
                     FROM package_versions
                     WHERE name = %s AND slot = %s
                     GROUP BY version
                     ORDER BY version ASC''', ('npm:' + name, list(slot)))
        return tuple(tuple(version[0]) for version in c)

    def npm_info(self, name):
        c = self.conn.cursor()
        c.execute('SELECT opts FROM gems WHERE name = %s', ('npm:' + name, ))
        result = c.fetchone()
        if result is None:
            self.register_npm(name)
            return self.npm_info(name)
        opts = result[0]
        if type(opts) is str:
            opts = json.loads(opts)
        slots = {}
        c.execute('SELECT slot, metadata FROM packages WHERE name = %s', ('npm:' + name, ))
        for slot, metadata in c:
            if type(metadata) is str:
                metadata = json.loads(metadata)
            slots[tuple(slot)] = metadata
        return opts, slots

    def set_gem_opts(self, name, opts):
        c = self.conn.cursor()
        c.execute('UPDATE gems SET opts = %s WHERE name = %s', (json.dumps(opts), 'rubygem:' + name))
        self.conn.commit()

    def set_gem_native(self, name, native):
        c = self.conn.cursor()
        c.execute('UPDATE gems SET native = %s WHERE name = %s', (native, 'rubygem:' + name))
        self.conn.commit()

    def set_gem_slot_metadata(self, name, slot, metadata):
        c = self.conn.cursor()
        c.execute('UPDATE packages SET metadata = %s WHERE name = %s AND slot = %s',
                  (json.dumps(metadata), 'rubygem:' + name, list(slot)))
        self.conn.commit()

    def _iter_builds(self, state):
        c = self.conn.cursor()
        while True:
            c.execute('''SELECT split_part(name, ':', 1), split_part(name, ':', 2), slot, version, revision
                         FROM package_versions
                         WHERE state = %s
                         LIMIT 1''', (state, ))
            pkg = c.fetchone()
            if pkg:
                yield pkg
            else:
                break

    def _dump_builds(self, state):
        c = self.conn.cursor()
        c.execute('''SELECT split_part(name, ':', 1), split_part(name, ':', 2), slot, version, revision
                     FROM package_versions
                     WHERE state = %s''', (state, ))
        for pkg in c:
            yield pkg

    def scheduled_builds(self, all=False):
        yield from (self._dump_builds if all else self._iter_builds)('scheduled')

    def failed_builds(self, all=False):
        yield from (self._dump_builds if all else self._iter_builds)('failed')

    def update_build(self, pkger, name, slot, version, revision, state):
        c = self.conn.cursor()
        c.execute('UPDATE package_versions SET state = %s'
                  + ' WHERE name = %s AND slot = %s AND version = %s AND revision = %s',
                  (state, pkger + ':' + name, slot, version, revision))
        self.conn.commit()

    def create_gem_version(self, name, slot, *, version, revision,
                           format=None, changelog, distribution,
                           extra={}):
        now = datetime.now(tz=tzlocal()).strftime('%Y-%m-%d %H:%M:%S %z')
        c = self.conn.cursor()
        c.execute("""INSERT INTO package_versions (name, slot, version, revision,
                format, scheduled_at, changelog, distribution, extra)
             VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s);""",
                  ('rubygem:' + name, list(slot), version, revision, format or config.gem_format,
                   now, changelog, distribution, json.dumps(extra)))
        self.conn.commit()

    def schedule_npm_version(self, name, slot, *, version, revision,
                             format=None, changelog, distribution):
        now = datetime.now(tz=tzlocal()).strftime('%Y-%m-%d %H:%M:%S %z')
        c = self.conn.cursor()
        c.execute("""INSERT INTO package_versions (name, slot, version, revision,
                format, scheduled_at, changelog, distribution)
             VALUES (%s, %s, %s, %s, %s, %s, %s, %s);""",
                  ('npm:' + name, list(slot), version, revision, format or config.gem_format,
                   now, changelog, distribution))
        self.conn.commit()

    def changelog_entries(self, pkger, name, slot, until_version):
        c = self.conn.cursor()
        c.execute("""SELECT version, revision, scheduled_at, changelog, distribution
            FROM package_versions
            WHERE name=%s AND slot = %s AND version <= %s
            ORDER BY version ASC, revision ASC;""", (pkger + ':' + name, list(slot), list(until_version)))
        for version, revision, scheduled_at, changelog, distribution in c:
            yield (GemVersion(version), revision, scheduled_at, changelog, distribution)

    def gem_format_rebuild(self, changelog):
        c = self.conn.cursor()
        c.execute("""SELECT substring(name from 9), slot, version, revision, dist
            FROM (
                SELECT DISTINCT substring(name from 9), slot,
                    first_value(version) OVER w AS version,
                    first_value(revision) OVER w AS revision,
                    first_value(distribution) OVER w AS dist,
                    first_value(format) over w AS format
                FROM package_versions
                WINDOW w AS (PARTITION BY substring(name from 9), slot ORDER BY version DESC, revision DESC)
            ) AS w
            WHERE format < %s;""", (list(config.gem_format), ))
        for data in c:
            self._gem_rebuild(changelog, *data)

    def gem_rebuild(self, name, message):
        c = self.conn.cursor()
        c.execute("""SELECT gem_name, slot, version, revision, dist
            FROM (
                SELECT DISTINCT substring(name from 9) AS gem_name,
                    slot,
                    first_value(version) OVER w AS version,
                    first_value(revision) OVER w AS revision,
                    first_value(distribution) OVER w AS dist
                FROM package_versions
                WINDOW w AS (PARTITION BY substring(name from 9), slot ORDER BY version DESC, revision DESC)
            ) AS w
            WHERE gem_name = %s""", (name, ))
        for data in c:
            self._gem_rebuild(message, *data)

    def _gem_rebuild(self, message, name, slot, version, revision, dist):
        print('rebuild {}:{} in version {}-{}'.format(
            name, '.'.join(str(s) for s in slot),
            '.'.join(str(v) for v in version), revision + 1))
        self.create_gem_version(
            name, slot,
            version=version, revision=revision + 1,
            changelog=message, distribution=dist)
