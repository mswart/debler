ALTER TABLE packages RENAME TO gemslots;

CREATE FUNCTION version2str(int[]) RETURNS text AS $$
DECLARE
  s text := '';
  needdot boolean := false;
  instr boolean := false;
  inrev boolean := false;
  part int;
BEGIN
  FOREACH part IN ARRAY $1
  LOOP
    IF needdot THEN
        s := s || '.';
    ELSE
        needdot := true;
    END IF;
    IF part = 0 AND (instr OR inrev) THEN
        instr := false;
    ELSIF instr THEN
        s := s || chr(part);
        needdot := false;
    ELSIF inrev THEN
        s := s || lpad(to_hex(CASE WHEN part > 0 THEN
                part::bigint
            ELSE
                part::bigint + POW(2,32)::bigint
            END::bigint), 8, '0');
        needdot := false;
    ELSIF part >= 0 THEN
        s := s || part::text;
    ELSIF part = -1 THEN
        instr := true;
        needdot := false;
    ELSIF part = -2 THEN
        inrev := true;
        needdot := false;
        s := s || 'rev';
    ELSEIF part = -9 THEN
        s := s || 'beta';
        needdot := false;
    ELSEIF part = -8 THEN
        s := s || 'xikolo';
    ELSEIF part = -7 THEN
        s := s || 'openhpi';
    END IF;
  END LOOP;
  RETURN s;
END;
$$ LANGUAGE plpgsql;


CREATE EXTENSION IF NOT EXISTS debversion;

CREATE TABLE packager (
  id SERIAL PRIMARY KEY,
  name VARCHAR(60) NOT NULL,
  config JSONB NOT NULL default '{}'
);

CREATE TABLE packages (
  id SERIAL PRIMARY KEY,
  pkger_id integer NOT NULL REFERENCES packager(id) ON DELETE RESTRICT ON UPDATE CASCADE,
  name VARCHAR(60) NOT NULL,
  config JSONB NOT NULL DEFAULT '{}',
  UNIQUE (pkger_id, name)
);

CREATE TABLE slots (
  id SERIAL PRIMARY KEY,
  pkg_id integer NOT NULL REFERENCES  packages(id) ON DELETE RESTRICT ON UPDATE CASCADE,
  version debversion NOT NULL,
  config JSONB NOT NULL DEFAULT '{}',
  metadata JSONB NOT NULL DEFAULT '{}',
  UNIQUE (pkg_id, version)
);

CREATE TABLE versions (
  id SERIAL PRIMARY KEY,
  slot_id integer NOT NULL REFERENCES  slots(id) ON DELETE CASCADE ON UPDATE CASCADE,
  version debversion NOT NULL,
  config JSONB NOT NULL DEFAULT '{}',
  metadata JSONB NOT NULL DEFAULT '{}',
  published_at timestamptz NULL,
  created_at timestamptz NULL,
  UNIQUE (slot_id, version)
);

CREATE TABLE revisions (
  id SERIAL PRIMARY KEY,
  version_id integer NOT NULL REFERENCES  versions(id) ON DELETE CASCADE ON UPDATE CASCADE,
  version debversion NOT NULL,
  scheduled_at timestamptz NOT NULL,
  builder varchar(60) NULL,
  built_at timestamptz NOT NULL,
  changelog TEXT,
  result VARCHAR NULL,
  UNIQUE (version_id, version)
);


INSERT INTO packager (name) SELECT DISTINCT split_part(name, ':', 1) from packages;


INSERT INTO packages (pkger_id, name, config) SELECT
  (SELECT id FROM packager WHERE packager.name = split_part(gems.name, ':', 1)),
  split_part(gems.name, ':', 2),
  case when gems.opts::text = '{}' or gems.opts::text = '{"default": {}}' THEN
    '{"default": {"native": ' || gems.native::text || ', "level": ' || gems.level::text || '}}'
  else
    rtrim(gems.opts::text, '}') || ', "native": ' || gems.native::text || ', "level": ' || gems.level::text || '}}'
  END::jsonb
  FROM gems;


INSERT INTO slots (pkg_id, version, metadata) SELECT
  (SELECT id
   FROM packages
   WHERE packages.name = split_part(gemslots.name, ':', 2)
     AND pkger_id = (SELECT id FROM packager
          WHERE packager.name = split_part(gemslots.name, ':', 1))),
  version2str(gemslots.slot),
  gemslots.metadata
  FROM gemslots;


INSERT INTO versions (slot_id, version, created_at) SELECT
  (SELECT id
   FROM slots
   WHERE version = version2str(package_versions.slot)
    AND pkg_id = (SELECT id
       FROM packages
       WHERE packages.name = split_part(package_versions.name, ':', 2)
         AND pkger_id = (SELECT id FROM packager
              WHERE packager.name = split_part(package_versions.name, ':', 1)))),
  version2str(package_versions.version),
  MIN(scheduled_at)
  FROM package_versions
  GROUP BY package_versions.name, package_versions.slot, package_versions.version;


INSERT INTO revisions (version_id, version, changelog, scheduled_at, built_at, result) SELECT
  (SELECT id FROM
  versions
  WHERE slot_id = (SELECT id
     FROM slots
     WHERE version = version2str(package_versions.slot)
      AND pkg_id = (SELECT id
         FROM packages
         WHERE packages.name = split_part(package_versions.name, ':', 2)
           AND pkger_id = (SELECT id FROM packager
                WHERE packager.name = split_part(package_versions.name, ':', 1))))
    AND versions.version = version2str(package_versions.version)),
  version2str(version) || '-' || revision::text,
  changelog,
  scheduled_at,
  scheduled_at,
  state
  FROM package_versions;
