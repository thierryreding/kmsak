#!/usr/bin/env python3

import difflib, multiprocessing, os, pathlib, re, subprocess, sys
import click

import kmsak

CURDIR = pathlib.Path.cwd()
HOME = pathlib.Path.home()

ISSUE = re.compile(r'(.*?):\s*([^:\s(]+?)(?:@([0-9a-fA-F]+))?(?:\s*\((.*?)\))?:\s*(.*)$')

class ContextObject:
    def __init__(self):
        self.output = None
        self.log_dir = None

        self.config = kmsak.Configuration()
        self.arch = self.config.architecture
        self.vendor = self.config.vendor

    def PATH(self, arch):
        return self.config.PATH(arch)

    @property
    def CROSS_COMPILE(self):
        return self.config.CROSS_COMPILE(self.arch)

@click.group()
@click.option('--arch', '-A')
@click.option('--output', '-O', type = click.Path(), default = CURDIR / 'build' / 'dtbs')
@click.pass_obj
def cli(obj, arch, output):
    if arch:
        obj.arch = arch

    obj.output = output

    # setup PATH environment variable for subcommands
    PATH = f'{os.environ['PATH']}:{obj.PATH(obj.arch)}'
    os.environ['PATH'] = PATH

@cli.group()
@click.pass_obj
def bindings(obj):
    pass

@bindings.command()
@click.argument('schemas', nargs = -1, required = False)
@click.pass_obj
def check(obj, schemas):
    cmd =  [ 'make', f'ARCH={obj.arch}', f'CROSS_COMPILE={obj.CROSS_COMPILE}' ]
    cmd += [ f'O={obj.output}', f'DT_SCHEMA_FILES={':'.join(schemas)}' ]
    cmd += [ 'dt_binding_check' ]

    subprocess.run(cmd)

@cli.group()
@click.option('--vendor', '-V')
@click.pass_obj
def dtbs(obj, arch, output, vendor):
    obj.arch = arch
    obj.output = output
    obj.vendor = vendor

    obj.top_dir = CURDIR / 'arch' / obj.arch / 'boot' / 'dts'
    obj.log_dir = obj.output / 'logs' / obj.arch

    if not obj.vendor:
        obj.dirs = [ x for x in obj.top_dir.iterdir() if x.is_dir() ]
    else:
        obj.dirs = [ obj.top_dir / obj.vendor ]

@dtbs.command()
@click.argument('directory', type = click.Path(path_type = pathlib.Path))
@click.pass_obj
def analyze(obj, directory):
    total = []

    for subdir in obj.dirs:
        for dts in subdir.glob('*.dts'):
            stem = os.path.join(subdir.name, dts.stem)

            if directory is None:
                directory = obj.log_dir

            with open(directory / (stem + '.err'), 'r') as log:
                for line in log:
                    if not line or line[0].isspace():
                        continue

                    #match = re.match(r'(.*?):\s*([^:\s(]+?)(?:@([0-9a-fA-F]+))?(?:\s*\((.*?)\))?:\s*(.*)$', line)
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
    for subdir in obj.dirs:
        for dts in sorted(subdir.glob('*.dts')):
            stem = os.path.join(subdir.name, dts.stem)
            total = []

            if directory is None:
                directory = obj.log_dir

            with open(directory / (stem + '.err'), 'r') as log:
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
            total = click.style(len(total), fg = 'green' if len(total) == 0 else 'red', bold = True)
            click.echo(f'{path}: {total} issues')

def check_dtb(subdir, dts, obj):
    stem = os.path.join(subdir.name, dts.stem)
    dtb = stem + '.dtb'

    cmd  = [ 'make', f'ARCH={obj.arch}', f'CROSS_COMPILE={obj.CROSS_COMPILE}' ]
    cmd += [ f'O={obj.output}', 'CHECK_DTBS=1', dtb ]

    proc = subprocess.run(cmd, capture_output = True)

    with open(obj.log_dir / (stem + '.out'), 'wb') as log:
        log.write(proc.stdout)

    with open(obj.log_dir / (stem + '.err'), 'wb') as log:
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
@click.pass_obj
def check(obj, force):
    if not (CURDIR / 'Makefile').exists() or not (CURDIR / 'Kconfig').exists():
        print(f'{CURDIR} does not look like a Linux kernel source directory')
        sys.exit(1)

    # force rebuild of DTS files by updating the mtime
    if force:
        for subdir in obj.dirs:
            for dts in subdir.glob('*.dts'):
                dts.touch()

    os.makedirs(obj.log_dir, exist_ok = True)
    total = []

    for subdir in obj.dirs:
        os.makedirs(obj.log_dir / subdir.name, exist_ok = True)

        for dts in subdir.glob('*.dts'):
            stem = os.path.join(subdir.name, dts.stem)

            path, code, issues = check_dtb(subdir, dts, obj)
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

    for subdir in obj.dirs:
        target = output / subdir.name
        os.makedirs(target, exist_ok = True)

        for dts in subdir.glob('*.dts'):
            stem = os.path.join(subdir.name, dts.stem)
            err = obj.log_dir / (stem + '.err')
            out = obj.log_dir / (stem + '.out')

            err.move_into(target)
            out.move_into(target)

@dtbs.command()
@click.argument('a', type = click.Path(path_type = pathlib.Path))
@click.argument('b', type = click.Path(path_type = pathlib.Path))
@click.pass_obj
def diff(obj, a, b):
    for subdir in obj.dirs:
        for src in (a / subdir.name).glob('*.err'):
            dst = b / subdir.name / src.name

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
