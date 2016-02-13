# Debler

Debler maps ruby's bundler into the debian packaging world:

  - efficient packaging as each gem is packaged separated
  - multiple version of a gem are coinstallable (e.g. rails 4.2 and 4.1)
  - automatic patch- and security-updates (4.2.5 replaces 4.2.4; if you will)
  - multiruby support: works with all (MRI) rubies that you find packages for
  - static processing: low runtime overhead (bundler is not used, but its interface is provided)
  - flexible: packaging behaviour are highly configurable (e.g. which gem should be in which version coinstallable)
  - self-hosted: it is designed to maintain a own self-hosted Debian repository in our infrastructure for your needs


### Why?

For clean, efficient and reproduceable installs of ruby applications, we need a way to automatically package a application. The first approach was [Cany](https://github.com/mswart/cany): run `bundler install --deployment` within the packaging and include all installed gems in the package. It solves that tasks but is inefficient as it install each gem on each install, error-prone as it debugs on the rubygems.org API and network connectivity within the packaging environment.

Debler maps the gem dependencies directly on Debian packages, resulting in a more flexible and efficient packaging approach. This allows more flexible CI pipelining experiments.


### Status

Debler is highly under development. This can package full `rails-api` projects on a prototype basic. Further experiments and bugfixes are planed for the new future. The goal is the use Debler productive within this year (2016) - we will see.


### Architecture

A central PostgreSQL database is used to track with gems exists (and its configuration like build dependencies and slot creating policies). In addition the metadata for generated packages and builds are also stored there.

They are used to schedule gem package upgrade and used when packaging applications.

Debler is implemented in Python 3. Python 3 is a modern scripting language, has good tooling for Debian (package) development. All needed dependencies exists as Debian packages, allow a easy packaging of Debler itself without chicken-egg problem.


### Planed/missing Features

Some important planed features:

* full gem to deb dependency management (tested)
* multi distribution support
* module support for apkpkg (base module is bundler, framework modules like rails; own add-ones for gems with external lauch like webservers ...)
* license management
* improve package publishing (e.g. remove old versions)
* semi-automatical gem and app rebuild on changes
* bundler/rails: separate binary packages for individual rails environments
* proper interface for configuration changes (like gems)
* auto-update and auto-packaging of new gem versions
