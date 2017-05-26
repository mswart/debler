import debler.db


def run(args):
    db = debler.db.Database()

    if args.format_rebuild:
        db.gem_format_rebuild(args.message)
    elif args.simple:
        for gem in args.gem:
            db.gem_rebuild(gem, args.message)


def register(subparsers):
    parser = subparsers.add_parser('rebuild')
    parser.add_argument('message',
                        help='debian changelog text / reason for rebuild')
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--format-rebuild', action='store_true',
                       help='rebuild all gems with outdated format version')
    group.add_argument('--simple', action='store_true',
                       help='rebuild list of provided gem name')
    # todo: --native-rebuild
    parser.add_argument('gem', nargs='*', help='limit list of gems to rebuild')
    parser.set_defaults(run=run)
