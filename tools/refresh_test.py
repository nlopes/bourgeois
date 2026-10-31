from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from grub_config_test import SOURCE
from refresh import refresh


class RefreshTests(unittest.TestCase):
    def test_new_kernel_replaces_scene_atomically(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'grub.cfg.new'
            target = Path(directory) / 'scene.cfg'
            target.write_text('previous scene')
            source.write_text(SOURCE.replace('/vmlinuz', '/vmlinuz-updated'))
            settings = dict(linux_id='linux-id', windows_id='windows-id', edition='slim')
            with patch('refresh.subprocess.run') as check:
                output = refresh(settings, source, target)
            check.assert_called_once()
            self.assertIn('/vmlinuz-updated', target.read_text())
            self.assertIn('configfile', output)
            self.assertFalse(target.with_suffix('.cfg.new').exists())

    def test_failed_refresh_keeps_previous_file(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'grub.cfg.new'
            target = Path(directory) / 'scene.cfg'
            target.write_text('previous scene')
            source.write_text(SOURCE)
            with self.assertRaises(ValueError):
                refresh(dict(linux_id='missing', windows_id='windows-id'), source, target)
            self.assertEqual(target.read_text(), 'previous scene')
