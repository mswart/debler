from debler.app import AppInfo, AppBuilder
from debler.builder import publish
from debler.db import Database


def run(args):
    db = Database()
    app = AppInfo.fromyml(db, args.app_info)

    app.schedule_gemdeps_builds()

    builder = AppBuilder(db, app)
    builder.generate()
    builder.build()

    publish('app')


def register(subparsers):
    parser = subparsers.add_parser('pkgapp')
    parser.add_argument('app_info',
                        help='file to app info yml description file')
    parser.set_defaults(run=run)
