#!/usr/bin/env python3

import difflib, multiprocessing, os, pathlib, re, subprocess, sys
import click, git

import kmsak

CURDIR = pathlib.Path.cwd()
HOME = pathlib.Path.home()

ISSUE = re.compile(r'(.*?):\s*([^:\s(]+?)(?:@([0-9a-fA-F]+))?(?:\s*\((.*?)\))?:\s*(.*)$')
INFO = click.style('kmsak', fg = 'magenta')
ERROR = click.style('kmsak', fg = 'red', bold = True)

class Run:
    def __init__(self, arch, output, cross_compile):
        self.arch = arch
        self.output = output / arch
        self.CROSS_COMPILE = cross_compile

        self.top_dir = CURDIR / 'arch' / self.arch / 'boot' / 'dts'
        self.log_dir = self.output / 'logs' / self.arch
        self.dirs = []

class ContextObject:
    def __init__(self):
        self.output = None
        self.log_dir = None

        self.config = kmsak.Configuration()
        self.architectures = self.config.architectures
        self.vendors = self.config.vendors

    def PATH(self, arch):
        return self.config.PATH(arch)

    def CROSS_COMPILE(self, arch):
        return self.config.CROSS_COMPILE(arch)

    def make_runs(self):
        runs = []

        for arch in self.architectures:
            run = Run(arch, self.output, self.CROSS_COMPILE(arch))

            if self.vendors:
                run.dirs = [ run.top_dir / vendor for vendor in self.vendors ]
            else:
                run.dirs = [ x for x in run.top_dir.iterdir() if x.is_dir() ]

            runs.append(run)

        return runs

@click.group()
@click.option('--architectures', '-A', type = str)
@click.option('--vendors', '-V', type = str)
@click.option('--output', '-O', type = click.Path(), default = CURDIR / 'build' / 'dtbs')
@click.pass_obj
def cli(obj, architectures, vendors, output):
    if architectures:
        obj.architectures = [ x.strip() for x in architectures.split(',') ]

    if vendors:
        obj.vendors = [ x.strip() for x in vendors.split(',') ]

    obj.output = output

    # setup PATH environment variable for subcommands
    PATH = os.environ['PATH']
    paths = []

    for arch in obj.architectures:
        path = obj.PATH(arch)

        if path not in paths:
            paths.append(path)

    PATH = ':'.join([ PATH ] + paths)
    os.environ['PATH'] = PATH

@cli.group()
@click.pass_obj
def bindings(obj):
    pass

@bindings.command()
@click.option('--all', is_flag = True)
@click.argument('schemas', nargs = -1, required = False)
@click.pass_obj
def check(obj, all, schemas):
    schemas = list(schemas)

    # cannot use --all with an explicit list of schemas
    if all and schemas:
        click.echo(f'{ERROR}: --all option conflicts with schemas: {':'.join(schemas)}')
        return

    # try to determine from the latest commit message which bindings were
    # modified and test only those
    if not schemas and not all:
        repo = git.Repo()

        if repo.is_dirty:
            changes = repo.index.diff(None) + repo.index.diff()

            for diff in changes:
                name = diff.b_path

                if name.startswith('Documentation/devicetree/bindings/'):
                    schemas.append(name)
        else:
            for name, stats in repo.head.commit.stats.files.items():
                if name.startswith('Documentation/devicetree/bindings/'):
                    schemas.append(name)

        if not schemas:
            click.echo(f'{INFO}: no schemas modified, use --all?')
            return

    cmd =  [ 'make', f'ARCH={obj.arch}', f'CROSS_COMPILE={obj.CROSS_COMPILE}' ]
    cmd += [ f'O={obj.output}' ]

    if schemas:
        cmd += [ f'DT_SCHEMA_FILES={':'.join(schemas)}' ]

    cmd += [ 'dt_binding_check' ]

    click.echo(f'{INFO} $ {' '.join(cmd)}')
    proc = subprocess.Popen(cmd, stdout = subprocess.PIPE,
                            stderr = subprocess.STDOUT, text = True,
                            bufsize = 1)
    for line in proc.stdout:
        click.echo(f'{INFO} > {line.strip()}')

