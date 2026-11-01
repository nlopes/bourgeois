"""Actionable dependency checks for host artwork and the disposable lab."""
import argparse
import importlib.util
from pathlib import Path
import shutil
import sys

FONT = Path('/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf')


class HostSetupError(RuntimeError):
    pass


def missing_tools(operation, *, include_sudo=False, which=None, pillow=None, font=FONT):
    which = which or shutil.which
    issues = []
    if operation == 'lab':
        absent = [name for name in ('qemu-system-x86_64', 'qemu-img', 'xorriso', 'ssh', 'ssh-keygen')
                  if not which(name)]
        if absent:
            issues.append(f'Missing {", ".join(absent)}. On Ubuntu: sudo apt install '
                          'qemu-system-x86 qemu-utils ovmf xorriso openssh-client. '
                          'On macOS: brew install qemu xorriso; OpenSSH must also be available.')
    if operation in ('stage', 'all'):
        if pillow is None:
            pillow = importlib.util.find_spec('PIL') is not None
        if not pillow:
            issues.append('Pillow is required to build artwork. On Ubuntu: sudo apt install python3-pil. '
                          'For a virtual environment, install Pillow in that environment.')
        if not which('grub-mkfont'):
            issues.append('grub-mkfont is required for menu text. On Ubuntu: sudo apt install grub2-common.')
        if not Path(font).is_file():
            issues.append('DejaVu Sans Mono is missing. On Ubuntu: sudo apt install fonts-dejavu-mono.')
    if operation in ('install', 'all'):
        absent = [name for name in ('update-grub', 'grub-script-check') if not which(name)]
        if absent:
            issues.append(f'Missing {", ".join(absent)}. On Ubuntu: sudo apt install grub2-common.')
    if include_sudo and not which('sudo'):
        issues.append('sudo is required for host installation. Install the sudo package or ask your administrator.')
    return issues


def require_tools(operation, **kwargs):
    issues = missing_tools(operation, **kwargs)
    if issues:
        raise HostSetupError('\n'.join(issues))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=('stage', 'install', 'all', 'lab'))
    parser.add_argument('--sudo', action='store_true', help='also require the sudo command')
    args = parser.parse_args()
    try:
        require_tools(args.operation, include_sudo=args.sudo)
    except HostSetupError as error:
        sys.exit(f'bourgeois: {error}')
    print('Host tools are available.')
