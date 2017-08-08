from datetime import datetime
from importlib import import_module
import json
import socket

from dateutil.tz import tzlocal
from debian import debian_support
import psycopg2
import psycopg2.extras

from debler import config


class Version(debian_support.Version):
    pass


class PkgInfo():
    def __init__(self, db, id, name, deb_name, opts, slots):
        self.db = db
        self.id = id
        self.name = name
        self.deb_name = deb_name
        self.opts = opts
        self.slots = slots

    def lookup(self, name, default):
        return self.opts.get('default', {}).get(name, default)

    def get(self, name, default=None):
        return self.lookup(name, default=default)

    def set(self, name, value, context='default'):
        self.opts.setdefault(context, {})[name] = value
        self.db.set_pkg_config(self.id, self.opts)

    def __getattr__(self, name):
        return self.lookup(name, default=None)

    def __setattr__(self, name, value):
        if name in ('db', 'id', 'name', 'deb_name', 'opts', 'slots'):
            return object.__setattr__(self, name, value)
        return self.set(name, value, context='default')

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
        slot = self.db.create_pkg_slot(self, '.'.join(parts[:self.lookup('level', 1)]))
        self.slots.append(slot)
        return slot

    def __repr__(self):
        return 'PkgInfo({}, {}, {!r}, {!r})'.format(
            self.id, self.name, self.opts, self.slots)

    def rebuild(self, changelog):
        for slot in self.slots:
            newest_version = slot.versions()[-1]
            lastest_build = newest_version.revisions()[-1]
            self.db.schedule_rebuild(lastest_build.id, changelog)


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

    @property
    def min_version(self):
        return self.version

    @property
    def max_version(self):
        parts = str(self.version).split('.')
        parts[-1] = str(int(parts[-1]) + 1)
        return Version('.'.join(parts) + '~~~')

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

    def revisions(self):
        return self.db.get_revisions(self)

    def __repr__(self):
        return 'VersionInfo({!r}, {}, {!r}, {!r}, {!r})'.format(
            self.slot, self.id, self.version, self.config, self.metadata)


