import functools
import hashlib
import http.server
import json


import debler.db
from debler.gem import GemVersion
from debler import config


class DeblerHandler(http.server.BaseHTTPRequestHandler):
    server_version = 'debler/0.1'

    def __init__(self, db, *args, **kwargs):
        self.db = db
        super().__init__(*args, **kwargs)

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
        if 'Content-Type' not in self.headers or self.headers['Content-Type'] != 'application/json':
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
        if config.rubygems_apikey:
            hashdata = name + version + config.rubygems_apikey
            auth = hashlib.sha256(hashdata.encode('utf-8')).hexdigest()
            if auth != self.headers['Authorization']:
                self.send_error(403)
                return
        self.send_data(b'OK')
        print('{} published in version {}'.format(name, version), end='')
        info = self.db.gem_info(name, autocreate=False)
        if not info:
            print('  -> not used')
            return
        level, _, _, slots = info
        new_slot = tuple(int(v) for v in version.split('.')[:level])
        if new_slot in slots:
            self.db.create_gem_version(
                name, list(new_slot),
                version=list(int(v) for v in version.split('.')), revision=1,
                changelog='New upstream release', distribution=config.distribution)
            print('  -> scheduled build in slot {}'.format(new_slot))
        else:
            print('  -> version in unknown slot {}'.format(new_slot))


def run(args):
    db = debler.db.Database()
    connectedHandler = functools.partial(DeblerHandler, db)

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
    parser.set_defaults(run=run, native=None)
