"""Compile and install Fancy as the persistent host boot menu."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

from host_fancy import ROOT, prepare_build_tools, snapshot_menus, stage
from host_fancy_config import LIVE_CONFIG, configuration
from host_fancy_trial import (EFI, FILES, LABEL as TRIAL_LABEL, MOK, STATE as TRIAL_STATE,
                              boot_state, check_host_image, current_config, verify_files)
from host_fancy_trial import mok_hashes
from host_install import check_parents, copy

LABEL = 'bourgeois Fancy'
STATE = Path('var/lib/bourgeois/fancy-installed.json')
LIBRARY = Path('usr/lib/bourgeois-fancy')
HOOK = Path('etc/grub.d/zzzz_bourgeois_fancy')
BACKUPS = Path('var/backups/bourgeois/fancy')
CONFIGS = (Path('boot/grub/grub.cfg'), Path('boot/grub/clean-menu.cfg'))
CHANGED = (EFI, STATE, TRIAL_STATE, LIBRARY, HOOK, LIVE_CONFIG, *CONFIGS)
GENERATOR = '''#!/usr/bin/python3
import sys
sys.dont_write_bytecode = True
sys.path.insert(0, '/usr/lib/bourgeois-fancy')
from host_fancy_config import main
main()
'''


def execute(args):
    if args[:2] == ['mokutil', '--import-hash']:
        # Keep the temporary password prompt attached to the user's terminal.
        subprocess.run(args, check=True)
        return ''
    return subprocess.check_output([str(arg) for arg in args], text=True)


def command_runner(root, run):
    if root != Path('/') and run is None:
        raise ValueError('An isolated root requires an isolated command runner')
    return run or execute


def read_state(root, name):
    file = root / name
    if not file.exists():
        return None
    if file.is_symlink():
        raise ValueError(f'Refusing a symlink: {file}')
    manifest = json.loads(file.read_text())
    verify_files(root / EFI, manifest)
    return manifest


def entry_matches(entry):
    label, _, loader = entry.partition('\t')
    return (label in (LABEL, TRIAL_LABEL)
            and r'\efi\bourgeois-fancy\shimx64.efi' in loader.lower())


def ubuntu_entry(order, entries):
    for number in order.split(','):
        entry = entries.get(number, '').lower()
        if entry.startswith('ubuntu\t') and r'\efi\ubuntu\shimx64.efi' in entry:
            return number
    raise ValueError('The Ubuntu recovery entry is missing from BootOrder')


def snapshot(root):
    directory = root / BACKUPS
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    backup = Path(tempfile.mkdtemp(prefix='install-', dir=directory))
    present = {}
    for name in CHANGED:
        source = root / name
        present[str(name)] = source.exists()
        if source.exists():
            copy(source, backup / 'files' / name)
    (backup / 'manifest.json').write_text(json.dumps(present, indent=2) + '\n')
    return backup


def restore_files(root, backup):
    present = json.loads((backup / 'manifest.json').read_text())
    for name in CHANGED:
        target = root / name
        if target.is_dir():
            shutil.rmtree(target)
        else:
            target.unlink(missing_ok=True)
        if present[str(name)]:
            copy(backup / 'files' / name, target)


def verify_selection(run, order, pending):
    actual_order, _, actual_pending = boot_state(run(['efibootmgr', '-v']))
    if actual_order != order or actual_pending != pending:
        raise RuntimeError('Firmware boot selection did not match the requested values')


def restore_selection(run, order, pending):
    current, _, current_pending = boot_state(run(['efibootmgr', '-v']))
    if current != order:
        run(['efibootmgr', '--bootorder', order])
    if current_pending != pending:
        run(['efibootmgr', '--bootnext', pending] if pending
            else ['efibootmgr', '--delete-bootnext'])
    verify_selection(run, order, pending)


def verify_live_menu(root, run):
    expected, _ = configuration((root / CONFIGS[0]).read_text(),
                                (root / CONFIGS[1]).read_text())
    actual = (root / LIVE_CONFIG).read_text()
    # grub-mkconfig appends the generator's END comment after it has run.
    def without_markers(value):
        for marker in ('BEGIN', 'END'):
            value = value.replace(f'### {marker} /etc/grub.d/{HOOK.name} ###', '')
        return value.strip()
    if without_markers(actual) != without_markers(expected):
        raise ValueError('Fancy menu does not match the current distribution menu')
    run(['grub-script-check', str(root / LIVE_CONFIG)])


def install(stage_directory, root=Path('/'), run=None):
    run = command_runner(root, run)
    check_parents(root, (*CHANGED, BACKUPS))
    for name in (*CHANGED, BACKUPS):
        if (root / name).is_symlink():
            raise ValueError(f'Refusing to replace a symlink: {name}')
    manifest = json.loads((stage_directory / 'manifest.json').read_text())
    verify_files(stage_directory, manifest)
    check_host_image(manifest)
    if manifest.get('mode') != 'persistent':
        raise ValueError('Rebuild with make host-fancy-install; this is a one-time trial image')
    current_config(root, manifest)
    previous = read_state(root, STATE)
    trial = read_state(root, TRIAL_STATE)
    if previous and trial:
        raise ValueError('Conflicting Fancy installation records; inspect before installing')
    previous = previous or trial
    if (root / EFI).exists() and not previous:
        raise ValueError('Unmanaged Fancy EFI files already exist; inspect before replacing them')
    if not previous or trial:
        for name in (LIBRARY, HOOK, LIVE_CONFIG):
            if (root / name).exists():
                raise ValueError(f'Unmanaged Fancy file already exists: {name}')
    if 'SecureBoot enabled' not in run(['mokutil', '--sb-state']):
        raise ValueError('This host installer requires Secure Boot enabled')
    order, entries, pending = boot_state(run(['efibootmgr', '-v']))
    ubuntu = ubuntu_entry(order, entries)
    number = previous.get('bootnum') if previous else None
    if previous and not entry_matches(entries.get(number, '')):
        raise ValueError('The saved Fancy boot entry changed; inspect efibootmgr')
    if any(entry_matches(value) and key != number for key, value in entries.items()):
        raise ValueError('An untracked Fancy firmware entry already exists')
    if pending and pending != number:
        raise ValueError('An unrelated BootNext is pending; finish that boot before installing Fancy')
    mok = root / MOK
    enrolled = mok_hashes(mok.read_bytes()) if mok.exists() else set()
    needs_enrollment = manifest['authenticode_sha256'] not in enrolled
    if needs_enrollment and run(['mokutil', '--list-new']).strip():
        raise ValueError('Another MOK request is pending; complete it before installing Fancy')
    esp = run(['findmnt', '-n', '-o', 'SOURCE', '--mountpoint', str(root / 'boot/efi')]).strip()
    parent = run(['lsblk', '-n', '-o', 'PKNAME', esp]).strip()
    part = run(['lsblk', '-n', '-o', 'PARTN', esp]).strip()
    if not re.fullmatch('[A-Za-z0-9_-]+', parent) or not part.isdecimal():
        raise ValueError('Cannot determine the mounted ESP disk and partition')
    backup = snapshot(root)
    (backup / 'firmware.json').write_text(json.dumps({'boot_order': order, 'boot_next': pending}))
    created = None
    print(f'Fancy backup: {backup}', flush=True)
    try:
        destination = root / EFI
        destination.mkdir(parents=True, exist_ok=True, mode=0o755)
        for name in sorted(FILES):
            temporary = destination / ('.' + name + '.new')
            if temporary.exists() or temporary.is_symlink():
                raise ValueError(f'Unexpected temporary EFI file: {temporary}')
            shutil.copyfile(stage_directory / name, temporary)
            os.replace(temporary, destination / name)
        verify_files(destination, manifest)
        library = root / LIBRARY
        library.mkdir(parents=True, exist_ok=True, mode=0o755)
        for name in ('host_fancy_config.py', 'grub_config.py'):
            if (library / name).is_symlink():
                raise ValueError(f'Refusing a library symlink: {library / name}')
            shutil.copyfile(ROOT / 'tools' / name, library / name)
            (library / name).chmod(0o644)
        generator = root / HOOK
        generator.write_text(GENERATOR)
        generator.chmod(0o755)
        run(['update-grub'])
        verify_live_menu(root, run)
        if number is None:
            run(['efibootmgr', '--create-only', '--disk', '/dev/' + parent, '--part', part,
                 '--label', LABEL, '--loader', r'\EFI\bourgeois-fancy\shimx64.efi'])
            _, after_entries, _ = boot_state(run(['efibootmgr', '-v']))
            added = set(after_entries) - set(entries)
            if len(added) != 1:
                raise RuntimeError('Unexpected EFI entries after creation; inspect efibootmgr')
            created = number = added.pop()
            if not entry_matches(after_entries[number]):
                raise RuntimeError('Firmware created an unexpected Fancy entry')
            verify_selection(run, order, pending)
        if needs_enrollment:
            print('Secure Boot: choose a temporary password, then confirm Enroll MOK on reboot.\n'
                  f"Image hash: {manifest['authenticode_sha256']}", flush=True)
            run(['mokutil', '--import-hash', manifest['authenticode_sha256']])
        desired = ','.join([number, ubuntu, *[item for item in order.split(',')
                                            if item not in (number, ubuntu)]])
        if pending:
            run(['efibootmgr', '--delete-bootnext'])
        run(['efibootmgr', '--bootorder', desired])
        verify_selection(run, desired, None)
        manifest.update({'bootnum': number, 'boot_order': desired, 'backup': str(backup)})
        state = root / STATE
        state.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        state.write_text(json.dumps(manifest, indent=2) + '\n')
        state.chmod(0o600)
        (root / TRIAL_STATE).unlink(missing_ok=True)
    except BaseException:
        try:
            restore_selection(run, order, pending)
            if created:
                run(['efibootmgr', '--bootnum', created, '--delete-bootnum'])
            restore_files(root, backup)
        except Exception as error:
            raise RuntimeError(f'Automatic restore failed: {error}. Do not reboot. Backup: {backup}') from error
        raise
    return manifest, needs_enrollment


def uninstall(root=Path('/'), run=None):
    run = command_runner(root, run)
    check_parents(root, (*CHANGED, BACKUPS))
    for name in CHANGED:
        if (root / name).is_symlink():
            raise ValueError(f'Refusing to remove a symlink: {name}')
    manifest = read_state(root, STATE)
    if manifest is None:
        raise ValueError('No persistent Fancy installation exists')
    order, entries, pending = boot_state(run(['efibootmgr', '-v']))
    number = manifest['bootnum']
    if not entry_matches(entries.get(number, '')):
        raise ValueError('The saved Fancy firmware entry changed; inspect before removal')
    ubuntu = ubuntu_entry(order, entries)
    desired = ','.join([ubuntu, *[item for item in order.split(',') if item not in (number, ubuntu)]])
    backup = snapshot(root)
    try:
        if pending == number:
            run(['efibootmgr', '--delete-bootnext'])
        run(['efibootmgr', '--bootorder', desired])
        for name in (HOOK, LIVE_CONFIG):
            (root / name).unlink(missing_ok=True)
        shutil.rmtree(root / LIBRARY)
        run(['update-grub'])
        for name in CONFIGS:
            run(['grub-script-check', str(root / name)])
        verify_selection(run, desired, None if pending == number else pending)
    except BaseException:
        restore_files(root, backup)
        restore_selection(run, order, pending)
        raise
    run(['efibootmgr', '--bootnum', number, '--delete-bootnum'])
    shutil.rmtree(root / EFI)
    (root / STATE).unlink()
    return backup


def build_and_install(args):
    if os.geteuid() == 0:
        raise ValueError('Run make host-fancy-install as your regular user; compilation does not need root')
    prepare_build_tools()
    # Authenticate before spending time compiling, and keep snapshots private.
    subprocess.run(['sudo', '-v'], check=True)
    directory = ROOT / 'build'
    directory.mkdir(exist_ok=True)
    workspace = Path(tempfile.mkdtemp(prefix='fancy-install-', dir=directory))
    snapshot_directory = workspace / 'snapshot'
    snapshot_menus(snapshot_directory)
    stage(args.source, args.build or workspace / 'native', snapshot_directory, workspace / 'stage', args.pesign,
          args.module_source, persistent=True)
    subprocess.run(['sudo', sys.executable, str(Path(__file__).resolve()), 'deploy',
                    '--stage', str(workspace / 'stage')], check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('install', 'deploy', 'uninstall'))
    parser.add_argument('--stage', type=Path)
    parser.add_argument('--source', type=Path, default=ROOT / 'build/host-fancy-source/grub2-unsigned-2.14')
    parser.add_argument('--build', type=Path, help='override the private build directory')
    parser.add_argument('--pesign', default='pesign')
    parser.add_argument('--module-source', type=Path, default=ROOT / 'fancy/bourgeois.c')
    args = parser.parse_args()
    try:
        if args.command == 'install':
            build_and_install(args)
            return 0
        if os.geteuid() != 0:
            raise ValueError('Use make host-fancy-install or make host-fancy-uninstall for sudo authentication')
        if args.command == 'deploy' and args.stage is None:
            raise ValueError('--stage is required for deployment')
        with Path('/run/lock/bourgeois-fancy.lock').open('w') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            if args.command == 'deploy':
                _, needs_enrollment = install(args.stage.resolve())
                print('Fancy installed as the default for every boot. Ubuntu remains available for recovery.')
                if needs_enrollment:
                    print('On reboot, confirm this image hash in MokManager with the temporary password.')
            else:
                backup = uninstall()
                print(f'Fancy removed. Ubuntu/Slim is the default. Backup: {backup}')
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as error:
        print(f'bourgeois: {error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
