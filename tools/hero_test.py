"""Check gate-facing Slim icons without a font builder or VM."""
from pathlib import Path
import tempfile
import unittest

from PIL import Image, ImageChops

from hero import ROOT, icons, view


class GatePoseTests(unittest.TestCase):
    def test_each_door_uses_its_own_rear_pose(self):
        for width, height in ((800, 600), (1280, 720), (2560, 1440)):
            with self.subTest(size=(width, height)), tempfile.TemporaryDirectory() as directory:
                icons(directory, width, height)
                with Image.open(ROOT / 'assets/traveler-gates.png') as poses:
                    for name, frame, center in (('linux', 1, 326 / 1672),
                                                 ('windows', 0, 1358 / 1672)):
                        with Image.open(Path(directory) / 'icons' / f'{name}.png') as icon:
                            self.assertEqual(icon.size, (width, height // 7))
                            cell = poses.crop((frame * poses.width // 4, 0,
                                               (frame + 1) * poses.width // 4, poses.height))
                            expected = cell.resize((round(cell.width * icon.height / cell.height),
                                                     icon.height), Image.Resampling.NEAREST)
                            left = round(center * width) - expected.width // 2
                            actual = icon.crop((left, 0, left + expected.width, icon.height))
                            difference = ImageChops.difference(actual, expected)
                            self.assertTrue(all(bounds == (0, 0)
                                                for bounds in difference.getextrema()))
                            self.assertIsNone(icon.crop((0, 0, left, icon.height)).getbbox())
                            self.assertIsNone(icon.crop((left + expected.width, 0, width,
                                                        icon.height)).getbbox())

    def test_hero_view_keeps_stock_menu_selection(self):
        result = view(800, 600)
        self.assertIn('top = 73%-85', result)
        self.assertIn('icon_width = 800 icon_height = 85', result)
        self.assertIn('item_color = "#00000000"', result)
