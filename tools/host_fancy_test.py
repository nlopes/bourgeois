"""Host configuration and one-time trial safety regressions (no firmware writes)."""
import json
from pathlib import Path
import struct
import tempfile
import unittest
import uuid
from unittest.mock import patch

from host_fancy import CLEAN_HOOK, VERSION, configuration, digest, native_menus
from host_fancy_trial import EFI, FILES, LABEL, MOK, SHA256_GUID, STATE, arm, install, mok_hashes, remove, withdrawn_images

WITHDRAWN_IMAGES = {'de' * 32, 'ef' * 32}  # Synthetic fixture digests.


LINUX = '''menuentry 'Ubuntu' --class gnu-linux $menuentry_id_option 'linux-id' {
 linux /boot/vmlinuz-1 root=UUID=aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee ro quiet
 initrd /boot/initrd.img-1
}'''
WINDOWS = '''menuentry 'Windows' --class windows $menuentry_id_option 'windows-id' {
 chainloader /EFI/Microsoft/Boot/bootmgfw.efi
}'''
SUPPORT = '''set superusers='owner'
password_pbkdf2 owner grub.pbkdf2.sha512.example
load_env
loadfont $font
loadfont ($root)/boot/grub/themes/bourgeois/menu.pf2
'''


def database(value):
    entry = uuid.UUID(int=0).bytes_le + bytes.fromhex(value)
    return b'\x07\0\0\0' + struct.pack('<16sIII', SHA256_GUID, 28 + len(entry), 0, len(entry)) + entry


class ConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.source = SUPPORT + LINUX + '\n' + WINDOWS + '\n' + CLEAN_HOOK
        self.clean = LINUX + '\n' + WINDOWS

    def test_preserves_native_menus_and_authentication(self):
        result, root = configuration(self.source, self.clean)
        self.assertEqual(native_menus(result), native_menus(self.source))
        self.assertIn("set superusers='owner'\npassword_pbkdf2 owner", result)
        self.assertIn('load_env', result)
        self.assertEqual(root, 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee')
        self.assertNotIn('configfile $prefix/clean-menu.cfg', result)
        self.assertIn('set bourgeois_trace=0', result)
        self.assertIn('loadfont (memdisk)/boot/grub/bourgeois/unicode.pf2', result)
        self.assertNotIn('loadfont ($root)', result)

    def test_rejects_changed_boot_commands(self):
        with self.assertRaisesRegex(ValueError, 'boot commands differ'):
            configuration(self.source, self.clean.replace('ro quiet', 'rw quiet'))

    def test_rejects_unrecognized_scene_hook(self):
        with self.assertRaisesRegex(ValueError, 'Unrecognized clean-menu hook'):
            configuration(self.source.replace('99_clean_menu', '99_other'), self.clean)

    def test_rejects_unknown_font_setup(self):
        with self.assertRaisesRegex(ValueError, 'font initialization'):
            configuration(self.source.replace('loadfont $font', 'loadfont custom'), self.clean)


class TrialTests(unittest.TestCase):
    def setUp(self):
        registry = patch('host_fancy_trial.withdrawn_images', return_value=WITHDRAWN_IMAGES)
        registry.start()
        self.addCleanup(registry.stop)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'host'
        self.stage = Path(self.temp.name) / 'stage'
        self.stage.mkdir()
        (self.root / 'boot/efi/EFI/ubuntu').mkdir(parents=True)
        (self.root / 'boot/grub').mkdir()
        for name in ('grub.cfg', 'clean-menu.cfg'):
            (self.root / 'boot/grub' / name).write_text('native menu')
        for name in FILES:
            (self.stage / name).write_text('image ' + name)
        self.manifest = {'format': 1, 'grub_version': VERSION, 'authenticode_sha256': 'ab' * 32,
                         'files': {name: digest(self.stage / name) for name in FILES},
                         'snapshots': {name: digest(self.root / 'boot/grub' / name)
                                       for name in ('grub.cfg', 'clean-menu.cfg')}}
        (self.stage / 'manifest.json').write_text(json.dumps(self.manifest))
        self.added = False
        self.pending = None
        self.order = '0010,0020'
        self.commands = []

    def run_command(self, args):
        self.commands.append(args)
        if args[:2] == ['mokutil', '--sb-state']:
            return 'SecureBoot enabled\n'
        if args[0] == 'findmnt':
            return '/dev/nvme2n1p1\n'
        if args[:4] == ['lsblk', '-n', '-o', 'PKNAME']:
            return 'nvme2n1\n'
        if args[:4] == ['lsblk', '-n', '-o', 'PARTN']:
            return '1\n'
        if args[:2] == ['efibootmgr', '--create-only']:
            self.added = True
            return ''
        if args[:2] == ['efibootmgr', '--bootnext']:
            self.pending = args[2]
            return ''
        if args == ['efibootmgr', '--delete-bootnext']:
            self.pending = None
            return ''
        if args[:2] == ['efibootmgr', '--bootorder']:
            self.order = args[2]
            return ''
        if args == ['efibootmgr', '--bootnum', '0030', '--delete-bootnum']:
            self.added = False
            return ''
        if args == ['efibootmgr', '-v']:
            value = f'BootOrder: {self.order}\nBoot0010* Ubuntu\tHD()/\\EFI\\ubuntu\\shimx64.efi\n'
            if self.added:
                value += f'Boot0030* {LABEL}\tHD()/\\EFI\\bourgeois-fancy\\shimx64.efi\n'
            if self.pending:
                value += f'BootNext: {self.pending}\n'
            return value
        self.fail(f'Unexpected command: {args}')

    def test_install_creates_separate_entry_without_selecting_it(self):
        manifest = install(self.stage, self.root, self.run_command)
        self.assertEqual(manifest['bootnum'], '0030')
        self.assertIsNone(self.pending)
        self.assertEqual(set(p.name for p in (self.root / EFI).iterdir()), FILES)
        self.assertTrue((self.root / STATE).is_file())
        self.assertEqual((self.root / 'boot/grub/grub.cfg').read_text(), 'native menu')
        self.assertFalse(any('--bootorder' in cmd or '--bootnext' in cmd for cmd in self.commands))

    def test_install_rejects_stale_snapshot_before_writes(self):
        (self.root / 'boot/grub/grub.cfg').write_text('new kernel')
        with self.assertRaisesRegex(ValueError, 'menu changed'):
            install(self.stage, self.root, self.run_command)
        self.assertFalse((self.root / EFI).exists())
        self.assertEqual(self.commands, [])

    def test_install_rejects_changed_image_before_writes(self):
        (self.stage / 'grubx64.efi').write_text('altered')
        with self.assertRaisesRegex(ValueError, 'Trial file changed'):
            install(self.stage, self.root, self.run_command)
        self.assertEqual(self.commands, [])

    def test_install_rejects_withdrawn_image_before_writes(self):
        for value in WITHDRAWN_IMAGES:
            with self.subTest(image=value):
                self.manifest['authenticode_sha256'] = value
                (self.stage / 'manifest.json').write_text(json.dumps(self.manifest))
                with self.assertRaisesRegex(ValueError, 'withdrawn'):
                    install(self.stage, self.root, self.run_command)
                self.assertFalse((self.root / EFI).exists())
                self.assertEqual(self.commands, [])

    def test_install_rejects_withdrawn_manifest_without_registry_entry(self):
        self.manifest['withdrawn'] = True
        (self.stage / 'manifest.json').write_text(json.dumps(self.manifest))
        with self.assertRaisesRegex(ValueError, 'withdrawn'):
            install(self.stage, self.root, self.run_command)
        self.assertFalse((self.root / EFI).exists())
        self.assertEqual(self.commands, [])

    def test_install_preserves_existing_bootnext(self):
        self.pending = '0020'
        with self.assertRaisesRegex(ValueError, 'BootNext'):
            install(self.stage, self.root, self.run_command)
        self.assertFalse((self.root / EFI).exists())
        self.assertEqual(self.pending, '0020')

    def test_failed_copy_removes_partial_trial_without_touching_firmware(self):
        with patch('host_fancy_trial.shutil.copyfile', side_effect=OSError('disk full')):
            with self.assertRaisesRegex(OSError, 'disk full'):
                install(self.stage, self.root, self.run_command)
        self.assertFalse((self.root / EFI).exists())
        self.assertFalse(self.added)
        self.assertEqual(self.order, '0010,0020')

    def test_unexpected_firmware_order_change_is_restored_and_trial_removed(self):
        def firmware(args):
            result = self.run_command(args)
            if args[:2] == ['efibootmgr', '--create-only']:
                self.order = '0030,0010,0020'
            return result

        with self.assertRaisesRegex(RuntimeError, 'restored prior values'):
            install(self.stage, self.root, firmware)
        self.assertEqual(self.order, '0010,0020')
        self.assertFalse(self.added)
        self.assertFalse((self.root / EFI).exists())

    def test_install_refuses_symlink_in_efi_path(self):
        target = self.root / 'boot/efi/EFI'
        target.rename(target.with_name('other'))
        target.symlink_to('other')
        with self.assertRaisesRegex(ValueError, 'symlink'):
            install(self.stage, self.root, self.run_command)

    def enroll(self, value='ab' * 32):
        mok = self.root / MOK
        mok.parent.mkdir(parents=True, exist_ok=True)
        mok.write_bytes(database(value))

    def test_arm_uses_bootnext_only_after_matching_hash_enrollment(self):
        install(self.stage, self.root, self.run_command)
        self.enroll()
        arm(self.root, self.run_command)
        self.assertEqual(self.pending, '0030')
        self.assertIn(['efibootmgr', '--bootnext', '0030'], self.commands)
        self.assertFalse(any('--bootorder' in cmd for cmd in self.commands))

    def test_arm_rejects_wrong_enrolled_hash(self):
        install(self.stage, self.root, self.run_command)
        self.enroll('cd' * 32)
        with self.assertRaisesRegex(ValueError, 'not enrolled'):
            arm(self.root, self.run_command)
        self.assertIsNone(self.pending)

    def test_arm_rejects_withdrawn_image_without_setting_bootnext(self):
        manifest = install(self.stage, self.root, self.run_command)
        self.commands.clear()
        for value in WITHDRAWN_IMAGES:
            with self.subTest(image=value):
                manifest['authenticode_sha256'] = value
                (self.root / STATE).write_text(json.dumps(manifest))
                with self.assertRaisesRegex(ValueError, 'withdrawn'):
                    arm(self.root, self.run_command)
                self.assertIsNone(self.pending)
                self.assertEqual(self.commands, [])

    def test_arm_rejects_stale_config_after_enrollment(self):
        install(self.stage, self.root, self.run_command)
        self.enroll()
        (self.root / 'boot/grub/grub.cfg').write_text('updated kernel')
        with self.assertRaisesRegex(ValueError, 'menu changed'):
            arm(self.root, self.run_command)
        self.assertIsNone(self.pending)

    def test_remove_cancels_own_trial_without_changing_default(self):
        install(self.stage, self.root, self.run_command)
        self.enroll()
        arm(self.root, self.run_command)
        remove(self.root, self.run_command)
        self.assertIsNone(self.pending)
        self.assertFalse(self.added)
        self.assertFalse((self.root / EFI).exists())
        self.assertFalse((self.root / STATE).exists())
        self.assertEqual(self.order, '0010,0020')

    def test_remove_preserves_someone_elses_bootnext(self):
        install(self.stage, self.root, self.run_command)
        self.pending = '0020'
        remove(self.root, self.run_command)
        self.assertEqual(self.pending, '0020')

    def test_withdrawn_image_can_still_be_removed_for_recovery(self):
        for value in WITHDRAWN_IMAGES:
            with self.subTest(image=value):
                manifest = install(self.stage, self.root, self.run_command)
                manifest['authenticode_sha256'] = value
                (self.root / STATE).write_text(json.dumps(manifest))
                remove(self.root, self.run_command)
                self.assertFalse((self.root / EFI).exists())
                self.assertFalse((self.root / STATE).exists())

    def test_isolated_roots_never_invoke_real_firmware_tools(self):
        for action in (lambda: install(self.stage, self.root),
                       lambda: arm(self.root), lambda: remove(self.root)):
            with self.assertRaisesRegex(ValueError, 'isolated command runner'):
                action()

    def test_mok_parser_reads_hashes_and_rejects_truncated_entries(self):
        self.assertEqual(mok_hashes(database('ab' * 32)), {'ab' * 32})
        with self.assertRaisesRegex(ValueError, 'Invalid MOK'):
            mok_hashes(database('ab' * 32)[:-1])


class PrivateRegistryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.file = Path(self.temp.name) / 'withdrawn.json'
        setting = patch('host_fancy_trial.WITHDRAWN_REGISTRY', self.file)
        setting.start()
        self.addCleanup(setting.stop)

    def test_missing_private_registry_has_no_machine_data(self):
        self.assertEqual(withdrawn_images(), set())

    def test_private_registry_loads_local_digests(self):
        self.file.write_text(json.dumps({'format': 1, 'authenticode_sha256': list(WITHDRAWN_IMAGES)}))
        self.assertEqual(withdrawn_images(), WITHDRAWN_IMAGES)

    def test_private_registry_rejects_invalid_data(self):
        for value in [[], {'format': 2, 'authenticode_sha256': []},
                      {'format': 1, 'authenticode_sha256': 'invalid'},
                      {'format': 1, 'authenticode_sha256': ['invalid']}]:
            with self.subTest(value=value):
                self.file.write_text(json.dumps(value))
                with self.assertRaisesRegex(ValueError, 'private withdrawn-image registry'):
                    withdrawn_images()


if __name__ == '__main__':
    unittest.main()