@cli.group()
@click.option('--vendors', '-V', type = str)
@click.pass_obj
def dtbs(obj, vendors):
    if not (CURDIR / 'Makefile').exists() or not (CURDIR / 'Kconfig').exists():
        print(f'{CURDIR} does not look like a Linux kernel source directory')
        sys.exit(1)

    # override default vendor if command-line option is provided
    if vendors:
        obj.vendors = [ x.strip() for x in vendors.split(',') ]

@dtbs.command()
@click.argument('directory', type = click.Path(path_type = pathlib.Path))
@click.pass_obj
def analyze(obj, directory):
    total = []

    runs = obj.make_runs()

    for run in runs:
        for subdir in run.dirs:
            for dts in subdir.glob('*.dts'):
                stem = os.path.join(subdir.name, dts.stem)

                if directory is None:
                    directory = obj.log_dir

                with open(directory / run.arch / (stem + '.err'), 'r') as log:
                    for line in log:
                        if not line or line[0].isspace():
                            continue

                        match = ISSUE.match(line)
                        if not match:
                            click.echo(f'ERROR: failed to parse issue: {line}')
                            continue

                        path, node, unit, binding, message = match.groups()
                        total.append((path, node, unit, binding, message))

    print(f'Summary:')
    print(f'{len(total)} issues')

    messages = {}

    for path, node, unit, binding, message in total:
        if message not in messages:
            messages[message] = []

        messages[message].append((path, node, unit, binding))

    print(f'{len(messages)} unique')

    for message, instances in messages.items():
        print(f'{message}: {len(instances)} instances')

        for path, node, unit, binding in instances:
            if unit is not None:
                print(f'  {path}: {node}@{unit}')
            else:
                print(f'  {path}: {node}')

@dtbs.command()
@click.argument('directory', type = click.Path(path_type = pathlib.Path), required = False)
@click.pass_obj
def todo(obj, directory):
    runs = obj.make_runs()

    for run in runs:
        for subdir in run.dirs:
            for dts in sorted(subdir.glob('*.dts')):
                stem = os.path.join(subdir.name, dts.stem)
                total = []

                if directory is None:
                    directory = obj.log_dir

                with open(directory / run.arch / (stem + '.err'), 'r') as log:
                    for line in log:
                        if not line or line[0].isspace():
                            continue

                        match = ISSUE.match(line)
                        if not match:
                            click.echo(f'ERROR: failed to parse issue: {line}')
                            continue

                        path, node, unit, binding, message = match.groups()
                        total.append((path, node, unit, binding, message))

                path = click.style(stem, fg = 'magenta')
                color = 'green' if len(total) == 0 else 'red'
                total = click.style(len(total), fg = color, bold = True)
                click.echo(f'{path}: {total} issues')

def check_dtb(subdir, dts, run, verbose = False):
    warnings = 2 if verbose else 1

    stem = os.path.join(subdir.name, dts.stem)
    dtb = stem + '.dtb'

    cmd  = [ 'make', f'ARCH={run.arch}', f'CROSS_COMPILE={run.CROSS_COMPILE}' ]
    cmd += [ f'O={run.output}', 'CHECK_DTBS=1', f'W={warnings}', dtb ]

    print('running', ' '.join(cmd))

    proc = subprocess.run(cmd, capture_output = True)

    with open(run.log_dir / (stem + '.out'), 'wb') as log:
        log.write(proc.stdout)

    with open(run.log_dir / (stem + '.err'), 'wb') as log:
        log.write(proc.stderr)

    issues = []

    for line in proc.stderr.decode().splitlines():
        if not line or line[0].isspace():
            continue

        #match = re.match(r'(.*?):\s*([^:\s(]+?)(?:@([0-9a-fA-F]+))?(?:\s*\((.*?)\))?:\s*(.*)$', line)
        match = ISSUE.match(line)
        if not match:
            click.echo(f'ERROR: failed to parse issue: {line}')
            continue

        path, node, unit, binding, message = match.groups()
        issues.append((path, node, unit, binding, message))

    return (dtb, proc.returncode, issues)

