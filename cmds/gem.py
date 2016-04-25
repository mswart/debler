import debler.db


def run(args):
    db = debler.db.Database()

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
    parser.add_argument('gem', nargs='*', help='limit list of gems to rebuild')
    parser.set_defaults(run=run)
