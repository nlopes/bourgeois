import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from host_install import (BACKUPS, CHANGED_PATHS, CLEAN, CONFIG, HOOK, SETTINGS,
                          THEME, install, rollback)
from host_theme import BACKGROUND_HOOK, STAGED_FILES


def menus(kernel='old'):
    return f'''menuentry 'Linux' --class gnu-linux --id linux-id {{
  linux /vmlinuz-{kernel} root=UUID=test ro
  initrd /initrd-{kernel}
}}
menuentry 'Windows' --class windows --id windows-id {{
  chainloader /EFI/Microsoft/Boot/bootmgfw.efi
}}
'''


class HostInstallTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.root = self.base / 'system'
        self.stage = self.base / 'stage'
        for name in STAGED_FILES:
            file = self.stage / name
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_text(BACKGROUND_HOOK if name == '06_bourgeois_background'
                            else f'new artwork: {name}\n')
        manifest = {'format': 1, 'size': [1280, 720], 'files': {
            name: hashlib.sha256((self.stage / name).read_bytes()).hexdigest()
            for name in STAGED_FILES}}
        (self.stage / 'manifest.json').write_text(json.dumps(manifest))
        (self.root / THEME).mkdir(parents=True)
        (self.root / THEME / 'theme.txt').write_text('original theme')
        (self.root / THEME / 'original.png').write_bytes(b'original artwork')
        (self.root / 'etc/default/grub.d').mkdir(parents=True)
        generator = self.root / 'etc/grub.d/99_clean_menu'
        generator.parent.mkdir(parents=True)
        generator.write_text('#!/bin/sh\n')
        generator.chmod(0o755)
        (self.root / CONFIG).write_text(menus())
        (self.root / CLEAN).write_text(menus())
        self.commands = []
        self.kernel = 'old'

    def grub_command(self, command):
        self.commands.append(command)
        if command[0] == 'update-grub':
            settings = self.root / SETTINGS
            mode = '1280x720,auto'
            if settings.exists():
                mode = settings.read_text().split('GRUB_GFXMODE="', 1)[1].split('"')[0]
            (self.root / CONFIG).write_text(
                f'set gfxmode={mode}\n'
                'set theme=($root)/boot/grub/themes/bourgeois/theme.txt\n'
                + menus(self.kernel))
            (self.root / CLEAN).write_text(menus(self.kernel))

    def state(self):
        result = {}
        for name in CHANGED_PATHS:
            file = self.root / name
            paths = sorted(file.rglob('*')) if file.is_dir() else [file]
            result[name] = [(str(p.relative_to(self.root)), p.read_bytes(), p.stat().st_mode)
                            for p in paths if p.is_file()]
        return result

    def test_install_records_a_complete_backup_and_selects_the_staged_mode(self):
        original = self.state()
        backup = install(self.stage, self.root, self.grub_command)
        self.assertEqual((self.root / THEME / 'theme.txt').read_bytes(),
                         (self.stage / 'theme.txt').read_bytes())
        self.assertEqual((self.root / HOOK).read_text(), BACKGROUND_HOOK)
        self.assertIn('GRUB_GFXMODE="1280x720,auto"', (self.root / SETTINGS).read_text())
        self.assertEqual((self.root / BACKUPS / 'latest').resolve(), backup)
        self.assertEqual(json.loads((backup / 'manifest.json').read_text())['present'],
                         {name: bool(original[name]) for name in CHANGED_PATHS})
        self.assertEqual(self.commands.count(['update-grub']), 1)

    def test_failed_generation_restores_artwork_settings_hooks_and_both_menus(self):
        (self.root / HOOK).write_text('old background hook')
        (self.root / HOOK).chmod(0o751)
        (self.root / SETTINGS).write_text('old settings')
        original = self.state()

        def failure(command):
            if command[0] == 'update-grub':
                (self.root / CONFIG).write_text('broken full menu')
                (self.root / CLEAN).write_text('broken auxiliary menu')
                raise subprocess.CalledProcessError(1, command)

        with self.assertRaises(subprocess.CalledProcessError):
            install(self.stage, self.root, failure)
        self.assertEqual(self.state(), original)
        self.assertFalse((self.root / THEME / 'icons').exists())

    def test_failed_post_install_syntax_check_restores_the_snapshot(self):
        original = self.state()

        def failure(command):
            self.grub_command(command)
            if command[0] == 'grub-script-check' and ['update-grub'] in self.commands:
                raise subprocess.CalledProcessError(1, command)

        with self.assertRaises(subprocess.CalledProcessError):
            install(self.stage, self.root, failure)
        self.assertEqual(self.state(), original)

    def test_changed_staged_artwork_is_rejected_before_host_writes(self):
        original = self.state()
        (self.stage / 'theme.txt').write_text('changed after staging')
        with self.assertRaisesRegex(ValueError, 'Staged file changed'):
            install(self.stage, self.root, self.grub_command)
        self.assertEqual(self.state(), original)
        self.assertFalse((self.root / BACKUPS).exists())
        self.assertEqual(self.commands, [])

    def test_artwork_changed_during_copy_triggers_full_restoration(self):
        import shutil
        original = self.state()
        original_copy = shutil.copyfile

        def racing_copy(source, target, **kwargs):
            if Path(source) == self.stage / 'theme.txt':
                Path(source).write_text('changed during privileged copy')
            return original_copy(source, target, **kwargs)

        with patch('host_install.shutil.copyfile', side_effect=racing_copy):
            with self.assertRaisesRegex(ValueError, 'during installation'):
                install(self.stage, self.root, self.grub_command)
        self.assertEqual(self.state(), original)
        self.assertNotIn(['update-grub'], self.commands)

    def test_mismatched_clean_menu_is_rejected_before_installing(self):
        (self.root / CLEAN).write_text(menus('different'))
        original = self.state()
        with self.assertRaisesRegex(ValueError, 'boot commands differ'):
            install(self.stage, self.root, self.grub_command)
        self.assertEqual(self.state(), original)
        self.assertNotIn(['update-grub'], self.commands)

    def test_icon_directory_symlink_cannot_redirect_privileged_writes(self):
        outside = self.base / 'outside'
        outside.mkdir()
        (self.root / THEME / 'icons').symlink_to(outside, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'symlink'):
            install(self.stage, self.root, self.grub_command)
        self.assertEqual(list(outside.iterdir()), [])
        self.assertEqual(self.commands, [])

    def test_rollback_restores_the_theme_and_refreshes_current_kernel_entries(self):
        backup = install(self.stage, self.root, self.grub_command)
        self.kernel = 'upgraded'
        rollback(backup, self.root, self.grub_command)
        self.assertEqual((self.root / THEME / 'theme.txt').read_text(), 'original theme')
        self.assertFalse((self.root / THEME / 'icons').exists())
        self.assertFalse((self.root / HOOK).exists())
        self.assertFalse((self.root / SETTINGS).exists())
        self.assertIn('/vmlinuz-upgraded', (self.root / CLEAN).read_text())

    def test_failed_rollback_generation_restores_both_snapshot_menus(self):
        backup = install(self.stage, self.root, self.grub_command)

        def failure(command):
            if command[0] == 'update-grub':
                (self.root / CLEAN).write_text('partially regenerated')
                raise subprocess.CalledProcessError(1, command)

        with self.assertRaisesRegex(RuntimeError, 'Do not reboot'):
            rollback(backup, self.root, failure)
        self.assertEqual((self.root / CONFIG).read_text(), menus())
        self.assertEqual((self.root / CLEAN).read_text(), menus())

    def test_corrupt_backup_is_rejected_before_any_live_file_changes(self):
        backup = install(self.stage, self.root, self.grub_command)
        original = self.state()
        saved_config = backup / 'files' / CONFIG
        saved_config.unlink()
        saved_config.mkdir()
        with self.assertRaisesRegex(ValueError, 'Backup file is missing or unsupported'):
            rollback(backup, self.root, self.grub_command)
        self.assertEqual(self.state(), original)

    def test_isolated_root_cannot_accidentally_invoke_real_grub_commands(self):
        with self.assertRaisesRegex(ValueError, 'isolated command runner'):
            install(self.stage, self.root)
