from datetime import datetime
from importlib import import_module
import json

from debian import debian_support
from dateutil.tz import tzlocal
import psycopg2

from debler.gem import GemVersion
from debler import config


class Version(debian_support.Version):
    pass


class PkgInfo():
    def __init__(self, db, id, name, opts, slots):
        self.db = db
        self.id = id
        self.name = name
        self.opts = opts
        self.slots = slots

    def lookup(self, name, default):
        return self.opts.get('default', {}).get(name, default)

    def get(self, name, default=None):
        return self.lookup(name, default=default)

    def __getattr__(self, name):
        return self.lookup(name, default=None)

    def slot_for_version(self, version, create=False):
        parts = str(version).split('.')
        for slot in self.slots:
            slot_parts = str(slot.version).split('.')
            for pos, slot_part in enumerate(slot_parts):
                if parts[pos] != slot_part:
                    break
            else:
                return slot
        if not create:
            raise ValueError('No slot for version "{}" ({!r})'.format(
                             version, self))
        slot = self.db.create_pkg_slot(self, '.'.join(parts[:self.level]))
        self.slots.append(slot)
        return slot

    def __repr__(self):
        return 'PkgInfo({}, {}, {!r}, {!r})'.format(
            self.id, self.name, self.opts, self.slots)


class SlotInfo():
    def __init__(self, db, pkg, id, version, config, metadata):
        self.db = db
        self.pkg = pkg
        self.id = id
        self.version = Version(version)
        self.config = config
        self.metadata = metadata

    def __repr__(self):
        return 'SlotInfo({!r}, {}, {!r}, {!r}, {!r})'.format(
            self.pkg, self.id, self.version, self.config, self.metadata)

    def versions(self):
        return self.db.get_versions(self)

    def create(self, **kwargs):
        return self.db.schedule_build(self, **kwargs)


class VersionInfo():
    def __init__(self, db, slot, id, version, config, metadata, populated):
        self.db = db
        self.slot = slot
        self.id = id
        self.version = Version(version)
        self.config = config
        self.metadata = metadata
        self.populated = populated

    def __repr__(self):
        return 'VersionInfo({!r}, {}, {!r}, {!r}, {!r})'.format(
            self.slot, self.id, self.version, self.config, self.metadata)


class Database():
    rubygems = 'https://rubygems.org'

    def __init__(self):
        self.conn = psycopg2.connect(config.database)
        self.conn.autocommit = True

    def get_pkger(self, name):
        c = self.conn.cursor()
        c.execute('SELECT id, config FROM packager WHERE name = %s',
                  (name,))
        result = c.fetchone()
        if not result:
            raise NotImplementedError('packager "{}" is not defined'
                                      .format(name))
        impl = import_module(result[1].pop('module'))
        return getattr(impl, 'pkgerInfo')(self, result[0], **result[1])

    def register_pkg(self, pkger_id, name, config):
        c = self.conn.cursor()
        c.execute("""INSERT INTO packages (pkger_id, name, config)
             VALUES (%s, %s, %s);""", (pkger_id, name, json.dumps(config)))
        self.conn.commit()

    def pkg_info(self, pkger_id, name, klass=PkgInfo, slotklass=SlotInfo):
        c = self.conn.cursor()
        c.execute('SELECT id, config FROM packages '
                  'WHERE pkger_id = %s AND name = %s',
                  (pkger_id, name))
        result = c.fetchone()
        if not result:
            raise ValueError('Pkg "{}" unknown in pkger {}'.format(
                    name, pkger_id))
            return None
        pkg_id, config = result

        c.execute('SELECT id, version, config, metadata FROM slots '
                  'WHERE pkg_id = %s ORDER BY version', (pkg_id,))
        slots = []
        pkg = klass(self, pkg_id, name, config, slots)
        for row in c.fetchall():
            slots.append(slotklass(self, pkg, *row))
        return pkg

    def create_pkg_slot(self, pkg, slot):
        c = self.conn.cursor()
        c.execute("""INSERT INTO slots (pkg_id, version) VALUES (%s, %s)
                  RETURNING (id, version, config, metadata);""",
                  (pkg.id, slot))
        row = c.fetchone()
        self.conn.commit()
        return SlotInfo(self, pkg, *row)

    def get_versions(self, slot):
        c = self.conn.cursor()
        c.execute('''SELECT id, version, config, metadata, populated
                     FROM versions
                     WHERE slot_id = %s
                     ORDER BY version ASC''',
                  (slot.id, ))
        versions = []
        for row in c:
            versions.append(VersionInfo(self, slot, *row))
        return versions

    def schedule_build(self, slot, *, version, revision,
                       format=None, changelog, distribution,
                       extra={}):
        now = datetime.now(tz=tzlocal()).strftime('%Y-%m-%d %H:%M:%S %z')
        c = self.conn.cursor()
        c.execute("""INSERT INTO versions
                        (slot_id, version, config, populated, created_at)
                     VALUES (%s, %s, %s, %s, %s)
                     RETURNING (id);""",
                  (slot.id, version, json.dumps(extra), False, now))
        result = c.fetchone()
        c.execute("""SELECT id FROM distributions
                     WHERE name = %s""", (distribution, ))
        distribution_id = c.fetchone()[0]
        c.execute("""INSERT INTO revisions
            (version_id, distribution_id, version, scheduled_at, changelog)
                     VALUES (%s, %s, %s, %s, %s);""",
                  (result[0], distribution_id, version + '-' + str(revision),
                   now, changelog))
        self.conn.commit()

    # -- not ported - needed anymore?

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
