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
  populated boolean NOT NULL DEFAULT false,
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
  built_at timestamptz NULL,
  changelog TEXT,
  result VARCHAR NULL,
  UNIQUE (version_id, version)
);

# -> format or config.gem_format,
# -> distributions
