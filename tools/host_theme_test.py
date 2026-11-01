from pathlib import Path
import tempfile
import unittest

from host_theme import stage

try:
    from PIL import Image
except ImportError:
    Image = None


@unittest.skipIf(Image is None, 'Host artwork staging requires Pillow')
class HostThemeTests(unittest.TestCase):
    def test_each_class_shows_one_hero_at_its_own_door(self):
        for width, height in ((1280, 720), (1024, 768)):
            with self.subTest(size=(width, height)), tempfile.TemporaryDirectory() as directory:
                stage(directory, width, height)
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

    def test_invalid_dimensions_do_not_create_output(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'theme'
            for size in ((0, 720), (640, 480), (100000, 100000)):
                with self.subTest(size=size), self.assertRaises(ValueError):
                    stage(target, *size)
                self.assertFalse(target.exists())
