from functools import partial
import sys
from tempfile import TemporaryDirectory
import traceback

from debler.db import Database
from debler.builder import BuildFailError


def header(content, color=33):
    print()
    print('#'*80)
    print('#'*80)
    print("##### \033[1;{}m{:^68}\033[0m #####".format(color, content))
    print('#'*80)
    print('#'*80)


def run(args):
    db = Database()
    total = 0
    failed = 0
    successful = 0

    if args.builds:
        builds = partial(db.builds_by_id, args.builds)
    elif args.retry:
        builds = db.failed_builds
    else:
        builds = db.scheduled_builds

    for build_id, *data in builds(all=args.print_builds):
        if args.print_builds:
            print('{}:{},{},{},{},{}'.format(build_id, *data))
            continue
        if args.cancel:
            db.update_build(build_id, result='canceled')
            continue
        task = '{}: {}\'s {} in version {}:{} ({})'.format(build_id, *data)
        header(task)
        try:
            if not args.incognito:
                db.claim_build(build_id)
            with TemporaryDirectory() as d:
                builder = db.get_pkger(data[0]).builder(d, build_id)
                builder.generate()
                builder.run()
                if not args.incognito:
                    builder.upload()
            if not args.incognito:
                db.update_build(build_id, result='finished')
            header(task, color=32)
            successful += 1
        except BuildFailError:
            if not args.incognito:
                db.update_build(build_id, result='failed')
            failed += 1
            header(task, color=31)
            if args.fail_fast:
                break
        except Exception:
            if not args.incognito:
                db.update_build(build_id, result='failed')
            failed += 1
            traceback.print_exc()
            header(task, color=31)
            if args.fail_fast:
                break
        total += 1
        if args.limit and total >= args.limit:
            break

    if args.print_builds:
        return

    print('Built {} packages: {} successful, {} failed'.format(
          total, successful, failed))

    if failed:
        sys.exit(1)


def register(subparsers):
    parser = subparsers.add_parser('build', aliases=['b', 'work'])
    parser.add_argument('--fail-fast', '-F', action='store_true')
    parser.add_argument('--retry', '-R', action='store_true')
    parser.add_argument('--limit', '-L', type=int, default=None,
                        help='Build at most n packages',
                        metavar='n')
    parser.add_argument('--incognito', '-I', action='store_true',
                        help='private build, do not record any changes')
    parser.add_argument('--print-builds', '-P', action='store_true')
    parser.add_argument('--cancel', '-C', action='store_true',
                        help='mark build as canceled')
    parser.add_argument('builds', nargs='*', metavar='BUILDID',
                        type=int,
                        help='Specify build list explicit')
    parser.set_defaults(run=run)
