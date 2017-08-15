import functools
import http.server
import logging
import sys
import traceback


import debler.db

log = logging.getLogger(__name__)


class DeblerHandler(http.server.BaseHTTPRequestHandler):
    server_version = 'debler/0.1'

    def __init__(self, args, hooks, *pargs, **kwargs):
        self.args = args
        self.hooks = hooks
        super().__init__(*pargs, **kwargs)

    def send_data(self, data, content_type='text/plain', response_code=200):
        """ Helper method to send data as HTTP response. The data are
            transfered as :mimetype:`text/plain`.
            :param str data: The text to send as :py:obj:`Python String <str>`.
            :param int response_code: HTTP response code"""
        if type(data) is not bytes:
            data = str(data).encode('utf-8')
        self.send_response(response_code)
        self.send_header('Content-type', content_type)
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        """ Handles POST request (webhooks). """
        if not self.path.startswith('/debler/updatetrigger/'):
            self.send_error(404)
            return

        name = self.path[22:]
        if name not in self.hooks:
            self.send_error(404)
            return

        try:
            self.hooks[name].run(self)
        except Exception:
            log.exception('Could not run hook')
            self.send_error(500)

    def log_message(self, format, *args):
        pass


def run(args):
    db = debler.db.Database()
    pkgers = db.get_pkgers()
    hooks = {}
    for pkger in pkgers.values():
        if not hasattr(pkger, 'webhook'):
            continue
        webhook = pkger.webhook(args.hook, args.hook_arg)
        for name in webhook.hook_names:
            hooks[name] = webhook
    connectedHandler = functools.partial(DeblerHandler, args, hooks)

    server = http.server.HTTPServer((args.host, args.port), connectedHandler)
    server.allow_reuse_address = True
    server.serve_forever()


def register(subparsers):
    parser = subparsers.add_parser('serve')
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--port', type=int,
                       help='port to listen')
    group.add_argument('--host', default='0.0.0.0',
                       help='host bind for listen socket')
    parser.add_argument('--hook', help='script to be launch after new deps')
    parser.add_argument('--hook-arg', action='append', default=[],
                        help='Argument to hook script; python format is '
                             'called on each argument, with gem, slot, '
                             'version keyword arguments')
    parser.set_defaults(run=run, native=None)
