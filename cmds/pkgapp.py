from tempfile import TemporaryDirectory

from debler.app import AppInfo, AppBuilder
from debler.builder import publish
from debler.db import Database


def run(args):
    db = Database()
    app = AppInfo.fromyml(db, args.app_info)

    app.schedule_gemdeps_builds()
    if args.schedule_gemdeps_builds_only:
        return

    with TemporaryDirectory() as d:
        builder = AppBuilder(db, d, app)
        builder.generate()
        builder.build()

    publish('app')


def register(subparsers):
    parser = subparsers.add_parser('pkgapp')
    parser.add_argument('app_info',
                        help='file to app info yml description file')
    parser.add_argument('--schedule-gemdeps-builds-only', '-D',
                        action='store_true', default=False,
                        help='only schedule needed builds for depended gems')
    parser.set_defaults(run=run)
