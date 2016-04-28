import debler.db
from debler.gem import GemVersion
from debler import config


def run(args):
    db = debler.db.Database()

    if args.schedule:
        for gem in args.gem:
            name, version_str = gem.split(':')
            version = GemVersion.fromstr(version_str)
            level, builddeps, native, slots = db.gem_info(name)
            slot = tuple(version.limit(level).todb())
            if slot not in slots:
                db.create_gem_slot(name, slot)
            db.create_gem_version(
                name, slot,
                version=version.todb(), revision=1,
                changelog='Import newly into debler', distribution=config.distribution)
        return

    for gem in args.gem:
        _, opts, _, _ = db.gem_info(gem)
        opts.setdefault('default', {})
        if args.add_dir:
            message = 'rebuild to include "{}" dir into package'.format(args.add_dir)
            opts['default'].setdefault('extra_dirs', [])
            opts['default']['extra_dirs'].append(args.add_dir)
        elif args.so_subdir:
            message = 'rebuild to move so libs into "{}" subdir'.format(args.add_dir)
            opts['default']['so_subdir'] = args.so_subdir
        db.set_gem_opts(gem, opts)
        db.gem_rebuild(gem, message)


def register(subparsers):
    parser = subparsers.add_parser('gem')
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--add-dir',
                       help='add a other dir as required + schedule rebuilds of this gem')
    group.add_argument('--so-subdir',
                       help='set the so subdir + schedule rebuilds of this gem')
    group.add_argument('--schedule', action='store_true',
                       help='schedule building of gem:version tasks')
    parser.add_argument('gem', nargs='*', help='limit list of gems to rebuild')
    parser.set_defaults(run=run)
