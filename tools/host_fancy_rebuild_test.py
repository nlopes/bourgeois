"""Rebuild orchestration with synthetic menus and no host or firmware writes."""
import argparse
import contextlib
import io
import json
from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import host_fancy_rebuild as builder
from host_fancy import VERSION, bootstrap, configuration, digest, native_menus
from host_fancy_test import CLEAN_HOOK, LINUX, SUPPORT, WINDOWS
from host_fancy_trial import FILES


class RebuildTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.options = argparse.Namespace(output=None, source=self.root / 'source', pesign='pesign',
                                          module_source=self.root / 'bourgeois.c')
        self.menus = {'grub.cfg': SUPPORT + LINUX + '\n' + WINDOWS + '\n' + CLEAN_HOOK,
                      'clean-menu.cfg': LINUX + '\n' + WINDOWS}
        self.commands = []
        self.stage_calls = []
        self.after_vm = lambda: None
        self.stdout = io.StringIO()
        for setting in (patch.object(builder, 'ROOT', self.root),
                        patch.object(builder.os, 'geteuid', return_value=1000),
                        patch.object(builder, 'prepare_build_tools'),
                        patch.object(builder.subprocess, 'run', side_effect=self.run_command),
                        patch.object(builder, 'stage', side_effect=self.stage),
                        patch('host_fancy_trial.withdrawn_images', return_value=set()),
                        contextlib.redirect_stdout(self.stdout)):
            self.enterContext(setting)

    def stage(self, source, native, snapshot, output, pesign, module_source):
        self.stage_calls.append((source, native, snapshot, output, pesign, module_source))
        full, clean = ((snapshot / name).read_text() for name in ('grub.cfg', 'clean-menu.cfg'))
        config, uuid = configuration(full, clean)
        output.mkdir()
        (output / 'host.cfg').write_text(config)
        (output / 'bootstrap.cfg').write_text(bootstrap(uuid))
        for name in FILES:
            (output / name).write_text('synthetic EFI fixture: ' + name)
        manifest = {'format': 1, 'grub_version': VERSION, 'root_uuid': uuid,
                    'authenticode_sha256': 'ab' * 32,
                    'files': {name: digest(output / name) for name in FILES},
                    'snapshots': {name: digest(snapshot / name) for name in self.menus}}
        (output / 'manifest.json').write_text(json.dumps(manifest))

    def run_command(self, command, **kwargs):
        self.commands.append(command)
        if command == ['sudo', '-v']:
            return
        if command[:2] == ['sudo', 'cat']:
            kwargs['stdout'].write(self.menus[Path(command[2]).name].encode())
            return
        self.assertEqual(command[:2], [builder.sys.executable, str(self.root / 'tools/host_fancy_vm.py')])
        self.assertEqual(command[2:], ['--stage', str(self.stage_calls[-1][3]),
                                     '--output', str(self.stage_calls[-1][3].parent / 'evidence'),
                                     '--original-timing'])
        self.assertTrue(kwargs['check'])
        self.after_vm()

    def test_fresh_kernel_commands_are_embedded_and_checked_without_installing(self):
        self.menus = {name: content.replace('vmlinuz-1', 'vmlinuz-2').replace('initrd.img-1', 'initrd.img-2')
                      for name, content in self.menus.items()}
        workspace = builder.rebuild(self.options)
        self.assertEqual(workspace.stat().st_mode & 0o777, 0o700)
        self.assertEqual((workspace / 'snapshot').stat().st_mode & 0o777, 0o700)
        self.assertEqual(native_menus((workspace / 'stage/host.cfg').read_text()),
                         native_menus(self.menus['grub.cfg']))
        self.assertIn('configfile (memdisk)/boot/grub/host.cfg',
                      (workspace / 'stage/bootstrap.cfg').read_text())
        self.assertEqual(len(self.commands), 6)
        self.assertEqual(self.commands[0], ['sudo', '-v'])
        self.assertIn('Fancy rebuild passed.', self.stdout.getvalue())
        self.assertIn('make host-fancy-trial-install HOST_FANCY_STAGE=', self.stdout.getvalue())
        self.assertIn('Host boot configuration unchanged.', self.stdout.getvalue())

    def test_repeated_builds_preserve_previous_stages_and_evidence(self):
        first = builder.rebuild(self.options)
        marker = first / 'evidence/review.txt'
        marker.parent.mkdir()
        marker.write_text('previous review')
        original = (first / 'stage/manifest.json').read_bytes()
        self.menus = {name: content.replace('vmlinuz-1', 'vmlinuz-2')
                      for name, content in self.menus.items()}
        second = builder.rebuild(self.options)
        self.assertNotEqual(first, second)
        self.assertEqual(marker.read_text(), 'previous review')
        self.assertEqual((first / 'stage/manifest.json').read_bytes(), original)

    def test_existing_output_is_rejected_before_authentication(self):
        self.options.output = self.root
        with self.assertRaisesRegex(ValueError, 'new output directory'):
            builder.rebuild(self.options)
        self.assertEqual(self.commands, [])

    def test_explicit_workspace_with_spaces_has_a_usable_install_command(self):
        self.options.output = self.root / 'review with spaces'
        builder.rebuild(self.options)
        line = next(line for line in self.stdout.getvalue().splitlines()
                    if line.startswith('make host-fancy-trial-install'))
        self.assertEqual(shlex.split(line), ['make', 'host-fancy-trial-install',
                                            'HOST_FANCY_STAGE=' + str(self.options.output / 'stage')])

    def test_mismatched_snapshot_pair_never_runs_vm_checks(self):
        self.menus['clean-menu.cfg'] = self.menus['clean-menu.cfg'].replace('ro quiet', 'rw quiet')
        with self.assertRaisesRegex(ValueError, 'boot commands differ'):
            builder.rebuild(self.options)
        self.assertEqual(len(self.commands), 3)
        self.assertNotIn('Fancy rebuild passed.', self.stdout.getvalue())

    def test_failed_snapshot_never_builds(self):
        with patch.object(builder.subprocess, 'run', side_effect=[None, subprocess.CalledProcessError(1, 'cat')]):
            with self.assertRaises(subprocess.CalledProcessError):
                builder.rebuild(self.options)
        self.assertEqual(self.stage_calls, [])

    def test_failed_compilation_never_runs_vm_checks(self):
        with patch.object(builder, 'stage', side_effect=ValueError('compile failed')):
            with self.assertRaisesRegex(ValueError, 'compile failed'):
                builder.rebuild(self.options)
        self.assertEqual(len(self.commands), 3)

    def test_failed_vm_checks_never_offer_installation(self):
        def fail():
            raise subprocess.CalledProcessError(1, 'VM check')
        self.after_vm = fail
        with self.assertRaises(subprocess.CalledProcessError):
            builder.rebuild(self.options)
        self.assertEqual(len(self.commands), 4)
        self.assertNotIn('make host-fancy-trial-install', self.stdout.getvalue())

    def test_either_menu_changing_during_validation_rejects_the_build(self):
        for name in self.menus:
            with self.subTest(name=name):
                self.after_vm = lambda: self.menus.__setitem__(name, self.menus[name] + '\n# changed')
                with self.assertRaisesRegex(ValueError, 'changed during validation'):
                    builder.rebuild(self.options)
        self.assertNotIn('Fancy rebuild passed.', self.stdout.getvalue())

    def test_image_changing_during_validation_rejects_the_build(self):
        def tamper():
            (self.stage_calls[-1][3] / 'grubx64.efi').write_text('modified image')
        self.after_vm = tamper
        with self.assertRaisesRegex(ValueError, 'Trial file changed'):
            builder.rebuild(self.options)
        self.assertNotIn('Fancy rebuild passed.', self.stdout.getvalue())

    def test_compilation_as_root_is_rejected_before_any_commands(self):
        with patch.object(builder.os, 'geteuid', return_value=0):
            with self.assertRaisesRegex(ValueError, 'regular user'):
                builder.rebuild(self.options)
        self.assertEqual(self.commands, [])


if __name__ == '__main__':
    unittest.main()
