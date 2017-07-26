import debler.db


def run(args):
    db = debler.db.Database()

    message = ''

    for arg in args.args:
        if arg.isdigit():
            db.schedule_rebuild(arg, message)
        else:
            message = arg


def register(subparsers):
    parser = subparsers.add_parser('rebuild')
    parser.add_argument('args',
                        nargs='*',
                        metavar='MESSAGE [BUILDID [BUILDID]]',
                        help='debian changelog text / reason for rebuild')
    parser.set_defaults(run=run)
