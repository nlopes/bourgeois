"""Manage a separate, one-time Fancy host trial; never replace Ubuntu/Slim."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
import uuid

from host_fancy import VERSION, digest
from host_install import check_parents

EFI = Path('boot/efi/EFI/bourgeois-fancy')
STATE = Path('var/lib/bourgeois/fancy-trial.json')
FILES = {'grubx64.efi', 'shimx64.efi', 'mmx64.efi'}
LABEL = 'bourgeois Fancy trial'
MOK = 'sys/firmware/efi/efivars/MokListRT-605dab50-e046-4300-abb6-3dd810dd8b23'
SHA256_GUID = uuid.UUID('c1c41626-504c-4092-aca9-41f936934328').bytes_le
WITHDRAWN_REGISTRY = Path(__file__).resolve().parent.parent / 'build/fancy-withdrawn.json'


def execute(args):
    return subprocess.check_output([str(a) for a in args], text=True)


def verify_files(directory, manifest):
    if (manifest.get('format') != 1 or manifest.get('grub_version') != VERSION
            or set(manifest.get('files', {})) != FILES
            or not re.fullmatch('[0-9a-f]{64}', manifest.get('authenticode_sha256', ''))
            or set(manifest.get('snapshots', {})) != {'grub.cfg', 'clean-menu.cfg'}):
        raise ValueError('Unrecognized Fancy trial manifest')
    for name, expected in manifest['files'].items():
        file = directory / name
        if file.is_symlink() or digest(file) != expected:
            raise ValueError(f'Trial file changed: {file}')


def current_config(root, manifest):
    for name, expected in manifest['snapshots'].items():
        if digest(root / 'boot/grub' / name) != expected:
            raise ValueError('Host menu changed since staging. Take fresh snapshots and rebuild.')


def withdrawn_images():
    if not WITHDRAWN_REGISTRY.exists():
        return set()
    registry = json.loads(WITHDRAWN_REGISTRY.read_text())
    if not isinstance(registry, dict):
        raise ValueError('Invalid private withdrawn-image registry; expected an object')
    values = registry.get('authenticode_sha256')
    if (registry.get('format') != 1 or not isinstance(values, list)
            or any(not isinstance(value, str) or not re.fullmatch('[0-9a-f]{64}', value)
                   for value in values)):
        raise ValueError('Invalid private withdrawn-image registry; inspect build/fancy-withdrawn.json')
    return set(values)


def check_host_image(manifest):
    if manifest.get('withdrawn') or manifest['authenticode_sha256'] in withdrawn_images():
        raise ValueError('This Fancy image was withdrawn after a physical black-screen report. '
                         'Restore the original working image; '
                         'see docs/research/host-fancy.adoc.')


def boot_state(text):
    order = re.search(r'^BootOrder: ([0-9A-Fa-f,]+)$', text, re.M)
    if not order:
        raise ValueError('Cannot determine the existing EFI BootOrder')
    entries = dict(re.findall(r'^Boot([0-9A-Fa-f]{4})\*?\s+(.*)$', text, re.M))
    pending = re.search(r'^BootNext: ([0-9A-Fa-f]{4})$', text, re.M)
    return order[1].upper(), entries, pending[1].upper() if pending else None


def restore_selection(run, order):
    current, _, pending = boot_state(run(['efibootmgr', '-v']))
    if current != order:
        run(['efibootmgr', '--bootorder', order])
    if pending is not None:
        run(['efibootmgr', '--delete-bootnext'])
    current, _, pending = boot_state(run(['efibootmgr', '-v']))
    if current != order or pending is not None:
        raise RuntimeError('Could not restore EFI boot selection; inspect efibootmgr before rebooting')


def mok_hashes(data):
    """Read SHA256 entries from an efivarfs EFI_SIGNATURE_LIST database."""
    data = data[4:]  # efivarfs attributes precede the variable payload.
    hashes = set()
    while data:
        if len(data) < 28:
            raise ValueError('Truncated MOK signature database')
        kind, size, header, sigsize = struct.unpack_from('<16sIII', data)
        if size < 28 + header or size > len(data) or sigsize < 16:
            raise ValueError('Invalid MOK signature database')
        signatures = data[28 + header:size]
        if len(signatures) % sigsize:
            raise ValueError('Invalid MOK signature size')
        if kind == SHA256_GUID:
            if sigsize != 48:
                raise ValueError('Invalid MOK SHA256 entry')
            hashes.update(signatures[i + 16:i + 48].hex()
                          for i in range(0, len(signatures), sigsize))
        data = data[size:]
    return hashes


def install(stage, root=Path('/'), run=None):
    if root != Path('/') and run is None:
        raise ValueError('An isolated root requires an isolated command runner')
    run = run or execute
    manifest = json.loads((stage / 'manifest.json').read_text())
    verify_files(stage, manifest)
    check_host_image(manifest)
    current_config(root, manifest)
    check_parents(root, (str(EFI / 'grubx64.efi'), str(STATE)))
    if ((root / EFI).exists() or (root / EFI).is_symlink()
            or (root / STATE).exists() or (root / STATE).is_symlink()):
        raise ValueError('A trial already exists; remove it before installing another image')
    if 'SecureBoot enabled' not in run(['mokutil', '--sb-state']):
        raise ValueError('This trial requires Secure Boot enabled')
    before = run(['efibootmgr', '-v'])
    order, entries, pending = boot_state(before)
    if pending or any(value.startswith(LABEL) for value in entries.values()):
        raise ValueError('An existing BootNext or Fancy entry needs inspection first')
    default = entries.get(order.split(',')[0], '').lower()
    if not default.startswith('ubuntu\t') or r'\efi\ubuntu\shimx64.efi' not in default:
        raise ValueError('Expected Ubuntu/Slim to be first in BootOrder')
    esp = run(['findmnt', '-n', '-o', 'SOURCE', '--mountpoint', str(root / 'boot/efi')]).strip()
    parent = run(['lsblk', '-n', '-o', 'PKNAME', esp]).strip()
    part = run(['lsblk', '-n', '-o', 'PARTN', esp]).strip()
    if not re.fullmatch('[A-Za-z0-9_-]+', parent) or not part.isdecimal():
        raise ValueError('Cannot determine the mounted ESP disk and partition')
    destination = root / EFI
    destination.mkdir(mode=0o755)
    created = None
    try:
        for name in sorted(FILES):
            shutil.copyfile(stage / name, destination / name)
        verify_files(destination, manifest)
        run(['efibootmgr', '--create-only', '--disk', '/dev/' + parent,
             '--part', part, '--label', LABEL, '--loader', r'\EFI\bourgeois-fancy\shimx64.efi'])
        after_order, after_entries, after_pending = boot_state(run(['efibootmgr', '-v']))
        added = set(after_entries) - set(entries)
        if len(added) != 1:
            raise RuntimeError('Unexpected EFI entries after create-only; inspect efibootmgr')
        created = added.pop()
        if after_order != order or after_pending != pending:
            restore_selection(run, order)
            raise RuntimeError('Firmware changed BootOrder/BootNext unexpectedly; restored prior values')
        manifest.update({'bootnum': created, 'boot_order': order})
        state = root / STATE
        state.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        state.write_text(json.dumps(manifest, indent=2) + '\n')
        state.chmod(0o600)
    except BaseException:
        if created:
            run(['efibootmgr', '--bootnum', created, '--delete-bootnum'])
        shutil.rmtree(destination)
        (root / STATE).unlink(missing_ok=True)
        raise
    return manifest


def installed(root):
    manifest = json.loads((root / STATE).read_text())
    verify_files(root / EFI, manifest)
    if not re.fullmatch('[0-9A-Fa-f]{4}', manifest.get('bootnum', '')):
        raise ValueError('Invalid saved trial boot entry')
    return manifest


def arm(root=Path('/'), run=None):
    if root != Path('/') and run is None:
        raise ValueError('An isolated root requires an isolated command runner')
    run = run or execute
    manifest = installed(root)
    check_host_image(manifest)
    current_config(root, manifest)
    if 'SecureBoot enabled' not in run(['mokutil', '--sb-state']):
        raise ValueError('Secure Boot must remain enabled')
    if manifest['authenticode_sha256'] not in mok_hashes((root / MOK).read_bytes()):
        raise ValueError('The image hash is not enrolled. Complete MOK enrollment first.')
    order, entries, pending = boot_state(run(['efibootmgr', '-v']))
    entry = entries.get(manifest['bootnum'], '')
    if (order != manifest['boot_order'] or pending
            or not entry.startswith(LABEL + '\t')
            or r'\EFI\bourgeois-fancy\shimx64.efi'.lower() not in entry.lower()):
        raise ValueError('EFI state changed or BootNext is already set; inspect efibootmgr')
    run(['efibootmgr', '--bootnext', manifest['bootnum']])
    after_order, _, after_next = boot_state(run(['efibootmgr', '-v']))
    if after_order != order or after_next != manifest['bootnum']:
        restore_selection(run, order)
        raise RuntimeError('BootNext verification failed; restored prior EFI selection')


def remove(root=Path('/'), run=None):
    if root != Path('/') and run is None:
        raise ValueError('An isolated root requires an isolated command runner')
    run = run or execute
    manifest = installed(root)
    check_parents(root, (str(EFI / 'grubx64.efi'), str(STATE)))
    _, entries, pending = boot_state(run(['efibootmgr', '-v']))
    entry = entries.get(manifest['bootnum'], '')
    if (not entry.startswith(LABEL + '\t')
            or r'\EFI\bourgeois-fancy\shimx64.efi'.lower() not in entry.lower()):
        raise ValueError('Saved EFI entry changed; inspect before removal')
    if pending == manifest['bootnum']:
        run(['efibootmgr', '--delete-bootnext'])
    run(['efibootmgr', '--bootnum', manifest['bootnum'], '--delete-bootnum'])
    shutil.rmtree(root / EFI)
    (root / STATE).unlink()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('install', 'enroll', 'once', 'remove'))
    parser.add_argument('--stage', type=Path, default=Path('build/fancy-controller'))
    args = parser.parse_args()
    if os.geteuid() != 0:
        parser.error('Use the matching make host-fancy-* command with sudo authentication')
    try:
        # Serialize root operations without creating host state during read-only staging.
        with Path('/run/lock/bourgeois-fancy.lock').open('w') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            if args.command == 'install':
                manifest = install(args.stage.resolve())
                print(f"Installed separate trial Boot{manifest['bootnum']}; BootOrder unchanged.")
            elif args.command == 'once':
                arm()
                print('Fancy selected for the next boot only. Ubuntu/Slim remains the default.')
            elif args.command == 'enroll':
                manifest = installed(Path('/'))
                check_host_image(manifest)
                current_config(Path('/'), manifest)
                if execute(['mokutil', '--list-new']).strip():
                    raise ValueError('A MOK enrollment request is already pending; inspect mokutil --list-new')
                print('Enroll this image hash in MokManager on the next Ubuntu boot:',
                      manifest['authenticode_sha256'], flush=True)
                subprocess.run(['mokutil', '--import-hash', manifest['authenticode_sha256']], check=True)
            else:
                remove()
                print('Removed the separate Fancy trial. Its enrolled MOK hash can be deleted separately.')
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as error:
        sys.exit(f'bourgeois: {error}')


if __name__ == '__main__':
    main()