class RevisionsInfo():
    def __init__(self, id, version, distribution, scheduled_at,
                 builder, built_at, changelog, result):
        self.id = id
        self.version = Version(version)
        self.distribution = distribution
        self.scheduled_at = scheduled_at
        self.builder = builder
        self.built_at = built_at
        self.changelog = changelog
        self.result = result


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

    def get_pkgers(self):
        c = self.conn.cursor()
        c.execute('SELECT id, name, config FROM packager WHERE enabled = true')
        pkgers = {}
        for id, name, cfg in c:
            impl = import_module(cfg.pop('module'))
            pkgers[name] = getattr(impl, 'pkgerInfo')(self, id, **cfg)
        return pkgers

    def register_pkg(self, pkger_id, name, config):
        c = self.conn.cursor()
        c.execute("""INSERT INTO packages (pkger_id, name, config)
             VALUES (%s, %s, %s);""", (pkger_id, name, json.dumps(config)))
        self.conn.commit()

    def set_pkg_config(self, pkg_id, config):
        c = self.conn.cursor()
        c.execute('UPDATE packages SET config = %s WHERE id = %s',
                  (json.dumps(config), pkg_id))
        self.conn.commit()

    def pkg_info(self, pkger_id, name, deb_name,
                 klass=PkgInfo, slotklass=SlotInfo):
        c = self.conn.cursor()
        if pkger_id is not None:
            c.execute('SELECT id, config FROM packages '
                      'WHERE pkger_id = %s AND name = %s',
                      (pkger_id, name))
        else:
            c.execute('SELECT id, config FROM packages '
                      'WHERE name = %s',
                      (name, ))
        result = c.fetchone()
        if not result:
            raise ValueError('Pkg "{}" unknown in pkger {}'.format(
                name, pkger_id))
            return None
        pkg_id, config = result

        c.execute('SELECT id, version, config, metadata FROM slots '
                  'WHERE pkg_id = %s ORDER BY version', (pkg_id,))
        slots = []
        pkg = klass(self, pkg_id, name, deb_name, config, slots)
        for row in c.fetchall():
            slots.append(slotklass(self, pkg, *row))
        return pkg

    def create_pkg_slot(self, pkg, slot):
        c = self.conn.cursor()
        c.execute("""INSERT INTO slots (pkg_id, version) VALUES (%s, %s)
                  RETURNING id, version, config, metadata;""",
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

    def get_revisions(self, version):
        c = self.conn.cursor()
        c.execute('''SELECT revisions.id, version,
                            distributions.name, scheduled_at,
                            builder, built_at,
                            changelog, result
                     FROM revisions
                     INNER JOIN distributions
                        ON revisions.distribution_id = distributions.id
                     WHERE version_id = %s
                     ORDER BY version ASC''',
                  (version.id, ))
        reversions = []
        for row in c:
            reversions.append(RevisionsInfo(*row))
        return reversions

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

    def schedule_rebuild(self, build_id, changelog):
        now = datetime.now(tz=tzlocal()).strftime('%Y-%m-%d %H:%M:%S %z')
        c = self.conn.cursor()
        c.execute("""SELECT version_id, distribution_id, version
                     FROM revisions
                     WHERE id = %s""",
                  (build_id,))
        version_id, distribution_id, version = c.fetchone()
        version, revision = version.rsplit('-', 1)
        revision = str(int(revision) + 1)
        version = version + '-' + revision
        c.execute("""INSERT INTO revisions
            (version_id, distribution_id, version, scheduled_at, changelog)
                     VALUES (%s, %s, %s, %s, %s);""",
                  (version_id, distribution_id, version,
                   now, changelog))
        self.conn.commit()

    def _dump_builds(self, *, result=None, ids=None):
        c = self.conn.cursor()
        sql = '''SELECT
            rev.id,
            packager.name AS pkger,
            packages.name AS pkg,
            slots.version AS slot,
            rev.version AS version,
            distributions.name AS distribution
        FROM revisions AS rev
        INNER JOIN distributions ON rev.distribution_id = distributions.id
        INNER JOIN versions ON rev.version_id = versions.id
        INNER JOIN slots ON versions.slot_id = slots.id
        INNER JOIN packages ON slots.pkg_id = packages.id
        INNER JOIN packager ON packages.pkger_id = packager.id
        '''
        values = []
        if ids is not None:
            sql += ' WHERE rev.id = ANY(%s)'
            values.append(ids)
            if len(ids) > 1:
                sql += ' ORDER BY array_position(%s, rev.id)'
                values.append(ids)
        elif result is None:
            sql += ' WHERE rev.result IS NULL'
        else:
            sql += ' WHERE rev.result = %s'
            values.append(result)
        c.execute(sql, tuple(values))
        for pkg in c:
            yield pkg

    def _iter_builds(self, *args, **kwargs):
        while True:
            for build in self._dump_builds(*args, **kwargs):
                yield build
                break
            else:
                # no build return from dump_builds, end while loop
                break

    def scheduled_builds(self, all=False):
        query_by = self._dump_builds if all else self._iter_builds
        yield from query_by(result=None)

    def failed_builds(self, all=False):
        query_by = self._dump_builds if all else self._iter_builds
        yield from query_by(result='failed')

    def builds_by_id(self, build_ids, *, all=False):
        yield from self._dump_builds(ids=build_ids)

    def claim_build(self, build_id):
        now = datetime.now(tz=tzlocal()).strftime('%Y-%m-%d %H:%M:%S %z')
        c = self.conn.cursor()
        c.execute('''UPDATE revisions SET
                        builder = %s,
                        built_at = %s
                     WHERE id = %s''',
                  (socket.getfqdn(), now, build_id))
        self.conn.commit()

    def update_build(self, build_id, *, result):
        c = self.conn.cursor()
        c.execute('''UPDATE revisions SET
                        result = %s
                     WHERE id = %s''',
                  (result, build_id))
        self.conn.commit()

    def build_data(self, build_id):
        c = self.conn.cursor(cursor_factory=psycopg2.extras.NamedTupleCursor)
        sql = '''SELECT
            rev.id AS id,
            packager.name AS pkger,
            packages.name AS pkg,
            slots.version AS slot,
            slots.id AS slot_id,
            versions.version AS version,
            versions.config AS version_config,
            rev.version AS revision,
            distributions.name AS distribution
        FROM revisions AS rev
        INNER JOIN distributions ON rev.distribution_id = distributions.id
        INNER JOIN versions ON rev.version_id = versions.id
        INNER JOIN slots ON versions.slot_id = slots.id
        INNER JOIN packages ON slots.pkg_id = packages.id
        INNER JOIN packager ON packages.pkger_id = packager.id
        WHERE rev.id = %s
        '''
        c.execute(sql, (build_id, ))
        return c.fetchone()

    def changelog_entries(self, build_id):
        c = self.conn.cursor()
        c.execute("""
            WITH org AS (SELECT * from revisions WHERE id = %s)
            SELECT
                revs.version,
                revs.scheduled_at,
                revs.changelog,
                dists.name AS distribution
            FROM revisions AS revs
            INNER JOIN distributions dists ON revs.distribution_id = dists.id
            WHERE revs.version <= (SELECT version FROM org)
              AND revs.distribution_id = (SELECT distribution_id FROM org)
            ORDER BY revs.version ASC;
            """, (build_id, ))
        yield from c

    def set_slot_metadata(self, slot_id, metadata):
        c = self.conn.cursor()
        c.execute('UPDATE slots SET metadata = %s WHERE id = %s',
                  (json.dumps(metadata), slot_id))
        self.conn.commit()
