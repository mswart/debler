import debler.db
from debler.gem import GemVersion
from debler import config


def run(args):
    db = debler.db.Database()

    if args.schedule:
        for gem in args.gem:
            name, version_str = gem.split(':')
            version = GemVersion.fromstr(version_str)
            info = db.gem_info(name)
            slot = tuple(version.limit(info.level).todb())
            if slot not in info.slots:
                db.create_gem_slot(name, slot)
            db.create_gem_version(
                name, slot,
                version=version.todb(), revision=1,
                changelog='Import newly into debler',
                distribution=config.distribution)
        return

    for gem in args.gem:
        opts = db.gem_info(gem).opts
        opts.setdefault('default', {})
        if args.add:
            message = 'rebuild to include addition directories: {}'.format(
                ', '.join(args.add))
            opts['default'].setdefault('extra_dirs', [])
            opts['default']['extra_dirs'].extend(args.add)
        elif args.so_subdir:
            message = 'rebuild to move so libs into "{}" subdir'.format(
                args.so_subdir)
            opts['default']['so_subdir'] = args.so_subdir
        elif args.run_dep:
            message = 'rebuild to add new runtime dependencies: {}'.format(
                ', '.join(args.run_dep))
            opts['default'].setdefault('rundeps', [])
            opts['default']['rundeps'].extend(args.run_dep)
        elif args.native is True:
            message = 'rebuild as native gem'
            db.set_gem_native(gem, True)
        elif args.native is False:
            message = 'rebuild as none-native gem'
            db.set_gem_native(gem, False)
        db.set_gem_opts(gem, opts)
        db.gem_rebuild(gem, message)


def register(subparsers):
    parser = subparsers.add_parser('gem')
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--add', action='append', default=[],
                       help='add another dir or file as required + ' +
                       'schedule rebuilds of this gem')
    group.add_argument('--so-subdir',
                       help='set the so subdir + schedule rebuild of this gem')
    group.add_argument('--run-dep', action='append', default=[],
                       help='register a new runtime dependency')
    group.add_argument('--native', dest='native', action='store_true')
    group.add_argument('--no-native', dest='native', action='store_false')
    group.add_argument('--schedule', action='store_true',
                       help='schedule building of gem:version tasks')
    parser.add_argument('gem', nargs='*', help='limit list of gems to rebuild')
    parser.set_defaults(run=run, native=None)
