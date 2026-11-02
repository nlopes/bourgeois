"""Compile, run, or analyze the host C tests without a GRUB installation."""
import argparse
import os
from pathlib import Path
import re
import shlex
import subprocess

ROOT = Path(__file__).resolve().parent.parent
BUILD = ROOT / 'build' / 'c-checks'
TESTS = ('state', 'layout', 'command')


def check(mode):
    includes = BUILD / 'include'
    # The command test supplies only the GRUB services used by the module.
    source = (ROOT / 'fancy/bourgeois.c').read_text()
    for name in re.findall(r'^#include <(grub/[^>]+)>', source, re.M):
        header = includes / name
        header.parent.mkdir(parents=True, exist_ok=True)
        header.write_text('#include "grub_test.h"\n')
    compiler = shlex.split(os.environ.get('CLANG' if mode == 'analyze' else 'CC',
                                         'clang' if mode == 'analyze' else 'cc'))
    flags = ['-std=c99', '-Wall', '-Wextra', '-Werror', '-Wformat=2',
             '-Wstrict-prototypes', '-I' + str(includes), '-I' + str(ROOT / 'fancy')]
    if mode == 'sanitize':
        flags += ['-g', '-O1', '-fno-omit-frame-pointer', '-fsanitize=address,undefined',
                  '-fno-sanitize-recover=all']
    elif mode == 'analyze':
        flags += ['--analyze', '-Xanalyzer', '-analyzer-output=text',
                  '-Xanalyzer', '-analyzer-werror']
    for name in TESTS:
        output = BUILD / f'{name}-{mode}'
        subprocess.run([*compiler, *flags, str(ROOT / f'fancy/{name}_test.c'),
                        '-o', str(output)], check=True)
        if mode != 'analyze':
            subprocess.run([str(output)], check=True)
        print(f'PASS {mode}: {name}', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('test', 'sanitize', 'analyze'))
    check(parser.parse_args().mode)
