"""Persistent installation regressions using synthetic menus and firmware."""
import argparse
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import host_fancy_install as installer
from host_fancy import bootstrap, digest
from host_fancy_config import LIVE_CONFIG, configuration, native_menus, refresh
from host_fancy_test import CLEAN_HOOK, LINUX, SUPPORT, VERSION, WINDOWS, database
from host_fancy_trial import EFI, FILES, MOK, STATE as TRIAL_STATE, install as install_trial


class PersistentInstallTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'host'
        self.stage = Path(self.temp.name) / 'stage'
        self.stage.mkdir()
        (self.root / 'boot/efi/EFI/ubuntu').mkdir(parents=True)
        (self.root / 'boot/grub').mkdir()
        (self.root / 'etc/grub.d').mkdir(parents=True)
        self.source = SUPPORT + LINUX + '\n' + WINDOWS + '\n' + CLEAN_HOOK + '\n'
        (self.root / 'boot/grub/grub.cfg').write_text(self.source)
        (self.root / 'boot/grub/clean-menu.cfg').write_text(LINUX + '\n' + WINDOWS)
        for name in FILES:
            (self.stage / name).write_text('first image ' + name)
        self.manifest = {'format': 1, 'mode': 'persistent', 'grub_version': VERSION,
                         'authenticode_sha256': 'ab' * 32,
                         'files': {name: digest(self.stage / name) for name in FILES},
                         'snapshots': {name: digest(self.root / 'boot/grub' / name)
                                       for name in ('grub.cfg', 'clean-menu.cfg')}}
        self.save_manifest()
        self.order = '0010,0020'
        self.pending = None
        self.added = False
        self.label = installer.LABEL
        self.commands = []
        self.requests = ''
        self.secure_boot = True
        registry = patch('host_fancy_trial.withdrawn_images', return_value=set())
        registry.start()
        self.addCleanup(registry.stop)

    def save_manifest(self):
        (self.stage / 'manifest.json').write_text(json.dumps(self.manifest))

    def run_command(self, args):
        self.commands.append(args)
        if args == ['mokutil', '--sb-state']:
            return 'SecureBoot enabled\n' if self.secure_boot else 'SecureBoot disabled\n'
        if args == ['mokutil', '--list-new']:
            return self.requests
        if args[:2] == ['mokutil', '--import-hash']:
            return ''
        if args[0] == 'findmnt':
            return '/dev/nvme2n1p1\n'
        if args[:4] == ['lsblk', '-n', '-o', 'PKNAME']:
            return 'nvme2n1\n'
        if args[:4] == ['lsblk', '-n', '-o', 'PARTN']:
            return '1\n'
        if args == ['update-grub']:
            full = self.source
            if (self.root / installer.HOOK).exists():
                marker = f'/etc/grub.d/{installer.HOOK.name}'
                refresh(full + f'### BEGIN {marker} ###\n', self.root, self.run_command)
                full += f'### BEGIN {marker} ###\n\n### END {marker} ###\n'
            (self.root / installer.CONFIGS[0]).write_text(full)
            return ''
        if args[0] == 'grub-script-check':
            subprocess.run(args, check=True)
            return ''
        if args[:2] == ['efibootmgr', '--create-only']:
            self.added = True
            self.label = args[args.index('--label') + 1]
            return ''
        if args[:2] == ['efibootmgr', '--bootorder']:
            self.order = args[2]
            return ''
        if args == ['efibootmgr', '--delete-bootnext']:
            self.pending = None
            return ''
        if args[:2] == ['efibootmgr', '--bootnext']:
            self.pending = args[2]
            return ''
        if args == ['efibootmgr', '--bootnum', '0030', '--delete-bootnum']:
            self.added = False
            return ''
        if args == ['efibootmgr', '-v']:
            text = f'BootOrder: {self.order}\nBoot0010* Ubuntu\tHD()/\\EFI\\ubuntu\\shimx64.efi\n'
            text += 'Boot0020* Windows\tHD()/\\EFI\\Microsoft\\Boot\\bootmgfw.efi\n'
            if self.added:
                text += f'Boot0030* {self.label}\tHD()/\\EFI\\bourgeois-fancy\\shimx64.efi\n'
            if self.pending:
                text += f'BootNext: {self.pending}\n'
            return text
        self.fail(f'Unexpected command: {args}')

    def install(self, runner=None):
        return installer.install(self.stage, self.root, runner or self.run_command)

    def enroll(self):
        path = self.root / MOK
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(database(self.manifest['authenticode_sha256']))

    def test_install_selects_every_boot_and_preserves_ubuntu(self):
        manifest, needed = self.install()
        self.assertEqual(self.order, '0030,0010,0020')
        self.assertTrue(needed)
        self.assertEqual(manifest['bootnum'], '0030')
        self.assertIsNone(self.pending)
        self.assertFalse(any('--bootnext' in command for command in self.commands))
        self.assertIn(['mokutil', '--import-hash', 'ab' * 32], self.commands)
        self.assertEqual((self.root / installer.HOOK).stat().st_mode & 0o777, 0o755)
        self.assertEqual(native_menus((self.root / LIVE_CONFIG).read_text()), native_menus(self.source))
        self.assertTrue((Path(manifest['backup']) / 'firmware.json').exists())

    def test_reinstall_replaces_image_without_remove_or_duplicate_entry(self):
        self.install()
        self.commands.clear()
        (self.stage / 'grubx64.efi').write_text('second build')
        self.manifest['files']['grubx64.efi'] = digest(self.stage / 'grubx64.efi')
        self.manifest['authenticode_sha256'] = 'cd' * 32
        self.manifest['snapshots']['grub.cfg'] = digest(self.root / installer.CONFIGS[0])
        self.save_manifest()
        self.install()
        self.assertEqual((self.root / EFI / 'grubx64.efi').read_text(), 'second build')
        self.assertFalse(any('--create-only' in command or '--delete-bootnum' in command
                             for command in self.commands))
        self.assertEqual(self.order, '0030,0010,0020')

    def test_existing_hash_does_not_request_enrollment_again(self):
        self.enroll()
        _, needed = self.install()
        self.assertFalse(needed)
        self.assertFalse(any('--import-hash' in command for command in self.commands))

    def test_existing_trial_migrates_in_place_without_another_boot_entry(self):
        install_trial(self.stage, self.root, self.run_command)
        self.pending = '0030'
        self.commands.clear()
        self.install()
        self.assertFalse((self.root / TRIAL_STATE).exists())
        self.assertTrue((self.root / installer.STATE).exists())
        self.assertFalse(any('--create-only' in command for command in self.commands))
        self.assertIsNone(self.pending)
        self.assertEqual(self.order, '0030,0010,0020')

    def test_kernel_update_uses_new_native_commands_without_rebuilding_image(self):
        self.install()
        image = (self.root / EFI / 'grubx64.efi').read_bytes()
        self.source = self.source.replace('vmlinuz-1', 'vmlinuz-2').replace('initrd.img-1', 'initrd.img-2')
        clean = self.root / installer.CONFIGS[1]
        clean.write_text(clean.read_text().replace('vmlinuz-1', 'vmlinuz-2').replace('initrd.img-1', 'initrd.img-2'))
        self.run_command(['update-grub'])
        menu = (self.root / LIVE_CONFIG).read_text()
        self.assertIn('/boot/vmlinuz-2', menu)
        self.assertNotIn('/boot/vmlinuz-1', menu)
        self.assertEqual(native_menus(menu), native_menus(self.source))
        self.assertEqual((self.root / EFI / 'grubx64.efi').read_bytes(), image)

    def test_unrecognized_updated_menu_discards_stale_menu(self):
        self.install()
        with self.assertRaisesRegex(ValueError, 'Unrecognized clean-menu hook'):
            refresh(self.source.replace('99_clean_menu', '99_unknown'), self.root, self.run_command)
        self.assertFalse((self.root / LIVE_CONFIG).exists())

    def test_invalid_new_menu_discards_stale_menu_and_temporary_file(self):
        self.install()
        def invalid(args):
            raise subprocess.CalledProcessError(1, args)
        with self.assertRaises(subprocess.CalledProcessError):
            refresh(self.source, self.root, invalid)
        self.assertFalse((self.root / LIVE_CONFIG).exists())
        self.assertEqual(list((self.root / 'boot/grub').glob('.bourgeois-fancy-*')), [])

    def test_rejects_changed_stage_before_writing_host_files(self):
        (self.stage / 'grubx64.efi').write_text('tampered')
        with self.assertRaisesRegex(ValueError, 'file changed'):
            self.install()
        self.assertFalse((self.root / EFI).exists())
        self.assertEqual(self.commands, [])

    def test_rejects_snapshot_image_before_host_changes(self):
        del self.manifest['mode']
        self.save_manifest()
        with self.assertRaisesRegex(ValueError, 'one-time trial'):
            self.install()
        self.assertFalse((self.root / EFI).exists())

    def test_rejects_menu_changed_during_compilation(self):
        (self.root / installer.CONFIGS[0]).write_text('changed')
        with self.assertRaisesRegex(ValueError, 'make host-fancy-install'):
            self.install()
        self.assertEqual(self.commands, [])

    def test_preserves_unrelated_bootnext_and_pending_mok_requests(self):
        for request in ('boot', 'mok'):
            with self.subTest(request=request):
                self.pending = '0020' if request == 'boot' else None
                self.requests = 'existing certificate request' if request == 'mok' else ''
                with self.assertRaisesRegex(ValueError, 'pending'):
                    self.install()
                self.assertFalse((self.root / EFI).exists())
                self.assertFalse(any('--import-hash' in command or '--bootorder' in command
                                     for command in self.commands))

    def test_rejects_withdrawn_image_and_disabled_secure_boot(self):
        self.manifest['withdrawn'] = True
        self.save_manifest()
        with self.assertRaisesRegex(ValueError, 'withdrawn'):
            self.install()
        del self.manifest['withdrawn']
        self.save_manifest()
        self.secure_boot = False
        with self.assertRaisesRegex(ValueError, 'Secure Boot enabled'):
            self.install()
        self.assertFalse((self.root / EFI).exists())

    def test_failed_menu_generation_restores_original_files_before_entry_creation(self):
        def failed(args):
            if args == ['update-grub']:
                (self.root / installer.CONFIGS[0]).write_text('partial config')
                raise RuntimeError('generation failed')
            return self.run_command(args)
        with self.assertRaisesRegex(RuntimeError, 'generation failed'):
            self.install(failed)
        self.assertEqual((self.root / installer.CONFIGS[0]).read_text(), self.source)
        self.assertFalse((self.root / EFI).exists())
        self.assertFalse((self.root / installer.HOOK).exists())
        self.assertFalse(self.added)

    def test_partial_copy_during_reinstall_restores_the_previous_image(self):
        self.install()
        original = (self.root / EFI / 'grubx64.efi').read_bytes()
        self.manifest['snapshots']['grub.cfg'] = digest(self.root / installer.CONFIGS[0])
        self.save_manifest()
        copyfile = installer.shutil.copyfile
        def failed(source, target, **kwargs):
            if Path(target).name == '.shimx64.efi.new':
                raise OSError('ESP full')
            return copyfile(source, target, **kwargs)
        with patch.object(installer.shutil, 'copyfile', side_effect=failed):
            with self.assertRaisesRegex(OSError, 'ESP full'):
                self.install()
        self.assertEqual((self.root / EFI / 'grubx64.efi').read_bytes(), original)
        self.assertEqual(self.order, '0030,0010,0020')
        self.assertTrue((self.root / installer.STATE).exists())

    def test_symlink_in_managed_paths_never_receives_host_writes(self):
        outside = Path(self.temp.name) / 'unrelated'
        outside.write_text('keep this')
        (self.root / LIVE_CONFIG).symlink_to(outside)
        with self.assertRaisesRegex(ValueError, 'symlink'):
            self.install()
        self.assertEqual(outside.read_text(), 'keep this')
        self.assertEqual(self.commands, [])

    def test_failed_enrollment_restores_previous_trial_and_bootnext(self):
        install_trial(self.stage, self.root, self.run_command)
        self.pending = '0030'
        def failed(args):
            if args[:2] == ['mokutil', '--import-hash']:
                raise RuntimeError('password cancelled')
            return self.run_command(args)
        with self.assertRaisesRegex(RuntimeError, 'password cancelled'):
            self.install(failed)
        self.assertEqual(self.order, '0010,0020')
        self.assertEqual(self.pending, '0030')
        self.assertTrue(self.added)
        self.assertTrue((self.root / TRIAL_STATE).exists())
        self.assertFalse((self.root / installer.STATE).exists())
        self.assertFalse((self.root / installer.HOOK).exists())

    def test_firmware_rejecting_new_order_restores_files_and_deletes_created_entry(self):
        def firmware(args):
            if args == ['efibootmgr', '--bootorder', '0030,0010,0020']:
                return ''  # Firmware silently ignores the request.
            return self.run_command(args)
        with self.assertRaisesRegex(RuntimeError, 'Firmware boot selection'):
            self.install(firmware)
        self.assertEqual(self.order, '0010,0020')
        self.assertFalse(self.added)
        self.assertFalse((self.root / EFI).exists())

    def test_rejects_changed_firmware_entry_and_unmanaged_efi_files(self):
        (self.root / EFI).mkdir()
        with self.assertRaisesRegex(ValueError, 'Unmanaged Fancy EFI'):
            self.install()
        (self.root / EFI).rmdir()
        self.install()
        self.label = 'Some other bootloader'
        self.manifest['snapshots']['grub.cfg'] = digest(self.root / installer.CONFIGS[0])
        self.save_manifest()
        with self.assertRaisesRegex(ValueError, 'boot entry changed'):
            self.install()

    def test_uninstall_restores_ubuntu_and_preserves_unrelated_bootnext(self):
        self.install()
        self.pending = '0020'
        installer.uninstall(self.root, self.run_command)
        self.assertEqual(self.order, '0010,0020')
        self.assertEqual(self.pending, '0020')
        self.assertFalse(self.added)
        for name in (EFI, installer.STATE, installer.HOOK, installer.LIBRARY, LIVE_CONFIG):
            self.assertFalse((self.root / name).exists(), name)

    def test_failed_uninstall_regeneration_restores_the_working_installation(self):
        self.install()
        def failed(args):
            if args == ['update-grub']:
                raise RuntimeError('generation failed')
            return self.run_command(args)
        with self.assertRaisesRegex(RuntimeError, 'generation failed'):
            installer.uninstall(self.root, failed)
        self.assertEqual(self.order, '0030,0010,0020')
        self.assertTrue(self.added)
        self.assertTrue((self.root / installer.STATE).exists())
        self.assertTrue((self.root / installer.HOOK).exists())
        self.assertTrue((self.root / LIVE_CONFIG).exists())

    def test_isolated_roots_require_fake_firmware_tools(self):
        for operation in (lambda: installer.install(self.stage, self.root),
                          lambda: installer.uninstall(self.root),
                          lambda: refresh(self.source, self.root)):
            with self.assertRaisesRegex(ValueError, 'isolated command runner'):
                operation()

    def test_persistent_bootstrap_reads_live_menu_and_falls_back_to_distribution(self):
        source = bootstrap('aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee', persistent=True)
        self.assertIn('configfile $prefix/bourgeois-fancy.cfg', source)
        self.assertIn('configfile $prefix/grub.cfg', source)
        self.assertNotIn('configfile (memdisk)/boot/grub/host.cfg', source)