@dtbs.command()
@click.option('--force', '-F', is_flag = True)
@click.option('--verbose', '-v', is_flag = True)
@click.pass_obj
def check(obj, force, verbose):
    runs = obj.make_runs()

    # force rebuild of DTS files by updating the mtime
    if force:
        for run in runs:
            for subdir in run.dirs:
                for dts in subdir.glob('*.dts'):
                    dts.touch()

    total = []

    for run in runs:
        # run make olddefconfig in case Kconfig changed
        cmd  = [ 'make', f'ARCH={run.arch}', f'CROSS_COMPILE={run.CROSS_COMPILE}' ]
        cmd += [ f'O={run.output}', 'olddefconfig' ]

        print('running', ' '.join(cmd))

        proc = subprocess.run(cmd, capture_output = True)

        if proc.returncode != 0:
            print(proc.stderr, file = sys.stderr)
            sys.exit(proc.return_code)

        # prepare log directory
        os.makedirs(run.log_dir, exist_ok = True)

        for subdir in run.dirs:
            os.makedirs(run.log_dir / subdir.name, exist_ok = True)

            for dts in subdir.glob('*.dts'):
                stem = os.path.join(subdir.name, dts.stem)

                path, code, issues = check_dtb(subdir, dts, run, verbose)
                total.extend(issues)

                path = click.style(path, fg = 'magenta', bold = False)

                if not issues:
                    issues = click.style(len(issues), fg = 'green', bold = True)
                else:
                    issues = click.style(len(issues), fg = 'red', bold = True)

                click.echo(f'{path}: {issues} issues')

    if not total:
        summary = click.style(len(total), fg = 'green', bold = True)
    else:
        summary = click.style(len(total), fg = 'red', bold = True)

    click.echo(f'Summary:')
    click.echo(f'{summary} issues')

@dtbs.command()
@click.argument('output', type = click.Path(path_type = pathlib.Path))
@click.pass_obj
def snapshot(obj, output):
    os.makedirs(output, exist_ok = True)
    runs = obj.make_runs()

    for run in runs:
        for subdir in run.dirs:
            target = output / run.arch / subdir.name
            os.makedirs(target, exist_ok = True)

            for dts in subdir.glob('*.dts'):
                stem = os.path.join(subdir.name, dts.stem)
                err = run.log_dir / (stem + '.err')
                out = run.log_dir / (stem + '.out')

                err.move_into(target)
                out.move_into(target)

@dtbs.command()
@click.argument('a', type = click.Path(path_type = pathlib.Path))
@click.argument('b', type = click.Path(path_type = pathlib.Path))
@click.pass_obj
def diff(obj, a, b):
    runs = obj.make_runs()

    for run in runs:
        for subdir in run.dirs:
            for src in (a / run.arch / subdir.name).glob('*.err'):
                dst = b / run.arch / subdir.name / src.name

                with open(src, 'r') as fobj:
                    x = fobj.readlines()

                with open(dst, 'r') as fobj:
                    y = fobj.readlines()

                for line in difflib.unified_diff(x, y, src.name, dst.name):
                    if line[0] == '+':
                        if line[1] == '+':
                            line = click.style(line, bold = True)
                        else:
                            line = click.style(line, fg = 'green')
                    elif line[0] == '-':
                        if line[1] == '-':
                            line = click.style(line, bold = True)
                        else:
                            line = click.style(line, fg = 'red')
                    elif line[0] == '@':
                        line = click.style(line, fg = 'cyan', bold = True)

                    print(line, end = '')

def main():
    cli(obj = ContextObject())

if __name__ == '__main__':
    main()
