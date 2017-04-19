import traceback
from tempfile import TemporaryDirectory
import sys

from debler.db import Database
from debler.gem import GemBuilder, GemVersion
from debler.npm import NpmBuilder
from debler.builder import publish, BuildFailError


def header(content, color=33):
    print()
    print('#'*80)
    print('#'*80)
    print("##### \033[1;{}m{:^68}\033[0m #####".format(color, content))
    print('#'*80)
    print('#'*80)

pkers = {
    'rubygem': GemBuilder,
    'npm': NpmBuilder,
}


def run(args):
    db = Database()
    total = 0
    failed = 0
    successful = 0

    if args.builds:
        builds = lambda all: args.builds
    elif args.retry:
        builds = db.failed_builds
    else:
        builds = db.scheduled_builds

    for pkger, *data in builds(all=args.print_builds):
        if args.print_builds:
            print('{}:{}:{}:{}-{}'.format(pkger, data[0], '.'.join(str(i) for i in data[1]), '.'.join(str(i) for i in data[2]), data[3]))
            continue
        task = '{}:{} in version {}-{}'.format(data[0], GemVersion(data[1]), GemVersion(data[2]), data[3])
        header(task)
        try:
            db.update_build(pkger, *data, state='generating')
            with TemporaryDirectory() as d:
                conv = pkers[pkger](db, d, *data)
                conv.generate()
                db.update_build(pkger, *data, state='building')
                conv.build()
            db.update_build(pkger, *data, state='finished')
            header(task, color=32)
            successful += 1
        except BuildFailError:
            db.update_build(pkger, *data, state='failed')
            failed += 1
            header(task, color=31)
            if args.fail_fast:
                break
        except Exception:
            db.update_build(pkger, *data, state='failed')
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

    publish('gem')

    print('Built {} packages: {} successful, {} failed'.format(total, successful, failed))

    if failed:
        sys.exit(1)


def build(arg):
    arg, revision = arg.rsplit('-', 1)  # slots/versions could have negative numbers (-)
    pkger, name, slot, version = arg.split(':')
    slot = [int(s) for s in slot.split('.')]
    version = [int(s) for s in version.split('.')]
    return (pkger, name, slot, version, int(revision))


def register(subparsers):
    parser = subparsers.add_parser('build', aliases=['b', 'work'])
    parser.add_argument('--fail-fast', '-F', action='store_true')
    parser.add_argument('--retry', '-R', action='store_true')
    parser.add_argument('--limit', '-L', type=int, default=None,
                        help='Build at most n packages',
                        metavar='n')
    parser.add_argument('--print-builds', '-P', action='store_true')
    parser.add_argument('builds', nargs='*', metavar='builds',
                        type=build,
                        help='Specify build list explicit')
    parser.set_defaults(run=run)
