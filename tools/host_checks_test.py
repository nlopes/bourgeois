from pathlib import Path
import tempfile
import unittest

from host_checks import HostSetupError, missing_tools, require_tools


class HostChecksTests(unittest.TestCase):
    def test_lab_dependencies_report_platform_specific_remedies(self):
        issues = missing_tools('lab', which=lambda name: None)
        text = '\n'.join(issues)
        for name in ('qemu-system-x86_64', 'qemu-img', 'xorriso', 'ssh', 'ssh-keygen'):
            self.assertIn(name, text)
        self.assertIn('sudo apt install', text)
        self.assertIn('brew install qemu xorriso', text)

    def test_lab_does_not_require_host_grub_or_artwork_tools(self):
        available = ('qemu-system-x86_64', 'qemu-img', 'xorriso', 'ssh', 'ssh-keygen')
        self.assertEqual(missing_tools('lab', which=lambda name: '/bin/' + name
                                      if name in available else None,
                                      pillow=False, font='/nonexistent/font'), [])

    def test_all_missing_dependencies_include_package_remedies(self):
        issues = missing_tools('all', which=lambda name: None, pillow=False,
                               font='/nonexistent/bourgeois-font.ttf', include_sudo=True)
        text = '\n'.join(issues)
        for dependency in ('Pillow', 'grub-mkfont', 'DejaVu Sans Mono',
                           'update-grub', 'grub-script-check', 'sudo'):
            self.assertIn(dependency, text)
        for package in ('python3-pil', 'grub2-common', 'fonts-dejavu-mono'):
            self.assertIn('sudo apt install ' + package, text)

    def test_install_and_rollback_do_not_require_artwork_build_tools(self):
        issues = missing_tools('install', which=lambda name: '/usr/bin/' + name,
                               pillow=False, font='/nonexistent/bourgeois-font.ttf')
        self.assertEqual(issues, [])

    def test_staging_does_not_require_sudo_or_installer_commands(self):
        with tempfile.TemporaryDirectory() as directory:
            font = Path(directory) / 'font.ttf'
            font.touch()
            issues = missing_tools('stage', which=lambda name: '/bin/grub-mkfont'
                                   if name == 'grub-mkfont' else None, pillow=True, font=font)
            self.assertEqual(issues, [])

    def test_required_tools_report_all_missing_commands_together(self):
        with self.assertRaisesRegex(HostSetupError, 'update-grub, grub-script-check'):
            require_tools('install', which=lambda name: None)


if __name__ == '__main__':
    unittest.main()