class CompileAndInstallTests(unittest.TestCase):
    def test_single_command_snapshots_compiles_and_deploys_with_sudo(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            options = argparse.Namespace(source=root / 'source', build=None,
                                         pesign='pesign', module_source=root / 'bourgeois.c')
            with patch.object(installer, 'ROOT', root), \
                    patch.object(installer.os, 'geteuid', return_value=1000), \
                    patch.object(installer.subprocess, 'run') as run, \
                    patch.object(installer, 'stage') as compile_image:
                installer.build_and_install(options)
            self.assertEqual(run.call_args_list[0].args[0], ['sudo', '-v'])
            self.assertEqual(run.call_args_list[1].args[0], ['sudo', 'cat', '/boot/grub/grub.cfg'])
            self.assertEqual(run.call_args_list[2].args[0], ['sudo', 'cat', '/boot/grub/clean-menu.cfg'])
            self.assertEqual(compile_image.call_args.kwargs, {'persistent': True})
            self.assertEqual(compile_image.call_args.args[1].name, 'native')
            self.assertTrue(compile_image.call_args.args[1].parent.name.startswith('fancy-install-'))
            self.assertEqual(run.call_args_list[-1].args[0][0], 'sudo')
            self.assertIn('deploy', run.call_args_list[-1].args[0])
            self.assertEqual(len(list((root / 'build').glob('fancy-install-*'))), 1)

    def test_failed_compilation_never_invokes_deployment(self):
        with tempfile.TemporaryDirectory() as directory:
            options = argparse.Namespace(source=Path('source'), build=Path('native'),
                                         pesign='pesign', module_source=Path('bourgeois.c'))
            with patch.object(installer, 'ROOT', Path(directory)), \
                    patch.object(installer.os, 'geteuid', return_value=1000), \
                    patch.object(installer.subprocess, 'run') as run, \
                    patch.object(installer, 'stage', side_effect=ValueError('compile failed')):
                with self.assertRaisesRegex(ValueError, 'compile failed'):
                    installer.build_and_install(options)
            self.assertFalse(any('deploy' in call.args[0] for call in run.call_args_list))


if __name__ == '__main__':
    unittest.main()
