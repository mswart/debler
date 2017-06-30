class YarnAppIntegrator():
    def __init__(self, pkger, app, builder):
        self.pgker = pkger
        self.app = app

    def generate_control_file(self):
        if False:
            yield None
        return
        base_dir = '/usr/share/{}/{}'.format(self.app.name, self.app.npm.dir)
        new_deps, new_symlinks = self.app.npm.needed_relations(base_dir)
        deps.extend(new_deps)
        self.symlinks['all'].extend(new_symlinks)
