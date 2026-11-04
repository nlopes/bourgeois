"""Check threshold-light strength, transparent edges, and atlas frame bounds."""
from pathlib import Path
import tempfile
import unittest

from PIL import Image

import doorway


class DoorwayTests(unittest.TestCase):
    def test_light_fades_at_edges_and_brightens_for_entry(self):
        previous = 0
        for index in range(doorway.FRAMES):
            image = doorway.frame(index)
            alpha = image.getchannel('A')
            self.assertEqual(alpha.crop((0, 0, image.width, 1)).getextrema(), (0, 0))
            self.assertEqual(alpha.crop((0, 0, 1, image.height)).getextrema(), (0, 0))
            maximum = alpha.getextrema()[1]
            self.assertGreater(maximum, previous)
            self.assertLessEqual(maximum, 88)
            self.assertEqual(alpha.getpixel((160, 64)), maximum)
            previous = maximum
        for index in (-1, 8):
            with self.assertRaises(ValueError):
                doorway.frame(index)

    def test_atlas_keeps_each_brightness_level_in_its_own_cell(self):
        with tempfile.TemporaryDirectory() as directory:
            doorway.atlas(directory)
            with Image.open(Path(directory) / 'doorway.png') as image:
                self.assertEqual(image.size, (2560, 128))
                for index in range(8):
                    cell = image.crop((index * 320, 0, (index + 1) * 320, 128))
                    self.assertEqual(cell.getpixel((160, 64)),
                                     (255, 177, 70, 44 * (index + 1) // 4))
