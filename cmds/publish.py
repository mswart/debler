from debler import builder


def run(args):
    builder.publish(args.kind[:-1])


def register(subparsers):
    parser = subparsers.add_parser('publish')
    parser.add_argument('kind', choices=['gems', 'apps'])
    parser.set_defaults(run=run)
