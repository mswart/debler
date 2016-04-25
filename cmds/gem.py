import debler.db


def run(args):
    db = debler.db.Database()

    if args.add_dir:
        message = 'rebuild to include {} dir into package'.format(args.add_dir)
        for gem in args.gems:
            _, opts, _, _ = db.gem_info(gem)
            opts['default'].set_default('extra_dirs', [])
            opts['default']['extra_dirs'].append(args.add_dir)
            db.set_gem_opts(gem, opts)
            db.gem_rebuild(gem, message)


def register(subparsers):
    parser = subparsers.add_parser('gem')
    parser.add_argument('message', help='debian changelog text / reason for rebuild')
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--add-dir',
                       help='add a other dir as required + schedule rebuilds of this gem')
    # todo: --native-rebuild
    parser.add_argument('gem', nargs='*', help='limit list of gems to rebuild')
