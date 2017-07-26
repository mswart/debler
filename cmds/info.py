from debler.db import Database


def run(args):
    db = Database()

    for name in args.pkgs:
        if ':' in name:
            pkger_name, pkg_name = name.split(':', 1)
        else:
            pkg = db.pkg_info(None, name, None)
        print('''
{pkg.name}
=====================
id: {pkg.id}
deb_name: {pkg.deb_name}
config: {pkg.opts}
slots:'''.format(pkg=pkg))

        for slot in pkg.slots:
            print('''
- Slot "{slot.version}"
  ----------------------
  id: {slot.id}
  config: {slot.config}
  metadata: {slot.metadata}
  versions:
'''.format(slot=slot)[1:-1])
            for version in slot.versions():
                print('''
  - Version "{version.version}"
    ----------------------
    id: {version.id}
    config: {version.config}
    metadata: {version.metadata}
    populated: {version.populated}
    revisions:
'''.format(version=version)[1:-1])
                for revision in version.revisions():
                    print('''
      {r.id:5}: {r.version} {r.distribution} = {r.changelog:30}
         scheduled: {r.scheduled_at}
         build: {r.builder}@{r.built_at}
         => {r.result}
'''.format(r=revision)[1:-1])


def register(subparsers):
    parser = subparsers.add_parser('info', aliases=['i'])
    parser.add_argument('pkgs', nargs='*', metavar='PACKAGENAME',
                        help='Display info to the provided packages; '
                             'either name or packager:name')
    parser.set_defaults(run=run)
