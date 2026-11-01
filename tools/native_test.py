import subprocess
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from native import select_boot


class BootOrderTests(unittest.TestCase):
    def test_selects_custom_entry_without_dropping_recovery_order(self):
        entries = 'BootOrder: 0008,0002,0009\nBoot0008* Ubuntu\tHD(15,GPT,...)\nBoot0009* bourgeois preview\tHD(15,GPT,...)\n'
        with patch('native.lab.ssh', return_value=subprocess.CompletedProcess([], 0, entries)) as ssh:
            select_boot('fancy')
        self.assertEqual(ssh.call_args_list[1].args[0], 'sudo efibootmgr -o 0009,0008,0002')

    def test_missing_entry_does_not_write_firmware(self):
        with patch('native.lab.ssh', return_value=subprocess.CompletedProcess([], 0, 'BootOrder: 0008\n')) as ssh:
            with self.assertRaises(RuntimeError):
                select_boot('slim')
        self.assertEqual(ssh.call_count, 1)

    def test_wrong_grub_version_stops_before_upload(self):
        from native import build
        with patch('native.require_guest'), patch('native.lab.ssh', return_value=subprocess.CompletedProcess([], 0, '2.14\n2.14\n')), patch('native.upload') as upload:
            with self.assertRaisesRegex(RuntimeError, 'requires GRUB'):
                build()
            upload.assert_not_called()

    def test_uninitialized_guest_reports_setup_command_without_waiting(self):
        from native import require_guest
        with tempfile.TemporaryDirectory() as directory, patch('native.lab.VM', Path(directory)), \
                patch('native.require_tools'), patch('native.lab.wait_ssh') as wait:
            with self.assertRaisesRegex(RuntimeError, 'make vm first'):
                require_guest()
            wait.assert_not_called()

    def test_stopped_guest_reports_start_command_without_waiting(self):
        from native import require_guest
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'id_ed25519').touch()
            with patch('native.lab.VM', root), patch('native.require_tools'), \
                    patch('native.lab.QMP', side_effect=ConnectionRefusedError), patch('native.lab.wait_ssh') as wait:
                with self.assertRaisesRegex(RuntimeError, 'lab is stopped'):
                    require_guest()
                wait.assert_not_called()
