# Debler

Debler maps APM dependencies into the debian packaging world:

  - efficient packaging as each gem is packaged separated
  - multiple version of a gem are coinstallable (e.g. rails 4.2 and 4.1)
  - automatic patch- and security-updates (4.2.5 replaces 4.2.4; if you will)
  - multiruby support: works with all (MRI) rubies that you find packages for
  - static processing: low runtime overhead (bundler is not used, but its interface is provided)
  - flexible: packaging behaviour are highly configurable (e.g. which gem should be in which version coinstallable)
  - self-hosted: it is designed to maintain a own self-hosted Debian repository in our infrastructure for your needs

Bundler is supported fully. Yarn integration is currently experimantal.


### Why?

For clean, efficient and reproduceable installs of ruby applications, we need a way to automatically package a application. The first approach was [Cany](https://github.com/mswart/cany): run `bundler install --deployment` within the packaging and include all installed gems in the package. It solves that tasks but is inefficient as it install each gem on each install, error-prone as it debugs on the rubygems.org API and network connectivity within the packaging environment.

Debler maps the gem dependencies directly on Debian packages, resulting in a more flexible and efficient packaging approach. This allows more flexible CI pipelining experiments.


### Status

Debler is a prototype (developed during my master thesis). It successfully packaged multiple full `rails` applications with yarn as frontend package manager. Sadly, I didn't have the time to continue development or introduce its use in production.

The project remains as reference and maybe inspiration.

I will try to answer questions should they arise. Simple open an issue but be patient.


### Architecture

A central PostgreSQL database is used to track with gems exists (and its configuration like build dependencies and slot creating policies). In addition the metadata for generated packages and builds are also stored there.

They are used to schedule gem package upgrade and used when packaging applications.

Debler is implemented in Python 3. Python 3 is a modern scripting language, has good tooling for Debian (package) development. All needed dependencies exists as Debian packages, allow a easy packaging of Debler itself without chicken-egg problem.


### Python Dependencies

* debian
* dateutil
* psycopg2
* lepl 


### Missing Features

Originally planed features:

* multi distribution support
* license management
* improve package publishing (e.g. remove old versions)
* bundler/rails: separate binary packages for individual rails environments


### License

LGPL License

Copyright (c) 2016-2017 Malte Swart. LGPL license, see LICENSE for more details.
