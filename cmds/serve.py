import functools
import hashlib
import http.server
import json
import logging
import subprocess


import debler.db
from debler import config

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)-15s %(name)s %(levelname)s %(message)s',
    filename='debler-server.log')
log = logging.getLogger(__name__)


class DeblerHandler(http.server.BaseHTTPRequestHandler):
    server_version = 'debler/0.1'

    def __init__(self, args, db, *pargs, **kwargs):
        self.args = args
        self.db = db
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
        if self.path != '/debler/updatetrigger/gem':
            self.send_error(404)
            return

        if 'Authorization' not in self.headers:
            self.send_error(403)
            return
        if 'Content-Type' not in self.headers \
                or self.headers['Content-Type'] != 'application/json':
            self.send_error(415)
            return
        if 'Content-Length' not in self.headers:
            self.send_error(411)
            return
        content_length = int(self.headers['Content-Length'])
        if content_length > 1024*1024:  # 1M
            self.send_error(413)
            return
        try:
            encoded_data = self.rfile.read(content_length)
            data = json.loads(encoded_data.decode('utf-8'))
        except Exception as e:
            print(e)
            self.send_error(400)
            return
        if 'name' not in data or 'version' not in data:
            self.send_error(400)
            return
        name = data['name']
        version = data['version']
        kwargs = {'name': name, 'gem': name, 'version': version, 'slot': None}
        if config.rubygems_apikey:
            hashdata = name + version + config.rubygems_apikey
            auth = hashlib.sha256(hashdata.encode('utf-8')).hexdigest()
            if auth != self.headers['Authorization']:
                self.send_error(403)
                return
        self.send_data(b'OK')
        log.debug('Webhook triggered for %(gem)s in %(version)s', kwargs)
        info = self.db.gem_info(name, autocreate=False)
        if not info:
            log.debug('Skip release %(version)s of %(gem)s we do not use it',
                      kwargs)
            return
        new_slot = tuple(int(v) for v in version.split('.')[:info.level])
        kwargs['slot'] = '.'.join(str(s) for s in new_slot)
        if new_slot in info.slots:
            new_version = list(int(v) for v in version.split('.'))
            versions = self.db.gem_slot_versions(name, new_slot)
            if new_version in versions:
                log.warning('%(gem)s rerelease in version %(version)s',
                            kwargs)
                return
            self.db.create_gem_version(
                name, list(new_slot),
                version=new_version, revision=1,
                changelog='New upstream release',
                distribution=config.distribution)
            log.info('%(gem)s scheduled to build %(version)s in %(slot)s',
                     kwargs)
            if self.args.hook:
                args = [self.args.hook]
                for arg in self.args.hook_arg:
                    args.append(arg.format(**kwargs))
                log.debug('exec %s', ' '.join(args))
                subprocess.run(args, check=True, timeout=60)
        else:
            log.info('%(gem)s\'s release %(version)s in unknown slot %(slot)s',
                     kwargs)

    def log_message(self, format, *args):
        pass


def run(args):
    db = debler.db.Database()
    connectedHandler = functools.partial(DeblerHandler, args, db)

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
