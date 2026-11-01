from pathlib import Path
import re
import tempfile
import unittest

from host_checks import FONT, missing_tools
from host_theme import stage
from host_install import verify_stage

try:
    from PIL import Image, ImageFont
except ImportError:
    Image = None


@unittest.skipIf(missing_tools('stage'), 'Host artwork requires Pillow, grub-mkfont, and DejaVu Sans Mono')
class HostThemeTests(unittest.TestCase):
    def test_menu_is_only_slightly_wider_than_its_longest_title(self):
        for width, height in ((1280, 720), (2560, 1440)):
            with self.subTest(size=(width, height)), tempfile.TemporaryDirectory() as directory:
                stage(directory, width, height)
                output = (Path(directory) / 'theme.txt').read_text()
                panel = re.search(r'\+ canvas \{ left = 50%-(\d+) top = \S+ width = (\d+)', output)
                self.assertIsNotNone(panel)
                inset, panel_width = map(int, panel.groups())
                font = ImageFont.truetype(str(FONT), 20 * max(1, height // 720))
                text_width = max(font.getlength(title) for title in ('Linux', 'Windows'))
                self.assertGreater(panel_width, text_width)
                self.assertLess(panel_width, text_width * 1.5)
                self.assertEqual(inset * 2, panel_width)

    def test_each_class_shows_one_hero_at_its_own_door(self):
        for width, height in ((1280, 720), (1024, 768), (2560, 1440)):
            with self.subTest(size=(width, height)), tempfile.TemporaryDirectory() as directory:
                stage(directory, width, height)
                self.assertEqual(verify_stage(Path(directory))['size'], [width, height])
                for name, center in (('ubuntu', 326 / 1672), ('windows', 1358 / 1672)):
                    with Image.open(Path(directory) / 'icons' / f'{name}.png') as icon:
                        self.assertEqual(icon.size, (width, height // 7))
                        left, top, right, bottom = icon.getchannel('A').getbbox()
                        self.assertAlmostEqual((left + right) / 2, center * width,
                                               delta=width / 25)
                        # The rest of the courtyard must remain unobscured.
                        self.assertLess(right - left, width / 8)
                        self.assertGreater(bottom - top, height / 15)
                self.assertEqual((Path(directory) / 'icons/ubuntu.png').read_bytes(),
                                 (Path(directory) / 'icons/gnu-linux.png').read_bytes())
                # Distinct fills keep both selection states readable, with the
                # same assets whether Linux or Windows is highlighted.
                with Image.open(Path(directory) / 'selected_c.png') as selected:
                    self.assertEqual(selected.getpixel((selected.width // 2, selected.height // 2)),
                                     (246, 186, 76, 255))
                with Image.open(Path(directory) / 'item_c.png') as ordinary:
                    self.assertEqual(ordinary.getpixel((ordinary.width // 2, ordinary.height // 2)),
                                     (13, 23, 35, 255))
                self.assertTrue((Path(directory) / 'menu.pf2').read_bytes().startswith(b'FILE\0\0\0\4PFF2'))
                self.assertIn('Bitstream Vera', (Path(directory) / 'menu-font-license.txt').read_text())

    def test_invalid_dimensions_do_not_create_output(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'theme'
            for size in ((0, 720), (640, 480), (100000, 100000)):
                with self.subTest(size=size), self.assertRaises(ValueError):
                    stage(target, *size)
                self.assertFalse(target.exists())
