import hashlib
import json
import logging
import subprocess

from debler import config

log = logging.getLogger(__name__)


class RubygemsWebHook():
    hook_names = ('gem', )

    def __init__(self, pkger, hook, hook_args):
        self.pkger = pkger
        self.hook = hook
        self.hook_args = hook_args

    def run(self, request):
        if 'Authorization' not in request.headers:
            request.send_error(403)
            return
        if 'Content-Type' not in request.headers \
                or request.headers['Content-Type'] != 'application/json':
            request.send_error(415)
            return
        if 'Content-Length' not in request.headers:
            request.send_error(411)
            return
        content_length = int(request.headers['Content-Length'])
        if content_length > 1024*1024:  # 1M
            request.send_error(413)
            return
        try:
            encoded_data = request.rfile.read(content_length)
            data = json.loads(encoded_data.decode('utf-8'))
        except Exception as e:
            print(e)
            request.send_error(400)
            return
        if 'name' not in data or 'version' not in data:
            request.send_error(400)
            return
        name = data['name']
        version = data['version']
        kwargs = {'name': name, 'gem': name, 'version': version, 'slot': None}
        if self.pkger.rubygems_apikey:
            hashdata = name + version + self.pkger.rubygems_apikey
            auth = hashlib.sha256(hashdata.encode('utf-8')).hexdigest()
            if auth != request.headers['Authorization']:
                request.send_error(403)
                return
        request.send_data(b'OK')
        log.debug('Webhook triggered for %(gem)s in %(version)s', kwargs)
        try:
            info = self.pkger.gem_info(name, autocreate=False)
        except ValueError:
            log.debug('Skip release %(version)s of %(gem)s we do not use it',
                      kwargs)
            return
        try:
            slot = info.slot_for_version(version, create=False)
        except ValueError:
            log.info('%(gem)s\'s release %(version)s in unknown slot %(slot)s',
                     kwargs)
            return
        kwargs['slot'] = slot.version
        versions = [v.version for v in slot.versions()]
        if version in versions:
            log.warning('%(gem)s rerelease in version %(version)s',
                        kwargs)
            return
        slot.create(
            version=version, revision=1,
            changelog='New upstream release',
            distribution=config.distribution,
            extra={})
        log.info('%(gem)s scheduled to build %(version)s in %(slot)s',
                 kwargs)
        if self.hook:
            args = [self.hook]
            for arg in self.hook_args:
                args.append(arg.format(**kwargs))
            log.debug('exec %s', ' '.join(args))
            subprocess.run(args, check=True, timeout=60)
