import pathlib, tomllib

class Toolchain:
    def __init__(self, arch, prefix, path = []):
        self.arch = arch
        self.prefix = prefix
        self.path = path

    @property
    def CROSS_COMPILE(self):
        return self.prefix

    @property
    def PATH(self):
        return self.path

    def __str__(self):
        return f'{self.arch}: {self.prefix}'

class Configuration:
    FILENAME = pathlib.Path.home() / '.config' / 'kmsak' / 'kmsak.toml'

    def __init__(self, filename = FILENAME):
        self.toolchains = {}
        self.paths = []

        with open(filename, 'rb') as f:
            data = tomllib.load(f)

        if 'defaults' in data:
            self.architecture = data['defaults'].get('architecture', None)
            self.vendor = data['defaults'].get('vendor', None)

        if 'toolchains' in data:
            for key, value in data['toolchains'].items():
                if key == 'path':
                    for path in value.split(':'):
                        path = path.replace('$HOME', str(pathlib.Path.home()))
                        self.paths.append(path)

                    continue

                if isinstance(value, dict):
                    path = value.get('path', [])
                    prefix = value.get('prefix')

                    toolchain = Toolchain(key, prefix, path)
                    self.toolchains[key] = toolchain

    def PATH(self, arch):
        return ':'.join(self.paths + self.toolchains[arch].PATH)

    def CROSS_COMPILE(self, arch):
        return self.toolchains[arch].CROSS_COMPILE
