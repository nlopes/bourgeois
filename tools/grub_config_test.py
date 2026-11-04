import unittest

from grub_config import blocks, generate, hook


SOURCE = '''set menuentry_id_option=--id
function helper {
  echo "brace } # remains" # comment {
  set test=${prefix}
}
menuentry 'Ubuntu' --users alice $menuentry_id_option 'linux-id' {
  helper
  linux /vmlinuz root=UUID=old ro
  initrd /initrd.img
}
submenu 'Advanced' --id advanced {
  menuentry 'Recovery' --id recovery { echo recovery; }
}
if [ x = x ]; then
menuentry 'Windows Boot Manager' --id windows-id { chainloader /EFI/Microsoft/Boot/bootmgfw.efi; }
fi
'''


class ConfigurationTests(unittest.TestCase):
    def test_keeps_boot_body_and_authentication(self):
        result = generate(SOURCE, 'linux-id', 'windows-id')
        self.assertIn('linux /vmlinuz root=UUID=old ro\n  initrd /initrd.img', result)
        self.assertIn("'Linux' --users alice $menuentry_id_option 'linux-id' --hotkey=l", result)
        self.assertIn('function helper', result)
        self.assertNotIn("'Recovery'", result)
        self.assertEqual(len([b for b in blocks(result) if b.kind == 'menuentry']), 2)

    def test_kernel_update_is_taken_from_current_config(self):
        result = generate(SOURCE.replace('/vmlinuz', '/vmlinuz-new'), 'linux-id', 'windows-id')
        self.assertIn('linux /vmlinuz-new', result)

    def test_scene_does_not_override_the_distribution_display_mode(self):
        result = generate('set gfxmode=3840x2160,1920x1080,auto\n' + SOURCE,
                          'linux-id', 'windows-id')
        self.assertIn('set gfxmode=3840x2160,1920x1080,auto', result)
        self.assertNotIn('set gfxmode=1280x720', result)

    def test_missing_duplicate_or_unsafe_ids_fail_closed(self):
        for source, linux in [(SOURCE, 'missing'), (SOURCE + SOURCE, 'linux-id'), (SOURCE, "bad'; halt")]:
            with self.subTest(linux=linux), self.assertRaises(ValueError):
                generate(source, linux, 'windows-id')

    def test_broken_config_is_rejected(self):
        with self.assertRaises(ValueError):
            generate(SOURCE[:-3] + '{', 'linux-id', 'windows-id')

    def test_one_shot_and_recordfail_skip_scene(self):
        for edition in ('slim', 'fancy'):
            result = hook(edition, 'linux-id', 'windows-id')
            self.assertIn('"${boot_once}" != "true"', result)
            self.assertIn('"${recordfail}" = "1"', result)
            self.assertIn('set timeout=-1', result)

    def test_fancy_checks_module_capability_after_loading(self):
        result = hook('fancy', 'linux-id', 'windows-id')
        self.assertIn('if [ "${feature_bourgeois}" = "1" ]; then', result)
        self.assertNotIn('if insmod', result)
        self.assertIn('$prefix/bourgeois/traveler-gates.png', result)
        self.assertIn('$prefix/bourgeois/doorway.png', result)

    def test_fancy_loads_scaled_fonts_and_a_safe_terminal_font(self):
        result = hook('fancy', 'linux-id', 'windows-id')
        self.assertIn('if loadfont $prefix/bourgeois/menu-20.pf2; then', result)
        self.assertIn('set gfxterm_font="Bourgeois UI Regular 20"', result)
        self.assertIn('insmod gfxterm_background', result)
        self.assertNotIn('set gfxmode=', result.split('if [ "${timeout}"')[0])
