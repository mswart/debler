import debler.db
from debler import config


def run(args):
    db = debler.db.Database()
    pkger = db.get_pkger('bundler')

    if args.schedule:
        for gem in args.gem:
            name, version = gem.split(':')
            info = pkger.gem_info(name)
            slot = info.slot_for_version(version, create=True)
            slot.create(
                version=version, revision=1,
                changelog='Import newly into debler',
                distribution=config.distribution,
                extra={})
        return

    for gem in args.gem:
        info = pkger.gem_info(gem)
        if args.add:
            message = 'rebuild to include addition directories: {}'.format(
                ', '.join(args.add))
            info.extra_dirs = info.get('extra_dirs', default=[]) + args.add
        elif args.so_subdir:
            message = 'rebuild to move so libs into "{}" subdir'.format(
                args.so_subdir)
            info.so_subdir = args.so_subdir
        elif args.run_dep:
            message = 'rebuild to add new runtime dependencies: {}'.format(
                ', '.join(args.run_dep))
            info.rundeps = info.get('rundeps', default=[]) + args.run_dep
        elif args.native is True:
            message = 'rebuild as native gem'
            gem.native = True
        elif args.native is False:
            message = 'rebuild as none-native gem'
            gem.native = False
        info.rebuild(message)


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
