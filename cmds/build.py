import traceback
from tempfile import TemporaryDirectory
import sys

from debler.db import Database
from debler.gem import GemBuilder, GemVersion
from debler.builder import publish, BuildFailError


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

    for data in db.scheduled_builds():
        task = '{}:{} in version {}-{}'.format(data[0], GemVersion(data[1]), GemVersion(data[2]), data[3])
        header(task)
        try:
            db.update_build(*data, state='generating')
            with TemporaryDirectory() as d:
                conv = GemBuilder(db, d, *data)
                conv.generate()
                db.update_build(*data, state='building')
                conv.build()
            db.update_build(*data, state='finished')
            header(task, color=32)
            successful += 1
        except BuildFailError:
            db.update_build(*data, state='failed')
            failed += 1
            header(task, color=31)
            if args.fail_fast:
                break
        except Exception:
            db.update_build(*data, state='failed')
            failed += 1
            header(task, color=31)
            traceback.print_exc()
            if args.fail_fast:
                break
        total += 1
        if args.limit and total >= args.limit:
            break

    publish('gem')

    print('Built {} packages: {} successful, {} failed'.format(total, successful, failed))

    if failed:
        sys.exit(1)


def register(subparsers):
    parser = subparsers.add_parser('build', aliases=['b', 'work'])
    parser.add_argument('--fail-fast', '-F', action='store_true')
    parser.add_argument('--limit', '-L', type=int, default=None,
                        help='Build at most n packages',
                        metavar='n')
    parser.set_defaults(run=run)
