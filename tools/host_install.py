"""Install or roll back Slim artwork for this host's existing clean menu."""
import argparse
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

from grub_config import blocks, entry_id
from host_theme import BACKGROUND_HOOK, STAGED_FILES

THEME = 'boot/grub/themes/bourgeois'
HOOK = 'etc/grub.d/06_bourgeois_background'
SETTINGS = 'etc/default/grub.d/zzzz-bourgeois-host.cfg'
CONFIG = 'boot/grub/grub.cfg'
CLEAN = 'boot/grub/clean-menu.cfg'
BACKUPS = 'var/backups/bourgeois'
CHANGED_PATHS = (THEME, HOOK, SETTINGS, CONFIG, CLEAN)


def execute(command):
    subprocess.run(command, check=True)


def runner(root, run):
    if root != Path('/') and run is None:
        raise ValueError('An isolated test root requires an isolated command runner')
    return run if run is not None else execute


@contextmanager
def locked(root):
    directory = root / BACKUPS
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    with (directory / 'install.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield directory


def verify_stage(stage):
    manifest = json.loads((stage / 'manifest.json').read_text())
    if (not isinstance(manifest, dict) or manifest.get('format') != 1
            or not isinstance(manifest.get('files'), dict)
            or set(manifest['files']) != set(STAGED_FILES)):
        raise ValueError('Unrecognized or incomplete host theme manifest')
    size = manifest.get('size')
    if (not isinstance(size, list) or len(size) != 2
            or any(type(value) is not int for value in size)
            or not (800 <= size[0] <= 7680 and 600 <= size[1] <= 4320)):
        raise ValueError('Invalid host theme dimensions')
    for name, digest in manifest['files'].items():
        file = stage / name
        if file.is_symlink() or hashlib.sha256(file.read_bytes()).hexdigest() != digest:
            raise ValueError(f'Staged file changed; rebuild the theme: {name}')
    if (stage / '06_bourgeois_background').read_text() != BACKGROUND_HOOK:
        raise ValueError('The staged background hook is not the artwork-only hook')
    return manifest


def check_parents(root, names):
    for name in names:
        for parent in (root / name).parents:
            if parent == root:
                break
            if parent.is_symlink():
                raise ValueError(f'Refusing to write through a symlink: {parent}')


def verify_menus(root, run):
    for name in (CONFIG, CLEAN):
        run(['grub-script-check', str(root / name)])
    source = (root / CONFIG).read_text()
    clean = (root / CLEAN).read_text()
    entries = [b for b in blocks(clean) if b.kind == 'menuentry']
    if (len(entries) != 2 or '--class gnu-linux' not in entries[0].header
            or '--class windows' not in entries[1].header):
        raise ValueError('Expected the existing Linux-first, two-entry clean menu')
    original = [b for b in blocks(source) if b.kind == 'menuentry']
    for entry in entries:
        matches = [b for b in original if entry_id(b) == entry_id(entry)]
        if (entry_id(entry) is None or len(matches) != 1
                or source[matches[0].opening:matches[0].end] != clean[entry.opening:entry.end]):
            raise ValueError('Clean-menu boot commands differ from the full menu')


def copy(source, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    if source.is_dir():
        shutil.copytree(source, target, symlinks=True)
    else:
        shutil.copy2(source, target, follow_symlinks=False)


def snapshot(root, directory):
    backup = Path(tempfile.mkdtemp(prefix='slim-', dir=directory))
    present = {}
    for name in CHANGED_PATHS:
        source = root / name
        present[name] = source.exists()
        if present[name]:
            copy(source, backup / 'files' / name)
    (backup / 'manifest.json').write_text(json.dumps({'format': 1, 'present': present}, indent=2) + '\n')
    return backup


def restore(root, backup):
    if backup.resolve().is_relative_to((root / THEME).resolve()):
        raise ValueError('The backup must be outside the live theme directory')
    manifest = json.loads((backup / 'manifest.json').read_text())
    if not isinstance(manifest, dict):
        raise ValueError('Unrecognized host theme backup')
    present = manifest.get('present', {})
    if (manifest.get('format') != 1 or not isinstance(present, dict)
            or set(present) != set(CHANGED_PATHS)
            or any(type(value) is not bool for value in present.values())
            or not all(present[name] for name in (THEME, CONFIG, CLEAN))):
        raise ValueError('Unrecognized host theme backup')
    # Check the complete snapshot before replacing any live file.
    for name, exists in present.items():
        source = backup / 'files' / name
        expected_type = source.is_dir() if name == THEME else source.is_file()
        if exists and (not expected_type or source.is_symlink()):
            raise ValueError(f'Backup file is missing or unsupported: {source}')
    check_parents(root, CHANGED_PATHS)
    for name in CHANGED_PATHS:
        target = root / name
        if target.is_dir() and not target.is_symlink():
            shutil.rmtree(target)
        else:
            target.unlink(missing_ok=True)
        if present[name]:
            copy(backup / 'files' / name, target)


def install(stage, root=Path('/'), run=None):
    root, stage = Path(root), Path(stage).resolve()
    run = runner(root, run)
    manifest = verify_stage(stage)
    width, height = manifest['size']
    with locked(root) as directory:
        check_parents(root, (*CHANGED_PATHS,
                             *(THEME + '/' + name for name in STAGED_FILES)))
        for name in CHANGED_PATHS:
            if (root / name).is_symlink():
                raise ValueError(f'Refusing to replace a symlink: /{name}')
        generator = root / 'etc/grub.d/99_clean_menu'
        if not generator.is_file() or not os.access(generator, os.X_OK):
            raise ValueError('This installer requires the existing 99_clean_menu generator')
        if (root / 'etc/grub.d/99_bourgeois').exists():
            raise ValueError('The lab menu hook conflicts with this host artwork installer')
        if not (root / THEME / 'theme.txt').is_file():
            raise ValueError('This command updates the already-installed bourgeois host theme')
        verify_menus(root, run)
        backup = snapshot(root, directory)
        print(f'Backup: {backup}', flush=True)
        try:
            # Copy only the reviewed theme files, never extra staged executables.
            for name in STAGED_FILES:
                if name == '06_bourgeois_background':
                    continue
                target = root / THEME / name
                target.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
                # Replacing existing symlinks avoids following old theme assets.
                target.unlink(missing_ok=True)
                shutil.copyfile(stage / name, target)
                target.chmod(0o644)
                if hashlib.sha256(target.read_bytes()).hexdigest() != manifest['files'][name]:
                    raise ValueError(f'Staged file changed during installation: {name}')
            hook = root / HOOK
            hook.write_text(BACKGROUND_HOOK)
            hook.chmod(0o755)
            settings = root / SETTINGS
            settings.write_text(f'GRUB_THEME="/boot/grub/themes/bourgeois/theme.txt"\n'
                                f'GRUB_GFXMODE="{width}x{height},auto"\n')
            settings.chmod(0o644)
            run(['update-grub'])
            verify_menus(root, run)
            generated = (root / CONFIG).read_text()
            if (f'set gfxmode={width}x{height},auto' not in generated
                    or '/boot/grub/themes/bourgeois/theme.txt' not in generated):
                raise ValueError('Generated GRUB configuration did not select the requested theme and mode')
            temporary = directory / ('.latest-' + backup.name)
            temporary.symlink_to(backup.name)
            os.replace(temporary, directory / 'latest')
        except BaseException:
            try:
                restore(root, backup)
            except Exception as recovery_error:
                raise RuntimeError(f'Automatic restore failed: {recovery_error}. '
                                   f'Do not reboot. Backup: {backup}') from recovery_error
            print('Installation failed; restored the previous theme, settings, hook, and menus.', file=sys.stderr)
            raise
    return backup


def rollback(backup, root=Path('/'), run=None):
    root = Path(root)
    run = runner(root, run)
    with locked(root):
        backup = Path(backup).resolve()
        restore(root, backup)
        try:
            # Refresh kernel entries when rolling back after a later upgrade.
            run(['update-grub'])
            verify_menus(root, run)
        except BaseException:
            restore(root, backup)
            raise RuntimeError('Restored the snapshot, but GRUB regeneration failed. '
                               'Do not reboot until the generated menus are checked.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest='command', required=True)
    setup = subparsers.add_parser('install')
    setup.add_argument('--stage', type=Path, required=True)
    undo = subparsers.add_parser('rollback')
    undo.add_argument('--backup', type=Path, default=Path('/') / BACKUPS / 'latest')
    args = parser.parse_args()
    if os.geteuid() != 0:
        parser.error('Run this command through make host-install or sudo')
    try:
        if args.command == 'install':
            backup = install(args.stage)
            print(f'Slim installed and both menus checked. Backup: {backup}')
        else:
            rollback(args.backup)
            print('Previous theme restored and both menus checked.')
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as error:
        print(f'bourgeois: {error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
